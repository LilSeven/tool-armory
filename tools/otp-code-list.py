#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性口令清单 —— 打印一页一次性口令, 每行一条, 行尾带划线位, 用后划掉。

用途:
    为"打印一页、逐条用掉"的场景生成口令(临时门禁、设备授权、线下核销等)。
    口令由 secrets 模块生成, 默认 8 位、每 4 位一组(如 7F3K-9Q2M), 默认字符集
    为大写字母+数字并剔除易混字符(I/O/0/1), 便于人工抄读。
    约定: 口令用过一次, 就在行尾方括号"划线位"里划一道; 整页用完后纸质件
    碎毁, 不留截图或电子副本。

示例命令:
    python otp-code-list.py                     # 一页 20 条(默认)
    python otp-code-list.py -n 30 -l 6          # 30 条、每条 6 位
    python otp-code-list.py -n 12 --charset hex # 十六进制字符集
    python otp-code-list.py -n 10 --group 2     # 每 2 位一组: 7F-3K-9Q-2M
    python otp-code-list.py -n 8 --title "机房门禁" --allow-ambiguous
"""

import argparse
import datetime
import secrets
import string
import sys

# (剔除易混字符版, 完整版)
CLEAN = {
    "alnum":  "ABCDEFGHJKLMNPQRSTUVWXYZ23456789",
    "upper":  "ABCDEFGHJKLMNPQRSTUVWXYZ",
    "lower":  "abcdefghijkmnpqrstuvwxyz",
    "digits": "23456789",
    "hex":    "0123456789abcdef",
    "base32": "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567",
}
FULL = {
    "alnum":  string.ascii_uppercase + string.digits,
    "upper":  string.ascii_uppercase,
    "lower":  string.ascii_lowercase,
    "digits": "0123456789",
    "hex":    CLEAN["hex"],
    "base32": CLEAN["base32"],
}


def group_code(code, group):
    """按 group 位分组, 用 - 连接; group<=0 或不分组长时不处理。"""
    if group > 0 and len(code) > group:
        return "-".join(code[i:i + group] for i in range(0, len(code), group))
    return code


def render_page(codes, title):
    today = datetime.date.today().isoformat()
    bar = "-" * 64
    lines = [
        "一次性口令清单 — %s" % title,
        "生成日期 %s | 共 %d 条 | 每条仅用一次, 用后在划线位划掉, 整页用完即碎毁"
        % (today, len(codes)),
        bar,
        "%4s  %-22s  %s" % ("序号", "口令", "划线位(用后划掉)"),
    ]
    for i, code in enumerate(codes, 1):
        lines.append("%4d  %-22s  [          ]" % (i, code))
    lines.append(bar)
    lines.append("提醒: 请勿以截图或电子文档形式留存本页; 电子副本请随手销毁。")
    return "\n".join(lines)


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="打印一页一次性口令(每行一条, 行尾带划线位, 用后划掉)。")
    parser.add_argument("-n", "--count", type=int, default=20,
                        help="口令条数(默认 20, 范围 1-1000)")
    parser.add_argument("-l", "--length", type=int, default=8,
                        help="口令位数(默认 8, 范围 4-64)")
    parser.add_argument("--group", type=int, default=4,
                        help="每 GROUP 位一组用 - 连接(默认 4, 0 表示不分组)")
    parser.add_argument("--charset", default="alnum", choices=sorted(CLEAN),
                        help="字符集: alnum/upper/lower/digits/hex/base32(默认 alnum)")
    parser.add_argument("--title", default="OTP", help="页首标题(默认 OTP)")
    parser.add_argument("--allow-ambiguous", action="store_true",
                        help="不剔除易混字符(I/O/0/1 等)")
    args = parser.parse_args(argv)

    if not 1 <= args.count <= 1000:
        parser.error("--count 取值范围 1-1000")
    if not 4 <= args.length <= 64:
        parser.error("--length 取值范围 4-64")
    if not 0 <= args.group <= 32:
        parser.error("--group 取值范围 0-32")

    pool = FULL[args.charset] if args.allow_ambiguous else CLEAN[args.charset]
    codes = []
    for _ in range(args.count):
        raw = "".join(secrets.choice(pool) for _ in range(args.length))
        codes.append(group_code(raw, args.group))
    print(render_page(codes, args.title))
    return 0


if __name__ == "__main__":
    _utf8_stdio()
    sys.exit(main())
