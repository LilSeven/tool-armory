#!/usr/bin/env python3
"""定义骨架概览 (def-outline-counter)。

扫描类与函数定义，输出每个文件的代码骨架(带行号)及定义数量统计，
用于快速了解陌生代码库的结构。

规则:
  - .py 用标准库 ast 精确解析，类/函数按嵌套层级缩进展示，
    方法与嵌套函数也会列出; 语法错误的文件报警告后跳过;
  - 花括号语言(.c/.cpp/.h/.java/.js/.ts/.cs/.go/.kt/...)用正则识别
    class/struct/interface/enum 与函数定义(要求 { 与定义头同行)，
    按花括号深度近似缩进;
  - 统计数字 = class 数 + function 数(每文件与总计)。

示例命令:
  python def-outline-counter.py src/
  python def-outline-counter.py a.py b.c --ext .py,.c
  python def-outline-counter.py src --no-skeleton     # 只看数量统计

退出码: 0 = 正常运行; 2 = 参数或路径错误。
只使用 Python 标准库。
"""

import argparse
import os
import re
import sys

DEFAULT_EXTS = [
    ".py", ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx", ".java",
    ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cs", ".go", ".swift", ".kt", ".php",
]

SKIP_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".tox", ".mypy_cache",
    ".pytest_cache", "__pycache__", "node_modules", "venv", ".venv", "env",
    "dist", "build", "target", "vendor",
}

BRACE_EXTS = {
    ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx",
    ".java", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx",
    ".cs", ".go", ".rs", ".swift", ".kt", ".php",
}

FUNC_HEAD = re.compile(
    r"^[ \t]*(?:[A-Za-z_][\w]*[ \t\*&:<>,\[\]]+)*([A-Za-z_][\w]*)[ \t]*"
    r"\(([^;{]*)\)[ \t]*(?:const[ \t]*)?\{")
SKIP_NAMES = {
    "if", "for", "while", "switch", "catch", "do", "else", "return",
    "function", "sizeof", "foreach", "using", "lock", "synchronized", "with",
}
CLASSISH = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+|internal\s+|static\s+"
    r"|final\s+|abstract\s+|export\s+|default\s+)*"
    r"(class|struct|interface|enum)\s+([A-Za-z_]\w*)")
STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|' + r"'(?:\\.|[^'\\])*'")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT_RE = re.compile(r"//.*")


def iter_files(paths, exts):
    """产出待扫描文件: 显式给定的文件直接返回, 目录递归并按扩展名过滤。"""
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(
                    d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
                for name in sorted(files):
                    if os.path.splitext(name)[1].lower() in exts:
                        yield os.path.join(root, name)
        else:
            raise FileNotFoundError(p)


def read_text(path):
    """读取文本; 含 NUL 视为二进制返回 None, 读取失败打 warning 返回 None。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        print("warn: cannot read %s: %s" % (path, exc), file=sys.stderr)
        return None
    return None if "\x00" in text else text


def clean_line(line):
    """剔除字符串与注释(粗略)，降低误报。"""
    line = STRING_RE.sub('""', line)
    line = BLOCK_COMMENT_RE.sub(" ", line)
    line = LINE_COMMENT_RE.sub("", line)
    return line


def outline_python(text):
    """用 ast 解析 .py; 返回 (rows, counts) 或 (None, 错误信息)。

    rows = [(depth, kind, name, lineno)]; counts = {'class': n, 'function': n}
    """
    import ast

    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as exc:
        return None, "parse error: %s" % exc

    rows = []
    counts = {"class": 0, "function": 0}

    def rec(nodes, depth):
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                rows.append((depth, "class", node.name, node.lineno))
                counts["class"] += 1
                rec(node.body, depth + 1)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                rows.append((depth, kind, node.name, node.lineno))
                counts["function"] += 1
                rec(node.body, depth + 1)

    rec(tree.body, 0)
    return rows, counts


def outline_brace(text):
    """花括号语言: 正则识别类与函数定义，按花括号深度近似缩进。"""
    rows = []
    depth = 0
    for idx, raw in enumerate(text.splitlines(), 1):
        line = clean_line(raw)
        cm = CLASSISH.match(line)
        if cm:
            rows.append((depth, cm.group(1), cm.group(2), idx))
        fm = FUNC_HEAD.match(line)
        if fm and fm.group(1) not in SKIP_NAMES:
            rows.append((depth, "function", fm.group(1), idx))
        depth += line.count("{") - line.count("}")
        if depth < 0:
            depth = 0
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="def-outline-counter.py",
        description="扫描类与函数定义，输出每文件代码骨架及定义数量统计。",
    )
    parser.add_argument("paths", nargs="+", help="待扫描的文件或目录(可给多个)")
    parser.add_argument("--no-skeleton", action="store_true",
                        help="不打印骨架明细，只输出数量统计")
    parser.add_argument("--ext", default="",
                        help="逗号分隔扩展名过滤; 缺省用内置代码扩展名")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    if args.ext:
        exts = {e.strip().lower() for e in args.ext.split(",") if e.strip()}
    else:
        exts = set(DEFAULT_EXTS)

    try:
        files = list(iter_files(args.paths, exts))
    except FileNotFoundError as exc:
        parser.error("path not found: %s" % exc)

    if not files:
        print("no files matched (check paths / --ext filter)")
        return 0

    per_file = {}
    skipped = []
    for path in sorted(files):
        text = read_text(path)
        if text is None:
            skipped.append((path, "unreadable or binary"))
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext == ".py":
            rows, result = outline_python(text)
            if rows is None:
                skipped.append((path, result))
                continue
            counts = result
        elif ext in BRACE_EXTS:
            rows = outline_brace(text)
            counts = {"class": 0, "function": 0}
            for _, kind, _, _ in rows:
                if kind == "function":
                    counts["function"] += 1
                else:
                    counts["class"] += 1
        else:
            skipped.append((path, "unsupported extension"))
            continue
        per_file[path] = {"rows": rows, "counts": counts}

    print("=== skeleton ===")
    total_classes = total_functions = 0
    for path, entry in per_file.items():
        print(path)
        if not args.no_skeleton:
            for depth, kind, name, lineno in entry["rows"]:
                indent = "  " * (depth + 1)
                print("%s%-9s %-24s L%d" % (indent, kind, name[:24], lineno))
        print("  -> %d class(es), %d function(s)"
              % (entry["counts"]["class"], entry["counts"]["function"]))
        total_classes += entry["counts"]["class"]
        total_functions += entry["counts"]["function"]

    print()
    print("=== summary ===")
    print("files outlined: %d | classes: %d | functions: %d"
          % (len(per_file), total_classes, total_functions))
    for path, reason in skipped:
        print("  skipped %s: %s" % (path, reason))
    return 0


if __name__ == "__main__":
    sys.exit(main())
