#!/usr/bin/env python3
"""故事骰子（story-dice）—— 掷出九个图标词，串成一个即兴故事开头。

模拟故事骰（Story Cubes）：从 40 个图标词中不重复地掷出 9 个，按 3×3
九宫格摆开，并选一个叙事模板把它们串成一个即兴故事开头；也支持只掷
骰子不写故事，供自己即兴发挥。

用法：
    python story-dice.py                    # 掷骰并生成故事开头
    python story-dice.py --dice-only        # 只掷九个图标词
    python story-dice.py -n 2               # 掷两组
    python story-dice.py --seed 7           # 固定种子（可复现）
    python story-dice.py --icons            # 列出全部图标词
    python story-dice.py --help             # 查看帮助

示例输出：
    $ python story-dice.py --seed 7
    🎲 九宫图标：
      [1]王冠  [2]钥匙  [3]老猫
      [4]雨伞  [5]灯塔  [6]骰子
      [7]钢琴  [8]影子  [9]面具
    📖 故事开头：
      那晚，王冠从家里消失了。……

只用 Python 标准库。
"""

import argparse
import random
import sys

ICONS = [
    "王冠", "钥匙", "老猫", "闪电", "罗盘", "木门", "钟表", "石桥",
    "星星", "骰子", "面具", "蜡烛", "旧信", "水井", "火车", "雨伞",
    "镜子", "贝壳", "风筝", "梯子", "鸡蛋", "影子", "灯塔", "地图",
    "硬币", "玫瑰", "弯刀", "帐篷", "眼睛", "电梯", "钢琴", "面包",
    "乌鸦", "隧道", "气球", "骆驼", "戒指", "汽笛", "秋千", "铃铛",
]

# 每个模板恰好使用 w1..w9 各一次
STORY_TPL = [
    "那晚，{w1}从家里消失了。她推开{w2}，把{w3}塞进口袋，又顺手带上了{w4}。"
    "街角，{w5}忽然亮起，像在给她指路；{w6}在她身后轻轻晃动，仿佛有人跟着。"
    "走到桥心她才发现：{w7}、{w8}，还有那{w9}，全都不见了——故事从这一刻开始。",

    "清晨，他把{w1}和{w2}塞进背包，出门去寻找传说中的{w3}。路过{w4}时，"
    "一阵风把{w5}卷上了天；他追着它跑过{w6}，撞见一位守着{w7}的老人。"
    "老人只说了一句话：『带上{w8}，别回头，天黑之前，{w9}会来找到你。』",

    "从前，有一只会说话的{w1}。它每天看守着{w2}，最宝贝的收藏是{w3}。"
    "某天，{w4}和{w5}打了个赌：谁先取回{w6}，谁就能许一个愿。"
    "于是它们带上{w7}和{w8}，趁着月光出发——{w9}悄悄跟在队伍最后。",

    "警报响起时，{w1}正靠在舱门边打盹。舰长抓起{w2}冲向{w3}；屏幕上，{w4}正在逼近。"
    "工程师抱着{w5}大喊：『没有{w6}，我们回不了家！』舷窗外，{w7}缓缓漂过，像一声叹息。"
    "有人低声问：『还记得地球上的{w8}吗？』没人回答，只有{w9}在黑暗里闪了一下。",
]


def _setup_stdio():
    """让中文输出在管道/重定向场景下也按 UTF-8 走。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _check_data():
    """数据自检：图标够掷，模板恰好用 w1..w9 各一次。"""
    if len(ICONS) != len(set(ICONS)):
        raise SystemExit("数据错误：图标词有重复")
    if len(ICONS) < 9:
        raise SystemExit("数据错误：图标词不足 9 个")
    for i, tpl in enumerate(STORY_TPL, 1):
        filled = tpl.format(**{f"w{k}": "丶" for k in range(1, 10)})
        if "{" in filled or "}" in filled:
            raise SystemExit(f"数据错误：模板 {i} 有未知占位符")
        for k in range(1, 10):
            if f"{{w{k}}}" not in tpl:
                raise SystemExit(f"数据错误：模板 {i} 缺少占位符 w{k}")


def make_story(icons, rng):
    """把 9 个图标词填进随机模板，串成故事开头。"""
    return rng.choice(STORY_TPL).format(**{f"w{k}": icons[k - 1] for k in range(1, 10)})


def show_icons(icons):
    print("🎲 九宫图标：")
    for row in range(3):
        cells = [f"[{row * 3 + col + 1}] {icons[row * 3 + col]}" for col in range(3)]
        print("  " + "  ".join(cells))


def main(argv=None):
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="story-dice",
        description="故事骰子：掷出九个图标词，串成一个即兴故事开头。")
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="掷骰组数，默认 1")
    parser.add_argument("--dice-only", action="store_true",
                        help="只掷九宫图标词，不生成故事")
    parser.add_argument("--icons", action="store_true",
                        help="列出全部图标词后退出")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，便于复现")
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("-n/--count 需要正整数")

    _check_data()
    if args.icons:
        print("全部图标词：" + "、".join(ICONS))
        return 0

    rng = random.Random(args.seed)
    for i in range(args.count):
        icons = rng.sample(ICONS, 9)
        show_icons(icons)
        if not args.dice_only:
            print("📖 故事开头：")
            print("  " + make_story(icons, rng))
        if i < args.count - 1:
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
