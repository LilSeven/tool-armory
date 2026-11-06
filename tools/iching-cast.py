#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""六爻起卦 —— 模拟三枚铜钱起卦，输出卦名与白话断语。

按传统"三枚铜钱法"模拟六次摇卦：每枚铜钱"字"记 2、"背"记 3，
三枚合计 6=老阴、7=少阳、8=少阴、9=老阳，老阴老阳为动爻；
自初爻至六爻装成本卦，动爻翻转得变卦，输出卦名、卦象与白话断语。
仅依赖 Python 标准库。

用法：
    python iching-cast.py                # 随机起一卦
    python iching-cast.py --seed 3       # 指定种子复现
    python iching-cast.py --question 换工作之事
"""

from __future__ import annotations

import argparse
import random
import sys

# 八卦：(三爻二进制自下而上, 卦名, 卦符, 卦象)
TRIGRAMS = {
    "111": ("乾", "☰", "天"),
    "110": ("兑", "☱", "泽"),
    "101": ("离", "☲", "火"),
    "100": ("震", "☳", "雷"),
    "011": ("巽", "☴", "风"),
    "010": ("坎", "☵", "水"),
    "001": ("艮", "☶", "山"),
    "000": ("坤", "☷", "地"),
}

# 六十四卦，按文王卦序排列：(下卦, 上卦, 卦名, 白话断语)
HEXAGRAMS = (
    ("111", "111", "乾为天", "刚健有力，自强不息，宜进取不宜妄动。"),
    ("000", "000", "坤为地", "厚德载物，柔顺守成，先迷后得。"),
    ("100", "010", "水雷屯", "万事起头难，宜蓄力待时，忌急进。"),
    ("010", "001", "山水蒙", "蒙昧待启，宜求学问道、拜见明师。"),
    ("111", "010", "水天需", "时机未到，耐心等待，饮食宴乐自安。"),
    ("010", "111", "天水讼", "争讼之地，宜退让和解，勿逞口舌。"),
    ("010", "000", "地水师", "兴师动众，需严明纪律，师出有名。"),
    ("000", "010", "水地比", "亲比相依，宜结盟合作，择善而从。"),
    ("111", "011", "风天小畜", "力量小蓄，事有小阻，以柔克刚。"),
    ("110", "111", "天泽履", "如履虎尾，谨慎行事，守礼则吉。"),
    ("111", "000", "地天泰", "天地交泰，上下相通，大吉之象。"),
    ("000", "111", "天地否", "闭塞不通，宜守静待变，否极泰来。"),
    ("101", "111", "天火同人", "志同道合，宜协力同心，光明行事。"),
    ("111", "101", "火天大有", "盛大丰有，名实相符，宜广施惠泽。"),
    ("001", "000", "地山谦", "谦谦君子，卑以自牧，谦受益满招损。"),
    ("000", "100", "雷地豫", "顺动而豫，喜乐将临，忌乐极生悲。"),
    ("100", "110", "泽雷随", "随时而动，择善而从，不可盲随。"),
    ("011", "001", "山风蛊", "积弊待整，宜革故鼎新，整顿内部。"),
    ("110", "000", "地泽临", "阳长阴消，居高临下，宜把握时机。"),
    ("000", "011", "风地观", "观仰之光，多看多学，宜静观大势。"),
    ("100", "101", "火雷噬嗑", "咬合除梗，遇阻则断，明罚敕法。"),
    ("101", "001", "山火贲", "文饰之美，宜修饰外表，勿忘本质。"),
    ("000", "001", "山地剥", "剥落之象，阴盛阳衰，宜守不宜进。"),
    ("100", "000", "地雷复", "一阳来复，循环往复，迷途知返则吉。"),
    ("100", "111", "天雷无妄", "不妄为则吉，守正去邪，顺其自然。"),
    ("111", "001", "山天大畜", "大有积蓄，止而蓄能，宜养德待时。"),
    ("100", "001", "山雷颐", "颐养之道，慎言节食，自求口实。"),
    ("011", "110", "泽风大过", "非常之时，过人之举，刚过易折。"),
    ("010", "010", "坎为水", "重险叠陷，守持中道，履险如夷。"),
    ("101", "101", "离为火", "附丽光明，宜借势而上，忌急躁。"),
    ("001", "110", "泽山咸", "交感相应，两情相悦，宜坦诚相待。"),
    ("011", "100", "雷风恒", "持之以恒，守常则吉，忌朝三暮四。"),
    ("001", "111", "天山遁", "退避为宜，远小人而全身，宜隐忍。"),
    ("111", "100", "雷天大壮", "声势浩大，壮而不暴，以正制之。"),
    ("000", "101", "火地晋", "日出地上，晋升进取，柔而上行。"),
    ("101", "000", "地火明夷", "光明入地，晦而转明，宜韬光养晦。"),
    ("101", "011", "风火家人", "齐家之道，各正其位，内外有别。"),
    ("110", "101", "火泽睽", "乖离相背，小事可成，大事宜和解。"),
    ("001", "010", "水山蹇", "行路艰难，遇险则止，宜反身修德。"),
    ("010", "100", "雷水解", "险散难解，百事消散，宜速谋出路。"),
    ("110", "001", "山泽损", "损下益上，舍得舍得，先损后得。"),
    ("100", "011", "风雷益", "损上益下，风雷相助，宜乘势作为。"),
    ("111", "110", "泽天夬", "决而能和，当机立断，光明正大除弊。"),
    ("011", "111", "天风姤", "不期而遇，谨防阴私，勿取非分之遇。"),
    ("000", "110", "泽地萃", "荟萃聚集，宜聚人成事，备礼而敬。"),
    ("011", "000", "地风升", "上升之象，积小成大，宜乘虚而入。"),
    ("010", "110", "泽水困", "困顿受阻，有言不信，宜处困守志。"),
    ("011", "010", "水风井", "井养不穷，宜修内政、供养众人。"),
    ("101", "110", "泽火革", "变革之时，顺天应人，宜除旧布新。"),
    ("011", "101", "火风鼎", "鼎新之象，稳固尊荣，宜养贤任能。"),
    ("100", "100", "震为雷", "雷声震动，临危不乱，先惧后笑。"),
    ("001", "001", "艮为山", "止于当止，静如山岳，时止则止。"),
    ("001", "011", "风山渐", "循序渐进，鸿雁于飞，按部就班则吉。"),
    ("110", "100", "雷泽归妹", "名分未正，守卑谦则吉，勿急于求成。"),
    ("101", "100", "雷火丰", "丰盛之极，明动相资，盛时更要守正。"),
    ("001", "101", "火山旅", "旅途在外，谨慎小心，宜柔顺自处。"),
    ("011", "011", "巽为风", "随顺而入，谦逊行事，反复申命。"),
    ("110", "110", "兑为泽", "和悦相说，朋友讲习，以诚相待则吉。"),
    ("010", "011", "风水涣", "涣散之象，宜聚拢人心、化险为夷。"),
    ("110", "010", "水泽节", "节制有度，安节则吉，苦节不可久。"),
    ("110", "011", "风泽中孚", "诚信相感，中心诚实，可涉大川。"),
    ("001", "100", "雷山小过", "小事可过，大事宜敛，飞鸟宜下不宜上。"),
    ("101", "010", "水火既济", "功德已成，初吉终乱，守成防患。"),
    ("010", "101", "火水未济", "事未有成，慎终如始，否极将泰。"),
)

# (下卦, 上卦) -> (卦序号, 卦名, 断语)
HEX_KEY = {}
for _no, (_lo, _up, _name, _text) in enumerate(HEXAGRAMS, start=1):
    HEX_KEY[(_lo, _up)] = (_no, _name, _text)
if len(HEX_KEY) != 64:
    raise RuntimeError("六十四卦表配置有误：存在重复的上下卦组合")

COIN_VALUE_NAME = {6: "老阴", 7: "少阳", 8: "少阴", 9: "老阳"}
YANG_GLYPH, YIN_GLYPH = "⚊", "⚋"
POSITION_WORDS = ("初", "二", "三", "四", "五", "上")


def toss_one_line(rng: random.Random):
    """摇一次：三枚铜钱，字=2 背=3。返回 (铜钱面, 数值, 名称, 是否阳, 是否动)。"""
    coins = [rng.choice((2, 3)) for _ in range(3)]
    value = sum(coins)
    yang = value in (7, 9)
    changing = value in (6, 9)
    faces = " ".join("背" if c == 3 else "字" for c in coins)
    return faces, value, COIN_VALUE_NAME[value], yang, changing


def line_label(index: int, yang: bool) -> str:
    """第 index 爻（0=初）的爻题，如 初九 / 六二 / 上六。"""
    word = "九" if yang else "六"
    pos = POSITION_WORDS[index]
    if index == 0:
        return f"初{word}"
    if index == 5:
        return f"上{word}"
    return f"{word}{pos}"


def lookup(lines: str):
    """lines 为自下而上六位 0/1 串，返回 (序号, 卦名, 断语)。"""
    lower, upper = lines[:3], lines[3:]
    return HEX_KEY[(lower, upper)]


def describe(lines: str, changing_idx):
    """拼装断语区：本卦、动爻、变卦与白话断语。"""
    no, name, text = lookup(lines)
    lower = TRIGRAMS[lines[:3]]
    upper = TRIGRAMS[lines[3:]]
    parts = [f"本卦：{name}（第 {no} 卦）· {upper[0]}上{lower[0]}下"]
    moving = [line_label(i, lines[i] == "1") for i in changing_idx]
    if not changing_idx:
        parts.append("动爻：无，六爻安静")
    else:
        parts.append("动爻：" + "、".join(moving))
        flipped = "".join(
            ("0" if b == "1" else "1") if i in changing_idx else b
            for i, b in enumerate(lines))
        cno, cname, _ = lookup(flipped)
        parts.append(f"变卦：{cname}（第 {cno} 卦）")
    parts.append(f"断语：{text}")
    n = len(changing_idx)
    if n == 0:
        parts.append("（六爻安静：事体平稳，以本卦断之。）")
    elif n <= 2:
        parts.append("（动爻少则事机明，所动之爻即关键所在。）")
    elif n == 3:
        parts.append("（三爻齐动，主客交争，进退宜再酌。）")
    elif n < 6:
        parts.append("（动爻众多，变数大，宜缓图之。）")
    else:
        parts.append("（六爻皆动，旧局全翻，以变卦为主断。）")
    return "\n".join(parts)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="iching-cast", description="三枚铜钱六爻起卦，输出卦名与白话断语")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，便于复现")
    parser.add_argument("--question", default="", help="所问何事（仅作记录展示）")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    lines_bits = []      # 自下而上，"1"为阳
    changing_idx = []
    logs = []

    print("⛁ 六爻起卦 · 三枚铜钱法 ⛁")
    if args.question:
        print(f"所问：{args.question}")
    print("─" * 34)
    print("自初爻摇至六爻：")
    for i in range(6):
        faces, value, name, yang, changing = toss_one_line(rng)
        if changing:
            changing_idx.append(i)
        lines_bits.append("1" if yang else "0")
        glyph = YANG_GLYPH if yang else YIN_GLYPH
        mark = (" ○ 动" if value == 9 else " ✕ 动") if changing else ""
        logs.append(f"  {line_label(i, yang)}：{faces} → {value} · {name} {glyph}{mark}")
    print("\n".join(logs))

    lines = "".join(lines_bits)
    print("─" * 34)
    print("卦象（上爻在上）：")
    for i in range(5, -1, -1):
        yang = lines[i] == "1"
        glyph = YANG_GLYPH if yang else YIN_GLYPH
        if i in changing_idx:
            glyph += " ○" if yang else " ✕"
        print(f"  {glyph}   {POSITION_WORDS[i]}爻")
    print("─" * 34)
    print(describe(lines, changing_idx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
