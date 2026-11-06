#!/usr/bin/env python3
"""print-debug-finder —— 调试输出残留扫描（单文件，仅用 Python 标准库）。

用途:
    找出代码里遗留的调试输出语句:
      * Python : print() / pprint()
      * JS/TS  : console.log / console.debug / console.info / console.dir / console.table
      * Go     : fmt.Print / fmt.Println / fmt.Printf 及内置 println()
      * Ruby   : p / pp（自动跳过 `p = ...` 这类赋值）
      * Java   : System.out.print / println / printf
      * Rust   : println! / print! / eprintln! / eprint!
      * PHP    : var_dump() / print_r()
      * 其他扩展名: 使用通用模式集合。

示例（Git Bash / Windows）:
    python print-debug-finder.py src/                  # 递归扫描目录
    python print-debug-finder.py a.py lib/b.go         # 扫描指定文件
    python print-debug-finder.py . --ext .py,.js       # 限定扩展名
    python print-debug-finder.py src/ --json           # JSON 输出到 stdout
    python print-debug-finder.py src/ --fail-on-found  # 有发现则退出码 1（CI 用）

输出约定:
    发现列表（file:line: [类别] 说明）写 stdout，统计摘要写 stderr。

局限:
    行级启发式。Python 会先剔除注释、单行字符串与三引号字符串；其他语言剔除
    单行字符串与行注释后再匹配，因此字符串字面量里的 "console.log(...)" 字样
    不会误报。工具不区分"故意的业务输出"与"调试残留"，由使用者自行判断。

退出码: 0=扫描完成（无论是否有发现）；1=有发现且启用 --fail-on-found；2=用法或 IO 错误。
"""

import argparse
import json
import os
import re
import sys

TOOL = "print-debug-finder"

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

LANG_BY_EXT = {
    ".py": "python", ".pyw": "python",
    ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
    ".ts": "js", ".tsx": "js",
    ".go": "go",
    ".rb": "ruby", ".rake": "ruby",
    ".java": "java",
    ".rs": "rust",
    ".php": "php",
}

LANG_PATTERNS = {
    "python": [
        ("print()", re.compile(r"\bprint\s*\(")),
        ("pprint()", re.compile(r"\bpprint\s*\(")),
    ],
    "js": [
        ("console.log/debug/info/dir/table()",
         re.compile(r"\bconsole\.(?:log|debug|info|dir|table)\s*\(")),
    ],
    "go": [
        ("fmt.Print/Println/Printf()", re.compile(r"\bfmt\.Print\w*\s*\(")),
        ("builtin println()", re.compile(r"\bprintln\s*\(")),
    ],
    "ruby": [
        ("p / pp", re.compile(r"\bpp?\s+(?!=)|\bpp?\((?!\))")),
    ],
    "java": [
        ("System.out.print/println/printf()",
         re.compile(r"\bSystem\.out\.print\w*\s*\(")),
    ],
    "rust": [
        ("println!/print!/eprintln!/eprint!",
         re.compile(r"\be?print(?:ln)?!\s*\(")),
    ],
    "php": [
        ("var_dump()", re.compile(r"\bvar_dump\s*\(")),
        ("print_r()", re.compile(r"\bprint_r\s*\(")),
    ],
}

GENERIC_PATTERNS = [
    ("print()", re.compile(r"\bprint\s*\(")),
    ("println()", re.compile(r"\bprintln!?\s*\(")),
    ("console.log()", re.compile(r"\bconsole\.(?:log|debug|info|dir|table)\s*\(")),
    ("fmt.Print*()", re.compile(r"\bfmt\.Print\w*\s*\(")),
    ("System.out.print*()", re.compile(r"\bSystem\.out\.print\w*\s*\(")),
    ("var_dump()/print_r()", re.compile(r"\b(?:var_dump|print_r)\s*\(")),
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
    patterns = LANG_PATTERNS.get(LANG_BY_EXT.get(ext), GENERIC_PATTERNS)
    findings = []
    for idx, (raw, code0) in enumerate(zip(orig, cleaned), 1):
        code = code0 if is_py else STRING_RE.sub('""', raw)
        code = strip_line_comment(code, ext)
        for label, rx in patterns:
            if rx.search(code):
                findings.append((idx, "debug-print",
                                 "%s: %s" % (label, raw.strip()[:70])))
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
        description="调试输出残留扫描（print / console.log / fmt.Println 等）")
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
