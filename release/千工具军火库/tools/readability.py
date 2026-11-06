#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可读性评估（readability）：计算平均句长、平均词长与长句占比，
给出中文可读性评分（0-100）与分级（A/B/C/D）。

评分思路（经验公式，面向中文）：
  - 平均句长越短越好：<=20 字符满分，>=60 字符记 0 分；
  - 长句（>40 字符）占比越低越好；
  - 平均词长（中文按字，英文按字母）适中为佳：<=1.8 满分，>=3.5 记 0 分。
  综合分 = 句长分 50% + 长句占比分 30% + 词长分 20%，四舍五入。
  分级：>=85 A（易读）；70~84 B（正常）；55~69 C（偏难）；<55 D（艰深）。

用法示例：
    python -I readability.py sample.txt
    cat sample.txt | python -I readability.py
    python -I readability.py --long-sentence 50 sample.txt

选项：
    -f, --file PATH        输入文件（缺省读 stdin）
    --long-sentence N      长句阈值（默认 40 字符）
    --json                 以 JSON 输出
"""
import argparse
import json
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


def clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def main() -> int:
    ap = argparse.ArgumentParser(description="计算中文可读性评分与分级")
    ap.add_argument("file", nargs="?", default="-", help="输入文件，缺省或 '-' 为 stdin")
    ap.add_argument("--long-sentence", type=int, default=40, metavar="N", help="长句阈值（默认 40）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    text = read_text(args.file)

    sentences = [s.strip() for s in re.split(r"[。！？!?；;…]+|(?<=\.)\s+|\n+", text) if s.strip()]
    if not sentences:
        print("（无有效句子，无法评估）")
        return 1

    sent_lens = [len(re.sub(r"\s", "", s)) for s in sentences]
    han_chars = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
    en_words = re.findall(r"[A-Za-z0-9']+", text)
    en_letters = sum(len(w) for w in en_words)
    en_units = len(en_words)
    # 词：中文按字计；英文按词计。平均词长 = 总字数/词数。
    if han_chars + en_units > 0:
        avg_word_len = (han_chars + en_letters) / (han_chars + en_units)
    else:
        avg_word_len = 0.0
    avg_sent = sum(sent_lens) / len(sent_lens)
    long_ratio = sum(1 for n in sent_lens if n > args.long_sentence) / len(sent_lens)

    s_sent = clamp(100 * (60 - avg_sent) / (60 - 20)) if avg_sent != 20 else 100.0
    s_long = clamp(100 * (1 - long_ratio / 0.3)) if long_ratio < 0.3 else 0.0
    s_word = clamp(100 * (3.5 - avg_word_len) / (3.5 - 1.8)) if avg_word_len != 1.8 else 100.0
    score = round(0.5 * s_sent + 0.3 * s_long + 0.2 * s_word)
    grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"
    grade_desc = {"A": "易读", "B": "正常", "C": "偏难", "D": "艰深"}[grade]

    if args.json:
        print(json.dumps({
            "score": score, "grade": grade, "grade_desc": grade_desc,
            "avg_sentence_len": round(avg_sent, 2),
            "avg_word_len": round(avg_word_len, 3),
            "long_sentence_ratio": round(long_ratio, 4),
            "long_sentence_threshold": args.long_sentence,
            "sentences": len(sentences), "han_chars": han_chars, "en_words": en_units,
            "subscores": {"sentence_len": round(s_sent, 1),
                          "long_ratio": round(s_long, 1),
                          "word_len": round(s_word, 1)},
        }, ensure_ascii=False, indent=2))
        return 0

    print("==== 可读性评估 ====")
    print(f"句子数          ：{len(sentences)}")
    print(f"平均句长        ：{avg_sent:.1f} 字符（阈值>20 开始扣分，>=60 记 0）")
    print(f"平均词长        ：{avg_word_len:.2f}（中文按字、英文按词）")
    print(f"长句占比        ：{long_ratio * 100:.1f}%（>{args.long_sentence} 字符）")
    print(f"子分            ：句长 {s_sent:.0f} / 长句 {s_long:.0f} / 词长 {s_word:.0f}")
    print(f"可读性评分      ：{score}/100")
    print(f"分级            ：{grade}（{grade_desc}）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
