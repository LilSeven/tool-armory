#!/usr/bin/env python3
"""一次性密码本 (otp-pad-tool) —— 生成随机 pad 并做严格一次一密加解密.

用途:
    gen  生成随机密钥文件 (os.urandom): --length N 字节, 或 --like FILE
         生成与明文文件等长的 pad。
    enc  严格一次一密加密: 从 pad 的"已消费偏移"处取与明文等长的区段做
         XOR, 成功后把偏移写入状态文件 <pad>.state.json ({"used": N})。
         pad 剩余不足时拒绝 (退出码 3), 因此同一段 pad 永远不会加密两条
         消息 (杜绝"两次一密"被破)。
    dec  解密: 用 --offset 指定加密时消费的区段起点 (缺省 0), 只读不消费,
         不改状态文件。

退出码: 0=成功, 2=参数或文件错误, 3=pad 不足/区段越界 (重用被拒)。

示例:
    python -I otp-pad-tool.py gen --like plain.txt --out pad.bin
    python -I otp-pad-tool.py enc --in plain.txt --pad pad.bin --out ct.bin
    python -I otp-pad-tool.py dec --in ct.bin --pad pad.bin --out pt.bin --offset 0
    python -I otp-pad-tool.py gen --length 64 --out pad.bin
"""
import argparse
import json
import os
import sys


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def _state_path(pad_path: str) -> str:
    return pad_path + ".state.json"


def _load_used(pad_path: str) -> int:
    path = _state_path(pad_path)
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as fh:
        used = int(json.load(fh).get("used", 0))
    if used < 0:
        raise ValueError(f"{path} 中 used 为负数")
    return used


def _save_used(pad_path: str, used: int) -> None:
    with open(_state_path(pad_path), "w", encoding="utf-8") as fh:
        json.dump({"used": used}, fh)


def _read_bytes(path: str) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read()
    with open(path, "rb") as fh:
        return fh.read()


def _write_bytes(path, data: bytes) -> None:
    if path is None:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    else:
        with open(path, "wb") as fh:
            fh.write(data)


def cmd_gen(args) -> int:
    if (args.length is None) == (args.like is None):
        raise ValueError("gen 需要 --length N 或 --like FILE 之一 (且仅一个)")
    if args.like is not None:
        if not os.path.isfile(args.like):
            raise ValueError(f"找不到明文文件: {args.like}")
        length = os.path.getsize(args.like)
    else:
        if args.length < 0:
            raise ValueError("--length 不能为负")
        length = args.length
    pad = os.urandom(length)
    with open(args.out, "wb") as fh:
        fh.write(pad)
    if os.path.exists(_state_path(args.out)):
        os.remove(_state_path(args.out))
    origin = f" (与 {args.like} 等长)" if args.like else ""
    print(f"[otp-pad-tool] 已生成 {args.out}: {length} 字节 os.urandom 随机数{origin}")
    return 0


def cmd_enc(args) -> int:
    msg = _read_bytes(args.infile)
    pad = _read_bytes(args.pad)
    used = _load_used(args.pad)
    if used > len(pad):
        raise ValueError(f"状态文件记录偏移 {used} 超过 pad 长度 {len(pad)} (pad 被换过?)")
    remaining = len(pad) - used
    if len(msg) > remaining:
        print(f"错误: pad 剩余不足: 需要 {len(msg)} 字节, 偏移 {used} 处只剩 {remaining} 字节; "
              f"严格一次一密禁止重用已消费区段, 请用 gen 生成新 pad", file=sys.stderr)
        return 3
    _write_bytes(args.outfile, _xor(msg, pad[used:used + len(msg)]))
    _save_used(args.pad, used + len(msg))
    print(f"[otp-pad-tool] 加密 {len(msg)} 字节, 消费 {args.pad}[{used}:{used + len(msg)}], "
          f"剩余 {len(pad) - used - len(msg)} 字节", file=sys.stderr)
    return 0


def cmd_dec(args) -> int:
    if args.offset < 0:
        raise ValueError("--offset 不能为负")
    ct = _read_bytes(args.infile)
    pad = _read_bytes(args.pad)
    end = args.offset + len(ct)
    if end > len(pad):
        print(f"错误: pad 区段越界: 需要 [{args.offset}:{end}) 但 pad 只有 {len(pad)} 字节",
              file=sys.stderr)
        return 3
    _write_bytes(args.outfile, _xor(ct, pad[args.offset:end]))
    print(f"[otp-pad-tool] 解密 {len(ct)} 字节, 使用 {args.pad}[{args.offset}:{end}] "
          f"(只读, 不消费)", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="otp-pad-tool",
        description="生成与明文等长的随机密钥文件, 并做严格一次一密加解密。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("gen", help="生成随机 pad (os.urandom)")
    p_gen.add_argument("--length", type=int, help="pad 字节数")
    p_gen.add_argument("--like", help="生成与该明文文件等长的 pad")
    p_gen.add_argument("--out", required=True, help="pad 输出文件")
    p_gen.set_defaults(func=cmd_gen)

    p_enc = sub.add_parser("enc", help="加密 (消费 pad 区段, 拒绝重用)")
    p_enc.add_argument("--in", dest="infile", required=True, help="明文文件, '-' 读 stdin")
    p_enc.add_argument("--pad", required=True, help="pad 文件")
    p_enc.add_argument("--out", dest="outfile", help="密文输出文件; 缺省 stdout(原始字节)")
    p_enc.set_defaults(func=cmd_enc)

    p_dec = sub.add_parser("dec", help="解密 (只读指定区段)")
    p_dec.add_argument("--in", dest="infile", required=True, help="密文文件, '-' 读 stdin")
    p_dec.add_argument("--pad", required=True, help="pad 文件")
    p_dec.add_argument("--out", dest="outfile", help="明文输出文件; 缺省 stdout(原始字节)")
    p_dec.add_argument("--offset", type=int, default=0, help="加密时消费的区段起点, 缺省 0")
    p_dec.set_defaults(func=cmd_dec)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
