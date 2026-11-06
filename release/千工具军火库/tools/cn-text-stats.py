#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文字数统计 —— 分列统计汉字数、标点数、英文单词数、总字符数。

统计口径
  汉字数             CJK 统一表意文字（含扩展 A~H、兼容表意区）；
  中文标点/西文标点  Unicode 类别为 P* 的字符，按非 ASCII / ASCII 拆分，
                     省略号、破折号、书名号等均计入标点；
  英文单词数         连续拉丁字母串，允许内部连字符/撇号（co-op、don't 各记 1）；
  空格数             半角空格、制表符、全角空格（不含换行）；
  总字符数(计空格)   除换行符外全部字符数 —— 稿费结算常用的「字符数（计空格）」口径；
  总字符数(不计空格) 在计空格基础上扣除空格。

用法
  python cn-text-stats.py doc.txt
  python cn-text-stats.py a.txt b.txt        # 多文件，逐个输出并给合计
  cat doc.txt | python cn-text-stats.py -    # 从标准输入读
  python cn-text-stats.py doc.txt --json

仅用 Python 标准库。
"""

import argparse
import json
import re
import sys
import unicodedata

CJK_RANGES = (
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF), (0x2A700, 0x2B739), (0x2B740, 0x2B81D),
    (0x2B820, 0x2CEA1), (0x2CEB0, 0x2EBE0), (0x2EBF0, 0x2EE5D),
    (0x30000, 0x3134A), (0x31350, 0x323AF),
)
WORD_RE = re.compile(r"[A-Za-z]+(?:[-'’][A-Za-z]+)*")

STAT_ROWS = (
    ("汉字数", "han"),
    ("中文标点", "punct_cn"),
    ("西文标点", "punct_en"),
    ("标点合计", "punct_total"),
    ("英文单词数", "words_en"),
    ("空格数", "spaces"),
    ("总字符数(计空格)·稿费口径", "chars_with_space"),
    ("总字符数(不计空格)", "chars_no_space"),
    ("非空行数", "nonempty_lines"),
)


def _setup_stdio():
    for s in (sys.stdout, sys.stderr, sys.stdin):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def decode_auto(data, encoding=None):
    if encoding:
        return data.decode(encoding)
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def is_han(ch):
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in CJK_RANGES)


def analyze(text):
    han = punct_cn = punct_en = spaces = 0
    for ch in text:
        if ch in "\r\n":
            continue
        if is_han(ch):
            han += 1
        elif unicodedata.category(ch).startswith("P"):
            if ord(ch) < 128:
                punct_en += 1
            else:
                punct_cn += 1
        elif ch.isspace():
            spaces += 1
    chars_with_space = sum(1 for ch in text if ch not in "\r\n")
    return {
        "han": han,
        "punct_cn": punct_cn,
        "punct_en": punct_en,
        "punct_total": punct_cn + punct_en,
        "words_en": len(WORD_RE.findall(text)),
        "spaces": spaces,
        "chars_with_space": chars_with_space,
        "chars_no_space": chars_with_space - spaces,
        "nonempty_lines": sum(1 for ln in text.splitlines() if ln.strip()),
    }


def print_report(label, s):
    print(f"【{label}】")
    for name, key in STAT_ROWS:
        print(f"  {name:<20}{s[key]:>12,}")


def main(argv=None):
    _setup_stdio()
    p = argparse.ArgumentParser(description="中文字数统计（汉字/标点/英文单词/字符数·计空格）")
    p.add_argument("inputs", nargs="+", help="文本文件路径，- 表示标准输入；可传多个文件")
    p.add_argument("--json", action="store_true", help="以 JSON 输出（多文件时含 __total__）")
    args = p.parse_args(argv)

    results = []
    for label in args.inputs:
        try:
            text = sys.stdin.read() if label == "-" else decode_auto(read_bytes(label), None)
        except OSError as e:
            print(f"错误: 无法读取 {label}: {e}", file=sys.stderr)
            return 1
        except UnicodeDecodeError as e:
            print(f"错误: {label} 解码失败: {e}", file=sys.stderr)
            return 1
        results.append((label, analyze(text)))

    total = dict.fromkeys(results[0][1], 0)
    for _, s in results:
        for k, v in s.items():
            total[k] += v

    if args.json:
        payload = {label: s for label, s in results}
        if len(results) > 1:
            payload["__total__"] = total
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    for label, s in results:
        print_report(label, s)
        print()
    if len(results) > 1:
        print_report(f"合计（{len(results)} 个文件）", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
