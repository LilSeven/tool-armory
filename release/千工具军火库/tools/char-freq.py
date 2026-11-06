#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字符频率表（char-freq）：统计文本中每个字符的出现次数与占比。

支持按汉字（CJK）、非 ASCII 或全部字符过滤，按频次降序输出。
输入：文件参数或 stdin。输出：字符 / 次数 / 占比（占所选过滤范围内总字符数）。

用法示例：
    python -I char-freq.py sample.txt
    python -I char-freq.py --han --top 20 sample.txt
    python -I char-freq.py --non-ascii sample.txt
    cat sample.txt | python -I char-freq.py

选项：
    -f, --file PATH    输入文件（缺省读 stdin）
    --han              只统计汉字（CJK 统一表意文字及扩展A）
    --non-ascii        只统计非 ASCII 字符
    --top N            只显示前 N 个（默认全部）
    --asc              按字符升序排列（默认按频次降序）
    --csv              以 CSV 格式输出
"""
import argparse
import sys
import unicodedata


def is_han(ch: str) -> bool:
    """CJK 统一表意文字（含扩展A、兼容表意文字）。"""
    return ("\u4e00" <= ch <= "\u9fff") or ("\u3400" <= ch <= "\u4dbf") \
        or ("\uf900" <= ch <= "\ufaff")


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


def main() -> int:
    ap = argparse.ArgumentParser(description="统计文本中每个字符的出现次数与占比")
    ap.add_argument("file", nargs="?", default="-", help="输入文件，缺省或 '-' 为 stdin")
    ap.add_argument("--han", action="store_true", help="只统计汉字")
    ap.add_argument("--non-ascii", action="store_true", help="只统计非 ASCII 字符")
    ap.add_argument("--top", type=int, default=0, metavar="N", help="只显示前 N 个，0 为全部")
    ap.add_argument("--asc", action="store_true", help="按字符排序输出（默认按频次降序）")
    ap.add_argument("--csv", action="store_true", help="输出 CSV")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    text = read_text(args.file)
    counter: dict[str, int] = {}
    for ch in text:
        if ch in ("\n", "\r", "\t"):
            continue
        if args.han and not is_han(ch):
            continue
        if args.non_ascii and ord(ch) < 128:
            continue
        counter[ch] = counter.get(ch, 0) + 1

    total = sum(counter.values())
    if total == 0:
        print("（过滤后无字符可统计）")
        return 0

    items = list(counter.items())
    items.sort(key=lambda kv: kv[0]) if args.asc else items.sort(key=lambda kv: (-kv[1], kv[0]))
    if args.top > 0:
        items = items[:args.top]

    label = {"han": "汉字", "non_ascii": "非 ASCII", None: "全部"}[
        "han" if args.han else "non_ascii" if args.non_ascii else None]
    if args.csv:
        print("char,count,pct")
        for ch, n in items:
            print(f"{ch},{n},{n * 100.0 / total:.2f}")
    else:
        print(f"[字符频率表] 范围={label}  参与统计字符总数={total}  不同字符数={len(counter)}")
        print(f"{'字符':<6}{'次数':>8}{'占比':>10}  说明")
        for ch, n in items:
            try:
                desc = unicodedata.name(ch)
            except ValueError:
                desc = "?"
            shown = repr(ch)[1:-1] if ch.isspace() or not ch.isprintable() else ch
            print(f"{shown:<6}{n:>8}{n * 100.0 / total:>9.2f}%  {desc}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
