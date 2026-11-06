#!/usr/bin/env python3
"""重复行检测 (dup-line-finder)。

在单个文件或目录中查找出现多次的相同代码行并按频次排行，
用于定位复制粘贴痕迹、样板噪音或意外重复的代码行。

规则:
  - 目录会递归扫描，自动跳过 .git/__pycache__/node_modules 等隐藏与构建目录;
  - 每行去掉行首尾空白后作为比较键，空行与长度 < --min-len 的行不参与统计;
  - 每条结果输出频次、行内容预览(最长 72 字符)与最多 3 处样本位置 file:line。

示例命令:
  python dup-line-finder.py src/                      # 扫描目录, 默认显示 Top 20
  python dup-line-finder.py a.py b.py --top 10        # 显式指定多个文件
  python dup-line-finder.py src --min-count 3 --min-len 6
  python dup-line-finder.py src --ext .py,.c,.h       # 只统计指定扩展名

退出码: 0 = 正常运行(无论是否发现重复行); 2 = 参数或路径错误。
只使用 Python 标准库。
"""

import argparse
import os
import sys

DEFAULT_EXTS = [
    ".py", ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx", ".java",
    ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cs", ".go", ".rs", ".rb", ".php",
    ".swift", ".kt", ".scala", ".sh", ".bash", ".ps1", ".bat", ".sql", ".lua",
    ".vue", ".dart", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".css", ".html",
    ".xml",
]

SKIP_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".tox", ".mypy_cache",
    ".pytest_cache", "__pycache__", "node_modules", "venv", ".venv", "env",
    "dist", "build", "target", "vendor",
}


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


def preview(text, width=72):
    text = text.strip()
    return text if len(text) <= width else text[: width - 3] + "..."


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dup-line-finder.py",
        description="查找文件/目录中出现多次的相同代码行并按频次排行。",
    )
    parser.add_argument("paths", nargs="+", help="待扫描的文件或目录(可给多个)")
    parser.add_argument("--top", type=int, default=20,
                        help="只显示频次最高的前 N 行(默认 20)")
    parser.add_argument("--min-count", type=int, default=2,
                        help="最小重复次数(默认 2)")
    parser.add_argument("--min-len", type=int, default=4,
                        help="行的最小长度, 更短的行不计(默认 4)")
    parser.add_argument("--ext", default="",
                        help="逗号分隔扩展名过滤(如 .py,.c); 缺省用内置代码扩展名")
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

    counts = {}    # 归一行 -> 次数
    order = {}     # 归一行 -> 首次出现序号(用于稳定排序)
    samples = {}   # 归一行 -> [(file, lineno), ...] 最多 3 个样本
    total_lines = 0
    seq = 0
    for path in files:
        text = read_text(path)
        if text is None:
            continue
        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if len(line) < args.min_len:
                continue
            total_lines += 1
            if line in counts:
                counts[line] += 1
                if len(samples[line]) < 3:
                    samples[line].append((path, lineno))
            else:
                counts[line] = 1
                order[line] = seq
                seq += 1
                samples[line] = [(path, lineno)]

    dups = [(line, cnt) for line, cnt in counts.items() if cnt >= args.min_count]
    dups.sort(key=lambda item: (-item[1], order[item[0]]))

    print("=== duplicated lines by frequency (top %d, min-count=%d) ==="
          % (args.top, args.min_count))
    if not dups:
        print("(no duplicated lines found)")
    for rank, (line, cnt) in enumerate(dups[: args.top], 1):
        locs = ", ".join("%s:%d" % (f, ln) for f, ln in samples[line])
        print("%3d. x%-4d %s" % (rank, cnt, preview(line)))
        print("         at %s" % locs)

    redundant = sum(cnt - 1 for _, cnt in dups)
    print()
    print("=== summary ===")
    print("files scanned: %d | lines counted: %d | distinct duplicated lines: %d"
          " | redundant occurrences: %d"
          % (len(files), total_lines, len(dups), redundant))
    return 0


if __name__ == "__main__":
    sys.exit(main())
