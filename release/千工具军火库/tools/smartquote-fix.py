#!/usr/bin/env python3
"""引号规范化(smartquote-fix)

把中文弯引号(“”‘’)、英文智能引号(curly quotes)与直引号(' ")按目标风格统一。

用法:
  python smartquote-fix.py <输入文件> [-o 输出文件] [--style curly|straight|cn|en]

风格说明:
  curly  统一为弯引号 “ ” ‘ ’(中文/排版常用)
  straight 统一为直引号 " '(英文纯文本常用)
  cn     中文风格:双引号“”,单引号‘’(按配对处理)
  en     英文风格:双引号 " ",单引号 ' '(按配对处理)

示例:
  python smartquote-fix.py in.txt --style cn -o out.txt
  python smartquote-fix.py in.txt --style straight
不指定 -o 时输出到 stdout。
"""
import argparse
import sys

# Windows 控制台/管道默认 GBK,强制 UTF-8
for _s in (sys.stdout, sys.stderr, sys.stdin):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", newline="")

# 各类引号集合
CURLY = {"\u201c": "\u201d", "\u2018": "\u2019"}  # “” ‘’
STRAIGHT_D = '"'
STRAIGHT_S = "'"
# 中文弯引号与英文弯引号码点相同,仅按“风格目标”区分输出
CN_MAP = {"cn_d_open": "\u201c", "cn_d_close": "\u201d",
          "cn_s_open": "\u2018", "cn_s_close": "\u2019"}


def _pair_quotes(text, open_q, close_q, single_open, single_close):
    """把所有引号(双/单)按出现顺序配对:奇数个->open,偶数个->close。"""
    out = []
    d_count = 0
    s_count = 0
    for ch in text:
        if ch in ('\u201c', '\u201d', '"'):
            out.append(open_q if d_count % 2 == 0 else close_q)
            d_count += 1
        elif ch in ('\u2018', '\u2019', "'"):
            out.append(single_open if s_count % 2 == 0 else single_close)
            s_count += 1
        else:
            out.append(ch)
    return ''.join(out)


def normalize(text, style):
    if style == 'curly':
        # 直引号 -> 弯引号(按配对); 弯引号保持
        return _pair_quotes(text, CN_MAP["cn_d_open"], CN_MAP["cn_d_close"],
                            CN_MAP["cn_s_open"], CN_MAP["cn_s_close"])
    if style == 'straight':
        # 弯引号 -> 直引号
        table = str.maketrans({
            '\u201c': STRAIGHT_D, '\u201d': STRAIGHT_D,
            '\u2018': STRAIGHT_S, '\u2019': STRAIGHT_S,
        })
        return text.translate(table)
    if style == 'cn':
        return _pair_quotes(text, CN_MAP["cn_d_open"], CN_MAP["cn_d_close"],
                            CN_MAP["cn_s_open"], CN_MAP["cn_s_close"])
    if style == 'en':
        return _pair_quotes(text, STRAIGHT_D, STRAIGHT_D,
                            STRAIGHT_S, STRAIGHT_S)
    raise ValueError("未知风格: %s" % style)


def main(argv=None):
    ap = argparse.ArgumentParser(description="引号风格统一工具")
    ap.add_argument("input", help="输入文件,缺省读 stdin")
    ap.add_argument("-o", "--output", help="输出文件,缺省 stdout")
    ap.add_argument("--style", choices=["curly", "straight", "cn", "en"],
                    default="curly", help="目标风格(默认 curly)")
    args = ap.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = normalize(text, args.style)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(result)
        print("已写入: %s" % args.output, file=sys.stderr)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
