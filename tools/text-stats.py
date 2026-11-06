#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文本体检报告（text-stats）：统计行数、词数、字符数、段落数，
并给出句长分布与行长分布直方图。

- 行数：物理行；段落数：按空行分隔；词数：英文按空白切、中文按字计。
- 句子：按 。！？!?；;… 切分（含全角），ASCII 句点仅在后跟空白时切分；
  句长指句子内字符数（不含标点）。
- 行长指该行字符数（不含换行符）。

用法示例：
    python -I text-stats.py sample.txt
    cat sample.txt | python -I text-stats.py
    python -I text-stats.py --bins 12 sample.txt

选项：
    -f, --file PATH    输入文件（缺省读 stdin）
    --bins N           直方图桶数（默认 10）
    --no-hist          不输出直方图，只输出汇总
"""
import argparse
import re
import sys


def read_text(path: str | None) -> str:
    if path and path != "-":
        with open(path, "rb") as fh:
            data = fh.read()
    else:
        data = sys.stdin.buffer.read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def word_count(text: str) -> int:
    """英文词按连续字母/数字计，中文按字计。"""
    en = len(re.findall(r"[A-Za-z0-9']+", text))
    han = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
    return en + han


def histogram(values: list[int], bins: int) -> list[tuple[str, int]]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if lo == hi:
        return [(f"{lo}", len(values))]
    bins = max(1, min(bins, hi - lo))  # 小样本时避免大量空桶
    width = (hi - lo) / bins
    buckets = [0] * bins
    for v in values:
        idx = min(int((v - lo) / width), bins - 1)
        buckets[idx] += 1
    out = []
    for i, c in enumerate(buckets):
        b_lo = lo + i * width
        b_hi = lo + (i + 1) * width
        out.append((f"[{b_lo:.0f}~{b_hi:.0f})", c))
    if buckets:
        last = out[-1][0]
        out[-1] = (last[:-1] + "]", out[-1][1])
    return out


def draw_histo(title: str, values: list[int], bins: int) -> None:
    print(f"\n{title}")
    rows = histogram(values, bins)
    if not rows:
        print("  （无数据）")
        return
    peak = max(c for _, c in rows) or 1
    for label, c in rows:
        bar = "#" * max(1 if c else 0, round(c * 40 / peak))
        print(f"  {label:>12} {c:>7}  {bar}")


def main() -> int:
    ap = argparse.ArgumentParser(description="输出文本的行/词/字符/段落统计与分布直方图")
    ap.add_argument("file", nargs="?", default="-", help="输入文件，缺省或 '-' 为 stdin")
    ap.add_argument("--bins", type=int, default=10, metavar="N", help="直方图桶数（默认 10）")
    ap.add_argument("--no-hist", action="store_true", help="只输出汇总，不画直方图")
    args = ap.parse_args()

    if args.bins < 1:
        print("错误：--bins 必须 >= 1", file=sys.stderr)
        return 2

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    text = read_text(args.file)

    lines = text.splitlines()
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    sentences = [s for s in re.split(r"[。！？!?；;…]+|(?<=\.)\s+", text) if s.strip()]
    sent_lens = [sum(ch.isprintable() and not ch.isspace() for ch in s) for s in sentences]
    sent_lens = [n for n in sent_lens if n > 0]
    line_lens = [len(line) for line in lines]

    print("==== 文本体检报告 ====")
    print(f"行数      ：{len(lines)}")
    print(f"段落数    ：{len(paragraphs)}")
    print(f"词数      ：{word_count(text)}")
    print(f"字符数    ：{len(text)}（含换行），{len(text.replace(chr(10), '').replace(chr(13), ''))}（不含换行）")
    print(f"句子数    ：{len(sentences)}")
    if sent_lens:
        print(f"平均句长  ：{sum(sent_lens) / len(sent_lens):.1f} 字符（最长 {max(sent_lens)}）")
    if line_lens:
        print(f"平均行长  ：{sum(line_lens) / len(line_lens):.1f} 字符（最长 {max(line_lens)}）")

    if not args.no_hist:
        draw_histo("句长分布（字符数）", sent_lens, args.bins)
        draw_histo("行长分布（字符数）", line_lens, args.bins)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
