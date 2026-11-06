#!/usr/bin/env python3
"""assert-outside-tests —— 断言越界扫描（单文件，仅用 Python 标准库）。

用途:
    查找"测试目录以外"使用 assert 的位置，提示生产代码风险:
    生产环境常以 `python -O` 运行，assert 语句会被整体剥离，依赖 assert 做
    参数校验或业务判断的代码在 -O 下会静默失效。

判定规则:
    * Python: 基于 ast 的 Assert 节点（精确）；语法错误时报告 parse-error
      并退化为行级正则扫描。
    * 其他语言: 行级正则 `\\bassert!?`（自动排除 assertEqual / assert_eq 等
      标识符；先剔除单行字符串与行注释再匹配）。
    * 测试文件判定: 路径上任一父目录名属于 test / tests / testing / __tests__ /
      spec / specs（可用 --test-dir 追加），或文件名形如 test_*.py / tests.py /
      *_test.go / *.test.js / *.spec.ts / conftest.py 等。默认跳过测试文件
      不报告，--include-tests 可一并报告。

示例（Git Bash / Windows）:
    python assert-outside-tests.py src/                        # 递归扫描目录
    python assert-outside-tests.py a.py lib/b.go               # 扫描指定文件
    python assert-outside-tests.py . --ext .py,.go             # 限定扩展名
    python assert-outside-tests.py src/ --test-dir fixtures    # 追加测试目录名
    python assert-outside-tests.py src/ --include-tests        # 连测试文件一起报告
    python assert-outside-tests.py src/ --json                 # JSON 输出到 stdout
    python assert-outside-tests.py src/ --fail-on-found        # 有发现则退出码 1（CI 用）

输出约定:
    发现列表（file:line: [类别] 说明）写 stdout，统计摘要写 stderr。

局限:
    Python 判定精确；其他语言为行级启发式，跨行 assert 语句只报告起始行，
    多行字符串中的 assert 字样可能误报或漏报。

退出码: 0=扫描完成（无论是否有发现）；1=有发现且启用 --fail-on-found；2=用法或 IO 错误。
"""

import argparse
import ast
import json
import os
import re
import sys

TOOL = "assert-outside-tests"

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

TEST_DIR_NAMES = {"test", "tests", "testing", "__tests__", "spec", "specs"}
TEST_FILE_RE = re.compile(
    r"^(?:tests?|spec)(?:[._-]|$)|[._-]test\.|\.(?:test|spec)\.|^conftest\.",
    re.IGNORECASE,
)
# assert( / assert x / assert!（Rust）；排除 assertEqual、assert_eq 等标识符
ASSERT_RE = re.compile(r"\bassert!?(?![\w$])")


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


def is_test_file(path, extra_dirs=()):
    parts = path.replace("\\", "/").split("/")
    base = parts[-1]
    if TEST_FILE_RE.search(base):
        return True
    names = TEST_DIR_NAMES | set(extra_dirs)
    return any(p.lower() in names for p in parts[:-1])


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


def scan_python(text, findings):
    """AST 精确扫描 Assert 节点；解析失败返回 False（调用方退化到行级扫描）。"""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        line = getattr(exc, "lineno", 1) or 1
        findings.append((line, "parse-error", "cannot parse: %s" % exc.msg))
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            findings.append((node.lineno, "assert",
                             "assert statement outside tests"))
    return True


def scan_lines(text, ext, findings):
    """行级正则扫描（非 Python 文件，以及 Python 语法错误时的退化路径）。"""
    is_py = ext in (".py", ".pyw")
    orig = text.splitlines()
    cleaned = py_clean_lines(text) if is_py else orig
    for idx, (raw, code0) in enumerate(zip(orig, cleaned), 1):
        code = code0 if is_py else STRING_RE.sub('""', raw)
        code = strip_line_comment(code, ext)
        if ASSERT_RE.search(code):
            findings.append((idx, "assert",
                             "assert used outside tests: %s" % raw.strip()[:70]))


def scan_file(path):
    """返回 [(line_no, kind, message), ...]；文件不可读返回 None。"""
    ext = os.path.splitext(path)[1].lower()
    text = read_text(path)
    if text is None:
        return None
    findings = []
    if ext in (".py", ".pyw"):
        if not scan_python(text, findings):
            scan_lines(text, ext, findings)
    else:
        scan_lines(text, ext, findings)
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
        description="断言越界扫描：查找测试目录以外使用 assert 的位置")
    parser.add_argument("paths", nargs="*", default=["."],
                        help="文件或目录（默认: 当前目录，递归）")
    parser.add_argument("--ext", default="",
                        help="逗号分隔的扩展名过滤，如 .py,.js（默认: 内置常见语言）")
    parser.add_argument("--test-dir", action="append", default=[],
                        help="额外按测试目录处理的目录名（可多次指定）")
    parser.add_argument("--include-tests", action="store_true",
                        help="也报告测试文件里的 assert")
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
    skipped_tests = 0
    for f in iter_files(paths, exts):
        if not args.include_tests and is_test_file(f, args.test_dir):
            skipped_tests += 1
            continue
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
                          "test_files_skipped": skipped_tests,
                          "count": len(results), "findings": results},
                         ensure_ascii=False, indent=2))
    else:
        for r in results:
            print("%s:%d: [%s] %s" % (r["file"], r["line"], r["kind"], r["message"]))
        print("scanned %d file(s), %d test file(s) skipped, %d finding(s)"
              % (scanned, skipped_tests, len(results)), file=sys.stderr)
    return 1 if (args.fail_on_found and results) else 0


if __name__ == "__main__":
    sys.exit(main())
