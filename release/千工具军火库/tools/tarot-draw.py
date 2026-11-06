#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""塔罗三张抽 —— 抽过去/现在/未来三张塔罗牌，含逆位设定。

从完整 78 张韦特塔罗牌（22 大阿尔卡那 + 56 小阿尔卡那）中不重复抽出
三张，分别对应"过去 / 现在 / 未来"；每张带正逆位与牌意关键词，
最后按正逆位组合给出结语。仅依赖 Python 标准库。

用法：
    python tarot-draw.py                  # 随机三张
    python tarot-draw.py --seed 7         # 指定种子复现
    python tarot-draw.py --major-only     # 只用大阿尔卡那
    python tarot-draw.py --upright-only   # 全部正位（关闭逆位）
"""

from __future__ import annotations

import argparse
import random
import sys

# 大阿尔卡那：(编号, 中文, 英文, 正位关键词, 逆位关键词)
MAJOR = (
    (0, "愚者", "The Fool", "新的开始、自由与冒险", "鲁莽、迷失与停滞"),
    (1, "魔术师", "The Magician", "资源具足、心想事成", "巧言令色、力不从心"),
    (2, "女祭司", "The High Priestess", "直觉、静默与内在智慧", "秘密压顶、忽视直觉"),
    (3, "皇后", "The Empress", "丰饶、滋养与创造", "过度干预、创造枯竭"),
    (4, "皇帝", "The Emperor", "秩序、权威与掌控", "专断、僵化失序"),
    (5, "教皇", "The Hierophant", "传统、指引与传承", "教条束缚、离经叛道"),
    (6, "恋人", "The Lovers", "契合、选择与亲密", "分歧、失衡的取舍"),
    (7, "战车", "The Chariot", "意志、胜利与前进", "失控、原地打转"),
    (8, "力量", "Strength", "以柔克刚、温柔自持", "自我怀疑、被情绪反噬"),
    (9, "隐士", "The Hermit", "内省、求索与独处", "自我封闭、孤立无援"),
    (10, "命运之轮", "Wheel of Fortune", "转机、周期与际遇", "时运不济、抗拒变化"),
    (11, "正义", "Justice", "公正、权衡与因果", "偏颇、逃避责任"),
    (12, "倒吊人", "The Hanged Man", "换位思考、以退为进", "徒劳僵持、无谓牺牲"),
    (13, "死神", "Death", "终结与重生、断舍离", "抗拒结束、拖泥带水"),
    (14, "节制", "Temperance", "调和、平衡与耐心", "失衡、极端化"),
    (15, "恶魔", "The Devil", "欲望与束缚的警示", "挣脱枷锁、重获自由"),
    (16, "高塔", "The Tower", "骤变、崩塌与觉醒", "勉强支撑、余震未平"),
    (17, "星星", "The Star", "希望、疗愈与灵感", "信心低落、希望蒙尘"),
    (18, "月亮", "The Moon", "迷雾、潜意识与不安", "迷雾渐散、真相浮现"),
    (19, "太阳", "The Sun", "光明、成功与活力", "乌云蔽日、短暂低潮"),
    (20, "审判", "Judgement", "觉醒、复盘与召唤", "逃避检讨、错失召唤"),
    (21, "世界", "The World", "圆满、达成与新征程", "功亏一篑、未竟之局"),
)

# 小阿尔卡那：四元素牌组（中文, 英文, 正位主旨, 逆位主旨）
SUITS = (
    ("权杖", "Wands", "行动、热情与开拓", "冲动、拖延与内耗"),
    ("圣杯", "Cups", "情感、直觉与联结", "情绪化、疏离与失落"),
    ("宝剑", "Swords", "思考、清晰与决断", "焦虑、冲突与自困"),
    ("星币", "Pentacles", "务实、积累与安稳", "停滞、匮乏与固执"),
)

# 数字牌与宫廷牌（英文, 中文, 正位补充, 逆位补充）
RANKS = (
    ("Ace", "王牌", "新的开端", "错失的起势"),
    ("Two", "二", "权衡与选择", "摇摆不定"),
    ("Three", "三", "初步成果", "进度受阻"),
    ("Four", "四", "稳固与休整", "不安于室"),
    ("Five", "五", "冲突与考验", "走出低谷"),
    ("Six", "六", "顺利推进", "往返反复"),
    ("Seven", "七", "评估与坚持", "半途而废"),
    ("Eight", "八", "加速与专注", "力不从心"),
    ("Nine", "九", "临近收获的储备", "强撑的疲惫"),
    ("Ten", "十", "阶段性圆满", "过载与收尾难"),
    ("Page", "侍从", "学习与萌芽", "心浮气躁"),
    ("Knight", "骑士", "冲锋与推进", "横冲直撞"),
    ("Queen", "王后", "照护与成熟掌控", "过度操劳"),
    ("King", "国王", "统领与决断", "刚愎自用"),
)

POSITIONS = ("过去", "现在", "未来")

CONCLUSION = {
    "all-up": (
        "三张皆正位：事态清晰、路是顺的，大胆按计划推进即可。",
        "牌面一路坦荡，能量完整，心想事成的概率相当高。",
    ),
    "all-rev": (
        "三张皆逆位：阻力多在内不在外，先把自己理顺再谋事。",
        "牌面集体倒转，宜缓不宜急，旧模式不破新局不来。",
    ),
    "mixed": (
        "正逆交织：过去牵绊未清，把握好当下这一步，未来自会转正。",
        "有明有暗，顺势的部分乘胜追击，卡住的部分换个角度。",
        "半明半暗的局，关键在你现在这张牌给出的功课。",
    ),
}


def build_deck(major_only: bool):
    """返回 [(标题, 英文名, 正位关键词, 逆位关键词), ...]，共 78 或 22 张。"""
    deck = []
    for num, cn, en, up, rev in MAJOR:
        deck.append((f"{num}. {cn}", en, up, rev))
    if not major_only:
        for suit_cn, suit_en, s_up, s_rev in SUITS:
            for rank_en, rank_cn, r_up, r_rev in RANKS:
                deck.append((
                    f"{suit_cn}{rank_cn}",
                    f"{rank_en} of {suit_en}",
                    f"{s_up}·{r_up}",
                    f"{s_rev}·{r_rev}",
                ))
    return deck


def draw_cards(rng: random.Random, major_only: bool, allow_reversed: bool):
    deck = build_deck(major_only)
    rng.shuffle(deck)
    out = []
    for card in deck[:len(POSITIONS)]:
        reversed_ = allow_reversed and rng.random() < 0.5
        out.append((card, reversed_))
    return out


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="tarot-draw", description="抽过去/现在/未来三张塔罗牌，含逆位")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，便于复现")
    parser.add_argument("--major-only", action="store_true",
                        help="只用 22 张大阿尔卡那")
    parser.add_argument("--upright-only", action="store_true",
                        help="全部正位（关闭逆位）")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    cards = draw_cards(rng, args.major_only, not args.upright_only)

    line = "─" * 34
    print("🔮 塔罗三张抽（过去 · 现在 · 未来）")
    print(line)
    for idx, (card, reversed_) in enumerate(cards):
        title, en, up_kw, rev_kw = card
        pos = POSITIONS[idx]
        marker = "①②③"[idx]
        orient = "逆位" if reversed_ else "正位"
        kw = rev_kw if reversed_ else up_kw
        print(f"{marker} {pos} —— 「{title} {en}」{orient}")
        print(f"   牌意：{kw}")
    print(line)

    flags = [r for _, r in cards]
    if all(flags):
        pool = CONCLUSION["all-rev"]
    elif not any(flags):
        pool = CONCLUSION["all-up"]
    else:
        pool = CONCLUSION["mixed"]
    print(f"结语：{rng.choice(pool)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
