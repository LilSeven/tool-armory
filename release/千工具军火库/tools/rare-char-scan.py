#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生僻字扫描 —— 扫描文本中的生僻字、扩展区汉字与字体易缺字字符，生成替换确认清单。

判定口径（纯标准库启发式，无需联网与字库）
  · 私有区 PUA（U+E000~F8FF）        依赖特定字体，排版必查；
  · 扩展区汉字（扩展 A、B~H 区）      常见字体易缺字，优先确认；
  · 兼容表意区（U+F900~FAFF）        易缺字，且应优先换成基本区规范字；
  · 部首/部件区（U+2E80~2FDF）       属构件，不应作正文字符；
  · 基本区汉字以「是否在 GB2312 内」为生僻启发式：
    GB2312 外的基本区汉字（如人名用字 镕/堃/喆 等）列为待确认生僻字。
输出清单：字符、码位、分类、出现次数、首次出现上下文，便于排版前替换确认。

用法
  python rare-char-scan.py draft.txt
  python rare-char-scan.py draft.txt --json
  python rare-char-scan.py draft.txt --encoding gb18030
  python rare-char-scan.py draft.txt --strict    # 发现待确认字符时退出码为 1
  cat draft.txt | python rare-char-scan.py -

仅用 Python 标准库。
"""

import argparse
import json
import sys

CJK_RANGES = (
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF), (0x2A700, 0x2B739), (0x2B740, 0x2B81D),
    (0x2B820, 0x2CEA1), (0x2CEB0, 0x2EBE0), (0x2EBF0, 0x2EE5D),
    (0x30000, 0x3134A), (0x31350, 0x323AF),
)
CAT_ORDER = (
    "私有区(PUA)·排版必查",
    "扩展B~H区·易缺字",
    "扩展A区·易缺字",
    "兼容表意区·易缺字",
    "部首部件区·勿作正文",
    "基本区·GB2312外(生僻待确认)",
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


def classify(ch):
    """返回分类名（未命中返回 None）。"""
    o = ord(ch)
    if 0xE000 <= o <= 0xF8FF:
        return "私有区(PUA)·排版必查"
    if 0x20000 <= o <= 0x323AF:
        return "扩展B~H区·易缺字"
    if 0x3400 <= o <= 0x4DBF:
        return "扩展A区·易缺字"
    if 0xF900 <= o <= 0xFAFF:
        return "兼容表意区·易缺字"
    if 0x2E80 <= o <= 0x2FDF:
        return "部首部件区·勿作正文"
    if 0x4E00 <= o <= 0x9FFF:
        try:
            ch.encode("gb2312")
        except (UnicodeEncodeError, LookupError):
            return "基本区·GB2312外(生僻待确认)"
        return None
    return None


def scan(text):
    found = {}
    for idx, ch in enumerate(text):
        cat = classify(ch)
        if cat is None:
            continue
        rec = found.setdefault(ch, {"cat": cat, "count": 0, "first": idx})
        rec["count"] += 1
    return found


def make_context(text, idx, ch, width=10):
    before = text[max(0, idx - width):idx].replace("\r", " ").replace("\n", " ")
    after = text[idx + 1: idx + 1 + width].replace("\r", " ").replace("\n", " ")
    return f"…{before}[{ch}]{after}…"


def main(argv=None):
    _setup_stdio()
    p = argparse.ArgumentParser(description="生僻字/扩展区汉字/字体易缺字字符扫描清单")
    p.add_argument("input", help="文本文件路径，- 表示标准输入")
    p.add_argument("--encoding", help="输入编码（缺省自动探测 utf-8/gb18030）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    p.add_argument("--strict", action="store_true",
                   help="发现待确认字符时退出码置 1（用于流水线卡点）")
    args = p.parse_args(argv)

    try:
        if args.input == "-":
            text = sys.stdin.read()
        else:
            text = decode_auto(read_bytes(args.input), args.encoding)
    except OSError as e:
        print(f"错误: 无法读取输入: {e}", file=sys.stderr)
        return 1
    except (UnicodeDecodeError, LookupError) as e:
        print(f"错误: 解码失败: {e}", file=sys.stderr)
        return 1

    found = scan(text)
    rows = sorted(found.items(),
                  key=lambda kv: (CAT_ORDER.index(kv[1]["cat"]), -kv[1]["count"], ord(kv[0])))
    han_total = sum(1 for ch in text if is_han(ch))

    if args.json:
        print(json.dumps({
            "total_chars": len(text),
            "han_chars": han_total,
            "findings": [
                {"char": ch, "codepoint": f"U+{ord(ch):04X}", "category": r["cat"],
                 "count": r["count"], "context": make_context(text, r["first"], ch)}
                for ch, r in rows
            ],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"扫描完成: 全文 {len(text):,} 字符，汉字 {han_total:,}，待确认字符 {len(found):,} 种")
        if found:
            by_cat = {}
            for r in found.values():
                by_cat[r["cat"]] = by_cat.get(r["cat"], 0) + 1
            summary = "；".join(f"{c} {n} 种"
                                for c, n in sorted(by_cat.items(), key=lambda kv: CAT_ORDER.index(kv[0])))
            print(f"分类汇总: {summary}")
            print()
            print(f"{'字':<4}{'码位':<10}{'分类':<26}{'次数':>4}  上下文")
            for ch, r in rows:
                print(f"{ch:<4}U+{ord(ch):04X}  {r['cat']:<24}{r['count']:>5}  "
                      f"{make_context(text, r['first'], ch)}")
        print("\n说明: 分类为启发式口径；GB2312 外基本区汉字不一定是错字，请人工确认后替换或造字。")
    return 1 if (args.strict and found) else 0


if __name__ == "__main__":
    sys.exit(main())
