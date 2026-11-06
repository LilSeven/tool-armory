#!/usr/bin/env python3
"""依赖引入统计 (import-counter)。

统计每个文件的 import / include / using / require 等引入语句数量，
并汇总被引用最多的模块排行，用于快速了解代码的依赖面。

支持的语法(按扩展名选择):
  - .py           : `import a, b as c` 与 `from x.y import z`(含相对导入)
  - .c/.h/.cpp/...: `#include <x>` 与 `#include "x"`
  - .java/.kt     : `import a.b.C;`(含 static 与 .* )
  - .js/.ts/...   : `import ... from 'x'` / `import 'x'` /
                    `require('x')` / `export ... from 'x'`
  - .cs           : `using X.Y;`
  - .go           : `import "x"` 与 `import ( ... )` 块

示例命令:
  python import-counter.py src/                  # 每文件统计 + 模块排行
  python import-counter.py a.py b.c --top 15
  python import-counter.py src --ext .py         # 只统计 Python 文件

退出码: 0 = 正常运行; 2 = 参数或路径错误。
只使用 Python 标准库。
"""

import argparse
import os
import re
import sys
from collections import Counter

DEFAULT_EXTS = [
    ".py", ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx", ".java",
    ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".cs", ".go", ".kt", ".kts",
]

SKIP_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".tox", ".mypy_cache",
    ".pytest_cache", "__pycache__", "node_modules", "venv", ".venv", "env",
    "dist", "build", "target", "vendor",
}

C_EXTS = {".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx"}
JVM_EXTS = {".java", ".kt", ".kts"}
JS_EXTS = {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx"}

PY_IMPORT = re.compile(
    r"^\s*import\s+([\w.]+(?:\s+as\s+\w+)?(?:\s*,\s*[\w.]+(?:\s+as\s+\w+)?)*)"
    r"\s*(?:#.*)?$")
PY_FROM = re.compile(r"^\s*from\s+(\.+[\w.]*|[\w.]+)\s+import\b")
C_INCLUDE = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]')
JVM_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+(?:\.\*)?)\s*;")
JS_FROM = re.compile(r"^\s*(?:import|export)\b[^;]*?\bfrom\s*['\"]([^'\"]+)['\"]")
JS_BARE = re.compile(r"^\s*import\s*['\"]([^'\"]+)['\"]")
JS_REQUIRE = re.compile(r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
CS_USING = re.compile(r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;")
GO_SINGLE = re.compile(r'^\s*import\s+("[^"]+"|`[^`]+`)')
GO_BLOCK_ITEM = re.compile(r'^\s*(?:[_\w][\w.]*\s+)?"([^"]+)"')
GO_BLOCK_END = re.compile(r"^\s*\)")


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


def analyze_file(path, text):
    """按扩展名统计 (语句数, 模块引用列表)。"""
    ext = os.path.splitext(path)[1].lower()
    statements = 0
    mods = []
    in_go_block = False
    for raw in text.splitlines():
        if ext == ".py":
            m = PY_FROM.match(raw)
            if m:
                statements += 1
                mods.append(m.group(1))
                continue
            m = PY_IMPORT.match(raw)
            if m:
                statements += 1
                for part in m.group(1).split(","):
                    name = part.strip().split(" as ")[0].strip()
                    if name:
                        mods.append(name)
                continue
        elif ext in C_EXTS:
            m = C_INCLUDE.match(raw)
            if m:
                statements += 1
                mods.append(m.group(1))
        elif ext in JVM_EXTS:
            m = JVM_IMPORT.match(raw)
            if m:
                statements += 1
                mods.append(m.group(1))
        elif ext in JS_EXTS:
            m = JS_REQUIRE.search(raw)
            if m:
                statements += 1
                mods.append(m.group(1))
                continue
            m = JS_FROM.match(raw)
            if m:
                statements += 1
                mods.append(m.group(1))
                continue
            m = JS_BARE.match(raw)
            if m:
                statements += 1
                mods.append(m.group(1))
        elif ext == ".cs":
            m = CS_USING.match(raw)
            if m:
                statements += 1
                mods.append(m.group(1))
        elif ext == ".go":
            if in_go_block:
                if GO_BLOCK_END.match(raw):
                    in_go_block = False
                    continue
                m = GO_BLOCK_ITEM.match(raw)
                if m:
                    statements += 1
                    mods.append(m.group(1))
                continue
            m = GO_SINGLE.match(raw)
            if m:
                statements += 1
                mods.append(m.group(1).strip('"`'))
                continue
            if re.match(r"^\s*import\s*\(", raw):
                in_go_block = True
    return statements, mods


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="import-counter.py",
        description="统计每个文件的 import/include 语句数量及被引用最多的模块。",
    )
    parser.add_argument("paths", nargs="+", help="待扫描的文件或目录(可给多个)")
    parser.add_argument("--top", type=int, default=15,
                        help="模块排行只显示前 N 个(默认 15)")
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

    global_counter = Counter()
    total_statements = 0
    total_refs = 0
    print("=== per-file import/include stats ===")
    for path in sorted(files):
        text = read_text(path)
        if text is None:
            continue
        statements, mods = analyze_file(path, text)
        total_statements += statements
        total_refs += len(mods)
        global_counter.update(mods)
        if mods:
            seen = list(dict.fromkeys(mods))
            shown = ", ".join(seen[:8])
            if len(seen) > 8:
                shown += ", ... +%d more" % (len(seen) - 8)
        else:
            shown = "-"
        print("%s: %d statements, %d refs | %s"
              % (path, statements, len(mods), shown))

    print()
    print("=== most referenced modules (top %d) ===" % args.top)
    if not global_counter:
        print("(no import/include statements found)")
    for mod, cnt in global_counter.most_common(args.top):
        print("%4d  %s" % (cnt, mod))

    print()
    print("=== summary ===")
    print("files scanned: %d | import statements: %d | module references: %d"
          " | distinct modules: %d"
          % (len(files), total_statements, total_refs, len(global_counter)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
