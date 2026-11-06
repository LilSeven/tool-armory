#!/usr/bin/env python3
"""按字节序列分隔符拆二进制文件。

用给定的字节序列分隔符（如 \\x00 或固定魔数）把二进制文件切成多条记录，
每条记录写为一个文件。支持 \\xNN 转义、十六进制串两种分隔符写法。

用法:
    python split-binary-separator.py IN.bin -o outdir/ --sep "\\x00"
    python split-binary-separator.py IN.bin -o outdir/ --hex 00ffab
    python split-binary-separator.py IN.bin -o outdir/ --sep "MAGIC" --keep-empty

示例:
    python split-binary-separator.py blob.bin -o recs/ --sep "\\x00\\x00"
    python split-binary-separator.py blob.bin -o recs/ --hex DEADBEEF --prefix part --ext dat

说明:
    - --sep 接受 Python 风格转义（\\x00、\\n、\\t 等）或普通 ASCII 文本；
      --hex 接受纯十六进制字符串（长度须为偶数）。两者互斥。
    - 默认丢弃空记录；分隔符出现在文件末尾产生的尾部空串也被丢弃。
    - 输出文件按序号命名: prefix_0001.ext。
只使用 Python 标准库。
"""

import argparse
import os
import sys


def parse_sep(args):
    if bool(args.sep) == bool(args.hex):
        raise SystemExit("error: 必须且只能指定 --sep 或 --hex 之一")
    if args.hex is not None:
        h = args.hex.strip().lower()
        if h.startswith("0x"):
            h = h[2:]
        if len(h) == 0 or len(h) % 2 != 0 or not all(c in "0123456789abcdef" for c in h):
            raise SystemExit("error: --hex 必须是偶数长度的十六进制串")
        return bytes.fromhex(h)
    raw = args.sep
    try:
        # 解码 \xNN、\n、\t 等转义，再按 latin-1 还原为字节
        return raw.encode("latin-1", "backslashreplace").decode(
            "unicode_escape").encode("latin-1")
    except (UnicodeDecodeError, UnicodeEncodeError) as e:
        raise SystemExit("error: 无法解析 --sep %r: %s" % (raw, e))


def main(argv=None):
    ap = argparse.ArgumentParser(description="按字节序列分隔符拆二进制文件")
    ap.add_argument("input", help="输入二进制文件")
    ap.add_argument("-o", "--outdir", required=True, help="输出目录")
    ap.add_argument("--sep", default=None,
                    help=r'分隔符，支持转义如 "\x00" 或普通文本如 "MAGIC"')
    ap.add_argument("--hex", default=None, help="分隔符的十六进制串，如 00ff")
    ap.add_argument("--prefix", default="record", help="输出文件名前缀")
    ap.add_argument("--ext", default="bin", help="输出文件扩展名")
    ap.add_argument("--keep-empty", action="store_true",
                    help="保留空记录（默认丢弃）")
    args = ap.parse_args(argv)

    sep = parse_sep(args)
    if not os.path.isfile(args.input):
        print("error: 输入文件不存在: %s" % args.input, file=sys.stderr)
        return 2
    with open(args.input, "rb") as f:
        data = f.read()

    chunks = data.split(sep)
    if not chunks:  # data 为空时 split 返回 [b'']
        chunks = [b""]
    # data 以分隔符结尾时会产生尾部空串，丢弃
    if chunks and chunks[-1] == b"":
        chunks.pop()

    os.makedirs(args.outdir, exist_ok=True)
    width = max(4, len(str(len(chunks))))
    written = 0
    for i, chunk in enumerate(chunks, 1):
        if chunk == b"" and not args.keep_empty:
            continue
        name = "%s_%0*d.%s" % (args.prefix, width, i, args.ext)
        path = os.path.join(args.outdir, name)
        with open(path, "wb") as f:
            f.write(chunk)
        written += 1
        print("wrote %-40s bytes=%d" % (name, len(chunk)))
    print("separator: %s | records written: %d (dropped empty: %d) -> %s" % (
        sep.hex() or "(empty)", written, len(chunks) - written, args.outdir))
    if sep == b"":
        print("warning: 分隔符为空串，结果可能等于原样输出", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
