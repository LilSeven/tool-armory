#!/usr/bin/env python3
"""克隆块粗检 (dup-block-finder)。

用滑动窗口哈希检测相邻多行的重复代码块，提示疑似复制粘贴的代码克隆。
支持单文件或目录(递归)，同一文件内与跨文件之间的重复都会报告。

原理与规则:
  1) 每个文件的行先做 strip 归一并跳过空行，避免缩进/空行差异漏检;
  2) 对每个 --window 行的窗口内容计算 md5，出现 >= --min-count 次的窗口为候选;
  3) 同一文件内的重复窗口向前后两个方向扩展成最大相同块;
  4) 跨文件重复按窗口长度报告, 但同一文件对上偏移相同且位置连续的
     滑窗报告会合并还原成完整克隆块;
  5) 同一对起始位置只保留最长报告;
     与自身重叠(第二次出现落在第一块内部)的退化报告会被丢弃。

示例命令:
  python dup-block-finder.py src/                    # 默认窗口 5 行, Top 20
  python dup-block-finder.py a.py b.py --window 8    # 自定义窗口大小
  python dup-block-finder.py src --min-count 3 --top 15
  python dup-block-finder.py src --ext .py,.c

退出码: 0 = 正常运行(无论是否发现克隆块); 2 = 参数或路径错误。
只使用 Python 标准库。
"""

import argparse
import hashlib
import os
import sys

DEFAULT_EXTS = [
    ".py", ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx", ".java",
    ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cs", ".go", ".rs", ".rb", ".php",
    ".swift", ".kt", ".scala", ".sh", ".bash", ".ps1", ".bat", ".sql", ".lua",
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
        prog="dup-block-finder.py",
        description="滑动窗口哈希粗检相邻多行重复代码块(疑似复制粘贴)。",
    )
    parser.add_argument("paths", nargs="+", help="待扫描的文件或目录(可给多个)")
    parser.add_argument("--window", type=int, default=5,
                        help="滑动窗口行数(默认 5)")
    parser.add_argument("--min-count", type=int, default=2,
                        help="窗口最少出现次数(默认 2)")
    parser.add_argument("--top", type=int, default=20,
                        help="最多报告的块数(默认 20)")
    parser.add_argument("--ext", default="",
                        help="逗号分隔扩展名过滤; 缺省用内置代码扩展名")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    if args.window < 2:
        parser.error("--window must be >= 2")
    if args.min_count < 2:
        parser.error("--min-count must be >= 2")

    if args.ext:
        exts = {e.strip().lower() for e in args.ext.split(",") if e.strip()}
    else:
        exts = set(DEFAULT_EXTS)

    try:
        files = list(iter_files(args.paths, exts))
    except FileNotFoundError as exc:
        parser.error("path not found: %s" % exc)

    # 每个文件的归一化非空行: (行号, 文本)
    rows_by_path = {}
    for path in files:
        text = read_text(path)
        if text is None:
            continue
        rows = [(ln, raw.strip())
                for ln, raw in enumerate(text.splitlines(), 1) if raw.strip()]
        if len(rows) >= args.window:
            rows_by_path[path] = rows

    if not rows_by_path:
        print("no scannable files (need at least %d non-blank lines each)" % args.window)
        return 0

    paths = sorted(rows_by_path)
    rows_by_id = [rows_by_path[p] for p in paths]
    texts_by_id = [[t for _, t in rows] for rows in rows_by_id]

    groups = {}  # md5 -> [(file_id, start_index), ...]
    total_windows = 0
    for fid_i, texts in enumerate(texts_by_id):
        n = len(texts)
        for i in range(n - args.window + 1):
            h = hashlib.md5(
                "\x00".join(texts[i:i + args.window]).encode("utf-8", "replace")
            ).hexdigest()
            groups.setdefault(h, []).append((fid_i, i))
        total_windows += n - args.window + 1

    reports = []  # [fid_a, idx_a, fid_b, idx_b, length]
    for positions in groups.values():
        if len(positions) < args.min_count:
            continue
        positions = sorted(positions)
        ref_fid, ref_idx = positions[0]
        for other_fid, other_idx in positions[1:]:
            a, b = ref_idx, other_idx
            length = args.window
            if ref_fid == other_fid:
                texts = texts_by_id[ref_fid]
                n = len(texts)
                while (a + length < n and b + length < n
                       and texts[a + length] == texts[b + length]):
                    length += 1
                while a > 0 and b > 0 and texts[a - 1] == texts[b - 1]:
                    a -= 1
                    b -= 1
                    length += 1
                if b < a + length:  # 与自身重叠的退化报告(如连续重复行)
                    continue
            reports.append([ref_fid, a, other_fid, b, length])

    # 同一对位置只留最长报告
    best = {}
    for rep in reports:
        key = (rep[0], rep[1], rep[2], rep[3])
        if key not in best or rep[4] > best[key][4]:
            best[key] = rep

    # 同一 (文件对, 偏移) 且位置连续的滑窗报告合并为完整克隆块
    # (跨文件重复不做扩展, 靠此步骤还原完整块; 同文件重复已在扩展阶段归并)
    by_offset = {}
    for rep in best.values():
        fa, ia, fb, ib, ln = rep
        by_offset.setdefault((fa, fb, ib - ia), []).append(rep)
    kept = []
    for key in sorted(by_offset):
        reps = sorted(by_offset[key], key=lambda r: r[1])
        cur = None
        for rep in reps:
            if cur is not None and rep[1] <= cur[1] + cur[4]:
                # 同偏移且与已并区间重叠/相接(滑窗逐行推进) → 并入并延伸
                cur[4] = rep[1] + rep[4] - cur[1]
            else:
                if cur is not None:
                    kept.append(cur)
                cur = rep
        if cur is not None:
            kept.append(cur)

    kept.sort(key=lambda r: (-r[4], r[0], r[1], r[2], r[3]))
    shown = kept[: args.top]

    print("=== suspected cloned blocks (window=%d lines) ===" % args.window)
    if not shown:
        print("(no repeated blocks found)")
    for rank, (fa, ia, fb, ib, ln) in enumerate(shown, 1):
        ra0, ra1 = rows_by_id[fa][ia][0], rows_by_id[fa][ia + ln - 1][0]
        rb0, rb1 = rows_by_id[fb][ib][0], rows_by_id[fb][ib + ln - 1][0]
        print("%3d. %d lines duplicated" % (rank, ln))
        print("      A %s:%d-%d" % (paths[fa], ra0, ra1))
        print("      B %s:%d-%d" % (paths[fb], rb0, rb1))
        print("      | %s" % preview(rows_by_id[fa][ia][1]))

    repeated_groups = sum(1 for p in groups.values() if len(p) >= args.min_count)
    print()
    print("=== summary ===")
    print("files scanned: %d | windows hashed: %d | repeated window groups: %d"
          " | block pairs reported: %d"
          % (len(paths), total_windows, repeated_groups, len(kept)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
