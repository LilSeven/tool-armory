#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模糊文件指纹（ssdeep 风格）与文件相似度评估。

用途:
    基于分块滚动哈希（context-triggered piecewise hashing, CTPH）为文件
    生成 ssdeep 风格的模糊指纹，格式为 "blocksize:hash1:hash2"；给定两个
    文件时可计算 0-100 的相似度得分，用于检测近似重复文件（内容有增删改
    但大体相同的文件会得到高分）。

    说明：这是简化实现——滚动哈希、触发规则与打分方式与 ssdeep 官方输出
    不逐字节兼容（不能与官方 ssdeep 工具互通），但具备相同的核心性质：
    触发点只依赖局部内容，插入/删除/替换少量内容不会显著改变指纹。
    适用于中小文件（全量读入内存）。

    已知局限（与 ssdeep 同源）：极低熵/强周期内容（如同一行文本无限重复、
    全零文件）只有极少数不同的局部窗口，触发点可能永不命中，指纹段为空；
    此时两枚指纹若完全相同则直接判为 100（相同的局部结构）。
    建议主要用在对文本/日志/二进制等正常熵内容的近似重复检测。

示例:
    python file-fuzzy-fingerprint.py file.bin                # 输出单个文件指纹
    python file-fuzzy-fingerprint.py a.bin b.bin             # 对比相似度
    python file-fuzzy-fingerprint.py a.bin a.bin             # 相同文件应为 100
    python file-fuzzy-fingerprint.py a.bin b.bin --json      # JSON 输出

退出码: 0 成功；2 文件不存在或参数错误。
"""

import argparse
import json
import sys

B64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
MIN_BLOCK = 3            # 最小块大小（与 ssdeep 相同的取值）
TARGET_CHUNKS = 64       # 依据文件大小选择块大小，目标指纹约 64 字符
MAX_HASH_LEN = 64        # 单段指纹最大字符数
MIN_SCORE_LEN = 7        # 短于该长度的指纹段不参与打分（借鉴 ssdeep）
FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193
MASK32 = 0xFFFFFFFF


def _utf8_stdio():
    """让中文输出在管道/重定向时保持 UTF-8，避免 Windows 本地编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


class RollingHash(object):
    """7 字节窗口多项式滚动哈希：当前值只由最近 7 个字节决定。"""

    WINDOW = 7
    PRIME = FNV_PRIME

    def __init__(self):
        self._buf = []
        self._h = 0
        self._drop = (self.PRIME ** self.WINDOW) & MASK32

    def push(self, byte):
        self._buf.append(byte)
        self._h = (self._h * self.PRIME + byte) & MASK32
        if len(self._buf) > self.WINDOW:
            old = self._buf.pop(0)
            self._h = (self._h - old * self._drop) & MASK32
        return self._h


def choose_blocksize(nbytes):
    """块大小从 3 起成倍增长，直到 64 个块能覆盖整个文件。"""
    bs = MIN_BLOCK
    while bs * TARGET_CHUNKS < nbytes:
        bs *= 2
    return bs


def _block_hash(data, block_size):
    """按给定块大小生成触发指纹串。

    触发条件基于内容局部滚动哈希（与绝对位置无关），触发时记录的是
    自上次触发以来内容块的 FNV-1a 哈希低 6 位。
    """
    if block_size < 1:
        block_size = 1
    roll = RollingHash()
    block_h = FNV_OFFSET
    out = []
    for c in data:
        rh = roll.push(c)
        block_h = ((block_h ^ c) * FNV_PRIME) & MASK32
        if rh % block_size == block_size - 1:
            out.append(B64_CHARS[block_h & 0x3F])
            block_h = FNV_OFFSET
            if len(out) >= MAX_HASH_LEN:
                break
    return "".join(out)


def fuzzy_hash_bytes(data):
    if not data:
        return "3::"
    bs = choose_blocksize(len(data))
    s1 = _block_hash(data, bs)
    s2 = _block_hash(data, max(bs // 2, 1))
    return "%d:%s:%s" % (bs, s1, s2)


def fuzzy_hash_file(path):
    with open(path, "rb") as f:
        data = f.read()
    return fuzzy_hash_bytes(data), len(data)


def levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def score_strings(a, b):
    """把两段指纹的编辑距离映射为 0-100 的相似度。"""
    if len(a) < MIN_SCORE_LEN or len(b) < MIN_SCORE_LEN:
        return 0
    longest = max(len(a), len(b))
    dist = levenshtein(a, b)
    return max(0, int(round(100.0 * (longest - dist) / longest)))


def parse_fingerprint(sig):
    parts = sig.split(":")
    if len(parts) != 3:
        raise ValueError("指纹应为 blocksize:hash1:hash2 格式: %r" % sig)
    return int(parts[0]), parts[1], parts[2]


def fuzzy_compare(sig_a, sig_b):
    """两枚指纹的相似度 0-100；块大小相同或相差 2 倍才可比，否则为 0。"""
    bs_a, s1a, s2a = parse_fingerprint(sig_a)
    bs_b, s1b, s2b = parse_fingerprint(sig_b)
    if (bs_a, s1a, s2a) == (bs_b, s1b, s2b):
        # 指纹完全一致（含低熵内容导致空段的退化情形）视为高度相似
        return 100
    if bs_a == bs_b:
        return max(score_strings(s1a, s1b), score_strings(s2a, s2b))
    # 大块指纹的第二段（块大小减半）对应小块文件的第一段
    if bs_a == bs_b * 2:
        return score_strings(s2a, s1b)
    if bs_b == bs_a * 2:
        return score_strings(s2b, s1a)
    return 0


def main(argv=None):
    _utf8_stdio()
    ap = argparse.ArgumentParser(
        description="生成 ssdeep 风格模糊指纹并评估两文件相似度（纯标准库）")
    ap.add_argument("files", nargs="+", metavar="FILE",
                    help="一个文件（生成指纹）或两个文件（对比相似度）")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = ap.parse_args(argv)

    if len(args.files) > 2:
        ap.error("最多接受两个文件：1 个生成指纹，2 个对比相似度")
    try:
        results = [fuzzy_hash_file(p) for p in args.files]
    except OSError as e:
        print("错误: %s" % e, file=sys.stderr)
        return 2

    if len(args.files) == 1:
        sig, size = results[0]
        if args.json:
            print(json.dumps({"file": args.files[0], "size": size, "fuzzy": sig},
                             ensure_ascii=False))
        else:
            print(sig)
        return 0

    (sig_a, size_a), (sig_b, size_b) = results
    score = fuzzy_compare(sig_a, sig_b)
    if args.json:
        print(json.dumps({
            "file1": args.files[0], "fuzzy1": sig_a, "size1": size_a,
            "file2": args.files[1], "fuzzy2": sig_b, "size2": size_b,
            "similarity": score}, ensure_ascii=False))
        return 0
    print("%s  %s（%d 字节）" % (sig_a, args.files[0], size_a))
    print("%s  %s（%d 字节）" % (sig_b, args.files[1], size_b))
    verdict = "高度相似" if score >= 75 else ("可能相似" if score >= 50 else "不相似")
    print("相似度: %d/100（%s）" % (score, verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
