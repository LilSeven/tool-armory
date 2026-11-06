#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""御神签 —— 日本神社式大凶至大吉抽签，附签诗与解读。

模拟神社求签：按权重随机抽出一支"大吉→大凶"七等御神签，配七言签诗一首、
解签一句，以及愿望/恋爱/事业/财运/健康/旅行/失物七个方面的白话断语。
仅依赖 Python 标准库。

用法：
    python omikuji.py                       # 现在随机求一签
    python omikuji.py --date 2026-11-03     # 按日期定种子，同日同签
    python omikuji.py --date 2026-11-03 --name 小林
    python omikuji.py --seed 7              # 指定随机种子复现
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import random
import sys

# 等级与出现权重（合计 100），从吉到凶
FORTUNES = (
    ("大吉", 8),
    ("中吉", 20),
    ("吉", 30),
    ("小吉", 20),
    ("末吉", 12),
    ("凶", 8),
    ("大凶", 2),
)

# 七言签诗库：（四句, 解签一句）
POEMS = (
    (("春来花发映楼台，万事亨通不必猜。",
      "若得贵人相助力，前程步步上青天。"),
     "枯木逢春、花开满楼，喻时来运转；得贵人相助则一飞冲天。"),
    (("云开月出照前川，旧事重提莫怨天。",
      "守得云开终有日，春风一度再扬鞭。"),
     "阴霾散尽月色皎然，旧结可解；忍耐守正，来日重振旗鼓。"),
    (("莫笑枯木不成林，静待春雷第一声。",
      "时至自然花满树，何须烦恼苦伤情。"),
     "眼前沉寂只是伏笔，一声春雷即转生机；烦恼皆可放下。"),
    (("舟行绿水浪悠悠，帆稳风轻莫强求。",
      "若问归期何日是，月圆之夜下滩头。"),
     "风平浪静宜稳进、不宜强求；月圆之际自有圆满消息。"),
    (("石中藏玉少人知，一朝剖出便光辉。",
      "劝君切莫多犹疑，此去前程步步高。"),
     "怀才如玉藏于石中，时机一到光华自现；切忌犹疑坐失良机。"),
    (("雾锁山头山锁雾，眼前迷路莫心焦。",
      "待到日高雾散尽，回头即是旧时道。"),
     "眼前迷雾重重、看不清方向时稍安勿躁；日出雾散路自明。"),
    (("花开花谢总有时，人事纷纷莫强为。",
      "守己安分天注定，不必匆匆怨别离。"),
     "花开花谢各有时序，强求无益；安分守己自有安排。"),
    (("秋水无尘浸碧天，一行征雁下平川。",
      "前程有路休回首，直上云梯第几层。"),
     "天高水阔、征雁有路，前路明朗；一心向前，不必回头。"),
    (("明月当空本自圆，只因浮云遮眼前。",
      "云散终归明月现，何愁不见旧时天。"),
     "圆满本自俱足，只是暂被浮云遮蔽；云开之日一切如初。"),
    (("枯井生泉复旧流，困龙得水喜悠悠。",
      "从今莫叹时机晚，一到风云便出头。"),
     "困龙得水、枯井重泉，久困将解；风云一至即腾达。"),
    (("风急天寒且驻舟，静观波浪不须愁。",
      "他年风顺潮头稳，万里前程一望收。"),
     "风急天寒宜停泊静守、不宜强行出发；待风顺潮平一日万里。"),
    (("路入高山险处行，低头缓步自平稳。",
      "莫贪捷径伤大体，守正方能到顶程。"),
     "山路虽险，缓步低头则稳；舍捷径、守正道，方能登顶。"),
)

CATEGORIES = ("愿望", "恋爱", "事业", "财运", "健康", "旅行", "失物")

# 各签等 × 各方面的白话断语
ADVICE = {
    "大吉": {
        "愿望": "心想事成，宜立即行动。",
        "恋爱": "良缘天成，大胆表白必有好讯。",
        "事业": "鸿运当头，进取可得名利。",
        "财运": "财源广进，正偏财皆旺。",
        "健康": "元气充沛，旧疾亦将痊愈。",
        "旅行": "出行大吉，所到之处皆遇贵人。",
        "失物": "失物速还，往东边高处寻。",
    },
    "中吉": {
        "愿望": "愿望可成，但需再候一程。",
        "恋爱": "缘分渐近，真诚相待自有进展。",
        "事业": "稳中有升，得力助手即将出现。",
        "财运": "收入平稳，小有盈余。",
        "健康": "大体无恙，注意作息规律。",
        "旅行": "旅途平顺，宜结伴而行。",
        "失物": "失而复得，多在常去之处。",
    },
    "吉": {
        "愿望": "水到渠成，勿急勿躁。",
        "恋爱": "缘分中等，多制造相处机会。",
        "事业": "按部就班，功到自然成。",
        "财运": "财如细水，积少成多。",
        "健康": "注意小病小痛，及早调理。",
        "旅行": "近处为宜，远行劳顿。",
        "失物": "可在原地附近寻得。",
    },
    "小吉": {
        "愿望": "小愿易遂，大愿需再候时机。",
        "恋爱": "平稳淡雅，细水长流即是福。",
        "事业": "稳守为上，冒进则有失。",
        "财运": "薄利可图，切忌贪多。",
        "健康": "无大碍，宜清淡饮食。",
        "旅行": "短途小游，可怡身心。",
        "失物": "寻回希望约半，尽力即安。",
    },
    "末吉": {
        "愿望": "先难后易，年末可见转机。",
        "恋爱": "当下平淡，转身处别有风景。",
        "事业": "近处无光，远景可期。",
        "财运": "守成为宜，勿作担保借贷。",
        "健康": "劳累积身，宜早休养。",
        "旅行": "行程多有波折，宜改期。",
        "失物": "暂难寻回，来日或自现。",
    },
    "凶": {
        "愿望": "时机未至，宜静待不宜强求。",
        "恋爱": "口舌是非多，退一步海阔天空。",
        "事业": "阻力重重，谨言慎行。",
        "财运": "破财消灾，捂紧钱袋。",
        "健康": "小恙勿拖，及早就医。",
        "旅行": "诸事不宜远行。",
        "失物": "失物难寻，作罢为上。",
    },
    "大凶": {
        "愿望": "所求皆阻，宜守静修身。",
        "恋爱": "缘分散乱，不宜强留。",
        "事业": "诸事停滞，宜蛰伏养精蓄锐。",
        "财运": "大耗之象，分文不宜轻掷。",
        "健康": "起居失常恐生大病，务必自爱。",
        "旅行": "此路不通，另择他日。",
        "失物": "寻回无望，舍财免灾。",
    },
}


def _date_arg(value: str) -> _dt.date:
    try:
        return _dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"日期格式应为 YYYY-MM-DD，收到：{value!r}")


def _resolve_rng(args) -> random.Random:
    if args.seed is not None:
        return random.Random(args.seed)
    if args.date is not None:
        material = f"omikuji|{args.date.isoformat()}|{args.name or ''}"
        return random.Random(hashlib.sha256(material.encode("utf-8")).hexdigest())
    return random.Random()


def draw(rng: random.Random):
    """返回 (签等, 签号, 四句诗, 解签)。"""
    names = [f[0] for f in FORTUNES]
    weights = [f[1] for f in FORTUNES]
    rank = rng.choices(names, weights=weights, k=1)[0]
    poem, note = POEMS[rng.randrange(len(POEMS))]
    number = rng.randint(1, 100)
    return rank, number, poem, note


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="omikuji", description="日本神社式御神签：大凶至大吉，附签诗与解读")
    parser.add_argument("--date", type=_date_arg, default=None,
                        help="按日期定种子（同日同签），格式 YYYY-MM-DD")
    parser.add_argument("--name", default="", help="求签人名字，配合 --date 使用")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，便于复现")
    args = parser.parse_args(argv)

    rng = _resolve_rng(args)
    rank, number, poem, note = draw(rng)

    line = "─" * 34
    print("⛩ 御神签 ⛩")
    print(line)
    print(f"第 {number} 签 · {rank}")
    print()
    print("签诗：")
    for i in range(0, len(poem), 2):
        print("  " + "".join(poem[i:i + 2]))
    print()
    print(f"解签：{note}")
    print()
    print("──诸事断──")
    for cat in CATEGORIES:
        print(f"{cat}：{ADVICE[rank][cat]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
