#!/usr/bin/env python3
"""俳句抽签（haiku-maker）—— 随机组合季节意象，生成 5-7-5 三行俳句。

从春/夏/秋/冬四个季节词库里，各抽一句开笔句（5 字）、中段句（7 字）、
收束句（5 字），拼成一首三行俳句；季节随机或可指定，结果可用种子复现。

用法：
    python haiku-maker.py                    # 随机抽一首
    python haiku-maker.py --season 秋        # 指定季节（春/夏/秋/冬）
    python haiku-maker.py -n 3               # 一次抽三首
    python haiku-maker.py --seed 42          # 固定随机种子（可复现）
    python haiku-maker.py --help             # 查看帮助

示例输出：
    $ python haiku-maker.py --season 冬 --seed 1
    ❄【冬】
        初雪落无声
        围炉夜话雪敲窗
        春在爆竹里

只用 Python 标准库。
"""

import argparse
import random
import sys

MARKS = {"春": "🌸", "夏": "🌞", "秋": "🍂", "冬": "❄"}

SEASONS = {
    "春": {
        "open5": ["樱瓣落肩头", "细雨润新芽", "东风拂柳岸", "燕影掠湖心",
                  "苔色上阶青", "桃枝缀浅红", "薄雾锁远山", "新芽破土声"],
        "mid7": ["燕子衔泥掠水飞", "陌上花开缓缓归", "一池新绿皱春风",
                 "夜雨剪韭煮新茶", "风筝飞过短篱笆", "谁家纸鸢上碧霄",
                 "布谷声里种春山", "小猫追蝶过短墙"],
        "close5": ["风暖柳丝长", "炊烟起暮色", "一伞过小桥",
                   "蛙声漫过塘", "灯下读旧信", "花影落棋枰"],
    },
    "夏": {
        "open5": ["蝉声穿叶隙", "荷叶托雨珠", "骤雨洗青山", "萤火点夜幕",
                  "西瓜沉井水", "蜻蜓立荷尖", "麦浪翻金风", "南风掀竹帘"],
        "mid7": ["雷雨洗净半城尘", "老树浓荫盖钓矶", "竹席蒲扇数流萤",
                 "一竿斜日晒渔网", "蝉鸣拉长午梦声", "瓜棚豆架月色凉",
                 "孩童扑萤入苇丛", "乌篷船载菱歌还"],
        "close5": ["凉风起青萍", "晚荷别样红", "星河落瓦檐",
                   "一枕纳凉风", "竹影扫阶尘", "蛙鼓到天明"],
    },
    "秋": {
        "open5": ["红叶烧山径", "霜重染枫林", "雁字写长空", "桂香浮月色",
                  "稻浪低头笑", "枯荷听雨声", "蟹肥菊正黄", "晨露坠草尖"],
        "mid7": ["一行雁字过城南", "月光淌进旧陶罐", "落叶铺满归乡路",
                 "谁家篱下菊初开", "石榴咧嘴笑秋风", "银杏铺金小院深",
                 "芦花摇白一江秋", "促织声声伴灯凉"],
        "close5": ["霜叶红于花", "归鸿三两声", "新酒温旧梦",
                   "满地是月光", "一叶知秋深", "柿子挂灯笼"],
    },
    "冬": {
        "open5": ["初雪落无声", "寒梅著花未", "北风卷残叶", "雪压松枝低",
                  "围炉煮酒香", "冰凌悬檐角", "湖心结薄冰", "暮雪没石阶"],
        "mid7": ["围炉夜话雪敲窗", "一行脚印没入雪", "炭火煨着旧时光",
                 "麻雀踏雪寻碎粮", "谁家窗上开冰花", "腊味挂满旧屋檐",
                 "雪夜孤灯读闲书", "热气腾腾饺子香"],
        "close5": ["檐下腊梅开", "炉火映脸颊", "雪深掩柴门",
                   "一碗热汤面", "灯花结两蕊", "春在爆竹里"],
    },
}


def _setup_stdio():
    """让中文输出在管道/重定向场景下也按 UTF-8 走。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _check_data():
    """词库自检：开笔/收束句须 5 字，中段句须 7 字。"""
    for season, bank in SEASONS.items():
        for text in bank["open5"] + bank["close5"]:
            if len(text) != 5:
                raise SystemExit(f"数据错误：{season}季五字句『{text}』长度为 {len(text)}")
        for text in bank["mid7"]:
            if len(text) != 7:
                raise SystemExit(f"数据错误：{season}季七字句『{text}』长度为 {len(text)}")


def draw(bank, rng):
    """从某一季词库抽 5-7-5 三句。"""
    return (rng.choice(bank["open5"]),
            rng.choice(bank["mid7"]),
            rng.choice(bank["close5"]))


def main(argv=None):
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="haiku-maker",
        description="俳句抽签：随机组合季节意象，生成 5-7-5 三行俳句。")
    parser.add_argument("-s", "--season", choices=list(SEASONS) + ["随机"],
                        default="随机", help="季节（春/夏/秋/冬），默认随机")
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="抽取数量，默认 1")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，便于复现")
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("-n/--count 需要正整数")

    _check_data()
    rng = random.Random(args.seed)
    season = rng.choice(list(SEASONS)) if args.season == "随机" else args.season
    bank = SEASONS[season]
    total = len(bank["open5"]) * len(bank["mid7"]) * len(bank["close5"])

    seen, made = set(), 0
    while made < args.count and len(seen) < total:
        poem = draw(bank, rng)
        if poem in seen:
            continue
        seen.add(poem)
        made += 1
        print(MARKS[season] + "【" + season + "】")
        for line in poem:
            print("    " + line)
        if made < args.count:
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
