#!/usr/bin/env python3
"""乐队名生成器 —— 暗黑 / 文艺 / 搞笑三种风格的随机虚构乐队名。

用途:
    为小说、跑团、随笔或单纯想找灵感的你, 批量生成虚构乐队名。

用法:
    python band-namer.py [--style STYLE] [--count N] [--seed SEED]

示例命令:
    python band-namer.py                          # 三种风格混着出 5 个
    python band-namer.py --style dark --count 3   # 只要暗黑风, 出 3 个
    python band-namer.py --style funny --seed 42  # 固定随机种子, 结果可复现

风格 STYLE 取值: dark(暗黑) / art(文艺) / funny(搞笑) / all(混合, 默认)
仅依赖 Python 标准库; 成功时退出码为 0。
"""

from __future__ import annotations

import argparse
import random
import sys

# 词库: 风格 -> (前缀池, 后缀池), 随机 "前缀 + 后缀" 拼出乐队名
WORD_BANK = {
    "dark": (
        ["永夜", "血色", "丧钟", "荆棘", "墓志", "寒鸦", "蚀月", "黑潮",
         "亡灵", "幽谷", "骸骨", "灰烬", "深渊", "残阳", "锈蚀", "缄默"],
        ["挽歌", "弥撒", "先知", "回响", "典礼", "葬送", "咏叹", "迷雾",
         "低语", "圆舞曲", "安魂曲", "唱诗班", "圣殿", "残响", "夜巡", "教堂"],
    ),
    "art": (
        ["南方", "白色", "夏日", "北纬", "纸飞机", "慢递", "雨后", "十七",
         "候鸟", "鲸落", "晨光", "漂流", "旧巷", "橄榄", "海边", "银杏"],
        ["诗社", "民谣团", "邮局", "月光社", "旅行团", "信箱", "放映队",
         "乐团", "车站", "唱片行", "图书馆", "合奏团", "守望者", "手风琴"],
    ),
    "funny": (
        ["火锅底料", "隔壁老王", "养生朋克", "秃头", "咸鱼", "辣条",
         "社恐", "外卖骑手", "退堂鼓", "熬夜冠军", "枕头大战", "摸鱼",
         "杨枝甘露", "保温杯", "穿秋裤", "打工人"],
        ["天团", "合唱团", "女团", "男团", "组合", "俱乐部", "乐队",
         "突击队", "研究所", "后援会", "歌舞团", "进行曲", "互助会", "频道"],
    ),
}

STYLE_CN = {"dark": "暗黑", "art": "文艺", "funny": "搞笑"}


def make_name(style: str, rng: random.Random) -> str:
    prefixes, suffixes = WORD_BANK[style]
    return rng.choice(prefixes) + rng.choice(suffixes)


def generate(styles: list, count: int, rng: random.Random) -> list:
    """返回 [(风格, 乐队名), ...], 尽力保证互不重名。"""
    seen = set()
    out = []
    attempts = 0
    while len(out) < count and attempts < count * 200:
        attempts += 1
        style = rng.choice(styles)
        name = make_name(style, rng)
        if name in seen:
            continue
        seen.add(name)
        out.append((style, name))
    return out


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = argparse.ArgumentParser(
        description="乐队名生成器: 暗黑/文艺/搞笑三种风格随机虚构乐队名")
    parser.add_argument("--style", default="all",
                        help="dark(暗黑)/art(文艺)/funny(搞笑)/all(默认, 混合)")
    parser.add_argument("--count", type=int, default=5, help="生成数量 (默认 5)")
    parser.add_argument("--seed", type=int, default=None, help="随机种子, 便于复现")
    args = parser.parse_args(argv)

    styles = list(WORD_BANK) if args.style == "all" else [args.style]
    for s in styles:
        if s not in WORD_BANK:
            parser.error("未知风格: %s (可选 dark/art/funny/all)" % args.style)
    if args.count < 1:
        parser.error("--count 至少为 1")

    rng = random.Random(args.seed)
    results = generate(styles, args.count, rng)
    for i, (style, name) in enumerate(results, 1):
        print("%d. [%s] %s" % (i, STYLE_CN[style], name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
