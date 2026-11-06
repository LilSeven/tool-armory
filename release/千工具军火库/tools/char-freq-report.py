#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字频统计报告 —— 统计文本中汉字出现频率并输出 Top N 列表。

功能
  · 统计全部 CJK 表意文字（含扩展区）出现频次；
  · 按频次降序输出 Top N：排名、汉字、次数、占比、累计占比；
  · 可选 --baseline 提供通用字频基准表，输出「超用字/欠用字」偏差榜
    （偏差按万分率计，并给出观察/基准倍数），
    另列出基准表未收录的被观察字。

基准表格式（每行一条，# 开头为注释）
  字<TAB>次数          整数次数，按基准总量折算频率；
  字<TAB>占比小数      0~1 的小数占比（自动识别：总和 >1.5 或全为整数按次数口径）。

用法
  python char-freq-report.py novel.txt --top 50
  python char-freq-report.py novel.txt --baseline freq.tsv --top 20
  python char-freq-report.py novel.txt --json
  cat novel.txt | python char-freq-report.py -

基准表示例（freq.tsv）
  的	10
  一	3
  是	2

仅用 Python 标准库。
"""

import argparse
import json
import sys
from collections import Counter

CJK_RANGES = (
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF), (0x2A700, 0x2B739), (0x2B740, 0x2B81D),
    (0x2B820, 0x2CEA1), (0x2CEB0, 0x2EBE0), (0x2EBF0, 0x2EE5D),
    (0x30000, 0x3134A), (0x31350, 0x323AF),
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


def load_baseline(path):
    """返回 {字: 每字出现概率}；口径自动识别。"""
    table = {}
    for raw in decode_auto(read_bytes(path)).splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.replace("\t", " ").split()
        if len(parts) < 2 or len(parts[0]) != 1:
            continue
        try:
            v = float(parts[1])
        except ValueError:
            continue
        table[parts[0]] = table.get(parts[0], 0.0) + v
    if not table:
        return {}
    total = sum(table.values())
    if total > 1.5 or all(float(v).is_integer() for v in table.values()):
        return {ch: v / total for ch, v in table.items()}
    return dict(table)


def main(argv=None):
    _setup_stdio()
    p = argparse.ArgumentParser(description="字频统计报告（Top N + 可选通用字频基准偏差）")
    p.add_argument("input", help="文本文件路径，- 表示标准输入")
    p.add_argument("--top", type=int, default=50, help="输出前 N 名（默认 50）")
    p.add_argument("--baseline", help="通用字频基准表路径（每行：字<TAB>次数 或 字<TAB>占比小数）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出 Top N")
    args = p.parse_args(argv)

    try:
        text = sys.stdin.read() if args.input == "-" else decode_auto(read_bytes(args.input), None)
    except OSError as e:
        print(f"错误: 无法读取输入: {e}", file=sys.stderr)
        return 1
    except UnicodeDecodeError as e:
        print(f"错误: 解码失败: {e}", file=sys.stderr)
        return 1

    counts = Counter(ch for ch in text if is_han(ch))
    total = sum(counts.values())
    if total == 0:
        print("未发现汉字，无法统计。", file=sys.stderr)
        return 1

    top = counts.most_common(args.top)
    if args.json:
        print(json.dumps({
            "total_han": total,
            "distinct": len(counts),
            "top": [{"char": ch, "count": c, "percent": round(c / total * 100, 4)}
                    for ch, c in top],
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"总汉字数: {total:,}    不同汉字: {len(counts):,}    展示 Top {min(args.top, len(counts))}")
    print(f"{'排名':>4}  字  {'次数':>8}  {'占比':>8}  {'累计':>8}")
    cum = 0.0
    for i, (ch, c) in enumerate(top, 1):
        pct = c / total * 100
        cum += pct
        print(f"{i:>5}  {ch}  {c:>9,}  {pct:>7.2f}%  {cum:>7.2f}%")

    if args.baseline:
        base = load_baseline(args.baseline)
        print()
        if not base:
            print("警告: 基准表为空或无法解析，跳过偏差分析。", file=sys.stderr)
        else:
            rows = []
            for ch, c in counts.items():
                b = base.get(ch)
                if not b:
                    continue
                obs = c / total * 10000
                exp = b * 10000
                rows.append((ch, c, obs, exp, obs - exp, obs / exp))
            over = sorted((r for r in rows if r[4] > 0), key=lambda r: -r[4])[:args.top]
            under = sorted((r for r in rows if r[4] < 0), key=lambda r: r[4])[:args.top]
            print(f"与基准表偏差（万分率口径；基准 {len(base):,} 字，可比对 {len(rows):,} 字）")
            for title, rs in (("超用最多", over), ("欠用最多", under)):
                print(f"  —— {title} ——")
                if not rs:
                    print("    （无）")
                for ch, c, obs, exp, diff, ratio in rs:
                    print(f"    {ch}  观察 {obs:>8.1f}  基准 {exp:>8.1f}  "
                          f"偏差 {diff:>+9.1f}  倍数 {ratio:>7.2f}x")
            new = sorted(((ch, c) for ch, c in counts.items() if ch not in base),
                         key=lambda kv: -kv[1])
            if new:
                show = ", ".join(f"{ch}×{c}" for ch, c in new[:10])
                print(f"  基准未收录字 {len(new):,} 个，按频次示例: {show}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
