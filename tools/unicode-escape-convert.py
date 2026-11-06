#!/usr/bin/env python3
"""unicode-escape-convert 转义序列转换：把 \\uXXXX 转义形式的文本与真实
Unicode 字符互转（如 \\u4f60 → 你）。

用法:
  python unicode-escape-convert.py <输入> [-o 输出] --to text|escape [--encoding utf-8]
  cat in.txt | python unicode-escape-convert.py --to text     # 无输入文件时读 stdin

示例:
  python unicode-escape-convert.py escaped.txt --to text -o readable.txt
  echo -n "你好" | python unicode-escape-convert.py --to escape

说明:
  - --to text：把 \\uXXXX / \\UXXXXXXXX 转义还原为真实字符；\"\\\\u4f60\" 会还原成
    字面 \\u4f60（先处理 \\\\ 转义，保证双向无损）。
  - --to escape：非 ASCII 字符转为 \\uXXXX（BMP 外字符用代理对），ASCII 保持
    原样，反斜杠转义为 \\\\，因此 encode→decode 可以无损往返。
  - 输入按 --encoding 解码（默认 utf-8），输出文件同样按该编码写出。
"""

import argparse
import re
import sys

RE_U = re.compile(r"\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})")


def _unescape(match):
    if match.group(1) is not None:
        return chr(int(match.group(1), 16))
    return chr(int(match.group(2), 16))


def _combine_surrogates(s: str) -> str:
    """把相邻的高/低代理码点合并为 BMP 外的真实字符。"""
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if 0xD800 <= ord(c) <= 0xDBFF and i + 1 < len(s) and 0xDC00 <= ord(s[i + 1]) <= 0xDFFF:
            out.append(chr(0x10000 + ((ord(c) - 0xD800) << 10) + (ord(s[i + 1]) - 0xDC00)))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def to_text(s: str) -> str:
    # 先保护 \\ 为占位符，避免 \\\\u0041 被误解
    placeholder = "\x00"
    s = s.replace("\\\\", placeholder)
    s = RE_U.sub(_unescape, s)
    s = _combine_surrogates(s)
    return s.replace(placeholder, "\\")


def _escape_char(ch):
    cp = ord(ch)
    if ch == "\\":
        return "\\\\"
    if 0x20 <= cp < 0x7F:
        return ch
    if cp <= 0xFFFF:
        return "\\u%04x" % cp
    # BMP 外字符拆成代理对，与常见 \\u 写法一致
    cp -= 0x10000
    hi, lo = 0xD800 + (cp >> 10), 0xDC00 + (cp & 0x3FF)
    return "\\u%04x\\u%04x" % (hi, lo)


def to_escape(s: str) -> str:
    return "".join(_escape_char(c) for c in s)


def main(argv=None):
    ap = argparse.ArgumentParser(description="\\uXXXX 转义与真实 Unicode 字符互转")
    ap.add_argument("input", nargs="?", default="", help="输入文件；缺省读 stdin")
    ap.add_argument("-o", "--output", default="", help="输出文件；缺省写 stdout")
    ap.add_argument("--to", required=True, choices=["text", "escape"], dest="mode",
                    help="text=转义还原为字符；escape=字符转为 \\uXXXX")
    ap.add_argument("--encoding", default="utf-8", help="文件读写编码（默认 utf-8）")
    args = ap.parse_args(argv)

    if args.input:
        try:
            text = open(args.input, "r", encoding=args.encoding).read()
        except (OSError, UnicodeDecodeError) as e:
            print(f"读取失败 {args.input}: {e}", file=sys.stderr)
            return 1
    else:
        text = sys.stdin.buffer.read().decode(args.encoding, errors="replace")

    result = to_text(text) if args.mode == "text" else to_escape(text)

    if args.output:
        try:
            open(args.output, "w", encoding=args.encoding).write(result)
        except OSError as e:
            print(f"写入失败 {args.output}: {e}", file=sys.stderr)
            return 1
    else:
        sys.stdout.reconfigure(encoding=args.encoding, errors="replace")
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
