#!/usr/bin/env python3
"""疯狂填词 —— 按提示输入名词、动词等词，填进模板生成爆笑短文。

在终端直接运行会逐个提示输入（回车跳过则随机）；也支持全随机、
按顺序填词（逗号分隔）、或用管道把词一行一个喂进来。

示例命令:
  python mad-libs.py                        # 交互式填词
  python mad-libs.py --auto --seed 3        # 全随机来一篇
  python mad-libs.py --fill 火锅,跳舞,圆滚滚的,月球
  printf '火锅\n跳舞\n' | python mad-libs.py
  python mad-libs.py --list                 # 列出模板

退出码: 0 成功；1 参数不合法。
"""
import argparse
import random
import re
import sys
import textwrap

# 类别: (中文提示, 候选词)
BANKS = {
    "noun":   ("名词",   ["火锅", "皇帝", "香蕉", "拖鞋", "代码", "WiFi",
                          "仙人掌", "闹钟", "白菜", "机器人", "枕头", "论文",
                          "雨伞", "井盖"]),
    "verb":   ("动词",   ["跳舞", "冬眠", "打嗝", "翻跟头", "睡懒觉", "修空调",
                          "写检讨", "倒立", "背单词", "转圈", "炖汤", "拆快递"]),
    "adj":    ("形容词", ["闪闪发光的", "圆滚滚的", "一本正经的", "香喷喷的",
                          "气喘吁吁的", "神秘兮兮的", "粉红色的", "黑漆漆的",
                          "慢吞吞的", "得意洋洋的"]),
    "place":  ("地点",   ["太平洋底", "洗手间", "公司会议室", "月球背面",
                          "小区门口", "图书馆", "菜市场", "教室后排",
                          "天桥底下", "澡堂"]),
    "animal": ("动物",   ["柯基", "蜗牛", "北极熊", "鹦鹉", "仓鼠", "大鹅",
                          "水豚", "章鱼", "橘猫", "刺猬"]),
    "food":   ("食物",   ["螺蛳粉", "榴莲披萨", "老干妈", "珍珠奶茶", "辣条",
                          "泡面", "糖葫芦", "茶叶蛋", "烤冷面"]),
    "number": ("数量词", ["三千零一", "42", "十八", "9999", "七七四十九",
                          "零点五", "一百零八"]),
    "excl":   ("感叹词", ["天哪", "妈呀", "阿弥陀佛", "好家伙", "绝了",
                          "离谱", "救命"]),
    "body":   ("身体部位", ["脑袋", "脚趾头", "膝盖", "耳朵", "下巴",
                            "后槽牙", "腰"]),
}

STORIES = [
    ("修仙速递",
     "尊敬的{adj1}道友：你于{number1}年前在{place1}许下的愿望已经生效。"
     "请在三个时辰内，带上一只{adj2}{animal1}赶到{place2}，"
     "对着它大喊{excl1}，再原地{verb1}三十秒，"
     "即可领取{food1}味灵丹一枚。"
     "逾期不候——违者将变成{animal2}，罚在{place3}{verb2}一百年。"),
    ("离谱新闻",
     "本台消息：今日凌晨，一名{adj1}市民在{place1}目睹一只{animal1}当街{verb1}，"
     "引来{number1}人围观。目击者称，当时只觉{body1}一麻，脱口喊出{excl1}。"
     "相关部门提醒：近期请勿在{place2}食用{food1}，"
     "以免引来{adj2}的{animal2}，被拉着一起{verb2}。"),
    ("班级通知",
     "各位{adj1}的同学请注意：明天上午{number1}点，"
     "请自备{noun1}和{food1}各一份，到{place1}集合，"
     "参加一年一度的{verb1}大赛。"
     "本次评委是一只极其{adj2}的{animal1}，评分标准只有一条："
     "谁{verb2}得更离谱。无故缺席者，需手写{number2}字检讨，"
     "并对着自己的{body1}连说三遍{excl1}。"),
]

SLOT_RE = re.compile(r"\{([a-z]+)(\d+)\}")


def _setup_streams():
    """管道/重定向时强制 UTF-8 输入输出，避免 Windows 默认 GBK 报错。"""
    for s in (sys.stdout, sys.stderr, sys.stdin):
        try:
            if s is not None and not s.isatty():
                s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def slot_list(tpl):
    """按出现顺序返回 [(类别, 占位名), ...]，如 [("adj", "adj1"), ...]"""
    return [(m.group(1), m.group(1) + m.group(2))
            for m in SLOT_RE.finditer(tpl)]


def fill_story(tpl, provided, rng, interactive):
    slots = slot_list(tpl)
    words = {}
    for i, (cat, key) in enumerate(slots):
        w = provided[i] if i < len(provided) else ""
        if not w and interactive and i >= len(provided):
            try:
                w = input(f"[{i + 1}/{len(slots)}] "
                          f"请输入一个{BANKS[cat][0]}（回车随机）: ").strip()
            except (EOFError, KeyboardInterrupt):
                interactive = False
                print("（输入结束，剩余空位用随机词补齐）", file=sys.stderr)
                w = ""
        if not w:
            w = rng.choice(BANKS[cat][1])
        words[key] = w
    return tpl.format(**words)


def main(argv=None):
    _setup_streams()
    ap = argparse.ArgumentParser(description="按提示填词，套模板生成爆笑短文")
    ap.add_argument("--auto", action="store_true", help="全部用内置词库随机填")
    ap.add_argument("--fill", default=None,
                    help="按顺序填空，逗号分隔（中英文逗号均可）")
    ap.add_argument("--story", type=int, default=None, metavar="N",
                    help="指定模板序号 1~3（默认随机）")
    ap.add_argument("--seed", type=int, default=None, help="随机种子，可复现")
    ap.add_argument("--list", action="store_true", help="列出模板")
    a = ap.parse_args(argv)
    rng = random.Random(a.seed)

    if a.list:
        for i, (title, tpl) in enumerate(STORIES, 1):
            need = []
            for cat, _key in slot_list(tpl):
                zh = BANKS[cat][0]
                if zh not in need:
                    need.append(zh)
            print(f"{i}. 《{title}》 需填 {len(slot_list(tpl))} 个空"
                  f"（{'、'.join(need)}）")
        return 0

    idx = a.story if a.story is not None else rng.randrange(1, len(STORIES) + 1)
    if not 1 <= idx <= len(STORIES):
        print(f"--story 取值应为 1~{len(STORIES)}", file=sys.stderr)
        return 1
    title, tpl = STORIES[idx - 1]

    provided = []
    if a.fill is not None:
        provided = [w.strip() for w in re.split(r"[,，]", a.fill) if w.strip()]
    elif not a.auto and not sys.stdin.isatty():
        provided = [ln.strip() for ln in sys.stdin if ln.strip()]

    interactive = (sys.stdin.isatty() and not a.auto and a.fill is None)
    story = fill_story(tpl, provided, rng, interactive)

    print(f"《{title}》")
    print("\n".join(textwrap.wrap(story, width=38)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
