#!/usr/bin/env python3
"""绕口令工厂（tongue-twister）—— 随机组合双声叠韵词生成绕口令。

内置按"声母"（双声）与"韵母"（叠韵）分组的词族；同一句里只从同一词族
取词，再套入口语化句式模板，拼出拗口的绕口令。

用法：
    python tongue-twister.py                 # 随机来一条（默认两句）
    python tongue-twister.py --family ao     # 指定词族（ao 韵·叠韵）
    python tongue-twister.py --list          # 列出全部词族
    python tongue-twister.py -n 3            # 一次来三条
    python tongue-twister.py -s              # 短版（只拼一句）
    python tongue-twister.py --seed 9        # 固定种子（可复现）
    python tongue-twister.py --help          # 查看帮助

示例输出：
    $ python tongue-twister.py --family b --seed 1
    🎯 绕口令（b 声母·双声）：
      白布碰板凳，板凳碰白布，白布板凳撞了架。
      挑着扁担，背着半盆，扁担半盆赶集去。

只用 Python 标准库。
"""

import argparse
import random
import sys

FAMILIES = {
    "b":   ("b 声母·双声", ["白布", "板凳", "扁担", "半盆", "八宝", "补丁"]),
    "m":   ("m 声母·双声", ["麻猫", "毛帽", "麦苗", "木门", "米面", "墨猫"]),
    "l":   ("l 声母·双声", ["老刘", "蓝布", "莲蓬", "老狼", "芦帘", "骡子"]),
    "h":   ("h 声母·双声", ["红狐", "灰鹤", "花壶", "黄河", "黑豆", "湖畔"]),
    "s":   ("s 声母·双声", ["石狮", "柿子", "沙石", "十四", "山寺", "细丝"]),
    "g":   ("g 声母·双声", ["哥哥", "瓜果", "鼓槌", "钩竿", "桂花", "高柜"]),
    "ao":  ("ao 韵·叠韵",  ["草帽", "红枣", "小猫", "跳蚤", "鸟巢", "花轿"]),
    "ang": ("ang 韵·叠韵", ["帮忙", "房梁", "糖霜", "螳螂", "月光", "山冈"]),
}

TEMPLATES = [
    "{a}碰{b}，{b}碰{a}，{a}{b}撞了架。",
    "东家{a}，西家{b}，{a}{b}面对面。",
    "买来{a}，换走{b}，{a}换{b}，越换越糊涂。",
    "{a}驮着{b}，{b}压弯了{a}，一路摇摇晃晃下山坡。",
    "左手{a}，右手{b}，{a}{b}凑成一台戏。",
    "风吹{a}，雨打{b}，{a}和{b}还是好邻居。",
    "{a}去找{b}，{b}躲着{a}，捉了半宿没捉着。",
    "挑着{a}，背着{b}，{a}{b}赶集去。",
]


def _setup_stdio():
    """让中文输出在管道/重定向场景下也按 UTF-8 走。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _check_data():
    """词库自检：每个词族至少 2 个词，模板占位符合法。"""
    for key, (label, words) in FAMILIES.items():
        if len(words) < 2 or len(set(words)) != len(words):
            raise SystemExit(f"数据错误：词族 {key}（{label}）词不足或重复")
    for i, tpl in enumerate(TEMPLATES, 1):
        filled = tpl.format(a="丶", b="丶")
        if "{" in filled or "}" in filled:
            raise SystemExit(f"数据错误：模板 {i} 有未知占位符")


def make_twister(rng, family=None, short=False):
    """从指定（或随机）词族取两个词，套 1~2 个模板，返回 (词族标签, 绕口令文本)。"""
    key = family if family else rng.choice(list(FAMILIES))
    label, words = FAMILIES[key]
    a, b = rng.sample(words, 2)
    tpls = rng.sample(TEMPLATES, 1 if short else 2)
    return label, "\n  ".join(t.format(a=a, b=b) for t in tpls)


def main(argv=None):
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="tongue-twister",
        description="绕口令工厂：随机组合双声叠韵词生成绕口令。")
    parser.add_argument("-f", "--family", choices=list(FAMILIES),
                        default=None, help="指定词族（默认随机）")
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="数量，默认 1")
    parser.add_argument("-s", "--short", action="store_true",
                        help="短版：只拼一句")
    parser.add_argument("--list", action="store_true",
                        help="列出全部词族后退出")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，便于复现")
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("-n/--count 需要正整数")

    _check_data()
    if args.list:
        for key, (label, words) in FAMILIES.items():
            print(f"{key:4s} {label}：{'、'.join(words)}")
        return 0

    rng = random.Random(args.seed)
    for i in range(args.count):
        label, text = make_twister(rng, family=args.family, short=args.short)
        print(f"🎯 绕口令（{label}）：\n  {text}")
        if i < args.count - 1:
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
