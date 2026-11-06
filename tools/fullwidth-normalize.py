#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全角字母数字转半角 (fullwidth-normalize)。

把全角字母数字 (ＡＢＣ１２３) 及全角符号 (＠＃＄％…) 统一转为半角,
同时保留真正的全角标点。纯标准库实现。

处理范围与规则:
  - U+3000 全角空格          -> 半角空格
  - U+FF01~U+FF5E 中的字母、数字、符号 -> 经 NFKC 转半角
    (Ａ→A, １→1, ＠→@, ＄→$, ＋→+, ～→~ …)
  - 以下全角标点原样保留 (汉字排版惯用):
    ！＂＇（），．：；? 以及区外的 、。·《》「」【】等
    (后者在 U+3000~U+303F 等区间, 本工具不做任何改动)

用法:
    python fullwidth-normalize.py [文件...] [-i]

示例命令:
    python fullwidth-normalize.py note.txt
    echo "ＡＢＣ１２３" | python fullwidth-normalize.py -
    python fullwidth-normalize.py -i note.txt

退出码: 0 = 成功; 2 = 读文件失败。
"""

import argparse
import sys
import unicodedata

# U+FF01~U+FF5E 内保留原样的全角标点 (真正的全角标点)
_KEEP = set("！＂＇（），．：；？")


def normalize_char(ch):
    o = ord(ch)
    if o == 0x3000:  # 全角空格
        return " "
    if 0xFF01 <= o <= 0xFF5E:  # 全角形式区
        if ch in _KEEP:
            return ch
        return unicodedata.normalize("NFKC", ch)
    return ch


def normalize(text):
    return "".join(normalize_char(c) for c in text)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="全角字母数字与符号转半角, 保留全角标点")
    ap.add_argument("paths", nargs="*", default=[],
                    help="输入文件; 省略或 '-' 表示 stdin")
    ap.add_argument("-i", "--in-place", action="store_true",
                    help="就地改写文件")
    args = ap.parse_args(argv)

    paths = args.paths or ["-"]
    if args.in_place and paths == ["-"]:
        print("错误: -i 需要指定文件", file=sys.stderr)
        return 2

    rc = 0
    for p in paths:
        try:
            if p == "-":
                data = sys.stdin.buffer.read()
            else:
                with open(p, "rb") as fh:
                    data = fh.read()
        except OSError as exc:
            print(f"错误: 无法读取 {p}: {exc}", file=sys.stderr)
            rc = 2
            continue
        out = normalize(data.decode("utf-8", errors="replace"))
        if args.in_place:
            try:
                with open(p, "wb") as fh:
                    fh.write(out.encode("utf-8"))
            except OSError as exc:
                print(f"错误: 无法写入 {p}: {exc}", file=sys.stderr)
                rc = 2
        else:
            sys.stdout.write(out)
            if not out.endswith("\n"):
                sys.stdout.write("\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
