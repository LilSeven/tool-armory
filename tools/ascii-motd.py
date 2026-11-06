#!/usr/bin/env python3
"""每日一画 (ascii-motd) -- 按日期做种子, 确定性输出一幅随机 ASCII 艺术画。

示例命令:
    python ascii-motd                       # 输出今天的画
    python ascii-motd --date 2026-11-03     # 指定日期
    python ascii-motd --list                # 列出画廊全部作品名

说明:
    * 种子 = 日期字符串: 同一日期无论何时/何地运行, 输出逐字节一致。
    * 每天从画廊中确定性挑一幅画, 边框样式也由日期决定。
    * 日期格式 YYYY-MM-DD, 非法日期退出码 2。
    * 单文件, 只依赖 Python 标准库; 输出强制 UTF-8。
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date

GALLERY = {
    "cat": (
        r" /\_/\ ",
        r"( o.o )",
        r" > ^ < ",
    ),
    "coffee": (
        "  ( (",
        "   ) )",
        " ......",
        " |    |]",
        " \\    /",
        "  `--'",
    ),
    "rocket": (
        "   /\\",
        "  /  \\",
        "  |  |",
        " /|/\\|\\",
        "  ****",
    ),
    "mountain": (
        "     /\\      /\\",
        "    /  \\    /  \\",
        "   /    \\  /    \\",
        "  /      \\/      \\",
        "~~~~~~~~~~~~~~~~~~",
    ),
    "star": (
        "    *",
        "   ***",
        "*********",
        "  *****",
        " **   **",
    ),
    "fish": (
        "      o   o",
        "       o",
        "><(((('>",
    ),
    "tree": (
        "   *",
        "  /_\\",
        " /___\\",
        "  |=|",
    ),
    "heart": (
        "  __  __",
        " /  \\/  \\",
        " \\      /",
        "  \\    /",
        "   \\  /",
        "    \\/",
    ),
}

BORDERS = "+=*#~"


def force_utf8() -> None:
    """Windows 管道/Git Bash 下 stdout 默认是 ANSI 代码页 (如 gbk), 统一改成 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def render(iso: str) -> str:
    """以日期字符串为唯一种子, 确定性挑画与边框并排版输出。"""
    rng = random.Random(f"ascii-motd/{iso}")
    name = rng.choice(sorted(GALLERY))
    border = rng.choice(BORDERS)
    header = f"MOTD {iso} [{name}]"
    body = [header, ""] + list(GALLERY[name])
    width = max(len(line) for line in body)
    rule = border * (width + 6)  # 内容行 = 边框+2空格+文本+2空格+边框
    out = [rule]
    for i, line in enumerate(body):
        text = line.center(width) if i == 0 else line.ljust(width)
        out.append(f"{border}  {text}  {border}")
    out.append(rule)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(
        prog="ascii-motd.py",
        description="按日期做种子, 确定性输出一幅随机 ASCII 艺术画",
    )
    parser.add_argument("--date", default=None, help="YYYY-MM-DD; 省略则为今天")
    parser.add_argument("--list", action="store_true", help="列出画廊作品名后退出")
    args = parser.parse_args(argv)

    if args.list:
        print("画廊作品:", ", ".join(sorted(GALLERY)))
        return 0

    if args.date is None:
        iso = date.today().isoformat()
    else:
        try:
            iso = date.fromisoformat(args.date).isoformat()
        except ValueError:
            parser.error(f"日期格式应为 YYYY-MM-DD: {args.date!r}")

    print(render(iso))
    return 0


if __name__ == "__main__":
    sys.exit(main())
