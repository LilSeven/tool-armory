#!/usr/bin/env python3
"""currency-symbol-normalize.py — 货币符号规范化工具。

把文本中混用的 ￥（全角 U+FFE5）、¥（半角 U+00A5）、字母代码
RMB/CNY/rmb/cny（独立出现时）以及「数字+元」写法，统一为选定的
标准形式。数字本身保持原样（含全角数字、千分位逗号、小数点）。

三种目标形式（--to）：
  cny        半角 ¥ 前置（默认）：   ￥99 / 100元 / RMB 20 → ¥99 / ¥100 / ¥20
  fullwidth  全角 ￥ 前置：          ￥99 / ￥100 / ￥20
  yuan       「元」后置：            ¥99 / ￥99 / RMB 20  → 99元

示例命令：
  python currency-symbol-normalize.py --to cny --text "售价￥99，共¥1,050，预算5.5元"
  echo "RMB 20；标价100元" | python currency-symbol-normalize.py --to yuan
  python currency-symbol-normalize.py -i in.txt -o out.txt --to fullwidth

保护规则：
  「美元/日元/欧元/港元/人民币」等货币名称不会被改动（「元」前必须
  紧邻数字才视为金额）；「100多元」「几十元」等约数保持原样；
  「元旦」「元首」不受影响；--keep-codes 可保留 RMB/CNY 字母代码。
  --to yuan 时，后面不接数字的孤立 ¥/￥ 保持原样。
"""

import argparse
import re
import sys

YEN = "¥"       # 半角 U+00A5，作为中间统一符号
YEN_FW = "￥"    # 全角 U+FFE5
# 金额数字：半/全角数字开头，允许千分位逗号与小数点，但不以标点结尾
NUM = r"[0-9０-９](?:[0-9０-９,，.．]*[0-9０-９])?"
# 独立字母代码（前后都不是字母才视为货币代码）
CODE = re.compile(r"(?<![A-Za-z])(RMB|CNY|rmb|cny)(?![A-Za-z])")


def normalize(text: str, target: str = "cny", keep_codes: bool = False) -> str:
    if not keep_codes:
        text = CODE.sub(YEN, text)
    yen_class = "[" + re.escape(YEN) + re.escape(YEN_FW) + "]"

    if target == "yuan":
        # ¥100元 → 100元（先消重）；¥100多元 → 100多元（约数保持原样）；
        # ¥100 → 100元；100¥ → 100元
        approx = r"(?=[多几余来來])"
        text = re.sub(yen_class + r"\s*(" + NUM + r")(?=元)", r"\1", text)
        text = re.sub(yen_class + r"\s*(" + NUM + r")" + approx, r"\1", text)
        text = re.sub(yen_class + r"\s*(" + NUM + r")", r"\1元", text)
        text = re.sub("(" + NUM + r")\s*" + yen_class, r"\1元", text)
        return text

    sym = YEN if target == "cny" else YEN_FW
    # ¥100元 → ¥100（去掉重复的元）
    text = re.sub("(" + yen_class + r"\s*" + NUM + r")\s*元", r"\1", text)
    # 100元 / 100￥ → ¥100（「元」前必须紧邻数字；货币名如「美元」不受影响）
    text = re.sub(r"(?<![0-9０-９￥¥])(" + NUM + r")\s*" + yen_class, sym + r"\1", text)
    text = re.sub(r"(?<![0-9０-９￥¥])(" + NUM + r")\s*元", sym + r"\1", text)
    # 符号统一：紧跟数字时吃掉其后空格；孤立符号也统一为目标形式
    text = re.sub(yen_class + r"[ \t]*(?=[0-9０-９])", sym, text)
    text = re.sub(yen_class, sym, text)
    return text


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="货币符号规范化：￥/¥/RMB/元 → 选定标准形式")
    p.add_argument("-t", "--text", help="直接转换该段文本")
    p.add_argument("-i", "--input", help="从文件读取（默认按 --encoding 解码）")
    p.add_argument("-o", "--output", help="写出文件（默认打印到 stdout）")
    p.add_argument("--encoding", default="utf-8-sig",
                   help="输入文件编码，默认 utf-8-sig（自动去 BOM）")
    p.add_argument("--to", choices=["cny", "fullwidth", "yuan"], default="cny",
                   help="目标形式：cny=¥前置（默认），fullwidth=￥前置，yuan=N元后置")
    p.add_argument("--keep-codes", action="store_true",
                   help="保留 RMB/CNY 等字母代码不转换")
    args = p.parse_args(argv)

    if args.text is not None:
        text = args.text
    elif args.input:
        with open(args.input, "r", encoding=args.encoding, errors="replace") as f:
            text = f.read()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        raise SystemExit("未提供输入：请用 --text、--input 或管道传入文本")

    result = normalize(text, target=args.to, keep_codes=args.keep_codes)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
    else:
        sys.stdout.write(result)
        if not result.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
