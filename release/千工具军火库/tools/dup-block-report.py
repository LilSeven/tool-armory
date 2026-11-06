#!/usr/bin/env python3
"""重复块报告：在文本中找出重复出现的连续行块（>=N 行）并报告各出现位置。

用法:
    python dup-block-report.py <文件> [-n 3] [--min-total 2] [--out FILE]

示例:
    python dup-block-report.py log.txt -n 2
    python dup-block-report.py code.py -n 4 --out dup.txt
"""
import argparse
import sys
from collections import defaultdict


def find_dup_blocks(lines, n, min_total):
    """找出长度>=n 的重复连续行块，合并掉被更长块覆盖的部分。"""
    if n < 1 or len(lines) < n:
        return []
    pos = defaultdict(list)  # 块元组 -> [起始行号]
    for i in range(len(lines) - n + 1):
        key = tuple(lines[i:i + n])
        pos[key].append(i)

    # 先按长度降序收集重复块，再滤掉已被更长重复块完全覆盖的块
    blocks = [(k, locs) for k, locs in pos.items() if len(locs) >= min_total]
    blocks.sort(key=lambda b: -len(b[0]))

    covered = set()  # 已被更长块覆盖的起始位置（按文件行号记录）
    result = []
    all_starts = defaultdict(set)
    for key, locs in blocks:
        # 该块每个出现位置的行区间
        spans = [(i, i + len(key)) for i in locs]
        # 若所有出现都被更长重复块覆盖则丢弃
        if all(all(s in all_starts[j] for j in range(s, e)) for s, e in spans):
            covered.update(locs)
            continue
        for i, _ in spans:
            for j in range(i, i + len(key)):
                all_starts[j].add(i)
        result.append((key, locs))
    return result


def main():
    ap = argparse.ArgumentParser(description="找出文本中重复出现的连续行块")
    ap.add_argument("file", help="输入文本文件")
    ap.add_argument("-n", "--block", type=int, default=3, help="块最小行数，默认 3")
    ap.add_argument("--min-total", type=int, default=2,
                    help="块至少出现的次数，默认 2")
    ap.add_argument("--out", help="结果写入文件（默认打印 stdout）")
    args = ap.parse_args()

    if args.block < 1:
        print("error: -n must be >= 1", file=sys.stderr)
        return 2
    try:
        with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    blocks = find_dup_blocks(lines, args.block, args.min_total)
    blocks.sort(key=lambda b: (-len(b[0]), b[1][0]))

    out_lines = ["重复块报告: %s (最小块长 %d, 最少出现 %d 次)" % (args.file, args.block, args.min_total)]
    out_lines.append("共发现 %d 个重复块" % len(blocks))
    out_lines.append("=" * 60)
    for key, locs in blocks:
        out_lines.append("块 (%d 行), 出现 %d 次:" % (len(key), len(locs)))
        out_lines.append("  位置: 行 " + ", ".join(str(i + 1) for i in locs))
        out_lines.append("  内容预览:")
        for j, ln in enumerate(key[:10]):
            out_lines.append("    %s" % ln)
        if len(key) > 10:
            out_lines.append("    ... (共 %d 行)" % len(key))
        out_lines.append("")

    text = "\n".join(out_lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("written %s (%d dup blocks)" % (args.out, len(blocks)))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
