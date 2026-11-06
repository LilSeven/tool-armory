#!/usr/bin/env python3
"""中文废话文学 —— 生成“听君一席话，如听一席话”式的废话段落。

每段 = 开场白 + 若干句套话 + 收尾，信息量恒等于零，句句正确、
句句无用。可用 --count 控制长度、--topic 指定话题、--seed 复现。

示例命令:
  python lorem-zh.py                       # 随机来一段（默认 5 句）
  python lorem-zh.py --count 8 --seed 42   # 更长的一段，可复现
  python lorem-zh.py --topic 搬砖
  python lorem-zh.py --topics              # 列出可废的话题

退出码: 0 成功；1 参数不合法。
"""
import argparse
import random
import sys
import textwrap

TOPICS = ["青春", "生活", "爱情", "工作", "梦想", "读书",
          "减肥", "存钱", "早睡", "搬砖", "旅行", "加班"]

OPENERS = [
    "听君一席话，如听一席话。",
    "俗话说得好：俗话说得真好。",
    "关于{t}，我想说的话，都在这句话里了。",
]

MIDDLES = [
    "众所周知，{t}本来就是{t}。",
    "每次想到{t}，我都会想起上次想到{t}的时候。",
    "{t}的好处在于，当你体会到它的好，它就是好的。",
    "对{t}而言，明天最重要的事，就是等明天。",
    "但凡你对{t}上点心，也不至于一点心都不上。",
    "有人问{t}到底难不难：说难也难，说不难，也确实不难。",
    "在{t}这条路上，走得越远，离出发的地方就越远。",
    "你问{t}有什么意义？这个问题问得好，好就好在它是个问题。",
    "从某种意义上讲，{t}在某种意义上确实挺有意义的。",
    "{t}就像一盏灯，点亮之前，它是不亮的。",
    "十年前的我想不到，十年后的我会怀念十年前的我。",
    "如果{t}有颜色，那它一定不是没有颜色。",
    "只要不放弃{t}，就说明你还没有放弃{t}。",
    "每一个关于{t}的问题，都是一个关于{t}的问题。",
    "据我观察，{t}通常发生在{t}发生的时候。",
    "{t}和{t2}的区别，主要在于它们的区别。",
]

CLOSERS = [
    "综上所述，{t}不是别的，正是{t}本身。",
    "最后送大家一句话：听君一席话，如听一席话。",
    "以上就是关于{t}的全部内容，以及一部分内容。",
    "愿大家的{t}，都像{t}一样美好。",
]


def _setup_streams():
    """管道/重定向时强制 UTF-8 输出，避免 Windows 默认 GBK 报错。"""
    for s in (sys.stdout, sys.stderr):
        try:
            if s is not None and not s.isatty():
                s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def compose(rng, topic, count):
    t2 = rng.choice([x for x in TOPICS if x != topic])
    sents = [rng.choice(OPENERS).format(t=topic)]
    sents += [s.format(t=topic, t2=t2)
              for s in rng.sample(MIDDLES, count - 2)]
    sents.append(rng.choice(CLOSERS).format(t=topic))
    return "".join(sents)


def main(argv=None):
    _setup_streams()
    ap = argparse.ArgumentParser(
        description="生成“听君一席话，如听一席话”式废话段落")
    ap.add_argument("--count", type=int, default=5,
                    help=f"句子数 2~{2 + len(MIDDLES)}（默认 5）")
    ap.add_argument("--topic", default=None,
                    help="指定废话话题，如: 搬砖")
    ap.add_argument("--topics", action="store_true", help="列出可选话题")
    ap.add_argument("--seed", type=int, default=None, help="随机种子，可复现")
    a = ap.parse_args(argv)
    rng = random.Random(a.seed)

    if a.topics:
        print("可选话题: " + "、".join(TOPICS))
        return 0
    if not 2 <= a.count <= 2 + len(MIDDLES):
        print(f"--count 取值应为 2~{2 + len(MIDDLES)}", file=sys.stderr)
        return 1

    topic = a.topic if a.topic else rng.choice(TOPICS)
    text = compose(rng, topic, a.count)
    print("\n".join(textwrap.wrap(text, width=38)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
