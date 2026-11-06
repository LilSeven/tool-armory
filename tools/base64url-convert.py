#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""base64url-convert.py —— 标准 Base64 与 URL-safe 变体（+/ 换 -_）互转。

用途：
    在标准 Base64（字母表含 + /）与 URL-safe 变体（用 - _ 代替 + /，常见
    于 JWT、URL 参数、文件名）之间互相转换。默认自动识别输入属于哪种
    变体；目标是标准 Base64 时自动补齐 '=' padding，目标是 URL-safe 时
    保持原样；--strip/--pad 可显式去/补 padding，--to 可显式指定方向。
    转换前会先校验输入确为合法 Base64（兼容两种字母表，容忍缺失 padding）。

方向识别（--to auto，默认）：
    含 + 或 / 视为标准输入（转为 URL-safe）；含 - 或 _ 视为 URL-safe 输入
    （转为标准）；两者皆无时按「标准 -> URL-safe」处理；两者皆有时报错，
    需用 --to 显式指定方向。

示例命令（演示串均为合法长度：ab+/ 为 4 数据字符，ab+= 为 3 数据字符+1 padding）：
    python base64url-convert.py -s "ab+/"              # 自动识别 -> ab-_
    echo "ab+/" | python base64url-convert.py          # 从 stdin 读入
    python base64url-convert.py -s "ab-_"              # 自动识别 -> ab+/
    python base64url-convert.py -s "ab+=" --strip      # 去 padding -> ab-
    python base64url-convert.py -s "ab-=" --to std     # 指定转标准并补 padding -> ab+=
    python base64url-convert.py token.txt --to url     # token.txt 含 "aGk/" -> aGk_

退出码：0 成功；1 输入非法或方向不明；2 命令行参数错误（argparse）。
仅使用 Python 标准库（argparse / base64）。
"""

import argparse
import base64
import sys

_TO_URL = str.maketrans("+/", "-_")
_TO_STD = str.maketrans("-_", "+/")
_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               "abcdefghijklmnopqrstuvwxyz"
               "0123456789+-_/=")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="base64url-convert.py",
        description="在标准 Base64 与 URL-safe 变体（+/ 换 -_）之间互相转换。",
    )
    p.add_argument("input", nargs="?", default=None,
                   help="含 Base64 的文件路径；省略或为 '-' 时从 stdin 读取")
    p.add_argument("-s", "--string", default=None,
                   help="直接转换给定的 Base64 字符串（优先于文件/stdin）")
    p.add_argument("--to", choices=("auto", "url", "std"), default="auto",
                   help="转换方向：url=转 URL-safe，std=转标准，auto=自动识别（默认）")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--strip", action="store_true",
                   help="去掉输出中的 '=' padding（JWT 风格）")
    g.add_argument("--pad", action="store_true",
                   help="为输出补齐 '=' padding")
    return p


def load_text(args: argparse.Namespace) -> str:
    if args.string is not None:
        text = args.string
    elif args.input and args.input != "-":
        with open(args.input, "rb") as f:
            text = f.read().decode("utf-8", errors="replace")
    else:
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    return "".join(text.split())          # 剔除换行/空格/tab 等所有空白


def fix_padding(s: str) -> str:
    s = s.rstrip("=")
    return s + "=" * (-len(s) % 4)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        compact = load_text(args)

        bad = sorted({c for c in compact if c not in _ALLOWED})
        if bad:
            raise ValueError("输入含有非 Base64 字符: "
                             + " ".join(repr(c) for c in bad[:5]))

        has_std = ("+" in compact) or ("/" in compact)
        has_url = ("-" in compact) or ("_" in compact)
        if args.to == "auto":
            if has_std and has_url:
                raise ValueError("输入同时含有 '+/' 与 '-_'，无法自动判断方向；"
                                 "请显式指定 --to std 或 --to url")
            to_url = not has_url
        else:
            to_url = (args.to == "url")

        # 校验输入确为合法 Base64（兼容两种字母表，容忍缺失 padding）
        base64.b64decode(fix_padding(compact), altchars=b"-_", validate=True)

        converted = compact.translate(_TO_URL if to_url else _TO_STD)
        if args.strip:
            converted = converted.rstrip("=")
        elif args.pad or not to_url:
            # 目标为标准 Base64 时默认补齐 padding；--pad 显式补齐
            converted = fix_padding(converted)
        # 目标为 URL-safe 且未指定 --pad/--strip：保持原样

        sys.stdout.buffer.write(converted.encode("ascii") + b"\n")
        sys.stdout.buffer.flush()
    except (ValueError, OSError) as exc:
        print(f"base64url-convert: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
