#!/usr/bin/env python3
"""dead-code-marker —— 死代码模式扫描（单文件，仅用 Python 标准库）。

用途:
    在源码中查找占位/死代码模式:
      * `if False` / `elif False` / `while False` / `if 0:` / `if (false)` / `if (0)`
      * 常量短路 `0 && ...` / `... && 0` / `false && ...` / `... && false`
        （自动跳过 `a == 0 && b` 这类普通比较，避免误报）
      * `return` / `raise` / `break` / `continue` / `throw` / `exit()` / `panic()`
        之后的不可达语句: 基于缩进与 {} 深度的启发式，每个终止语句只报告其后第一条。

示例（Git Bash / Windows）:
    python dead-code-marker.py src/                     # 递归扫描目录
    python dead-code-marker.py a.py lib/b.js            # 扫描指定文件
    python dead-code-marker.py . --ext .py,.go          # 限定扩展名
    python dead-code-marker.py src/ --json              # JSON 输出到 stdout
    python dead-code-marker.py src/ --fail-on-found     # 有发现则退出码 1（CI 用）

输出约定:
    发现列表（file:line: [类别] 说明）写 stdout，统计摘要写 stderr。

局限:
    行级启发式，不做完整语法分析。Python 会先剔除注释、单行字符串与三引号
    字符串；其他语言剔除单行字符串与行注释后匹配，多行字符串/模板串可能带来
    个别误报或漏报。

退出码: 0=扫描完成（无论是否有发现）；1=有发现且启用 --fail-on-found；2=用法或 IO 错误。
"""

import argparse
import json
import os
import re
import sys

TOOL = "dead-code-marker"

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

# 单行字符串（含转义），匹配前先把字符串字面量抹掉，降低误报
STRING_RE = re.compile(
    r'"(?:\\.|[^"\\])*"'
    r"|'(?:\\.|[^'\\])*'"
    r"|`(?:\\.|[^`\\])*`"
)

DEAD_PATTERNS = [
    ("if-false", re.compile(r"\bif\s+False\b")),
    ("elif-false", re.compile(r"\belif\s+False\b")),
    ("while-false", re.compile(r"\bwhile\s+False\b")),
    ("if-zero-colon", re.compile(r"\bif\s+0\s*:")),
    ("if-false-paren", re.compile(r"\bif\s*\(\s*false\s*\)", re.IGNORECASE)),
    ("if-zero-paren", re.compile(r"\bif\s*\(\s*0\s*\)")),
]
# 常量短路: 需结合上下文校验，剔除 `== 0 &&` 这类比较
AND_LEFT = re.compile(r"\b(0|false|False)\s*&&")
AND_RIGHT = re.compile(r"&&\s*(0(?![\w.])|false|False)\b")
OPERATOR_CHARS = set("=!<>+-*/%&|^~")
OK_AFTER = set(";,)}]&|{:?")

TERMINATOR_RE = re.compile(
    r"^\s*(?:return|raise|break|continue|throw)\b"
    r"|^\s*(?:\w+\.)?_?exit\s*\("
    r"|^\s*panic!?\s*\("
)


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


def py_clean_lines(text):
    """Python 专用清洗: 剔除注释、单行/三引号字符串内容，保留代码与缩进。"""
    lines = []
    state = None  # None | '"' | "'" | '"""' | "'''"
    for raw in text.splitlines():
        out = []
        i, n = 0, len(raw)
        while i < n:
            if state in ('"""', "'''"):
                if raw.startswith(state, i):
                    state = None
                    i += 3
                elif raw[i] == "\\":
                    i += 2
                else:
                    i += 1
                continue
            if state in ('"', "'"):
                if raw[i] == "\\":
                    i += 2
                    continue
                if raw[i] == state:
                    state = None
                i += 1
                continue
            if raw.startswith('"""', i):
                state = '"""'
                i += 3
                continue
            if raw.startswith("'''", i):
                state = "'''"
                i += 3
                continue
            if raw[i] == "#":
                break  # 注释：丢弃行尾
            if raw[i] in ('"', "'"):
                state = raw[i]
                i += 1
                continue
            out.append(raw[i])
            i += 1
        if state in ('"', "'"):
            state = None  # 单行字符串不跨行
        lines.append("".join(out))
    return lines


def strip_line_comment(code, ext):
    if ext in HASH_COMMENTS:
        cut = code.find("#")
        if cut >= 0:
            return code[:cut]
    elif ext in SLASH_COMMENTS:
        cut = code.find("//")
        if cut >= 0:
            return code[:cut]
    return code


def scan_file(path):
    """返回 [(line_no, kind, message), ...]；文件不可读返回 None。"""
    ext = os.path.splitext(path)[1].lower()
    text = read_text(path)
    if text is None:
        return None
    is_py = ext in (".py", ".pyw")
    orig = text.splitlines()
    cleaned = py_clean_lines(text) if is_py else orig
    findings = []
    brace_depth = 0
    paren_depth = 0
    pending = None  # (indent, depth_after_line, line_no, keyword)

    for idx, (raw, code0) in enumerate(zip(orig, cleaned), 1):
        code = code0 if is_py else STRING_RE.sub('""', raw)
        code = strip_line_comment(code, ext)
        if not code.strip():
            continue

        for kind, rx in DEAD_PATTERNS:
            if rx.search(code):
                findings.append((idx, kind, "dead-code pattern: %s" % code.strip()[:60]))
        for m in AND_LEFT.finditer(code):
            j = m.start() - 1
            while j >= 0 and code[j] in " \t":
                j -= 1
            if j < 0 or code[j] not in OPERATOR_CHARS:
                findings.append((idx, "constant-short-circuit",
                                 "constant %r before '&&': %s"
                                 % (m.group(1), code.strip()[:60])))
        for m in AND_RIGHT.finditer(code):
            k = m.end()
            while k < len(code) and code[k] in " \t":
                k += 1
            if k >= len(code) or code[k] in OK_AFTER:
                findings.append((idx, "constant-short-circuit",
                                 "constant %r after '&&': %s"
                                 % (m.group(1), code.strip()[:60])))

        opens_paren = (code.count("(") - code.count(")")
                       + code.count("[") - code.count("]"))
        opens_brace = code.count("{") - code.count("}")
        if paren_depth == 0:
            stripped = code.strip()
            lead = len(code) - len(code.lstrip())
            if pending is not None:
                p_indent, p_depth, p_line, p_word = pending
                if brace_depth < p_depth:
                    pending = None
                elif brace_depth == p_depth and (stripped.startswith("}") or lead < p_indent):
                    pending = None
                elif stripped.startswith("}"):
                    pending = None
                else:
                    findings.append((idx, "unreachable",
                                     "unreachable code after '%s' on line %d"
                                     % (p_word, p_line)))
                    pending = None
            if pending is None:
                tm = TERMINATOR_RE.match(code)
                if tm and not ("{" in code and "}" in code):
                    words = re.findall(r"[A-Za-z_]+", tm.group(0))
                    pending = (lead, brace_depth + opens_brace, idx,
                               words[-1] if words else "exit")
        paren_depth += opens_paren
        brace_depth += opens_brace
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
        description="死代码模式扫描（if False / 0 && / return 后不可达等）")
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
