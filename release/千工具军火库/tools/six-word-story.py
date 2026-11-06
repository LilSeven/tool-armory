#!/usr/bin/env python3
"""六词小说（six-word-story）—— 随机抽六个词写微型小说，不满意可重掷。

致敬"出售：婴儿鞋，全新"式六词小说：从时间/人物/物件/动作×2/状态
六类词库中各抽一词，恰好六个词，再选一个叙事骨架把它们串成一句微型
小说。终端交互模式下回车即可重掷；在脚本/管道里运行时只输出一次，
可用 --times N 连掷 N 次。

用法：
    python six-word-story.py                # 抽六个词写一篇（可重掷）
    python six-word-story.py --times 5      # 连掷五篇（非交互）
    python six-word-story.py --seed 7       # 固定种子（可复现）
    python six-word-story.py --help         # 查看帮助

示例输出：
    $ python six-word-story.py --seed 7
    🎲 六词：战争那年 · 士兵 · 戒指 · 藏 · 找 · 碎
    📖 战争那年，士兵把戒指藏了。此后多年，他再没找过。有人问起，他只答一个字——碎。

只用 Python 标准库。
"""

import argparse
import random
import sys

TIMES = ["战争那年", "母亲走后", "雨夜", "大雪封城那天", "停电的夏夜",
         "搬家那天", "黎明前", "最后一个秋天", "电话接通前",
         "生日蜡烛熄灭后", "放榜那天", "退潮之后"]
PEOPLE = ["母亲", "父亲", "士兵", "老人", "孩子", "医生", "邮差",
          "守林人", "修表匠", "画家", "天文学家", "渔夫"]
OBJECTS = ["婴儿鞋", "情书", "军功章", "戒指", "老照片", "钥匙",
           "机票", "闹钟", "种子", "地图", "钢笔", "猫"]
VERBS1 = ["丢", "藏", "烧", "埋", "卖", "送", "扔", "锁", "撕", "摔"]  # 及物：把{o}{v1}了
VERBS2 = ["等", "找", "哭", "跑", "追", "念", "写", "数", "画", "问"]  # 不及物：再没/一路/转身去
STATES = ["空", "碎", "冷", "远", "哑", "散", "沉", "湿", "灰", "断", "醒", "薄"]

STORIES = [
    "{t}，{p}把{o}{v1}了。此后多年，他再没{v2}过。有人问起，他只答一个字——{s}。",
    "{t}，有人说{p}的{o}{v1}了。{p}追出门，一路{v2}到天亮，最后只带回一个{s}的影子。",
    "{t}，{p}的{o}不见了。人们说他{v1}了它，他说自己只是{v2}得太久，梦里全是{s}。",
    "{t}，{p}用最后的力气{v1}了{o}，然后转身去{v2}。多年以后讲起那天，人们只记得一个字：{s}。",
]


def _setup_stdio():
    """让中文输出在管道/重定向场景下也按 UTF-8 走。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _check_data():
    """数据自检：词库非空，叙事骨架占位符合法。"""
    for name, pool in (("时间", TIMES), ("人物", PEOPLE), ("物件", OBJECTS),
                       ("动作一", VERBS1), ("动作二", VERBS2), ("状态", STATES)):
        if not pool:
            raise SystemExit(f"数据错误：{name}词库为空")
    for i, tpl in enumerate(STORIES, 1):
        filled = tpl.format(t="一", p="人", o="物", v1="丢", v2="找", s="空")
        if "{" in filled or "}" in filled:
            raise SystemExit(f"数据错误：骨架 {i} 有未知占位符")


def draw_words(rng):
    """抽六个词：时间/人物/物件/动作/动作/状态。"""
    return {"t": rng.choice(TIMES), "p": rng.choice(PEOPLE),
            "o": rng.choice(OBJECTS), "v1": rng.choice(VERBS1),
            "v2": rng.choice(VERBS2), "s": rng.choice(STATES)}


def write_story(words, rng):
    """把六个词填进随机叙事骨架。"""
    return rng.choice(STORIES).format(**words)


def show(words, story):
    six = [words["t"], words["p"], words["o"], words["v1"], words["v2"], words["s"]]
    print("🎲 六词：" + " · ".join(six))
    print("📖 " + story)


def main(argv=None):
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="six-word-story",
        description="六词小说：随机抽六个词写微型小说，不满意可重掷。")
    parser.add_argument("--times", type=int, default=1,
                        help="连掷次数（非交互），默认 1")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，便于复现")
    args = parser.parse_args(argv)
    if args.times < 1:
        parser.error("--times 需要正整数")

    _check_data()
    rng = random.Random(args.seed)

    for i in range(args.times):
        words = draw_words(rng)
        show(words, write_story(words, rng))
        if i < args.times - 1:
            print()

    # 终端交互模式：回车重掷，q 退出（仅当标准输入输出都是终端时才提示，
    # 避免 Git Bash 下 /dev/null 被 stdin.isatty() 误判为终端）
    if sys.stdin.isatty() and sys.stdout.isatty():
        while True:
            try:
                ans = input("↻ 回车重掷，q 退出 > ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if ans.strip().lower() in ("q", "quit", "exit", "退出"):
                break
            print()
            words = draw_words(rng)
            show(words, write_story(words, rng))
    return 0


if __name__ == "__main__":
    sys.exit(main())
