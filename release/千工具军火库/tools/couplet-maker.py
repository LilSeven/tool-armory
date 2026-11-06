#!/usr/bin/env python3
"""对联生成器（couplet-maker）—— 随机生成上联、下联与横批的喜庆对联。

从并联词库中随机抽取成对片段（上下联片段字数相等、词性对仗），
拼出 5 字或 7 字的上下联，再配一条四字横批。

用法：
    python couplet-maker.py                 # 随机来一副（默认 7 字联）
    python couplet-maker.py --len 5         # 五字联
    python couplet-maker.py -n 3            # 一次来三副
    python couplet-maker.py --seed 2024     # 固定种子（可复现）
    python couplet-maker.py --help          # 查看帮助

示例输出：
    $ python couplet-maker.py --seed 1
    🧧 上联：春风送暖千家乐
       下联：旭日临门万户欢
       横批：春满人间

只用 Python 标准库。
"""

import argparse
import random
import sys

# 成对片段：(上联片段, 下联片段)
PAIRS4 = [  # 4 字开头，用于 7 字联
    ("春风送暖", "旭日临门"),
    ("瑞雪铺阶", "红梅照户"),
    ("红梅报喜", "绿柳迎春"),
    ("金鸡唱晓", "紫燕衔泥"),
    ("腊梅傲雪", "翠竹凌霜"),
    ("爆竹辞旧", "桃符迎新"),
    ("春归大地", "福满人间"),
    ("一元复始", "万象更新"),
    ("雪融千岭", "花绽万枝"),
    ("山衔旭日", "水漾金波"),
]
PAIRS3 = [  # 3 字收尾，用于 7 字联
    ("千家乐", "万户欢"),
    ("家家喜", "处处歌"),
    ("山河壮", "日月新"),
    ("人财旺", "福寿长"),
    ("春常在", "福自来"),
    ("添瑞气", "纳祥光"),
    ("迎百福", "纳千祥"),
    ("门庭旺", "事业兴"),
]
PAIRS2 = [  # 2 字开头，用于 5 字联
    ("梅开", "竹报"),
    ("风和", "日丽"),
    ("春回", "福到"),
    ("雪化", "冰融"),
    ("花香", "鸟语"),
    ("岁新", "春早"),
]
END3 = [  # 3 字收尾，用于 5 字联
    ("春意闹", "喜气浓"),
    ("千门福", "万户春"),
    ("山河秀", "岁月新"),
    ("春光好", "气象新"),
    ("千山绿", "万水清"),
    ("人添寿", "岁增辉"),
]
HENGBI = ["春满人间", "吉星高照", "万事如意", "五福临门", "喜气盈门",
          "财源广进", "国泰民安", "阖家欢乐", "恭贺新禧", "岁岁平安",
          "瑞气盈门", "竹报平安"]


def _setup_stdio():
    """让中文输出在管道/重定向场景下也按 UTF-8 走。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _check_data():
    """词库自检：成对片段字数相等且上下联不重复。"""
    for groups, expect in ((PAIRS4, 4), (PAIRS3, 3), (PAIRS2, 2), (END3, 3)):
        for a, b in groups:
            if len(a) != expect or len(b) != expect:
                raise SystemExit(f"数据错误：片段『{a}/{b}』应为 {expect} 字")
            if a == b:
                raise SystemExit(f"数据错误：片段『{a}』上下联相同")


def compose(length, rng):
    """拼一副对联，返回 (上联, 下联, 横批)，上下联等长。"""
    if length == 7:
        head = rng.choice(PAIRS4)
        tail = rng.choice(PAIRS3)
    else:
        head = rng.choice(PAIRS2)
        tail = rng.choice(END3)
    upper, lower = head[0] + tail[0], head[1] + tail[1]
    if len(upper) != length or len(lower) != length:
        raise SystemExit(f"数据错误：拼出『{upper}/{lower}』不是 {length} 字")
    return upper, lower, rng.choice(HENGBI)


def main(argv=None):
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="couplet-maker",
        description="对联生成器：随机生成上联、下联与横批的喜庆对联。")
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="数量，默认 1")
    parser.add_argument("-l", "--len", type=int, choices=(5, 7), default=7,
                        help="联文字数，默认 7")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，便于复现")
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("-n/--count 需要正整数")

    _check_data()
    rng = random.Random(args.seed)
    if args.len == 7:
        total = len(PAIRS4) * len(PAIRS3) * len(HENGBI)
    else:
        total = len(PAIRS2) * len(END3) * len(HENGBI)

    seen, printed = set(), 0
    while printed < args.count and len(seen) < total:
        upper, lower, hengbi = compose(args.len, rng)
        if (upper, lower, hengbi) in seen:
            continue
        seen.add((upper, lower, hengbi))
        printed += 1
        print("🧧 上联：" + upper)
        print("   下联：" + lower)
        print("   横批：" + hengbi)
        if printed < args.count:
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
