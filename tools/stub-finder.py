#!/usr/bin/env python3
"""stub-finder —— 未实现桩查找（单文件，仅用 Python 标准库）。

用途:
    找出还没写完的函数/方法:
      * Python（基于 ast，较精确）: 函数体只有 pass、`...`（Ellipsis）、
        docstring、`raise NotImplementedError`（或任何必然 raise），
        或函数体内（含 docstring、含 def 行尾注释）出现 TODO/FIXME/XXX 注释；
        嵌套函数/类内部的 TODO 不会重复算到外层函数头上。
      * 其他语言（启发式）: 行内出现 TODO/FIXME/XXX、not implemented、
        NotImplementedException、Rust 的 unimplemented!()/todo!() 等标记；
        或单行空函数体 `function f() {}` / `func f() {}` / `fun f() {}` /
        Java 风格 `public void f() {}`。
      * Python 文件语法错误时报告 parse-error，并退化为行级标记扫描。

示例（Git Bash / Windows）:
    python stub-finder.py src/                         # 递归扫描目录
    python stub-finder.py a.py lib/b.go                # 扫描指定文件
    python stub-finder.py . --ext .py,.js              # 限定扩展名
    python stub-finder.py src/ --json                  # JSON 输出到 stdout
    python stub-finder.py src/ --fail-on-found         # 有发现则退出码 1（CI 用）

输出约定:
    发现列表（file:line: [类别] 说明）写 stdout，统计摘要写 stderr。

局限:
    Python 判定精确；其他语言为行级启发式，多行空函数体与跨行签名可能漏报，
    TODO 出现在字符串字面量里也会被当作标记报告。

退出码: 0=扫描完成（无论是否有发现）；1=有发现且启用 --fail-on-found；2=用法或 IO 错误。
"""

import argparse
import ast
import io
import json
import os
import re
import sys
import tokenize

TOOL = "stub-finder"

SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".tox", ".nox", ".venv", "venv", "env", "node_modules", "dist", "build",
    ".idea", ".vscode", ".eggs",
}

HASH_COMMENTS = {".py", ".pyw", ".rb", ".rake", ".sh", ".bash", ".yml", ".yaml", ".toml"}
SLASH_COMMENTS = {
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".go", ".java", ".c", ".h",
    ".cpp", ".hpp", ".cs", ".php", ".rs", ".swift", ".kt", ".kts", ".scala",
}
DEFAULT_EXTS = sorted(HASH_COMMENTS | SLASH_COMMENTS)

STRING_RE = re.compile(
    r'"(?:\\.|[^"\\])*"'
    r"|'(?:\\.|[^'\\])*'"
    r"|`(?:\\.|[^`\\])*`"
)

PY_EXTS = (".py", ".pyw")

TODO_WORD_RE = re.compile(r"\b(?:TODO|FIXME|XXX)\b")
IMPL_MARKER_RE = re.compile(
    r"NotImplementedException"
    r"|\bnot[\s_-]?implemented\b"
    r"|\bnotImplemented\b"
    r"|\bunimplemented!\s*\("
    r"|\btodo!\s*\(",
    re.IGNORECASE,
)
EMPTY_BODY_RES = [
    re.compile(r"\bfunction\s+\w+\s*\([^)]*\)\s*[^{};]*\{\s*\}"),   # js/ts/php
    re.compile(r"\bfunc\s+\w+\s*\([^)]*\)\s*[^{};]*\{\s*\}"),       # go/swift
    re.compile(r"\bfun\s+\w+\s*\([^)]*\)\s*[^{};]*\{\s*\}"),        # kotlin
    # java/c#/c++ 风格: `public void run() {}`（排除 `new Xxx() {}`）
    re.compile(r"\b(?!new\b)[A-Za-z_]\w*\s+[A-Za-z_]\w*\s*\([^)]*\)\s*\{\s*\}"),
]


def read_text(path, max_bytes=2 * 1024 * 1024):
    """读取文本文件；过大（>2MB）或疑似二进制（含 NUL）返回 None。"""
    try:
        if os.path.getsize(path) > max_bytes:
            return None
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1", errors="replace")


def iter_files(paths, exts):
    """按扩展名收集待扫描文件（显式给出的文件不受扩展名过滤限制）。"""
    wanted = None
    if exts:
        wanted = {e.lower().lstrip(".") for e in exts}
    for p in paths:
        ap = os.path.abspath(p)
        if os.path.isfile(ap):
            yield ap
        elif os.path.isdir(ap):
            for root, dirs, files in os.walk(ap):
                dirs[:] = sorted(
                    d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")
                )
                for name in sorted(files):
                    if wanted is not None and os.path.splitext(name)[1].lower().lstrip(".") not in wanted:
                        continue
                    yield os.path.join(root, name)


def collect_comments(text):
    """用 tokenize 收集 Python 源码中的注释 (行号, 列号, 文本)；失败返回已收集部分。"""
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                out.append((tok.start[0], tok.start[1], tok.string))
    except Exception:
        pass
    return out


def classify_function(fn, comments):
    """返回桩类型字符串；不是桩返回 None。"""
    body = fn.body
    rest = body
    doc = None
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        doc = body[0].value.value
        rest = body[1:]
    if not rest:
        return "docstring-only"
    if len(rest) == 1:
        node = rest[0]
        if isinstance(node, ast.Pass):
            return "pass"
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and node.value.value is Ellipsis):
            return "ellipsis"
        if isinstance(node, ast.Raise):
            if "NotImplementedError" in ast.dump(node):
                return "raise-NotImplementedError"
            return "always-raises"
    if doc and TODO_WORD_RE.search(doc):
        return "todo"
    end = getattr(fn, "end_lineno", fn.lineno) or fn.lineno
    nested = []
    for child in ast.iter_child_nodes(fn):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nested.append((getattr(child, "lineno", 0) or 0,
                           getattr(child, "end_lineno", 0) or 0))

    def in_nested(ln):
        return any(a <= ln <= b for a, b in nested)

    for ln, col, txt in comments:
        if not TODO_WORD_RE.search(txt):
            continue
        if ln == fn.lineno and col >= fn.col_offset:
            return "todo"
        if fn.lineno < ln <= end and col > fn.col_offset and not in_nested(ln):
            return "todo"
    return None


def scan_python(text, findings):
    """AST 精确扫描；解析失败返回 False（调用方退化到行级扫描）。"""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        line = getattr(exc, "lineno", 1) or 1
        findings.append((line, "parse-error", "cannot parse: %s" % exc.msg))
        return False
    comments = collect_comments(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = classify_function(node, comments)
            if kind:
                findings.append((node.lineno, kind,
                                 "function '%s' is not implemented (%s)"
                                 % (node.name, kind)))
    return True


def scan_other(text, ext, findings):
    """非 Python 的行级启发式扫描（也用作 Python 语法错误时的退化路径）。"""
    for idx, raw in enumerate(text.splitlines(), 1):
        if TODO_WORD_RE.search(raw) or IMPL_MARKER_RE.search(raw):
            findings.append((idx, "stub-marker",
                             "stub marker: %s" % raw.strip()[:70]))
            continue
        code = STRING_RE.sub('""', raw)
        if ext in SLASH_COMMENTS:
            cut = code.find("//")
            if cut >= 0:
                code = code[:cut]
        for rx in EMPTY_BODY_RES:
            if rx.search(code):
                findings.append((idx, "empty-body",
                                 "empty function body: %s" % raw.strip()[:70]))
                break


def scan_file(path):
    """返回 [(line_no, kind, message), ...]；文件不可读返回 None。"""
    ext = os.path.splitext(path)[1].lower()
    text = read_text(path)
    if text is None:
        return None
    findings = []
    if ext in PY_EXTS:
        if not scan_python(text, findings):
            scan_other(text, ext, findings)
    else:
        scan_other(text, ext, findings)
    return findings


def display_path(p):
    try:
        rel = os.path.relpath(p, os.getcwd())
    except ValueError:
        rel = p
    if os.path.isabs(rel) or rel.startswith(".."):
        return p.replace(os.sep, "/")
    return rel.replace(os.sep, "/")


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="未实现桩查找（pass / raise NotImplementedError / TODO 等）")
    parser.add_argument("paths", nargs="*", default=["."],
                        help="文件或目录（默认: 当前目录，递归）")
    parser.add_argument("--ext", default="",
                        help="逗号分隔的扩展名过滤，如 .py,.js（默认: 内置常见语言）")
    parser.add_argument("--json", action="store_true", help="JSON 输出到 stdout")
    parser.add_argument("--fail-on-found", action="store_true",
                        help="发现任何问题时退出码 1")
    args = parser.parse_args(argv)

    paths = args.paths or ["."]
    for p in paths:
        if not os.path.exists(p):
            print("%s: error: 路径不存在: %s" % (TOOL, p), file=sys.stderr)
            return 2
    exts = [x.strip() for x in args.ext.split(",") if x.strip()] or DEFAULT_EXTS

    results = []
    scanned = 0
    for f in iter_files(paths, exts):
        items = scan_file(f)
        if items is None:
            continue
        scanned += 1
        for line_no, kind, msg in items:
            results.append({
                "file": display_path(f), "line": line_no,
                "kind": kind, "message": msg,
            })
    results.sort(key=lambda d: (d["file"], d["line"]))

    if args.json:
        print(json.dumps({"tool": TOOL, "scanned": scanned,
                          "count": len(results), "findings": results},
                         ensure_ascii=False, indent=2))
    else:
        for r in results:
            print("%s:%d: [%s] %s" % (r["file"], r["line"], r["kind"], r["message"]))
        print("scanned %d file(s), %d finding(s)" % (scanned, len(results)),
              file=sys.stderr)
    return 1 if (args.fail_on_found and results) else 0


if __name__ == "__main__":
    sys.exit(main())
