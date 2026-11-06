#!/usr/bin/env python3
"""uuencode-tool.py — 传统 uuencode/uudecode 编解码器(单文件, 仅标准库)。

用途:
    将任意二进制文件编码为传统 uuencode 纯文本格式(每行 45 字节, "begin <mode> <name>"
    头 + 长度前缀数据行 + "end" 尾), 适合在纯文本信道传输; 或将 uuencode 文本解码还原
    为二进制。优先使用标准库 uu 模块; Python 3.13 起该模块已被移除, 此时自动退回基于
    binascii.b2a_uu/a2b_uu 的等价实现(输出与传统格式逐字节一致), 也可用 --impl 指定。

示例:
    python uuencode-tool.py encode photo.jpg photo.uue            # 编码到文件
    python uuencode-tool.py encode photo.jpg - --name photo.jpg   # 编码到 stdout
    python uuencode-tool.py decode photo.uue restored.jpg         # 解码到指定文件
    python uuencode-tool.py decode photo.uue                      # 输出名取自 begin 行
    cat data.bin | python uuencode-tool.py encode - - --name data.bin > data.uue
    python uuencode-tool.py encode data.bin out.uue --mode 644 --impl fallback
"""

from __future__ import annotations

import argparse
import binascii
import os
import sys

try:
    import uu as _uu  # Python 3.12 及更早版本自带
except ImportError:   # Python 3.13+: 标准库已删除 uu 模块
    _uu = None

LINE_BYTES = 45  # 传统 uuencode 每行编码 45 字节


def _resolve_impl(impl):
    if impl == "auto":
        return "uu" if _uu is not None else "fallback"
    if impl == "uu" and _uu is None:
        raise SystemExit(
            "uuencode-tool: stdlib uu module unavailable (removed in Python 3.13+); use --impl fallback")
    return impl


def _encode_fallback(fin, fout, name, mode):
    """binascii 手写编码, 输出与标准库 uu.encode 逐字节一致(镜像其实现)。"""
    fout.write(("begin %o %s\n" % (mode & 0o777, name)).encode("ascii"))
    while True:
        data = fin.read(LINE_BYTES)
        if not data:
            break
        fout.write(binascii.b2a_uu(data))
    fout.write(b" \nend\n")


def _decode_fallback(fin, fout):
    """binascii 手写解码, 行处理逻辑与标准库 uu.decode 相同(含损坏行容错)。"""
    started = False
    for raw in fin:
        if not started:
            parts = raw.split(b" ", 2)
            if len(parts) == 3 and parts[0] == b"begin":
                try:
                    int(parts[1], 8)
                    started = True
                except ValueError:
                    pass
            continue
        if raw.strip(b" \t\r\n\f") == b"end":
            break
        try:
            data = binascii.a2b_uu(raw)
        except binascii.Error:
            # 镜像 uu.decode 对非标准编码器的容错: 按长度字符截取后重试
            nbytes = (((raw[0] - 32) & 63) * 4 + 5) // 3
            data = binascii.a2b_uu(raw[:nbytes])
        fout.write(data)


def _uu_name(path):
    """从 begin 行取出记录的文件名(镜像 uu.decode 的头部校验), 无效则返回 None。"""
    try:
        with open(path, "rb") as f:
            for _ in range(8):
                line = f.readline()
                if not line:
                    break
                parts = line.split(b" ", 2)
                if len(parts) == 3 and parts[0] == b"begin":
                    try:
                        int(parts[1], 8)
                    except ValueError:
                        continue
                    name = parts[2].rstrip(b" \t\r\n\f").decode("ascii", "replace")
                    name = name.replace("\\", "/").split("/")[-1].strip('"')
                    if name not in ("", ".", ".."):
                        return name
                    return None
    except OSError:
        pass
    return None


def do_encode(args):
    impl = _resolve_impl(args.impl)
    name = args.name
    try:
        if args.infile == "-":
            if not name:
                name = "stdin.bin"
            fin = sys.stdin.buffer
            in_close = False
        else:
            if not name:
                name = os.path.basename(args.infile.replace("\\", "/")) or "input.bin"
            fin = open(args.infile, "rb")
            in_close = True
        try:
            if args.outfile == "-":
                sys.stdout.flush()
                fout = sys.stdout.buffer
                out_close = False
            else:
                fout = open(args.outfile, "wb")
                out_close = True
            try:
                if impl == "uu":
                    _uu.encode(fin, fout, name=name, mode=args.mode)
                else:
                    _encode_fallback(fin, fout, name, args.mode)
                fout.flush()
            finally:
                if out_close:
                    fout.close()
        finally:
            if in_close:
                fin.close()
    except OSError as exc:
        print("uuencode-tool: encode failed: %s" % exc, file=sys.stderr)
        return 1
    return 0


def do_decode(args):
    impl = _resolve_impl(args.impl)
    try:
        if args.infile == "-":
            fin = sys.stdin.buffer
            in_close = False
        else:
            fin = open(args.infile, "rb")
            in_close = True
        try:
            target = args.outfile
            if target is None:
                target = _uu_name(args.infile) if args.infile != "-" else None
                if target is None:
                    target = "-"
            if target == "-":
                sys.stdout.flush()
                fout = sys.stdout.buffer
                out_close = False
                shown = "<stdout>"
            else:
                fout = open(target, "wb")
                out_close = True
                shown = target
            try:
                if impl == "uu":
                    try:
                        _uu.decode(fin, fout)
                    except _uu.Error as exc:
                        print("uuencode-tool: decode failed: %s" % exc, file=sys.stderr)
                        return 1
                else:
                    _decode_fallback(fin, fout)
                fout.flush()
            finally:
                if out_close:
                    fout.close()
        finally:
            if in_close:
                fin.close()
    except OSError as exc:
        print("uuencode-tool: decode failed: %s" % exc, file=sys.stderr)
        return 1
    print("decoded -> %s" % shown, file=sys.stderr)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="uuencode-tool",
        description="传统 uuencode/uudecode 编解码工具(优先标准库 uu 模块)。")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="{encode,decode}")

    pe = sub.add_parser("encode", help="二进制 -> uuencode 文本")
    pe.add_argument("infile", help="输入文件; '-' 表示 stdin")
    pe.add_argument("outfile", nargs="?", default="-",
                    help="输出文件; 缺省 '-' 表示 stdout")
    pe.add_argument("--name", default=None, help="begin 行记录的文件名(缺省取输入文件名)")
    pe.add_argument("--mode", type=lambda s: int(s, 8), default=0o644,
                    help="begin 行中的八进制权限(缺省 644)")
    pe.add_argument("--impl", choices=("auto", "uu", "fallback"), default="auto",
                    help="实现选择: auto=优先 uu 模块(缺省), fallback=binascii 手写")
    pe.set_defaults(func=do_encode)

    pd = sub.add_parser("decode", help="uuencode 文本 -> 二进制")
    pd.add_argument("infile", help="输入文件; '-' 表示 stdin")
    pd.add_argument("outfile", nargs="?", default=None,
                    help="输出文件; 缺省取 begin 行的文件名, '-' 表示 stdout")
    pd.add_argument("--impl", choices=("auto", "uu", "fallback"), default="auto")
    pd.set_defaults(func=do_decode)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
