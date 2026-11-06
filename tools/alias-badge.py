#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""alias-badge（匿名代号牌）—— 为匿名评审/匿名问卷批量生成不重复的"颜色+动物"代号表。

从内置颜色词与动物词的笛卡尔积中不放回抽取 N 个组合，保证互不重复；
支持 --seed 固定随机种子以便复现，支持 --csv 导出（utf-8-sig，Excel 可直接打开）。
中文字符按全角宽度对齐表格。

示例:
    python alias-badge.py --count 20                  # 生成 20 个代号
    python alias-badge.py -n 8 --seed 42              # 固定种子，结果可复现
    python alias-badge.py -n 8 --order animal-color   # 动物在前，如 熊猫·赤焰
    python alias-badge.py -n 5 --sep "-"              # 自定义连接符，如 赤焰-熊猫
    python alias-badge.py -n 100 --csv badges.csv     # 同时导出 CSV 文件

退出码: 0 成功；2 参数错误或词库组合不足。
"""

import argparse
import csv
import random
import sys
import unicodedata

# 内置词库：22 色 × 36 兽 = 792 种组合
COLORS = [
    "赤焰", "橙霞", "鎏金", "琥珀", "樱粉", "玫红", "绛紫", "翠竹",
    "青柠", "松绿", "天青", "湛蓝", "藏蓝", "黛紫", "雾灰", "银白",
    "象牙", "墨玉", "珊瑚", "月白", "茶白", "紫罗兰",
]
ANIMALS = [
    "熊猫", "云豹", "雪豹", "白鲸", "海豚", "狐狸", "猫头鹰", "企鹅",
    "梅花鹿", "刺猬", "蜂鸟", "天鹅", "水獭", "灵猫", "麋鹿", "犀鸟",
    "萤火虫", "章鱼", "白鹤", "松鼠", "玳瑁", "羚羊", "獾", "貉",
    "夜鹭", "锦鲤", "斑马", "驯鹿", "狼", "狐獴", "树懒", "穿山甲",
    "丹顶鹤", "信天翁", "小熊猫", "雪貂",
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


def disp_width(s):
    """按终端显示宽度计宽：全角字符（F/W）算 2 列，其余算 1 列。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("F", "W") else 1 for c in s)


def pad(s, width):
    """把字符串按显示宽度左对齐补空格到 width 列。"""
    return s + " " * max(0, width - disp_width(s))


def decode(index, order, sep):
    ci, ai = divmod(index, len(ANIMALS))
    color, animal = COLORS[ci], ANIMALS[ai]
    if order == "color-animal":
        return color + sep + animal
    return animal + sep + color


def build_parser():
    p = argparse.ArgumentParser(
        prog="alias-badge",
        description="批量生成不重复的匿名代号（颜色 + 动物），适合匿名评审/问卷。",
    )
    p.add_argument("-n", "--count", type=int, default=10, help="生成代号数量（默认 10）")
    p.add_argument("--seed", type=int, default=None, help="随机种子；指定后结果可复现")
    p.add_argument("--order", choices=("color-animal", "animal-color"), default="color-animal",
                   help="组合顺序（默认 color-animal，如 赤焰·熊猫）")
    p.add_argument("--sep", default="·", help="词与词之间的连接符（默认 ·）")
    p.add_argument("--csv", metavar="PATH", default=None,
                   help="额外导出到 CSV 文件（utf-8-sig 编码）")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    force_utf8_stdio()
    if args.count < 0:
        print("错误：--count 不能为负数。", file=sys.stderr)
        return 2
    total = len(COLORS) * len(ANIMALS)
    if args.count > total:
        print("错误：词库只有 %d 种组合，无法生成 %d 个不重复代号。" % (total, args.count),
              file=sys.stderr)
        return 2

    rng = random.Random(args.seed) if args.seed is not None else random.SystemRandom()
    picks = rng.sample(range(total), args.count)
    aliases = [decode(i, args.order, args.sep) for i in picks]

    numw = max(4, len(str(args.count)))
    alw = max((disp_width(a) for a in aliases), default=4)
    print(pad("编号", numw) + "  代号")
    print(pad("-" * numw, numw) + "  " + "-" * max(2, alw))
    for no, alias in enumerate(aliases, 1):
        print(pad(str(no), numw) + "  " + alias)

    if args.csv:
        try:
            with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["编号", "代号"])
                for no, alias in enumerate(aliases, 1):
                    writer.writerow([no, alias])
        except OSError as exc:
            print("错误：无法写入 CSV %s：%s" % (args.csv, exc), file=sys.stderr)
            return 2
        print("[已导出 CSV：%s]" % args.csv, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
