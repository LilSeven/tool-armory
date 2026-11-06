#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MBTI 扭蛋机 —— 随机抽一个人格类型并附搞笑人设解读。

用途:
    从 16 型 MBTI 中随机"扭"出一颗，附上搞笑人设、必杀技、致命弱点、
    口头禅、今日运势与幸运物。纯属娱乐，请勿用于招聘、相亲或看病。

用法:
    python mbti-random.py                 # 给"神秘路人"随机扭一颗
    python mbti-random.py 小明            # 给小明扭一颗
    python mbti-random.py --seed 42 老王  # 固定种子，结果可复现（自测友好）
    python mbti-random.py --list          # 列出全部 16 型人设速览

示例命令:
    python mbti-random.py 小红
    python mbti-random.py --seed 7 老王
"""

from __future__ import annotations

import argparse
import random
import sys

# 16 型 MBTI：代号 -> (称号, 搞笑人设, 必杀技, 致命弱点, 口头禅)
TYPES = {
    "INTJ": (
        "建筑师",
        "脑内剧场每天上演三部史诗，见面只说得出一个'哦'。",
        "三秒看穿这场会议本可以是一封邮件",
        "被当面夸奖会当场死机重启",
        "这不是冷漠，是省电模式。",
    ),
    "INTP": (
        "逻辑学家",
        "床分三个区：睡眠区、想事区、思考宇宙区——常用第三个。",
        "把简单问题聊到宇宙尽头",
        "出门前永远差一只袜子",
        "马上到——说的是三天后。",
    ),
    "ENTJ": (
        "指挥官",
        "群里没人说话时第一个@全体成员的勇者。",
        "把周末排成季度会议还不许请假",
        "对'随便'两个字过敏",
        "计划A失败？那本来就是给B探路的。",
    ),
    "ENTP": (
        "辩论家",
        "杠精界的艺术家，抬杠也要抬出花来。",
        "三句话让对方开始怀疑人生",
        "deadline 前夜灵感才上线",
        "我不是反对你，我是支持你反驳我。",
    ),
    "INFJ": (
        "提倡者",
        "白天是朋友们的树洞，深夜自己悄悄长蘑菇。",
        "一眼看穿你的'我没事'",
        "宁可内耗绝不开口",
        "我可以帮你，但别问我怎么了。",
    ),
    "INFP": (
        "调停者",
        "收藏夹里躺着八百个'改变人生'教程，一个都没点开。",
        "共情能力点满，泪点比想象中低",
        "点奶茶都比别人多纠结十分钟",
        "再躺五分钟，灵感就来了。",
    ),
    "ENFJ": (
        "主人公",
        "人形充电宝：充别人的电，漏自己的电。",
        "记得所有人的生日和忌口",
        "不敢拒绝'帮个小忙'",
        "大家都开心就好，我不重要。",
    ),
    "ENFP": (
        "竞选者",
        "兴趣班报满员，技能树点到一半全枯了。",
        "三分钟把陌生人处成老熟人",
        "热情来得快，去得更快",
        "这个想法绝了！——明天再爱。",
    ),
    "ISTJ": (
        "物流师",
        "连生活都建了 Excel，还做了三份备份。",
        "把一锅粥的现场整理成表格",
        "计划被打乱时血压当场表演",
        "按规矩来，谢谢配合。",
    ),
    "ISFJ": (
        "守卫者",
        "默默把你的杯子续满，然后说'顺手而已'。",
        "记住你上个月说的每句废话",
        "自己的委屈永远排在最后处理",
        "没事，我来就行。",
    ),
    "ESTJ": (
        "总经理",
        "家庭聚会自带议程表和计时器。",
        "三分钟拍板你纠结三天的事",
        "听到'随缘'就想复盘流程",
        "效率就是生命，闲聊就是犯罪。",
    ),
    "ESFJ": (
        "执政官",
        "聚餐点菜前把所有人的忌口问一遍的人。",
        "冷场时自动切换救场模式",
        "被冷落时内心戏能拍八十集",
        "多吃点，别客气，真的别客气。",
    ),
    "ISTP": (
        "鉴赏家",
        "话少，但家里坏了的东西没一样逃得过他的手。",
        "万物皆可拆，多数能装回去",
        "聊天窗口一开就忘回",
        "嗯。哦。还行。",
    ),
    "ISFP": (
        "探险家",
        "朋友圈三天可见，但每张照片都像电影截图。",
        "审美自成一派，讲不出但好看",
        "一被安排就浑身难受",
        "随便，都行，看你。",
    ),
    "ESTP": (
        "企业家",
        "先动手再思考，事后总结：'我这不是挺好的'。",
        "危机现场最淡定的那个人",
        "无聊比困难更致命",
        "来都来了，整呗。",
    ),
    "ESFP": (
        "表演者",
        "聚会的灵魂人物，散场后电量归零。",
        "自带 BGM 出场",
        "独处一小时就开始怀疑人生",
        "开心最重要，其他明天再说。",
    ),
}

FORTUNES = [
    "今天的你会因一件小事莫名其妙地开心。",
    "今天说话前先数到三，能避开一次社死。",
    "今天遇到的坑，其实是你下个段位的经验包。",
    "今天的灵感密度超标，记得随手记下来。",
    "今天宜摸鱼，但别摸到领导视线里。",
    "今天的你有概率被陌生人的善意暖到。",
    "今天不宜做重大决定，尤其不宜换头像。",
    "今天的效率值随咖啡因摄入量线性增长。",
]

LUCKY_ITEMS = [
    "一包辣条",
    "一张过期但舍不得扔的优惠券",
    "电量 100% 的充电宝",
    "一支写得出字的笔",
    "降噪开满的耳机",
    "半杯还温热的奶茶",
    "一个靠窗的座位",
    "一个提前下班的理由",
]


def _setup_stdio() -> None:
    """尽力把输出流切到 UTF-8，避免 Windows 控制台中文/表情乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mbti-random.py",
        description="MBTI 扭蛋机 —— 随机抽一个人格类型并附搞笑人设解读。",
    )
    parser.add_argument("name", nargs="?", default="神秘路人",
                        help="要扭蛋的人名（可选，默认'神秘路人'）")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，固定后结果可复现")
    parser.add_argument("--list", action="store_true",
                        help="列出全部 16 型人设速览")
    return parser


def gacha(name: str, seed: int | None) -> str:
    """扭一颗：随机取型 + 随机配运势与幸运物。"""
    rng = random.Random(seed)
    code = rng.choice(sorted(TYPES))
    title, persona, skill, weakness, motto = TYPES[code]
    fortune = rng.choice(FORTUNES)
    lucky = rng.choice(LUCKY_ITEMS)
    return "\n".join([
        f"🎰 MBTI 扭蛋机 · 为「{name}」扭出一颗！",
        f"🎲 结果：{code} · {title}",
        f"👤 人设：{persona}",
        f"⚔️ 必杀技：{skill}",
        f"💣 致命弱点：{weakness}",
        f"💬 口头禅：{motto}",
        f"📈 今日运势：{fortune}",
        f"🍀 幸运物：{lucky}",
        "（结果纯属娱乐，请勿用于招聘、相亲或自我设限。）",
    ])


def list_all() -> str:
    lines = ["🎰 MBTI 全 16 型速览："]
    for i, code in enumerate(sorted(TYPES), 1):
        title, persona, *_ = TYPES[code]
        lines.append(f"{i:>2}. {code} {title}：{persona}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    args = build_parser().parse_args(argv)
    if args.list:
        print(list_all())
    else:
        print(gacha(args.name, args.seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
