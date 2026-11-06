#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""万能借口机（excusator）。

用途：
    按「迟到 / 忘事 / 不想开会 / 请假 / 不回消息」等场景随机生成借口，
    支持指定场景与数量。

示例命令：
    python excusator.py                     # 随机场景来一个借口
    python excusator.py -s 迟到 -n 3        # 迟到借口连来三个
    python excusator.py -s 不想开会         # 给"不想开会"配个说法
    python excusator.py --list              # 查看全部支持的场景
    python excusator.py --seed 7            # 固定随机种子，方便复现
"""

import argparse
import random
import sys

# ---- 迟到：原因 + 努力 + 态度 三段拼接 ----
LATE_CAUSE = [
    "地铁在两站之间临时停车清客",
    "公交司机一脚急刹，全车人集体做了套广播体操",
    "共享单车连开三辆，三辆都是坏锁",
    "电梯停电，我被困在一楼和负一楼之间",
    "小区门口的大爷下棋，非拉着我当裁判",
    "高架上堵成露天停车场，一动不动",
    "出门踩到水坑，回家换鞋又遇上堵车",
]
LATE_EFFORT = [
    "我以百米冲刺的速度狂奔了三条街",
    "我当场打车绕了两公里",
    "我一边狂奔一边给同事打电话报备",
    "我把通勤路上能用的交通工具全试了一遍",
]
LATE_TAIL = [
    "以后我提前两班车出门",
    "我愿意请全组喝奶茶谢罪",
    "今晚加班一定补回这段时间",
    "明天我把闹钟拨到凌晨五点",
]

# ---- 忘事：对象 + 理由 + 补救 三段拼接 ----
FORGET_THING = [
    "要交的周报",
    "答应带的资料",
    "下午的例会",
    "说好的回电",
    "落在工位的伞",
]
FORGET_BODY = [
    "是我的大脑内存不足，重要事项把缓存挤爆了",
    "昨晚睡前还在反复确认，一睁眼记忆就被梦格式化了",
    "我怀疑那是别人的记忆，不然备忘录为什么背叛我",
    "大脑磁盘已满，它很不幸是第一个被清出缓存的",
]
FORGET_TAIL = [
    "给我一次机会，我马上补救",
    "现在补救还来得及，我立刻去办",
    "该罚就罚，下午茶我包了",
]

# ---- 其余场景：整句库 ----
MEETING_LINES = [
    "医生说我今天不能久坐，一开会就头疼，属于医学无法解释的那种。",
    "我这会儿灵感如泉涌正适合干正事，一开会灵感就溜了，为了项目我选择留守工位。",
    "灵魂到场比肉体到场更重要，而我的灵魂今天已经在会上全程旁听了。",
    "我算过了，我缺席能让会议平均缩短二十分钟，这是在为团队延长寿命。",
    "今日水逆，不宜集体动脑，我一个人动就够了，会议室让给状态好的人。",
]
LEAVE_LINES = [
    "本人今日电量仅剩3%，申请充电一日，明天满血上岗。",
    "我家WiFi昨晚造反了，我得留守家园稳定军心。",
    "宠物医生说我家猫情绪不稳定需要陪伴，它的话比我的请假条管用。",
    "我需要去处理一件人生大事：把去年欠的觉全部还清，否则影响本周生产力。",
    "今天是黄历上的「宜在家忌上班」，我这个人一向尊重传统文化。",
]
REPLY_LINES = [
    "我的手机刚才掉进沙发缝了，那是连搜救队都到不了的百慕大三角。",
    "我不是故意不回，我是在想怎么回才显得又快又从容，想着想着睡着了。",
    "系统延迟：我的手已经看到消息了，但大脑还没完成批处理。",
    "刚才在忙一个大项目，主题是「假装自己很忙」，现在忙完了。",
    "我的社交电量刚充到30%，省电模式下只回最重要的消息——比如现在这条。",
]


def excuse_late() -> str:
    return "今天迟到真不怪我：{c}。{e}，奈何时间不等人。{t}。".format(
        c=random.choice(LATE_CAUSE),
        e=random.choice(LATE_EFFORT),
        t=random.choice(LATE_TAIL),
    )


def excuse_forget() -> str:
    return "关于{thing}，你听我解释：{body}。{tail}。".format(
        thing=random.choice(FORGET_THING),
        body=random.choice(FORGET_BODY),
        tail=random.choice(FORGET_TAIL),
    )


def excuse_meeting() -> str:
    return random.choice(MEETING_LINES)


def excuse_leave() -> str:
    return random.choice(LEAVE_LINES)


def excuse_reply() -> str:
    return random.choice(REPLY_LINES)


SCENES = {
    "迟到": excuse_late,
    "忘事": excuse_forget,
    "不想开会": excuse_meeting,
    "请假": excuse_leave,
    "不回消息": excuse_reply,
}


def main() -> int:
    try:  # Windows 控制台默认 GBK，切到 UTF-8 避免输出报错
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        prog="excusator",
        description="万能借口机：按场景随机生成借口。",
    )
    parser.add_argument(
        "-s", "--scene", choices=sorted(SCENES), default=None,
        help="借口场景（默认随机选一个场景）",
    )
    parser.add_argument("-n", "--count", type=int, default=1, help="生成条数（默认 1）")
    parser.add_argument("--list", action="store_true", help="列出全部支持的场景后退出")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（用于复现）")
    args = parser.parse_args()

    if args.list:
        print("支持的场景：" + "、".join(sorted(SCENES)))
        return 0
    if args.count < 1:
        parser.error("-n/--count 必须 >= 1")
    if args.seed is not None:
        random.seed(args.seed)

    scene = args.scene or random.choice(sorted(SCENES))
    maker = SCENES[scene]
    for _ in range(args.count):
        print("【{scene}】{line}".format(scene=scene, line=maker()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
