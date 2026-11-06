#!/usr/bin/env python3
"""story-title —— 小说标题机。

用途:
    随机生成网文风 / 推理风 / 科幻风的小说书名，供找灵感、起名、开脑洞使用。

示例:
    python story-title.py                          # 随机 1 个书名（任意风格）
    python story-title.py -n 5                     # 随机 5 个
    python story-title.py --style 网文 -n 3        # 指定风格: any/网文/推理/科幻
    python story-title.py --style 推理 --bracket   # 输出带书名号《…》
    python story-title.py --seed 7                 # 固定随机种子，可复现

仅使用 Python 标准库。
"""

import argparse
import random
import sys

# ---------- 网文风 ----------
XH_PREFIX = ["万古", "逆天", "绝世", "混沌", "太初", "九天", "玄天", "无上",
             "永恒", "遮天", "焚天", "镇世", "不灭", "盖世"]
XH_CORE = ["神帝", "剑神", "魔尊", "武魂", "战神", "龙帝", "神王", "天骄",
           "圣体", "仙尊", "刀帝", "雷帝"]
XH_DOMAIN = ["都市", "末日", "深山", "盛唐", "大明", "星际", "网游", "异界", "诡秘"]
XH_ROLE = ["剑仙", "皇帝", "包工头", "咸鱼", "军师", "掌柜", "宗师", "驯龙师"]
XH_VERB = ["修仙", "种田", "点外卖", "养龙", "摆地摊", "抄书", "炼丹", "抓鬼"]
XH_START = ["零", "签到", "赘婿", "学徒", "摆烂", "摸鱼"]
XH_GOAL = ["修仙", "成神", "称霸诸天", "无敌天下", "长生", "点满科技树"]
XH_NUM = ["三千", "九转", "百炼", "十方", "万相", "七窍"]
XH_NUMN = ["星辰诀", "剑歌", "焚天图", "界主", "问鼎", "浮屠"]

# ---------- 推理风 ----------
MY_PLACE = ["山庄", "游轮", "雪夜列车", "图书馆", "歌剧院", "无人岛",
            "旧公寓", "博物馆", "天台", "医院"]
MY_THING = ["证人", "新娘", "第十三层", "手稿", "钥匙", "合影", "独白", "凶器"]
MY_PERSON = ["证人", "访客", "琴师", "宿敌", "目击者", "遗孤"]
MY_ADJ = ["无人知晓的", "倾斜的", "消失的", "冰封的", "迟到的", "沉默的", "褪色的"]
MY_NOUN = ["葬礼", "证词", "密室", "晚餐", "回声", "日记", "解药", "供词"]
MY_TIME = ["午夜", "暴雨之夜", "闭馆之后", "停电时刻", "散场之后"]
NUMCN = ["二", "三", "五", "七", "九", "十二", "一百零一"]

# ---------- 科幻风 ----------
SF_PREFIX = ["量子", "引力", "曲率", "熵", "光速", "暗物质", "平行", "降维",
             "奇点", "真空"]
SF_NOUN = ["迷宫", "幽灵", "王座", "归途", "边境", "花园", "孤岛", "挽歌",
           "回响", "拓荒者"]
SF_GALAXY = ["银河", "星际", "深空", "猎户座", "边疆星域"]
SF_EVENT = ["接触", "跃迁", "坍缩", "静默", "回溯"]
SF_EVENT2 = ["AI觉醒", "恒星熄灭", "时间静止", "记忆成为商品", "最后的信号抵达"]
SF_ROLE = ["宇航员", "图书馆员", "时间旅行者", "守灯人", "拓荒者", "翻译官"]


def _setup_stdio():
    """尽量把 stdout/stderr 切到 UTF-8，避免 Windows 管道下输出报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if (stream.encoding or "").replace("-", "").lower() != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _gen_xuanhuan(rng):
    patterns = [
        lambda: rng.choice(XH_PREFIX) + rng.choice(XH_CORE),
        lambda: "我在" + rng.choice(XH_DOMAIN) + rng.choice(XH_VERB),
        lambda: "我在" + rng.choice(XH_DOMAIN) + "当" + rng.choice(XH_ROLE),
        lambda: "从" + rng.choice(XH_START) + "开始" + rng.choice(XH_GOAL),
        lambda: rng.choice(XH_NUM) + rng.choice(XH_NUMN),
    ]
    return rng.choice(patterns)()


def _gen_mystery(rng):
    patterns = [
        lambda: rng.choice(MY_PLACE) + "之谜",
        lambda: rng.choice(MY_PLACE) + "杀人事件",
        lambda: "消失的" + rng.choice(MY_THING),
        lambda: rng.choice(MY_ADJ) + rng.choice(MY_NOUN),
        lambda: "第" + rng.choice(NUMCN) + "位" + rng.choice(MY_PERSON),
        lambda: rng.choice(MY_TIME) + "，" + rng.choice(MY_ADJ) + rng.choice(MY_NOUN),
    ]
    return rng.choice(patterns)()


def _gen_scifi(rng):
    patterns = [
        lambda: rng.choice(SF_PREFIX) + rng.choice(SF_NOUN),
        lambda: rng.choice(SF_GALAXY) + "编年史",
        lambda: "第" + rng.choice(NUMCN) + "次" + rng.choice(SF_EVENT),
        lambda: "当" + rng.choice(SF_EVENT2) + "时",
        lambda: "最后一位" + rng.choice(SF_ROLE),
        lambda: str(rng.randint(2, 999)) + "光年之外",
    ]
    return rng.choice(patterns)()


GENERATORS = {
    "网文": _gen_xuanhuan,
    "推理": _gen_mystery,
    "科幻": _gen_scifi,
}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="story-title",
        description="随机生成网文风/推理风/科幻风小说书名",
    )
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="生成数量（默认 1）")
    parser.add_argument("--style", default="any",
                        choices=["any"] + list(GENERATORS),
                        help="标题风格: any/网文/推理/科幻（默认 any）")
    parser.add_argument("--bracket", action="store_true",
                        help="给书名加上《》")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子（便于复现）")
    return parser


def main(argv=None):
    _setup_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("-n/--count 必须 >= 1")
    rng = random.Random(args.seed)
    for _ in range(args.count):
        style = args.style if args.style != "any" else rng.choice(list(GENERATORS))
        title = GENERATORS[style](rng)
        if args.bracket:
            title = "《" + title + "》"
        print(title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
