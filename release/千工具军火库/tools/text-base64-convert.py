#!/usr/bin/env python3
"""文本 Base64 转换 —— 按指定字符集编码读写文本文件的 Base64 编解码工具。

与二进制 Base64 工具不同：本工具按字符集分三段处理，三个字符集各管一段：
  --in-encoding   输入文件字节的解读字符集（默认 utf-8）
  --text-encoding Base64 内 payload 字节的字符集（默认 utf-8）
      encode: 输入字节 --按 in-encoding 解码--> 文本 --按 text-encoding 编码--> payload --Base64--> 输出
      decode: 输入 --Base64 解码--> payload --按 text-encoding 解码--> 文本 --按 out-encoding 编码--> 输出字节
  --out-encoding  decode 输出文件的落盘字符集（默认跟随 --text-encoding）
三个字符集一致时（如全 utf-8，或全 gbk）即为无损往返。

用法：
  python text-base64-convert.py encode -i in.txt -o out.b64
  python text-base64-convert.py decode -i out.b64 -o back.txt
  python text-base64-convert.py encode --text "你好, 世界"        # 直接处理命令行文本
  echo "aGk=" | python text-base64-convert.py decode              # stdin/stdout 流式

示例命令（每组两行按原样执行即可无损往返，还原文件与原文件 cmp 一致）：
  # GBK 文件，payload 也保持 GBK 字节（等效于对原文件做二进制 Base64）：
  python text-base64-convert.py encode -i gbk.txt -o gbk.b64 --in-encoding gbk --text-encoding gbk
  python text-base64-convert.py decode -i gbk.b64 -o gbk-back.txt --text-encoding gbk
  # GBK 文件，payload 转成 UTF-8 字节（便于跨系统传输），decode 时再转回 GBK 落盘：
  python text-base64-convert.py encode -i gbk.txt -o u8.b64 --in-encoding gbk
  python text-base64-convert.py decode -i u8.b64 -o gbk-back.txt --text-encoding utf-8 --out-encoding gbk

选项：
  encode|decode           子命令（必选）
  -i, --input PATH        输入文件；缺省读 stdin
  -o, --output PATH       输出文件；缺省写 stdout
  --text STR              直接处理该字符串（忽略 -i）
  --in-encoding ENC       输入文件解码用字符集（默认 utf-8）
  --text-encoding ENC     Base64 内 payload 字节的字符集（默认 utf-8）
  --out-encoding ENC      decode 输出落盘字符集（默认跟随 --text-encoding）
  -w, --wrap N            encode 时每 N 字符换行（默认 76，0 表示不换行）
  --errors MODE           编解码错误处理：strict/replace/ignore（默认 replace）
"""

import argparse
import base64
import sys
import textwrap


def _read_text(path: str, enc: str, errors: str) -> str:
    if path is None:
        data = sys.stdin.buffer.read()
    else:
        with open(path, "rb") as f:
            data = f.read()
    return data.decode(enc, errors)


def _write_text(path: str, text: str, enc: str, errors: str) -> None:
    data = text.encode(enc, errors)
    if path is None:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    else:
        with open(path, "wb") as f:
            f.write(data)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="text-base64-convert",
        description="按指定字符集对文本文件做 Base64 编解码",
    )
    sub = p.add_subparsers(dest="mode", required=True)
    for name in ("encode", "decode"):
        sp = sub.add_parser(name)
        sp.add_argument("-i", "--input", help="输入文件，缺省读 stdin")
        sp.add_argument("-o", "--output", help="输出文件，缺省写 stdout")
        sp.add_argument("--text", help="直接处理该字符串")
        sp.add_argument("--in-encoding", default="utf-8", metavar="ENC",
                        help="输入文件解码用字符集（默认 utf-8）")
        sp.add_argument("--text-encoding", default="utf-8", metavar="ENC",
                        help="Base64 内 payload 字节的字符集（默认 utf-8）")
        sp.add_argument("--out-encoding", default=None, metavar="ENC",
                        help="decode 输出落盘字符集（默认跟随 --text-encoding）")
        sp.add_argument("-w", "--wrap", type=int, default=76,
                        help="encode 每行字符数（0=不换行），默认 76")
        sp.add_argument("--errors", default="replace",
                        choices=["strict", "replace", "ignore"])
    a = p.parse_args(argv)

    errors = a.errors
    if a.mode == "encode":
        if a.text is not None:
            text = a.text
        else:
            text = _read_text(a.input, a.in_encoding, errors)
        payload = text.encode(a.text_encoding, errors)
        b64 = base64.b64encode(payload).decode("ascii")
        if a.wrap and a.wrap > 0:
            b64 = "\n".join(textwrap.wrap(b64, a.wrap)) + "\n"
        _write_text(a.output, b64, "ascii", "strict")
    else:
        raw = a.text if a.text is not None else _read_text(a.input, a.in_encoding, errors)
        compact = "".join(raw.split())  # 去掉换行与空白
        try:
            payload = base64.b64decode(compact, validate=True)
        except Exception as e:
            print(f"error: Base64 解码失败: {e}", file=sys.stderr)
            return 1
        # payload 按 --text-encoding 解码为文本，再按 --out-encoding（缺省跟随
        # --text-encoding）落盘；缺省时两者相同，即为无损往返
        out_enc = a.out_encoding or a.text_encoding
        _write_text(a.output, payload.decode(a.text_encoding, errors),
                    out_enc, errors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
