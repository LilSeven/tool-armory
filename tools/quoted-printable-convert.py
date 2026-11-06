#!/usr/bin/env python3
"""quoted-printable-convert Quoted-Printable 转换：用标准库 quopri 在 QP 编码
文本（邮件正文常见）与原文之间互转。

用法:
  python quoted-printable-convert.py <输入> [-o 输出] --to encode|decode
  cat mail.txt | python quoted-printable-convert.py --to decode   # 无输入文件时读 stdin

示例:
  python quoted-printable-convert.py mail.txt --to decode -o plain.txt
  python quoted-printable-convert.py plain.txt --to encode

说明:
  - 在字节层面用 quopri.encodestring / decodestring 处理，不关心字符集，
    因此 GBK/UTF-8 邮件正文都能正确往返。
  - encode 默认不强制空格转义（quotetabs=False），与邮件正文习惯一致；
    末尾软换行 =\\r\\n 等 QP 规则由 quopri 标准实现处理。
"""

import argparse
import quopri
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description="Quoted-Printable 编码/解码（基于 quopri）")
    ap.add_argument("input", nargs="?", default="", help="输入文件；缺省读 stdin")
    ap.add_argument("-o", "--output", default="", help="输出文件；缺省写 stdout")
    ap.add_argument("--to", required=True, choices=["encode", "decode"], dest="mode",
                    help="encode=原文转 QP；decode=QP 还原为原文")
    args = ap.parse_args(argv)

    if args.input:
        try:
            data = open(args.input, "rb").read()
        except OSError as e:
            print(f"读取失败 {args.input}: {e}", file=sys.stderr)
            return 1
    else:
        data = sys.stdin.buffer.read()

    if args.mode == "encode":
        result = quopri.encodestring(data, quotetabs=False)
    else:
        result = quopri.decodestring(data)

    if args.output:
        try:
            open(args.output, "wb").write(result)
        except OSError as e:
            print(f"写入失败 {args.output}: {e}", file=sys.stderr)
            return 1
    else:
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
