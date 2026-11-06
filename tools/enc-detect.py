#!/usr/bin/env python3
"""编码探测 - 启发式猜测文本文件编码并给出置信度。

用途
    综合 BOM 检查、严格解码尝试、字节分布与高频字统计，猜测一个文本文件的
    编码（UTF-8 / UTF-16 / GBK / GB18030 / Big5 / Shift-JIS / Latin-1 / ASCII），
    并输出猜测结果、置信度与依据。

只用 Python 标准库。仅做只读检测，不修改任何文件。

示例命令
    python -I enc-detect.py sample.txt
    python -I enc-detect.py sample.txt --sample-bytes 8192
    python -I enc-detect.py dir/*.txt
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

BOMS = [
    ("utf-32-le", b"\xff\xfe\x00\x00"),
    ("utf-32-be", b"\x00\x00\xfe\xff"),
    ("utf-8-sig", b"\xef\xbb\xbf"),
    ("utf-16-le", b"\xff\xfe"),
    ("utf-16-be", b"\xfe\xff"),
]

# 常用中日韩/西文 "常见字符" 集合，用于给候选编码打分
CJ_RANGES = (
    (0x4E00, 0x9FFF),   # CJK 统一表意文字
    (0x3400, 0x4DBF),   # CJK 扩展 A
    (0x3000, 0x303F),   # CJK 标点
    (0xFF00, 0xFFEF),   # 全角字符
)
COMMON_PUNCT = set("，。、；：？！“”‘’（）《》【】—…·ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 \t\r\n")


def _check_bom(data: bytes):
    for enc, bom in BOMS:
        if data.startswith(bom):
            return enc, len(bom)
    return None, 0


def _printable_score(text: str) -> float:
    """返回 0~1，衡量解码结果的可读程度。"""
    if not text:
        return 0.0
    good = 0
    for ch in text:
        cp = ord(ch)
        if ch in COMMON_PUNCT or ch.isspace():
            good += 1
        elif 0x20 <= cp < 0x7F:
            good += 1
        elif any(lo <= cp <= hi for lo, hi in CJ_RANGES):
            good += 1
        elif 0xA0 <= cp <= 0x24F or 0x1E00 <= cp <= 0x1FFF:  # 拉丁扩展/希腊/西里尔
            good += 0.7
        elif cp == 0xFFFD:
            pass
        else:
            good += 0.3
    return good / len(text)


def _high_freq_bonus(text: str) -> float:
    """高频字统计：常见中文字/常见英文单词重复出现加分，罕见符号堆叠减分。"""
    if not text:
        return 0.0
    sample = text[:4000]
    cjk = [c for c in sample if any(lo <= ord(c) <= hi for lo, hi in CJ_RANGES)]
    if len(cjk) >= 10:
        cnt = Counter(cjk)
        top = sum(n for _, n in cnt.most_common(min(10, len(cnt))))
        return min(0.15, (top / len(cjk)) * 0.2)
    ascii_alpha = sum(1 for c in sample if c.isascii() and c.isalpha())
    if ascii_alpha >= 20:
        cnt = Counter(w.lower() for w in sample.split() if len(w) > 2)
        top = sum(n for _, n in cnt.most_common(5)) if cnt else 0
        return min(0.10, (top / max(ascii_alpha, 1)) * 0.4)
    return 0.0


def detect(data: bytes):
    """返回按置信度排序的候选列表 [(encoding, confidence, reason), ...]。"""
    candidates = []

    enc, bomlen = _check_bom(data)
    if enc:
        text = data[bomlen:].decode(enc, errors="replace")
        score = min(0.99, 0.75 + 0.2 * _printable_score(text) + _high_freq_bonus(text))
        candidates.append((enc, score, f"BOM 标记 {enc}"))

    sample = data[:65536]
    if not sample:
        return [("empty", 0.0, "空文件")]

    # 纯 ASCII
    if all(b < 0x80 for b in sample):
        candidates.append(("ascii", 0.99, "全部字节 < 0x80"))

    # UTF-16 无 BOM：奇偶位大量 \x00
    if len(sample) >= 8:
        null_even = sum(1 for i in range(0, len(sample) - 1, 2) if sample[i] == 0)
        null_odd = sum(1 for i in range(1, len(sample), 2) if sample[i] == 0)
        half = len(sample) // 2
        if null_even > half * 0.8 and null_odd < half * 0.1:
            candidates.append(("utf-16-le", 0.85, "偶数位大量 NUL，无 BOM"))
        elif null_odd > half * 0.8 and null_even < half * 0.1:
            candidates.append(("utf-16-be", 0.85, "奇数位大量 NUL，无 BOM"))

    # 逐个尝试严格解码
    for enc in ("utf-8", "gb18030", "gbk", "big5", "shift_jis", "latin-1"):
        if any(enc == c[0] for c in candidates):
            continue
        try:
            text = sample.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        ps = _printable_score(text)
        if enc == "latin-1" and ps < 0.95:
            continue  # latin-1 永远能解，只有可读性很高时才作为候选
        score = ps * 0.9 + _high_freq_bonus(text)
        if enc == "utf-8" and sum(1 for b in sample if b >= 0x80) > 0:
            score = min(0.98, score + 0.08)  # utf-8 严格通过是很强的信号
        if enc in ("gb18030", "gbk"):
            cjk = sum(1 for c in text if any(lo <= ord(c) <= hi for lo, hi in CJ_RANGES))
            if cjk / max(len(text), 1) > 0.2:
                score = min(0.95, score + 0.05)
        candidates.append((enc, round(min(score, 0.99), 3), "严格解码成功 + 可读性评分"))

    candidates.sort(key=lambda c: -c[1])
    return candidates


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="启发式猜测文本文件编码并给出置信度")
    ap.add_argument("paths", nargs="+", help="待检测的文件")
    ap.add_argument("--sample-bytes", type=int, default=65536, help="每个文件读取的最大字节数")
    ap.add_argument("--top", type=int, default=3, help="每个文件显示的候选数量")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    rc = 0
    for p in args.paths:
        path = Path(p)
        if not path.is_file():
            print(f"[跳过] {path}: 不是文件或不存在")
            rc = 2
            continue
        try:
            data = path.read_bytes()[: args.sample_bytes]
        except OSError as e:
            print(f"[错误] {path}: {e}")
            rc = 2
            continue
        cands = detect(data)
        best = cands[0] if cands else ("unknown", 0.0, "")
        print(f"{path}  ->  {best[0]}  (置信度 {best[1]:.0%}, {best[2]})")
        for enc, conf, why in cands[1 : args.top]:
            print(f"    备选: {enc}  ({conf:.0%}, {why})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
