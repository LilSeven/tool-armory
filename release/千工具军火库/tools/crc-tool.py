#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crc-tool.py —— CRC 多项式校验/校验和命令行工具（仅 Python 标准库）。

用途:
    计算输入数据（文本或十六进制字节串）的 CRC-8 / CRC-16(ARC) /
    CRC-16-CCITT(FALSE 与 XMODEM) / CRC-32 / Adler-32 校验值；
    支持自定义初始值（--init）与输出进制（--radix hex|dec|bin，--upper 大写）。

示例命令:
    python crc-tool.py "123456789"                          # CRC-32（默认），十六进制
    python crc-tool.py "123456789" -a crc8                  # CRC-8 (SMBus)
    python crc-tool.py "123456789" -a ccitt --init 0xFFFF   # 自定义寄存器初始值
    python crc-tool.py "123456789" -a crc16 --radix dec     # 十进制输出
    python crc-tool.py --hex 313233343536373839 -a adler32  # 输入按十六进制字节解析
    echo -n abc | python crc-tool.py -a xmodem              # 从 stdin 读取原始字节
    python crc-tool.py --selftest                           # 运行内置自测

说明:
    crc8/crc16/ccitt/xmodem 的 --init 直接覆盖寄存器初始值；
    crc32/adler32 的 --init 为 zlib 连续计算起点（默认分别为 0/1）。
    标准检查向量 "123456789": crc8=F4, crc16=BB3D, ccitt=29B1,
    xmodem=31C3, crc32=CBF43926, adler32=091E01DE。
"""

import argparse
import sys
import zlib

# 算法名 -> (说明, CRC 参数；crc32/adler32 用 zlib 实现，参数为 None)
PRESETS = {
    "crc8": ("CRC-8 (SMBus)",
             dict(width=8, poly=0x07, init=0x00, refin=False, refout=False, xorout=0x00)),
    "crc16": ("CRC-16/ARC (IBM)",
              dict(width=16, poly=0x8005, init=0x0000, refin=True, refout=True, xorout=0x0000)),
    "ccitt": ("CRC-16/CCITT-FALSE",
              dict(width=16, poly=0x1021, init=0xFFFF, refin=False, refout=False, xorout=0x0000)),
    "xmodem": ("CRC-16/XMODEM (CCITT)",
               dict(width=16, poly=0x1021, init=0x0000, refin=False, refout=False, xorout=0x0000)),
    "crc32": ("CRC-32 (IEEE 802.3, zlib)", None),
    "adler32": ("Adler-32 (RFC 1950, zlib)", None),
}

CHECK_DATA = b"123456789"
CHECK_VALUES = {
    "crc8": 0xF4,
    "crc16": 0xBB3D,
    "ccitt": 0x29B1,
    "xmodem": 0x31C3,
    "crc32": 0xCBF43926,
    "adler32": 0x091E01DE,
}


def _force_utf8_stdio():
    """让输出在非 UTF-8 控制台上也不因中文而报编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _reflect(value, width):
    """按位反转 width 宽的整数。"""
    out = 0
    for _ in range(width):
        out = (out << 1) | (value & 1)
        value >>= 1
    return out


def crc_generic(data, width, poly, init, refin, refout, xorout):
    """通用按位 CRC。refin=True 采用反射算法（refout 隐含完成）。"""
    mask = (1 << width) - 1
    crc = init & mask
    if refin:
        rpoly = _reflect(poly & mask, width)
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ rpoly if crc & 1 else crc >> 1
    else:
        top = 1 << (width - 1)
        for byte in data:
            crc ^= byte << (width - 8)
            for _ in range(8):
                crc = ((crc << 1) & mask) ^ poly if crc & top else (crc << 1) & mask
        if refout:
            crc = _reflect(crc, width)
    return (crc ^ xorout) & mask


def compute(algo, data, init=None):
    """计算校验值，返回整数。"""
    if algo == "crc32":
        return zlib.crc32(data, 0 if init is None else init) & 0xFFFFFFFF
    if algo == "adler32":
        return zlib.adler32(data, 1 if init is None else init) & 0xFFFFFFFF
    params = PRESETS[algo][1]
    if init is not None:
        params = dict(params, init=init)
    return crc_generic(data, **params)


def algo_width(algo):
    params = PRESETS[algo][1]
    return params["width"] if params else 32


def parse_hex_bytes(text):
    """把 '0x31 32:33' 之类的十六进制串解析为 bytes。"""
    cleaned = text.strip()
    if cleaned.lower().startswith("0x"):
        cleaned = cleaned[2:]
    cleaned = "".join(cleaned.split()).replace(":", "")
    if len(cleaned) % 2 != 0:
        raise ValueError("十六进制输入长度须为偶数: {!r}".format(text))
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError("非法十六进制输入: {!r}".format(text)) from exc


def format_value(value, width, radix="hex", upper=False):
    if radix == "dec":
        return str(value)
    if radix == "bin":
        return format(value, "0{}b".format(width))
    text = "{:0{w}X}".format(value, w=width // 4)
    return text if upper else text.lower()


def read_input(args, parser):
    if args.data is not None:
        if args.as_hex:
            try:
                return parse_hex_bytes(args.data)
            except ValueError as exc:
                parser.error(str(exc))
        return args.data.encode("utf-8")
    if sys.stdin.isatty():
        parser.error("缺少输入：请传入 data 参数或用管道送入 stdin")
    return sys.stdin.buffer.read()


def selftest():
    ok = True

    def check(cond, label):
        nonlocal ok
        ok = ok and bool(cond)
        print("[{}] {}".format("PASS" if cond else "FAIL", label))

    for algo in sorted(PRESETS):
        want = CHECK_VALUES[algo]
        got = compute(algo, CHECK_DATA)
        w = algo_width(algo) // 4
        check(got == want, "{:<7} {:<26} got=0x{:0{w}X} want=0x{:0{w}X}".format(
            algo, PRESETS[algo][0], got, want, w=w))

    check(parse_hex_bytes("31 32 33 34 35 36 37 38 39") == CHECK_DATA,
          "十六进制输入解析（含空格分隔）")
    check(compute("ccitt", CHECK_DATA, init=0x0000) == compute("xmodem", CHECK_DATA),
          "--init 覆盖：ccitt(init=0x0000) == xmodem")
    check(format_value(CHECK_VALUES["crc32"], 32, "dec") == str(CHECK_VALUES["crc32"]),
          "十进制输出")
    check(len(format_value(1, 16, "bin")) == 16, "二进制输出按宽度补零")
    check(format_value(0xAB, 8, "hex", upper=True) == "AB", "大写十六进制输出")
    print("自测结果: {}".format("全部通过" if ok else "存在失败"))
    return 0 if ok else 1


def build_parser():
    parser = argparse.ArgumentParser(
        prog="crc-tool.py",
        description="计算 CRC8/CRC16/CCITT/CRC32/Adler32 校验值（支持自定义初始值与输出进制）")
    parser.add_argument("data", nargs="?",
                        help="输入文本（配合 --hex 则按十六进制解析；缺省读 stdin）")
    parser.add_argument("-a", "--algo", choices=sorted(PRESETS), default="crc32",
                        help="校验算法（默认 crc32）")
    parser.add_argument("--hex", dest="as_hex", action="store_true",
                        help="把输入按十六进制字节串解析（允许空格/冒号分隔、0x 前缀）")
    parser.add_argument("--init", type=lambda s: int(s, 0), default=None, metavar="N",
                        help="自定义初始值（支持 0x 前缀；crc32/adler32 为连续计算起点）")
    parser.add_argument("--radix", choices=("hex", "dec", "bin"), default="hex",
                        help="输出进制（默认 hex）")
    parser.add_argument("--upper", action="store_true", help="十六进制输出用大写")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测并退出")
    return parser


def main(argv=None):
    _force_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    data = read_input(args, parser)
    value = compute(args.algo, data, args.init)
    print(format_value(value, algo_width(args.algo), args.radix, args.upper))
    return 0


if __name__ == "__main__":
    sys.exit(main())
