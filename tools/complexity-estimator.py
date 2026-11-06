#!/usr/bin/env python3
"""粗略复杂度估算 (complexity-estimator)。

按「分支关键字/分支节点数量 + 嵌套深度」粗略估算每个函数的圈复杂度(CC)，
按 CC 降序排行，快速找出最值得拆分重构的函数。这是启发式粗检，
不与 radon/lizard 等精确工具的计权完全一致。

估算规则:
  - Python (.py): 基于标准库 ast 精确解析。CC = 1 + 分支节点数
      (if / for / while / async for / except / ifexp / assert /
       boolop 的额外取值 / 推导式 for 与 if / match case)，
      不下钻嵌套函数、嵌套类与 lambda; 另报告控制结构最大嵌套深度。
  - 花括号语言 (.c/.cpp/.h/.java/.js/.ts/.cs/.go/.kt/...):
      正则定位函数头(要求 { 与函数头同行, K&R 风格) + 花括号配对截取函数体;
      CC = 1 + 分支关键字命中数(if/for/while/case/catch/&&/||/?)
          + max(0, 函数体内最大花括号嵌套深度 - 1)。
      字符串与 // 行注释会粗略剔除; 跨行块注释未处理(粗检)。

示例命令:
  python complexity-estimator.py src/                # 扫描目录, 默认 Top 20
  python complexity-estimator.py a.py b.c --top 10
  python complexity-estimator.py src --min-cc 5      # 只显示 CC >= 5 的函数

退出码: 0 = 正常运行; 2 = 参数或路径错误。
只使用 Python 标准库。
"""

import argparse
import os
import re
import sys

DEFAULT_EXTS = [
    ".py", ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx", ".java",
    ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cs", ".go", ".rs", ".swift", ".kt",
    ".php",
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
BRANCH_WORD = re.compile(r"\b(?:if|for|while|case|catch)\b")
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


def analyze_python(text):
    """用 ast 估算 .py 中每个函数的 CC; 返回 (results, error)。"""
    import ast

    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as exc:
        return None, "parse error: %s" % exc

    branch_nodes = (ast.If, ast.For, ast.While, ast.AsyncFor, ast.ExceptHandler,
                    ast.IfExp, ast.Assert)
    nest_nodes = (ast.If, ast.For, ast.While, ast.AsyncFor, ast.With,
                  ast.AsyncWith, ast.Try, ast.ExceptHandler)
    func_nodes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    lambda_node = getattr(ast, "Lambda", None)
    match_node = getattr(ast, "Match", None)

    results = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        cc = 1
        stack = list(ast.iter_child_nodes(node))
        while stack:
            child = stack.pop()
            if isinstance(child, func_nodes) or (
                    lambda_node and isinstance(child, lambda_node)):
                continue
            if isinstance(child, branch_nodes):
                cc += 1
            elif isinstance(child, ast.BoolOp):
                cc += len(child.values) - 1
            elif isinstance(child, ast.comprehension):
                cc += 1 + len(child.ifs)
            elif match_node and isinstance(child, match_node):
                cc += len(child.cases)
            stack.extend(ast.iter_child_nodes(child))

        def max_nesting(nodes, depth):
            best = depth
            for child in nodes:
                if isinstance(child, func_nodes) or (
                        lambda_node and isinstance(child, lambda_node)):
                    continue
                child_depth = depth + 1 if (
                    isinstance(child, nest_nodes)
                    or (match_node and isinstance(child, match_node))
                ) else depth
                best = max(best,
                           max_nesting(list(ast.iter_child_nodes(child)),
                                       child_depth))
            return best

        nesting = max_nesting(list(ast.iter_child_nodes(node)), 0)
        results.append({
            "name": node.name,
            "line": node.lineno,
            "end": getattr(node, "end_lineno", node.lineno) or node.lineno,
            "cc": cc,
            "nest": nesting,
            "lang": "python",
        })
    return results, None


def clean_line(line):
    """剔除字符串与注释，降低关键字误报(粗略)。"""
    line = STRING_RE.sub('""', line)
    line = BLOCK_COMMENT_RE.sub(" ", line)
    line = LINE_COMMENT_RE.sub("", line)
    return line


def analyze_brace(text):
    """花括号语言: 正则定位函数头 + 花括号配对截取函数体后计数。"""
    lines = text.splitlines()
    results = []
    i = 0
    n = len(lines)
    while i < n:
        header = clean_line(lines[i])
        m = FUNC_HEAD.match(header)
        if m and m.group(1) not in SKIP_NAMES:
            name = m.group(1)
            start = i + 1
            depth = header.count("{") - header.count("}")
            max_depth = max(depth, 1)
            branches = 0
            j = i + 1
            while j < n and depth > 0:
                cleaned = clean_line(lines[j])
                if depth >= 1:
                    branches += (len(BRANCH_WORD.findall(cleaned))
                                 + cleaned.count("&&") + cleaned.count("||")
                                 + cleaned.count("?"))
                depth += cleaned.count("{") - cleaned.count("}")
                if depth > max_depth:
                    max_depth = depth
                j += 1
            nesting = max(0, max_depth - 1)
            results.append({
                "name": name,
                "line": start,
                "end": j,
                "cc": 1 + branches + nesting,
                "nest": nesting,
                "lang": "brace",
            })
            i = j
        else:
            i += 1
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="complexity-estimator.py",
        description="按分支数量与嵌套深度粗略估算每个函数的圈复杂度并排序。",
    )
    parser.add_argument("paths", nargs="+", help="待扫描的文件或目录(可给多个)")
    parser.add_argument("--top", type=int, default=20,
                        help="只显示 CC 最高的前 N 个函数(默认 20)")
    parser.add_argument("--min-cc", type=int, default=1,
                        help="只显示 CC >= 该值的函数(默认 1)")
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

    rows = []
    skipped = []
    n_py = n_brace = 0
    for path in files:
        text = read_text(path)
        if text is None:
            skipped.append((path, "unreadable or binary"))
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext == ".py":
            results, err = analyze_python(text)
            if err:
                skipped.append((path, err))
                continue
            n_py += 1
        elif ext in BRACE_EXTS:
            results = analyze_brace(text)
            n_brace += 1
        else:
            skipped.append((path, "unsupported extension"))
            continue
        for r in results:
            r["path"] = path
            rows.append(r)

    rows.sort(key=lambda r: (-r["cc"], r["path"], r["line"]))
    shown = [r for r in rows if r["cc"] >= args.min_cc][: args.top]

    print("=== functions by estimated cyclomatic complexity "
          "(top %d, min-cc=%d) ===" % (args.top, args.min_cc))
    if not shown:
        print("(no functions found)")
    for rank, r in enumerate(shown, 1):
        print("%3d. CC=%-3d nest=%-2d [%s] %s:%d  %s"
              % (rank, r["cc"], r["nest"], r["lang"], r["path"], r["line"],
                 r["name"]))
    print()
    print("=== summary ===")
    print("files analyzed: %d (python: %d, brace: %d) | skipped: %d | functions: %d"
          % (n_py + n_brace, n_py, n_brace, len(skipped), len(rows)))
    for path, reason in skipped:
        print("  skipped %s: %s" % (path, reason))
    if rows:
        top = rows[0]
        print("highest CC: %d at %s:%d (%s)"
              % (top["cc"], top["path"], top["line"], top["name"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
