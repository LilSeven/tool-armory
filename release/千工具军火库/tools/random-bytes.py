#!/usr/bin/env python3
"""加密随机字节输出 (random-bytes)。

用途:
    用 secrets.token_bytes 批量输出加密安全随机字节, 格式可选:
      hex     每行一串十六进制 (默认)
      base64  每行一段标准 base64
      dec     每行一组空格分隔的十进制字节值 (0..255)
      int     每行一个由这些字节组成的大整数 (大端)
    也可用 --range LOW HIGH 在闭区间 [LOW, HIGH] 内输出加密安全
    随机整数 (基于 secrets.randbelow; 此时忽略 --bytes,
    --format 只能是 int 或不指定)。

退出码: 0=成功, 2=参数错误。

示例:
    python -I random-bytes.py -b 32 -n 3
    python -I random-bytes.py -b 16 -f base64 -n 2
    python -I random-bytes.py -b 8 -f dec
    python -I random-bytes.py -b 8 -f int -n 2
    python -I random-bytes.py --range 1000 9999 -n 5
"""
import argparse
import base64
import secrets
import sys


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="random-bytes",
        description="批量输出加密安全随机字节(hex/base64/dec/int)或区间随机整数。",
    )
    parser.add_argument("-b", "--bytes", dest="nbytes", type=int, default=32,
                        help="每次随机字节数 (默认 32)")
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="输出条数 (默认 1)")
    parser.add_argument("-f", "--format", choices=("hex", "base64", "dec", "int"),
                        default=None,
                        help="输出格式 (默认: hex; --range 模式下默认 int)")
    parser.add_argument("--range", dest="int_range", nargs=2, type=int,
                        metavar=("LOW", "HIGH"),
                        help="输出 [LOW, HIGH] 闭区间内的加密安全随机整数")
    args = parser.parse_args(argv)

    try:
        if args.count < 1:
            raise ValueError("--count 必须 >= 1")
        fmt = args.format or ("int" if args.int_range else "hex")
        if args.int_range:
            low, high = args.int_range
            if low > high:
                raise ValueError("--range 要求 LOW <= HIGH")
            if fmt != "int":
                raise ValueError("--range 模式要求 --format int (或不指定 -f)")
            for _ in range(args.count):
                print(low + secrets.randbelow(high - low + 1))
            return 0
        if args.nbytes < 1:
            raise ValueError("--bytes 必须 >= 1")
        for _ in range(args.count):
            raw = secrets.token_bytes(args.nbytes)
            if fmt == "hex":
                print(raw.hex())
            elif fmt == "base64":
                print(base64.b64encode(raw).decode("ascii"))
            elif fmt == "dec":
                print(" ".join(str(b) for b in raw))
            else:
                print(int.from_bytes(raw, "big"))
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
