#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阅读时长估算 (reading-time)。

用途:
    按中文字符数 / 英文词数分别统计文本（文件或 stdin），以各自速率
    估算「阅读」与「朗读」所需时间。默认速率: 阅读 中文 300 字/分钟、
    英文 200 词/分钟；朗读 中文 240 字/分钟、英文 130 词/分钟。

示例命令:
    python -I reading-time.py article.md
    python -I reading-time.py post.txt --read 250 --speak 200
    cat post.txt | python -I reading-time.py --json
    python -I reading-time.py --self-test
"""
import argparse
import json
import re
import sys

RE_CJK = re.compile(r"[\u4e00-\u9fff]")
RE_EN_WORD = re.compile(r"[A-Za-z]+(?:['\u2019-][A-Za-z]+)*")

DEFAULT_READ_CJK = 300    # 字/分钟
DEFAULT_READ_EN = 200     # 词/分钟
DEFAULT_SPEAK_CJK = 240
DEFAULT_SPEAK_EN = 130


def count_units(text: str):
    """返回 (中文字符数, 英文词数)。数字串按 2 个字符折算 1 个词计入词数。"""
    cjk = len(RE_CJK.findall(text))
    en_words = len(RE_EN_WORD.findall(text))
    digits = len(re.findall(r"\d+", text))
    return cjk, en_words + digits


def fmt_minutes(minutes: float) -> str:
    total_sec = int(round(minutes * 60))
    m, s = divmod(total_sec, 60)
    if m == 0:
        return f"{s} 秒"
    return f"{m} 分 {s:02d} 秒"


def estimate(text: str, read_cjk=DEFAULT_READ_CJK, read_en=DEFAULT_READ_EN,
             speak_cjk=DEFAULT_SPEAK_CJK, speak_en=DEFAULT_SPEAK_EN):
    cjk, en = count_units(text)
    read_min = cjk / read_cjk + en / read_en
    speak_min = cjk / speak_cjk + en / speak_en
    return {
        "cjk_chars": cjk,
        "en_words": en,
        "reading_minutes": round(read_min, 2),
        "speaking_minutes": round(speak_min, 2),
        "reading_human": fmt_minutes(read_min),
        "speaking_human": fmt_minutes(speak_min),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="按字符/词速率估算阅读与朗读时长")
    ap.add_argument("input", nargs="?", help="输入文件；缺省或为 - 时读 stdin")
    ap.add_argument("--read", type=float, default=DEFAULT_READ_CJK,
                    help=f"中文阅读速率（字/分钟，默认 {DEFAULT_READ_CJK}）")
    ap.add_argument("--speak", type=float, default=DEFAULT_SPEAK_CJK,
                    help=f"中文朗读速率（字/分钟，默认 {DEFAULT_SPEAK_CJK}）")
    ap.add_argument("--read-en", type=float, default=DEFAULT_READ_EN)
    ap.add_argument("--speak-en", type=float, default=DEFAULT_SPEAK_EN)
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--self-test", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)

    if args.self_test:
        sample = ("这是一段中文测试文本。" * 300) + " " + ("word " * 200)
        r = estimate(sample)
        assert r["cjk_chars"] == 300 * 10, r["cjk_chars"]   # 每句 10 个汉字
        assert r["en_words"] == 200, r["en_words"]
        assert abs(r["reading_minutes"] - (3000 / 300 + 200 / 200)) < 1e-6
        assert abs(r["speaking_minutes"] - round(3000 / 240 + 200 / 130, 2)) < 1e-6
        assert "分" in r["reading_human"]
        r2 = estimate("Hello world")
        assert r2["cjk_chars"] == 0 and r2["en_words"] == 2
        print("self-test OK")
        return 0

    if args.input and args.input != "-":
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        text = sys.stdin.read()

    r = estimate(text, args.read, args.read_en, args.speak, args.speak_en)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(f"中文字符: {r['cjk_chars']}")
        print(f"英文词数: {r['en_words']}")
        print(f"预计阅读: {r['reading_human']}（{r['reading_minutes']} 分钟）")
        print(f"预计朗读: {r['speaking_human']}（{r['speaking_minutes']} 分钟）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
