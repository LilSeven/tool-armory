#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2FA 恢复码生成 —— 批量生成 xx-xxxx 格式的双因子恢复码(如 a3-9k2m)。

用途:
    为双因子认证(2FA)准备离线备用恢复码: 每条 2 字符-4 字符共 6 个随机字符,
    默认 10 条, 默认字符集为小写字母+数字并剔除易混字符(l/i/o/0/1),
    批内保证互不重复。随机源为 secrets 模块。恢复码属敏感凭据, 建议打印或
    离线保存, 不要提交进代码仓库; 十六进制字符集按惯例保留 0/1。

示例命令:
    python backup-codes-gen.py                      # 默认 10 条, 如 k3-9m2q
    python backup-codes-gen.py -n 8                 # 指定数量
    python backup-codes-gen.py -n 6 --charset hex   # 十六进制字符集(0-9a-f)
    python backup-codes-gen.py -n 5 --upper         # 输出转大写
    python backup-codes-gen.py -n 5 --chars abcdef234567   # 自定义字符集
    python backup-codes-gen.py -n 5 --allow-ambiguous      # 不剔除易混字符
    python backup-codes-gen.py -n 5 --stats         # 行末附批内去重统计(stderr)
"""

import argparse
import secrets
import string
import sys

# (剔除易混字符版, 完整版)
SETS = {
    "lower": ("abcdefghjkmnpqrstuvwxyz", string.ascii_lowercase),
    "upper": ("ABCDEFGHJKLMNPQRSTUVWXYZ", string.ascii_uppercase),
    "digits": ("23456789", "0123456789"),
    "alnum": ("abcdefghjkmnpqrstuvwxyz23456789", string.ascii_lowercase + string.digits),
    "hex": ("0123456789abcdef", "0123456789abcdef"),
}


def gen_codes(count, pool):
    """生成 count 条互不重复的 xx-xxxx 恢复码, 返回 (码列表, 批内去重重试次数)。"""
    capacity = len(pool) ** 6
    if capacity < count * 10:
        sys.exit("错误: 字符集组合空间仅 %d, 难以生成 %d 条互异恢复码, 请扩大字符集"
                 % (capacity, count))
    codes, seen, retries = [], set(), 0
    while len(codes) < count:
        code = ("".join(secrets.choice(pool) for _ in range(2)) + "-"
                + "".join(secrets.choice(pool) for _ in range(4)))
        if code in seen:
            retries += 1
            continue
        seen.add(code)
        codes.append(code)
    return codes, retries


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="批量生成 xx-xxxx 格式的双因子(2FA)恢复码。")
    parser.add_argument("-n", "--count", type=int, default=10,
                        help="恢复码条数(默认 10, 范围 1-1000)")
    parser.add_argument("--charset", default="alnum", choices=sorted(SETS),
                        help="字符集: lower/upper/digits/alnum/hex(默认 alnum)")
    parser.add_argument("--chars", help="自定义字符集字符串(覆盖 --charset, 自动去重去连字符)")
    parser.add_argument("--upper", action="store_true", help="输出转大写")
    parser.add_argument("--allow-ambiguous", action="store_true", help="不剔除易混字符")
    parser.add_argument("--stats", action="store_true",
                        help="向 stderr 输出字符集规模/组合空间/去重统计")
    args = parser.parse_args(argv)

    if not 1 <= args.count <= 1000:
        parser.error("--count 取值范围 1-1000")

    if args.chars:
        pool = "".join(dict.fromkeys(args.chars.replace("-", "").replace(" ", "")))
        if len(pool) < 4:
            parser.error("自定义字符集至少需要 4 个不同字符")
        desc = "自定义[%s]" % pool
    else:
        clean, full = SETS[args.charset]
        pool = full if args.allow_ambiguous else clean
        desc = args.charset + ("(未去易混)" if args.allow_ambiguous else "(已去易混)")
    if args.upper:
        pool = pool.upper()

    codes, retries = gen_codes(args.count, pool)
    for code in codes:
        print(code.upper() if args.upper else code)
    if args.stats:
        print("统计: 字符集 %s 共 %d 字符 | 组合空间 %d^6=%d | 生成 %d | 批内去重重试 %d"
              % (desc, len(pool), len(pool), len(pool) ** 6, len(codes), retries),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    _utf8_stdio()
    sys.exit(main())
