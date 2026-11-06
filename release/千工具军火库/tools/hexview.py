#!/usr/bin/env python3
"""十六进制查看：输出文件的 hex dump 视图（偏移 + 十六进制 + ASCII 栏）。

每行显示起始偏移、十六进制字节与可打印 ASCII，不可打印字符显示为 '.'。

用法:
    python hexview.py file.bin
    python hexview.py file.bin --start 16 --length 64
    python hexview.py file.bin --width 32
    python hexview.py --offset-dec file.bin    # 显示十进制偏移

示例命令:
    python hexview.py data.bin -w 8
    python hexview.py hello.txt --start 0 --length 32 --offset-hex
"""
import argparse
import sys

PRINTABLE = set(range(0x20, 0x7F))


def dump(data: bytes, width: int, base: int, offset_hex: bool) -> str:
    lines = []
    hexw = width * 3 - 1
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        offset = base + i
        off = f"{offset:08X}" if offset_hex else f"{offset:08d}"
        hexpart = " ".join(f"{b:02X}" for b in chunk)
        hexpart = hexpart.ljust(hexw)
        asciipart = "".join(chr(b) if b in PRINTABLE else "." for b in chunk)
        lines.append(f"{off}  {hexpart}  |{asciipart}|")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="输出文件的 hex dump 视图")
    ap.add_argument("file", help="输入文件；'-' 表示 stdin")
    ap.add_argument("-s", "--start", type=int, default=0,
                    help="起始字节偏移（默认 0）")
    ap.add_argument("-n", "--length", type=int, default=None,
                    help="最多显示的字节数（默认全部）")
    ap.add_argument("-w", "--width", type=int, default=16,
                    help="每行字节数（默认 16）")
    og = ap.add_mutually_exclusive_group()
    og.add_argument("--offset-hex", dest="offset_mode", action="store_const",
                    const="hex", default="hex",
                    help="偏移用十六进制显示（默认）")
    og.add_argument("-o", "--offset-dec", dest="offset_mode",
                    action="store_const", const="dec",
                    help="偏移用十进制显示")
    args = ap.parse_args()

    if args.width < 1 or args.width > 256:
        print("错误: --width 须在 1..256", file=sys.stderr)
        return 2
    if args.start < 0:
        print("错误: --start 不能为负", file=sys.stderr)
        return 2

    if args.file == "-":
        data = sys.stdin.buffer.read()
    else:
        try:
            with open(args.file, "rb") as f:
                data = f.read()
        except OSError as e:
            print(f"错误: 无法读取 {args.file}: {e}", file=sys.stderr)
            return 1

    data = data[args.start:]
    if args.length is not None:
        if args.length < 0:
            print("错误: --length 不能为负", file=sys.stderr)
            return 2
        data = data[:args.length]

    out = dump(data, args.width, args.start, args.offset_mode == "hex")
    if out:
        print(out)
    else:
        print("(空输入，无字节可显示)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
