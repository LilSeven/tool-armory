#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""entropy-analyzer.py —— 字节分布与香农熵分析器，辅助判断数据是否被加密或压缩。

统计输入中 256 种字节值的频率，计算:
  * 香农熵 H = -SUM p*log2(p)，单位 bit/字节（上限 8.0，均匀随机时逼近）；
  * 卡方均匀性统计量（df=255，越小越接近均匀分布）；
  * 可打印字符占比与最高频字节列表，并据此给出经验性判断。

用法:
  python -I entropy-analyzer.py <file> [--top N] [--json]
  python -I entropy-analyzer.py --text "hello world" [--top N]
  cat data.bin | python -I entropy-analyzer.py [--json]

示例:
  python -I entropy-analyzer.py backup.zip        # 熵接近 8 -> 疑似加密/压缩
  python -I entropy-analyzer.py notes.txt         # 熵低且可打印占比高 -> 明文文本

说明: 文件整体读入内存，适合中小文件；退出码 0 成功、2 参数/文件错误。
仅使用 Python 标准库。
"""

import argparse
import json
import math
import sys


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def analyze(data):
    n = len(data)
    counts = [data.count(v) for v in range(256)]
    entropy = 0.0
    for c in counts:
        if c:
            p = c / n
            entropy -= p * math.log2(p)
    printable = sum(counts[v] for v in range(0x20, 0x7F))
    printable += counts[0x09] + counts[0x0A] + counts[0x0D]
    printable_pct = (printable / n) if n else 0.0
    chi2 = None
    if n >= 256:
        expected = n / 256.0
        chi2 = sum((c - expected) ** 2 / expected for c in counts)
    order = sorted(range(256), key=lambda v: counts[v], reverse=True)
    top = [(v, counts[v]) for v in order if counts[v] > 0]
    return counts, entropy, printable_pct, chi2, top


def make_verdict(n, entropy, printable_pct):
    if n == 0:
        return "空输入（无数据可分析）"
    if printable_pct >= 0.9 and entropy < 6.0:
        return "低熵且可打印字符为主：大概率是明文文本"
    if entropy >= 7.95:
        return "熵逼近上限：纯随机数据或强加密输出（二者难以区分）"
    if entropy >= 7.5:
        return "高熵：疑似已加密或已压缩"
    if entropy >= 6.0:
        return "中高熵：可能是压缩流、编码数据或混合二进制"
    if entropy >= 3.0:
        return "中等熵：结构化二进制或含冗余数据"
    return "低熵：明文文本或高度重复的数据"


def main(argv=None):
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        prog="entropy-analyzer.py",
        description="统计字节分布与香农熵，辅助判断加密/压缩")
    ap.add_argument("input", nargs="?", help="待分析文件；缺省时读 stdin")
    ap.add_argument("--text", help="直接分析给定文本（utf-8 编码）")
    ap.add_argument("--top", type=int, default=16,
                    help="显示最高频的前 N 种字节（默认 16，0 不显示）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.top < 0:
        ap.error("--top 必须 >= 0")

    if args.text is not None:
        data = args.text.encode("utf-8")
        source = "<text 参数>"
    elif args.input:
        source = args.input
        try:
            with open(args.input, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            ap.error("读取文件失败: %s" % exc)
    elif not sys.stdin.isatty():
        source = "<stdin>"
        data = sys.stdin.buffer.read()
    else:
        ap.error("缺少输入：请给文件、--text 或管道 stdin")

    counts, entropy, printable_pct, chi2, top = analyze(data)
    n = len(data)
    verdict = make_verdict(n, entropy, printable_pct)

    if args.json:
        print(json.dumps({
            "source": source,
            "size": n,
            "distinct_bytes": sum(1 for c in counts if c),
            "entropy_bits_per_byte": round(entropy, 6),
            "max_entropy_bits_per_byte": 8.0,
            "printable_pct": round(printable_pct * 100, 4),
            "chi_square_df255": round(chi2, 4) if chi2 is not None else None,
            "top": [["0x%02x" % v, c, round(c / n * 100, 4)] for v, c in top[:args.top]],
            "verdict": verdict,
        }, ensure_ascii=False, indent=2))
        return 0

    print("source: %s" % source)
    print("size: %d bytes" % n)
    print("distinct_bytes: %d / 256" % sum(1 for c in counts if c))
    print("entropy: %.6f bits/byte（上限 8.0 = 均匀随机）" % entropy)
    print("printable_pct: %.2f%%" % (printable_pct * 100))
    if chi2 is not None:
        print("chi_square: %.2f (df=255, 越小越接近均匀分布)" % chi2)
    if args.top and top:
        print("top %d bytes:" % min(args.top, len(top)))
        for v, c in top[:args.top]:
            glyph = chr(v) if 0x20 <= v < 0x7F else "."
            print("  0x%02x %r: %d (%.2f%%)" % (v, glyph, c, (c / n * 100) if n else 0))
    print("verdict: %s" % verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
