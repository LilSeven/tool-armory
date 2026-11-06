#!/usr/bin/env python3
"""藏头诗生成 —— 给定藏头几个字，套用意象模板逐句生成藏头诗。

每句 = 藏头字 + 从同一韵脚组的意象短语库中抽取的六字短语，组成七言；
全诗共用一个随机韵脚，短语不重复。可用 --seed 固定随机结果。

示例命令:
  python acrostic-poem.py 春风得意
  python acrostic-poem.py 中 秋 --seed 42
  python acrostic-poem.py 星辰大海 --seed 1
  python acrostic-poem.py              # 不带参数时用“春花秋月”演示

退出码: 0 成功；1 藏头字数量不合法（1~12 个）。
"""
import argparse
import random
import sys

# 每组 12 条六字短语，末字同韵
RHYMES = {
    "ou": ["风起绿水行舟", "云过千山未休", "月照孤帆远游", "花落随水东流",
           "夜静星垂似钩", "霜染层林晚秋", "雨歇长堤系舟", "雪拥空山客愁",
           "人立黄昏渡口", "雁字回时满楼", "灯下故人白头", "一蓑烟雨难收"],
    "an": ["月照空山寂然", "风吹细雨轻寒", "花开陌上如烟", "云归远岫连山",
           "雪压孤松未弯", "星沉碧落更阑", "灯照小窗夜半", "雁过南山悠然",
           "水漫平桥稻田", "春深绿柳拂栏", "秋高清露满山", "雨霁春江如蓝"],
    "ing": ["风过松林有声", "月出东山正明", "云散长空雨晴", "花底黄鹂一声",
            "雪落梅梢自轻", "星河夜半澄明", "灯昏古寺钟鸣", "雁写长空字成",
            "水送轻舟远行", "春山雾散初晴", "秋夜梧桐雨声", "梦入江南水程"],
    "ao": ["风起寒林叶飘", "月满西楼人悄", "雪霁寒梅正俏", "花底蜂儿正闹",
           "夜静秋虫声小", "星低野旷天高", "灯昏旅梦迢迢", "水阔孤帆影遥",
           "春涨一篙芳草", "秋老疏林叶少", "梦逐孤云缥缈", "山暝忽闻猿叫"],
}


def _setup_streams():
    """管道/重定向时强制 UTF-8 输出，避免 Windows 默认 GBK 报错。"""
    for s in (sys.stdout, sys.stderr):
        try:
            if s is not None and not s.isatty():
                s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def compose(heads, rng):
    rhyme = rng.choice(sorted(RHYMES))
    phrases = rng.sample(RHYMES[rhyme], len(heads))
    lines = [h + p for h, p in zip(heads, phrases)]
    return rhyme, lines


def main(argv=None):
    _setup_streams()
    ap = argparse.ArgumentParser(description="按藏头字套意象模板生成七言藏头诗")
    ap.add_argument("heads", nargs="*", help="藏头字（多个参数会拼接，1~12 个）")
    ap.add_argument("--seed", type=int, default=None, help="随机种子，可复现")
    a = ap.parse_args(argv)

    rng = random.Random(a.seed)
    text = "".join(a.heads)
    heads = [c for c in text if not c.isspace()]
    defaulted = not heads
    if defaulted:
        heads = list("春花秋月")
    if not 1 <= len(heads) <= 12:
        print(f"藏头字数量须在 1~12 个之间（当前 {len(heads)} 个）。",
              file=sys.stderr)
        return 1

    rhyme, lines = compose(heads, rng)
    print("《" + "".join(heads) + "》")
    for i, line in enumerate(lines):
        print(line + ("，" if i < len(lines) - 1 else "。"))
    print(f"（藏头七言 · 押 {rhyme} 韵 · 意象模板随机生成）")
    if defaulted:
        print("（未指定藏头字，以上为演示；试试: python acrostic-poem.py 你的名字）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
