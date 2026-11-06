#!/usr/bin/env python3
"""project-motto —— 项目口号机。

用途:
    为任意项目名称随机配一句中二风格标语，适合 README、发布公告或群公告整活。

示例:
    python project-motto.py my-app            # 给 my-app 配一句口号
    python project-motto.py my-app -n 3       # 配 3 句
    python project-motto.py my-app --bracket  # 整句包进「」
    python project-motto.py my-app --seed 9   # 固定随机种子，可复现

仅使用 Python 标准库。
"""

import argparse
import random
import sys

MOTTOS = [
    "{n}：以代码为剑，划破这长夜",
    "当世界陷入沉默，{n}将发出第一声轰鸣",
    "{n}——命运的齿轮，自此刻开始转动",
    "此身即是{n}，此界由我定义",
    "在虚无中点亮{n}，于混沌里写下序章",
    "{n}觉醒之日，旧秩序崩塌之时",
    "记住{n}这个名字，未来会替我解释一切",
    "{n}不为拯救世界而生，只为让世界好看一点",
    "世人皆言不可能，{n}偏要一意孤行",
    "深红的王座之上，唯有{n}独自屹立",
    "凡人仰望星空，{n}已在铸造星辰",
    "所谓奇迹，不过是{n}的另一个名字",
    "浩劫将至，唯{n}可挽狂澜",
    "{n}启动的瞬间，世界悄悄改写了规则",
]


def _setup_stdio():
    """尽量把 stdout/stderr 切到 UTF-8，避免 Windows 管道下输出报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if (stream.encoding or "").replace("-", "").lower() != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def build_parser():
    parser = argparse.ArgumentParser(
        prog="project-motto",
        description="为任意项目名称随机配一句中二标语",
    )
    parser.add_argument("project", help="项目名称（如 my-app）")
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="生成数量（默认 1）")
    parser.add_argument("--bracket", action="store_true",
                        help="整句包进「」")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子（便于复现）")
    return parser


def main(argv=None):
    _setup_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("-n/--count 必须 >= 1")
    if not args.project.strip():
        parser.error("项目名称不能为空白")
    rng = random.Random(args.seed)
    for _ in range(args.count):
        motto = rng.choice(MOTTOS).format(n=args.project)
        if args.bracket:
            motto = "「" + motto + "」"
        print(motto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
