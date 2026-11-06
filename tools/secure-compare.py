#!/usr/bin/env python3
"""常数时间比较器 (secure-compare)。

用途:
    用 hmac.compare_digest 在常数时间内比较两个值是否相等,
    避免逐字符短路比较造成的时序侧信道。支持三种模式:
      * 默认      直接比较两个文本 (按 UTF-8 编码成字节后比较);
      * --digest  先对两个文本做摘要再比较 (等长比较, 不泄露原文长度);
      * --file    流式读取并比较两个文件的摘要, 支持大文件。

退出码: 0=相等(MATCH), 1=不相等(MISMATCH, 属正常设计), 2=参数或 IO 错误。

示例:
    python -I secure-compare.py tokenA tokenA
    python -I secure-compare.py --digest password1 password2
    python -I secure-compare.py --file a.bin b.bin
    python -I secure-compare.py --file --algo sha1 old.bin new.bin
"""
import argparse
import hashlib
import hmac
import sys


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def digest_file(path: str, algo: str) -> bytes:
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.digest()


def main(argv=None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="secure-compare",
        description="用 hmac.compare_digest 常数时间比较文本或文件摘要。",
    )
    parser.add_argument("a", help="第一个值 (文本或文件路径, 取决于 --file)")
    parser.add_argument("b", help="第二个值")
    parser.add_argument("--file", action="store_true",
                        help="把 a、b 当作文件路径, 比较文件摘要")
    parser.add_argument("--digest", action="store_true",
                        help="文本模式: 先做摘要再比较 (等长比较, 不泄露原文长度)")
    parser.add_argument("--algo", default="sha256",
                        help="摘要算法, 默认 sha256 (配合 --file / --digest)")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="不打印 MATCH/MISMATCH, 只用退出码表达结果")
    args = parser.parse_args(argv)

    try:
        if args.file:
            left = digest_file(args.a, args.algo)
            right = digest_file(args.b, args.algo)
        elif args.digest:
            left = hashlib.new(args.algo, args.a.encode("utf-8")).digest()
            right = hashlib.new(args.algo, args.b.encode("utf-8")).digest()
        else:
            left = args.a.encode("utf-8")
            right = args.b.encode("utf-8")
    except (OSError, ValueError, TypeError) as exc:
        if not args.quiet:
            print(f"错误: {exc}", file=sys.stderr)
        return 2

    equal = hmac.compare_digest(left, right)
    if not args.quiet:
        print("MATCH" if equal else "MISMATCH")
    return 0 if equal else 1


if __name__ == "__main__":
    sys.exit(main())
