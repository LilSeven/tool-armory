#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""风水小贴士 —— 每日一条玄学建议，可信度自负。

用途:
    以日期为种子，每天输出一条固定不变的"风水"小贴士，附幸运方位、
    幸运颜色、宜、忌与可信度。同一天重复运行结果一致。纯属娱乐玄学，
    照做翻车概不负责。

用法:
    python feng-shui-tip.py
    python feng-shui-tip.py --date 2026-11-03
    python feng-shui-tip.py --seed 42
    python feng-shui-tip.py --list

示例命令:
    python feng-shui-tip.py --date 2026-11-03
"""

from __future__ import annotations

import argparse
import datetime
import random
import sys

TIPS = [
    "工位显示器下压一枚硬币，寓意'有钱有屏'；升职加薪从视觉暗示开始。",
    "手机充电线从左往右绕三圈再插，据说能理顺一周运势；理不顺就换线。",
    "冰箱门上贴一张写着'瘦'的便签，玄学减肥第一步，饿了还能看字饱。",
    "进门先迈右脚，今日可避开 87% 的倒霉事（样本：编的）。",
    "卧室别堆单只袜子，单袜会扰乱气场，也会让你迟到。",
    "绿植放窗户左手边，光合作用顺时针，好运跟着转。",
    "钱包里留一张大额钞票当'镇包之宝'；花了它，气场会跟着破防。",
    "键盘底下藏一张写着'发达'的纸条，切记别让保洁看见。",
    "床头朝东宜早起，朝西宜赖床，朝天花板宜躺平。",
    "镜子别对床：半夜照见自己没洗的头，运势再好也吓没。",
    "水杯放右手边，伸手即饮，福气不洒。",
    "门上挂串铃铛，开门自带 BGM，气势先赢一半。",
    "每天把椅子转一圈再坐下，转走昨天的水逆。",
    "阳台晾三件红衣服，越看越喜庆，甲方看了都顺眼。",
    "书桌左高右低，事业盘旋向上；右高左低——那是堆了没洗的碗。",
    "玄关放块脚垫写'欢迎回家'，把外面的晦气蹭在门外。",
    "手机壁纸换成绿色森林，护眼又护运，一举两得纯属巧合。",
    "睡前把鞋尖朝外摆好，明早出门不磨蹭；风水讲究的是执行力。",
    "香薰点在房间东南角，据说是'财位'；闻着困了去睡觉也算进财。",
    "鱼缸别放卧室，鱼该有鱼自己的生活，你也一样。",
    "圆形餐具助人缘，方形餐具助原则，三角形的……慎用。",
    "窗帘留条缝睡觉，让月光知道你还没放弃自己。",
    "书架上摆一本永远读不完的书，学问会一直'在路上'。",
    "出门前看一眼天空：好天气心气顺，坏天气早备伞，此为最灵的一条。",
    "玄学第一定律：桌面越乱灵感越多；但甲方来前，请收拾。",
    "存钱罐放客厅显眼处，天天看见，天天心虚，心虚就存钱。",
    "别在床下堆旧物，旧物会做梦，你的梦会串台。",
    "东南角放一盆水培绿萝，财位有水又有绿，讲究。",
]

DIRECTIONS = ["正东", "东南", "正南", "西南", "正西", "西北", "正北", "东北"]

COLORS = ["石榴红", "雾霾蓝", "抹茶绿", "燕麦色", "落日橙",
          "丁香紫", "水泥灰", "奶油黄", "克莱因蓝", "豆沙粉"]

YI = ["把烦恼写下来再撕掉", "给绿植浇水", "整理一个抽屉", "主动夸一次人",
      "提前十分钟出门", "吃一顿热乎早餐", "还一笔小债", "删掉三个不用的APP"]
JI = ["深夜做重大决定", "跟人掰扯对错", "翻旧账", "冲动剁手",
      "已读乱回", "熬夜复盘人生", "在饿的时候逛超市", "拿自己跟别人比"]

CREDIBILITY = [
    "12%（玄学不含保质期）",
    "50%……的一半",
    "7.3%，随机小数更显得科学",
    "99%，信的人自然信",
    "0%，但你都已经点开了",
    "45%，剩下 55% 看你执行力",
]


def _setup_stdio() -> None:
    """尽力把输出流切到 UTF-8，避免 Windows 控制台中文/表情乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _parse_date(text: str) -> datetime.date:
    """解析 YYYY-MM-DD / YYYY/MM/DD，失败抛 ArgumentTypeError。"""
    try:
        y, m, d = (int(p) for p in text.replace("/", "-").split("-"))
        return datetime.date(y, m, d)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD，收到：{text!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feng-shui-tip.py",
        description="风水小贴士 —— 每日一条玄学建议，可信度自负。",
    )
    parser.add_argument("--date", type=_parse_date, default=None,
                        help="指定日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，固定后忽略日期直接复现")
    parser.add_argument("--list", action="store_true",
                        help="列出全部备选贴士")
    return parser


def daily_tip(day: datetime.date, seed: int | None) -> str:
    """按日期生成当天的小贴士：同一天结果固定。"""
    rng = random.Random(seed if seed is not None
                        else f"fengshui|{day.isoformat()}")
    return "\n".join([
        f"🧭 风水小贴士 · {day.isoformat()}",
        f"  今日建议：{rng.choice(TIPS)}",
        f"  幸运方位：{rng.choice(DIRECTIONS)}（做选择时优先考虑它，比如午饭就往那边吃）",
        f"  幸运颜色：{rng.choice(COLORS)}（衣服没有就换个手机壁纸）",
        f"  宜：{rng.choice(YI)}",
        f"  忌：{rng.choice(JI)}",
        f"  可信度：{rng.choice(CREDIBILITY)}",
        "（玄学仅供娱乐，可信度自负；翻车请找水逆，勿找开发者。）",
    ])


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    args = build_parser().parse_args(argv)
    if args.list:
        for i, tip in enumerate(TIPS, 1):
            print(f"{i:>2}. {tip}")
        return 0
    day = args.date if args.date is not None else datetime.date.today()
    print(daily_tip(day, args.seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
