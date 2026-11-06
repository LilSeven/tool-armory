#!/usr/bin/env python3
"""XOR 加解密 (xor-tool) —— 重复密钥 XOR, 供教学与 CTF 使用.

用途:
    用重复密钥对数据逐字节 XOR。XOR 是对称运算: 同一密钥再 XOR 一次即
    还原原文, 因此 encrypt 与 decrypt 是同一实现, 保留两个名字只为命令
    可读。输入与输出均可选 raw(原始字节)或 hex(十六进制文本)。

参数:
    输入: --text STR 或 --input FILE ('-' 读 stdin), 二选一,
          配合 --input-format raw|hex (缺省 raw)。
    密钥: --key STR (按 UTF-8 编码) 或 --key-hex HEX, 二选一, 不能为空。
    输出: --out-format raw|hex (缺省 raw), --output FILE (缺省 stdout)。

退出码: 0=成功, 2=参数或数据错误。

示例:
    python -I xor-tool.py encrypt --key "K" --text "hi" --out-format hex     # -> 2322
    python -I xor-tool.py decrypt --key "K" --input-format hex --text 2322   # -> hi
    python -I xor-tool.py enc --key "s3cr3t" --input plain.txt --output ct.hex --out-format hex
    python -I xor-tool.py dec --key "s3cr3t" --input ct.hex --input-format hex --output pt.txt
    python -I xor-tool.py encrypt --key-hex 4b4559 --input - --out-format hex < plain.bin
"""
import argparse
import sys


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _hex_to_bytes(text: str, what: str) -> bytes:
    clean = "".join(text.split())
    try:
        return bytes.fromhex(clean)
    except ValueError:
        raise ValueError(f"{what} 不是合法的十六进制: {clean[:64]!r}") from None


def xor_bytes(data: bytes, key: bytes) -> bytes:
    klen = len(key)
    return bytes(b ^ key[i % klen] for i, b in enumerate(data))


def read_payload(args) -> bytes:
    if (args.text is not None) == (args.input is not None):
        raise ValueError("--text 与 --input 必须二选一")
    if args.text is not None:
        if args.input_format == "hex":
            return _hex_to_bytes(args.text, "--text")
        return args.text.encode("utf-8")
    if args.input == "-":
        data = sys.stdin.buffer.read()
    else:
        with open(args.input, "rb") as fh:
            data = fh.read()
    if args.input_format == "hex":
        return _hex_to_bytes(data.decode("ascii", "replace"), "--input")
    return data


def read_key(args) -> bytes:
    if args.key is not None and args.key_hex:
        raise ValueError("--key 与 --key-hex 只能提供一个")
    if args.key_hex:
        key = _hex_to_bytes(args.key_hex, "--key-hex")
    elif args.key is not None:
        key = args.key.encode("utf-8")
    else:
        raise ValueError("需要 --key STR 或 --key-hex HEX 之一")
    if not key:
        raise ValueError("密钥不能为空")
    return key


def write_result(args, data: bytes) -> None:
    if args.output:
        if args.out_format == "hex":
            with open(args.output, "w", encoding="ascii") as fh:
                fh.write(data.hex() + "\n")
        else:
            with open(args.output, "wb") as fh:
                fh.write(data)
        print(f"[xor-tool] 已写入 {args.output} ({len(data)} 字节, {args.out_format})",
              file=sys.stderr)
    elif args.out_format == "hex":
        print(data.hex())
    else:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()


def main(argv=None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="xor-tool",
        description="重复密钥 XOR 加解密, 输入输出可选 hex/raw (encrypt 与 decrypt 等价)。",
    )
    parser.add_argument("mode", choices=["encrypt", "decrypt", "enc", "dec", "x"],
                        help="encrypt/decrypt (XOR 对称, 二者等价); enc/dec/x 为别名")
    parser.add_argument("--text", help="输入内容 (hex 字符串需配 --input-format hex)")
    parser.add_argument("--input", help="输入文件, '-' 读 stdin")
    parser.add_argument("--input-format", choices=["raw", "hex"], default="raw",
                        help="输入格式, 缺省 raw")
    parser.add_argument("--key", help="密钥字符串 (UTF-8)")
    parser.add_argument("--key-hex", help="密钥十六进制, 如 4b4559")
    parser.add_argument("--out-format", choices=["raw", "hex"], default="raw",
                        help="输出格式, 缺省 raw")
    parser.add_argument("--output", help="输出文件; 缺省 stdout")
    args = parser.parse_args(argv)
    try:
        key = read_key(args)
        data = read_payload(args)
        result = xor_bytes(data, key)
        write_result(args, result)
        action = {"enc": "encrypt", "dec": "decrypt", "x": "encrypt"}.get(args.mode, args.mode)
        print(f"[xor-tool] mode={action} in={len(data)}B key={len(key)}B out={args.out_format}",
              file=sys.stderr)
        return 0
    except (ValueError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
