#!/usr/bin/env python3
"""随机令牌生成 (token-gen)。

用途:
    基于 secrets.token_hex / secrets.token_urlsafe 生成加密安全随机
    API token, 可指定字节数与数量, 可加固定前缀。
    hex 格式: token_hex(n) -> 2n 个十六进制字符;
    urlsafe 格式: token_urlsafe(n) -> 约 4n/3 个 URL 安全 base64 字符。

退出码: 0=成功, 2=参数错误。

示例:
    python -I token-gen.py                            # 1 个 32 字节 hex token
    python -I token-gen.py -n 5 -b 32                 # 5 个 32 字节 hex token
    python -I token-gen.py -n 3 -b 32 -f urlsafe      # urlsafe(base64url) 格式
    python -I token-gen.py -n 2 -b 16 --prefix "sk_live_"
"""
import argparse
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
        prog="token-gen",
        description="用 secrets 生成加密安全随机 API token。",
    )
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="生成数量 (默认 1)")
    parser.add_argument("-b", "--bytes", dest="nbytes", type=int, default=32,
                        help="每个 token 的随机字节数 (默认 32)")
    parser.add_argument("-f", "--format", choices=("hex", "urlsafe"),
                        default="hex",
                        help="编码格式: hex=token_hex, urlsafe=token_urlsafe (默认 hex)")
    parser.add_argument("--prefix", default="", help="每个 token 的固定前缀")
    args = parser.parse_args(argv)

    if args.count < 1:
        print("错误: --count 必须 >= 1", file=sys.stderr)
        return 2
    if args.nbytes < 1:
        print("错误: --bytes 必须 >= 1", file=sys.stderr)
        return 2

    for _ in range(args.count):
        if args.format == "hex":
            token = secrets.token_hex(args.nbytes)
        else:
            token = secrets.token_urlsafe(args.nbytes)
        print(args.prefix + token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
