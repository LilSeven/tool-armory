#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fortune-cookie（签语饼）—— 经典 fortune 命令的克隆，随机输出一条签语或格言。

内置 36 条中文签语/格言；亦兼容经典 fortune 文件格式（每条签语一段，
段与段之间用仅含 "%" 的行分隔），可用 --file 换成自己的签语库。

示例:
    python fortune-cookie.py                  # 随机来一条
    python fortune-cookie.py --seed 7         # 固定种子（可复现，适合测试）
    python fortune-cookie.py -n 3             # 一次抽 3 条
    python fortune-cookie.py --file my.txt    # 从自定义签语库抽取
    python fortune-cookie.py --stats          # 查看签语库条数

退出码: 0 成功；2 参数错误、签语库为空或不可读。
"""

import argparse
import random
import re
import sys

FORTUNES = [
    "机会总是留给已经出发的人。",
    "今天适合把最难的那件事先做掉，剩下的会自己排队。",
    "少刷手机，多看云。",
    "你担心的 99% 坏结果，连入场券都没拿到。",
    "慢慢来，比较快。",
    "运气是概率的昵称，多试几次就熟了。",
    "把 Deadline 当赠品，而不是枷锁。",
    "真正的敌人是：再睡五分钟。",
    "今天的你，是昨天的你所期待的样子吗？",
    "山不转水转，接口不转文档转。",
    "喝水，抬头，伸个懒腰——这就是此刻最重要的事。",
    "复杂的问题拆开看，通常只是三件简单的事叠在一起。",
    "敢说“我不知道”的人，走得最远。",
    "星星不会因为没人看，就不发光。",
    "你的幸运数字是 42。\n今天就照着它凑个整吧。",
    "提交代码之前先写测试，签语饼今晚请客。",
    "别急着填满日程表，空白也是好东西。",
    "竹子前四年只长三厘米，第五年每天长三十厘米——你可能正在第四年。",
    "允许自己今天只做到八十分。",
    "那件你拖了一周的事，其实只需要十分钟。",
    "天气不影响心情，影响心情的是没带伞。",
    "读一本旧书，胜过收藏十本新书。",
    "一起做事的人，比待办清单更重要。",
    "今晚适合早点睡，梦里没有甲方。",
    "你的努力正在排队兑奖，请勿中途离场。",
    "与其寻找完美的工具，不如先完成糟糕的第一版。",
    "小小的复利，大大的奇迹。",
    "忌打断别人；宜听完再说。",
    "幸运色是蓝色。\n穿错了也没关系，运气不看衣橱。",
    "走错的路也会被画进你的地图。",
    "把感谢说出口，比放在心里折旧划算。",
    "问题不可怕，可怕的是没人提问。",
    "你不是效率低，只是同时在做三件事——挑一件吧。",
    "明天的你会感谢今晚备好伞的自己。",
    "保持好奇，饿了就吃饭。",
    "此签没有有效期，好话永远不过期。",
]


def force_utf8_stdio():
    """输出流编码非 UTF-8 时（如 Windows 管道默认 GBK）切到 UTF-8，避免乱码或报错。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
            if enc and enc != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load_builtin():
    return list(FORTUNES)


def load_file(path):
    """读取经典 fortune 格式：各条签语之间用仅含 '%' 的行分隔。"""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    blocks = re.split(r"(?m)^%[ \t]*$", text)
    return [b.strip() for b in blocks if b.strip()]


def build_parser():
    p = argparse.ArgumentParser(
        prog="fortune-cookie",
        description="随机输出一条签语或格言（fortune 命令克隆）。",
    )
    p.add_argument("-f", "--file", metavar="PATH", default=None,
                   help="自定义签语库文件（fortune 格式，% 行分隔）")
    p.add_argument("-n", "--count", type=int, default=1, help="输出条数（默认 1）")
    p.add_argument("--seed", type=int, default=None, help="随机种子；指定后结果可复现")
    p.add_argument("--stats", action="store_true", help="只显示签语库条数，不抽签")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    force_utf8_stdio()
    if args.file:
        try:
            items = load_file(args.file)
        except OSError as exc:
            print("错误：无法读取签语库 %s：%s" % (args.file, exc), file=sys.stderr)
            return 2
        source = args.file
    else:
        items = load_builtin()
        source = "内置签语库"
    if not items:
        print("错误：签语库为空。", file=sys.stderr)
        return 2
    if args.stats:
        print("%s 共 %d 条签语。" % (source, len(items)))
        return 0
    if args.count < 1:
        print("错误：--count 至少为 1。", file=sys.stderr)
        return 2

    rng = random.Random(args.seed) if args.seed is not None else random.SystemRandom()
    picked = rng.sample(items, min(args.count, len(items)))
    print("\n\n".join(picked))
    return 0


if __name__ == "__main__":
    sys.exit(main())
