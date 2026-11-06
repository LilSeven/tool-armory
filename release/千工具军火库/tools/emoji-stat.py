#!/usr/bin/env python3
"""Emoji 统计剥离(emoji-stat)

统计文本中的 Emoji 种类与出现次数;可选全部剥离(--strip)或仅保留白名单
中的 Emoji(--keep)。

用法:
  python emoji-stat.py <输入文件> [--strip] [--keep 😀,🎉] [-o 输出文件]
  cat in.txt | python emoji-stat.py --strip

示例:
  python emoji-stat.py chat.log            # 只统计,输出种类与次数
  python emoji-stat.py chat.log --strip -o clean.txt   # 剥离全部 Emoji
  python emoji-stat.py chat.log --keep "😀,👍"         # 只保留白名单
不指定 -o 时,统计报告输出到 stderr,处理后的文本输出到 stdout。
"""
import argparse
import sys
import unicodedata

# Windows 控制台/管道默认 GBK,强制 UTF-8 以支持 Emoji 输出
for _s in (sys.stdout, sys.stderr, sys.stdin):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", newline="")

# Emoji 判定:基于 Unicode 属性的近似实现(标准库无 emoji 属性)
EMOJI_RANGES = [
    (0x1F300, 0x1F5FF),   # Misc Symbols and Pictographs
    (0x1F600, 0x1F64F),   # Emoticons
    (0x1F680, 0x1F6FF),   # Transport and Map
    (0x1F700, 0x1F77F),   # Alchemical Symbols
    (0x1F780, 0x1F7FF),   # Geometric Shapes Extended
    (0x1F800, 0x1F8FF),   # Supplemental Arrows-C
    (0x1F900, 0x1F9FF),   # Supplemental Symbols and Pictographs
    (0x1FA00, 0x1FAFF),   # Symbols and Pictographs Extended-A
    (0x1FB00, 0x1FBFF),   # Symbols for Legacy Computing
    (0x2600, 0x26FF),     # Misc symbols (☀☁… 部分)
    (0x2700, 0x27BF),     # Dingbats (✂✅… 部分)
    (0x2B00, 0x2BFF),     # Misc Symbols and Arrows (⭐ 等)
    (0x1F1E6, 0x1F1FF),   # Regional indicators (国旗)
    (0xFE0F, 0xFE0F),     # Variation selector-16 (emoji 呈现)
    (0x200D, 0x200D),     # ZWJ(emoji 组合用)
    (0x2190, 0x21FF),     # 箭头部分常作 emoji(→ ↗)
    (0x203C, 0x203C), (0x2049, 0x2049),
    (0x2122, 0x2122), (0x2139, 0x2139),
    (0x2194, 0x21AA),
    (0x231A, 0x231B), (0x2328, 0x2328), (0x23CF, 0x23CF),
    (0x23E9, 0x23FA),
    (0x24C2, 0x24C2),
    (0x25AA, 0x25FE),
    (0x2934, 0x2935),
    (0x3030, 0x3030), (0x303D, 0x303D), (0x3297, 0x3299),
]


def is_emoji(ch):
    cp = ord(ch)
    for lo, hi in EMOJI_RANGES:
        if lo <= cp <= hi:
            return True
    return False


def grapheme_clusters(text):
    """把 emoji 序列(ZWJ/变体选择符/皮肤色修饰)合并为簇。"""
    clusters = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if not is_emoji(ch):
            clusters.append(ch)
            i += 1
            continue
        cluster = ch
        i += 1
        joiners = '\u200d\ufe0f\U0001F3FB\U0001F3FC\U0001F3FD\U0001F3FE\U0001F3FF'
        while i < n and is_emoji(text[i]) and (text[i] in joiners or text[i - 1] == '\u200d'):
            cluster += text[i]
            i += 1
        clusters.append(cluster)
    return clusters


def main(argv=None):
    ap = argparse.ArgumentParser(description="Emoji 统计与剥离")
    ap.add_argument("input", nargs="?", help="输入文件,缺省读 stdin")
    ap.add_argument("--strip", action="store_true", help="剥离全部 Emoji")
    ap.add_argument("--keep", default="", help="逗号分隔的 Emoji 白名单")
    ap.add_argument("-o", "--output", help="输出文件")
    args = ap.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    keep = set(c for c in args.keep if c)

    clusters = grapheme_clusters(text)
    counts = {}
    for c in clusters:
        if is_emoji(c[0]) and not (c[0] in '\u200d\ufe0f'):
            counts[c] = counts.get(c, 0) + 1

    kept_lines = []
    for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        try:
            name = unicodedata.name(c[0])
        except ValueError:
            name = "?"
        kept_lines.append("U+%04X %s x%d  %s" % (ord(c[0]), name, n, c))

    changed = False
    if args.strip or keep:
        out_parts = []
        for c in clusters:
            if is_emoji(c[0]) and not (c[0] in '\u200d\ufe0f'):
                if args.strip or (keep and c not in keep):
                    changed = True
                    continue
            out_parts.append(c)
        result = ''.join(out_parts)
    else:
        result = text

    report = "Emoji 种类: %d, 总次数: %d\n" % (
        len(counts), sum(counts.values()))
    report += "\n".join(kept_lines) if kept_lines else "(未发现 Emoji)"
    print(report, file=sys.stderr)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(result)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
