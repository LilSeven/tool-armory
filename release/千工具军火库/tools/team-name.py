#!/usr/bin/env python3
"""team-name —— 团队战力名生成器。

用途:
    为黑客马拉松（hackathon）小组随机生成组名，并配一句口号。
    可传入主题关键词（如 AI、环保），让组名或口号带上它。

示例:
    python team-name.py                   # 随机 1 组：组名 + 口号
    python team-name.py -n 3              # 随机 3 组
    python team-name.py 人工智能          # 带主题关键词生成
    python team-name.py AI -n 2 --seed 3  # 固定随机种子，可复现

仅使用 Python 标准库。
"""

import argparse
import random
import sys

NAME_A = ["字节", "比特", "代码", "赛博", "量子", "光速", "极客", "像素",
          "二进制", "深夜", "螺旋", "星火", "黎明", "随机数", "番茄"]
NAME_B = ["风暴", "特攻队", "骑士团", "先锋", "联盟", "军团", "突击队",
          "破壁者", "点燃者", "编译器", "火星车", "服务器"]

SLOGANS = [
    "代码不息，bug 不止",
    "熬最深的夜，写最稳的代码",
    "先把 demo 跑通，再谈改变世界",
    "咖啡因驱动，deadline 制导",
    "我们不是在写 bug，是在生产 feature",
    "灵感有限，肝无限",
    "凡杀不死我们的 commit，终将使我们更强",
    "今天立 flag，凌晨打脸",
]

KEY_SLOGANS = [
    "让{kw}落地，让灵感起飞",
    "用{kw}撬动地球",
    "{kw}不问出处，代码不问英雄",
    "把{kw}按在地上摩擦，直到它发光",
    "万物皆可{kw}，先跑起来再说",
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
        prog="team-name",
        description="为黑客马拉松小组生成组名并配一句口号",
    )
    parser.add_argument("keyword", nargs="?", default=None,
                        help="可选主题关键词（如 AI、环保），融入组名或口号")
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="生成数量（默认 1）")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子（便于复现）")
    return parser


def generate_one(rng, keyword=None):
    b = rng.choice(NAME_B)
    if keyword and rng.random() < 0.6:
        name = keyword + b
    else:
        name = rng.choice(NAME_A) + b
    if keyword and rng.random() < 0.5:
        slogan = rng.choice(KEY_SLOGANS).format(kw=keyword)
    else:
        slogan = rng.choice(SLOGANS)
    return name, slogan


def main(argv=None):
    _setup_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("-n/--count 必须 >= 1")
    keyword = args.keyword.strip() if args.keyword else None
    if keyword == "":
        parser.error("关键词不能为空白")
    rng = random.Random(args.seed)
    blocks = []
    for _ in range(args.count):
        name, slogan = generate_one(rng, keyword)
        blocks.append("队名：" + name + "\n口号：" + slogan)
    print("\n\n".join(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
