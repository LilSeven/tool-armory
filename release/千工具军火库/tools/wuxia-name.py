#!/usr/bin/env python3
"""wuxia-name.py — 武侠人名生成: 姓氏+意境字组合出武侠角色名与江湖绰号(单文件, 仅标准库)。

用途:
    从单姓/复姓库与意境字库组合生成武侠角色名(如 白听澜、慕容望舒),
    并按模板拼一枚江湖绰号(如 踏雪快剑、玉面郎君、江北第一刀)。
    支持 --surname 指定姓氏、--gender 调整风格、--seed 复现结果。

示例:
    python wuxia-name.py gen                     # 随机 1 位侠客(名+绰号)
    python wuxia-name.py gen 5                   # 随机 5 位
    python wuxia-name.py gen 2 --seed 9          # 固定种子, 结果可复现
    python wuxia-name.py gen 1 --surname 慕容    # 指定姓氏(单姓/复姓均可)
    python wuxia-name.py gen 1 --gender female   # 偏女性风格
    python wuxia-name.py gen 1 --gender male     # 偏男性风格
    python wuxia-name.py list                    # 查看词库
"""

from __future__ import annotations

import argparse
import random
import sys

SURNAMES_SINGLE = [
    "沈", "苏", "楚", "萧", "叶", "顾", "白", "林", "陆", "秦", "温", "花",
    "卫", "云", "风", "洛", "段", "任", "蓝", "岳", "韩", "程", "许", "方",
    "姜", "孟", "宋", "唐", "傅", "施", "祝", "凌",
]
SURNAMES_DOUBLE = [
    "慕容", "欧阳", "上官", "司马", "独孤", "东方", "南宫", "西门", "令狐",
    "公孙", "长孙", "诸葛", "夏侯", "皇甫", "尉迟", "完颜", "拓跋", "纳兰",
    "钟离", "闻人",
]

MALE_CONNECT = ["惊", "断", "破", "擎", "啸", "凌", "御", "承", "慕",
                "听", "望", "归", "行", "踏", "拂", "饮"]
FEMALE_CONNECT = ["若", "凝", "听", "望", "慕", "如", "念", "语", "惜",
                  "梦", "拂", "映"]
MALE_IMAGE = ["鸿", "霄", "澜", "岳", "风", "川", "舟", "锋", "寒", "星",
              "河", "天", "涯", "城", "山", "潮", "云", "霜"]
FEMALE_IMAGE = ["雪", "月", "烟", "璃", "柔", "兰", "雁", "薇", "萍", "云",
                "霜", "梦", "溪", "铃", "荷", "绫"]

MODIFIERS = ["追风", "惊鸿", "断岳", "流云", "夺魄", "落雁", "踏雪", "穿云",
             "裂石", "分金", "碎玉", "摘星", "伏虎", "降龙", "听雨", "饮霜"]
WEAPONS = ["快剑", "神刀", "银枪", "铁鞭", "飞刀", "长戟", "玉箫", "铁掌",
           "双钩", "软剑"]
LOOKS = ["青衫", "白衣", "玉面", "赤发", "银髯", "寒眸", "断剑", "铁掌",
         "独臂", "双刀"]
MALE_ROLES = ["客", "郎", "侠", "叟", "翁", "公子", "先生"]
FEMALE_ROLES = ["姑", "娘子", "女侠", "仙子", "夫人"]
REGIONS = ["江北", "塞北", "江南", "关外", "中原", "漠北", "东海", "岭南",
           "川中", "河西"]


def make_given(rng, gender):
    """名 = 连接字+意境字 或 单意境字。"""
    if gender == "female":
        connect, image = FEMALE_CONNECT, FEMALE_IMAGE
    else:
        connect, image = MALE_CONNECT, MALE_IMAGE
    if rng.random() < 0.6:
        return rng.choice(connect) + rng.choice(image)
    return rng.choice(image)


def make_nickname(rng, gender):
    """绰号 = 修饰+兵器 / 气质+身份 / 地望+第一+兵器 三选一。"""
    roll = rng.random()
    if roll < 0.45:
        return rng.choice(MODIFIERS) + rng.choice(WEAPONS)
    if roll < 0.75:
        roles = FEMALE_ROLES if gender == "female" else MALE_ROLES
        return rng.choice(LOOKS) + rng.choice(roles)
    return rng.choice(REGIONS) + "第一" + rng.choice(WEAPONS)


def make_person(rng, gender, surname=None):
    """返回 (姓名, 绰号)。复姓约 1/4 概率。"""
    if surname:
        sur = surname
    elif rng.random() < 0.25:
        sur = rng.choice(SURNAMES_DOUBLE)
    else:
        sur = rng.choice(SURNAMES_SINGLE)
    return sur + make_given(rng, gender), make_nickname(rng, gender)


def gen_people(rng, count, gender, surname):
    people, seen = [], set()
    attempts = 0
    while len(people) < count and attempts < count * 50 + 100:
        attempts += 1
        g = gender if gender != "any" else ("male" if rng.random() < 0.5 else "female")
        person = make_person(rng, g, surname)
        if person not in seen:
            seen.add(person)
            people.append(person)
    return people


def cmd_gen(args):
    surname = (args.surname or "").strip()
    if args.surname is not None and not surname:
        raise ValueError("--surname 不能为空")
    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    for name, nick in gen_people(rng, args.count, args.gender, surname or None):
        print("%s · %s" % (name, nick))
    return 0


def cmd_list(args):
    print("单姓 %d 个: %s" % (len(SURNAMES_SINGLE), "".join(SURNAMES_SINGLE)))
    print("复姓 %d 个: %s" % (len(SURNAMES_DOUBLE), " ".join(SURNAMES_DOUBLE)))
    print("连接字: 男%s | 女%s" % ("".join(MALE_CONNECT), "".join(FEMALE_CONNECT)))
    print("意境字: 男%s | 女%s" % ("".join(MALE_IMAGE), "".join(FEMALE_IMAGE)))
    print("绰号模板: 修饰+兵器 | 气质+身份 | 地望+第一+兵器")
    print("  修饰: %s" % " ".join(MODIFIERS))
    print("  兵器: %s" % " ".join(WEAPONS))
    print("  气质: %s" % " ".join(LOOKS))
    print("  地望: %s" % " ".join(REGIONS))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="wuxia-name",
        description="姓氏+意境字组合生成武侠角色名与江湖绰号。")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="命令")

    sp = sub.add_parser("gen", help="生成侠客名与绰号")
    sp.add_argument("count", nargs="?", type=int, default=1, help="生成个数(默认 1)")
    sp.add_argument("--surname", default=None, help="指定姓氏, 如 慕容 / 白")
    sp.add_argument("--gender", choices=("male", "female", "any"), default="any",
                    help="风格倾向(默认 any)")
    sp.add_argument("--seed", type=int, default=None,
                    help="随机种子, 提供则结果可复现")
    sp.set_defaults(func=cmd_gen)

    sp = sub.add_parser("list", help="查看词库")
    sp.set_defaults(func=cmd_list)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print("wuxia-name: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
