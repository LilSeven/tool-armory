#!/usr/bin/env python3
"""宠物起名助手 —— 按物种与性格关键词生成可爱宠物名。

用途:
    给新到家的猫猫狗狗兔兔起名: 指定物种和性格关键词, 生成配套的
    可爱名字与一句「性格点评」。

用法:
    python pet-namer.py [--species SPECIES] [--mood KEYWORD] [--count N] [--seed SEED]

示例命令:
    python pet-namer.py --species cat --mood 高冷 --count 3
    python pet-namer.py --species hamster --mood 吃货 --seed 7
    python pet-namer.py --mood 粘人             # 不指定物种则随机
    python pet-namer.py --species 狗 --mood 调皮

物种 SPECIES: cat/猫  dog/狗  rabbit/兔  hamster/仓鼠  bird/鸟  fish/鱼  lizard/蜥蜴  any/通用
性格 MOOD:    高冷 吃货 活泼 粘人 慵懒 调皮 温柔 胆小, 也接受任意自造词(按通用库处理)
仅依赖 Python 标准库; 成功时退出码为 0。
"""

from __future__ import annotations

import argparse
import random
import sys

SPECIES = {
    "cat": "猫", "dog": "狗", "rabbit": "兔", "hamster": "仓鼠",
    "bird": "鸟", "fish": "鱼", "lizard": "蜥蜴", "any": "小家伙",
}
SPECIES_ALIASES = {
    "猫": "cat", "猫咪": "cat", "小猫": "cat", "猫猫": "cat",
    "狗": "dog", "狗狗": "dog", "犬": "dog",
    "兔": "rabbit", "兔子": "rabbit", "兔兔": "rabbit",
    "仓鼠": "hamster", "鼠": "hamster", "鼠鼠": "hamster",
    "鸟": "bird", "鸟鸟": "bird", "鱼": "fish", "鱼儿": "fish",
    "蜥蜴": "lizard", "爬宠": "lizard",
    "通用": "any", "随机": "any", "any": "any",
}

MOOD_POOLS = {
    "高冷": ["陛下", "大人", "爵士", "女王", "伯爵", "墨影", "雪岭", "殿下", "玄夜", "孤月"],
    "吃货": ["布丁", "汤圆", "麻薯", "饭团", "奶糖", "豆包", "年糕", "可乐", "糯米", "薯条", "蛋挞", "肉包"],
    "活泼": ["蹦蹦", "跳跳", "闪电", "冲冲", "火花", "闹闹", "果冻", "雷达", "小旋风", "冲天炮"],
    "粘人": ["贴贴", "抱抱", "跟屁虫", "小尾巴", "软糖", "糯米糍", "黏黏", "挂件", "口袋糖"],
    "慵懒": ["咸鱼", "被子", "瞌睡", "午睡", "沙发", "打盹", "慢羊", "躺躺", "葛优"],
    "调皮": ["捣蛋", "混世", "小魔王", "顽顽", "淘气", "拆家", "翻车", "皮皮"],
    "温柔": ["软软", "云朵", "棉花", "小满", "暖暖", "毛毛", "月牙", "清风", "糖水"],
    "胆小": ["躲躲", "悄悄", "糯米", "小埋", "怯怯", "影子", "角落"],
}
MOOD_ALIASES = {
    "冷": "高冷", "酷": "高冷", "傲娇": "高冷",
    "馋": "吃货", "能吃": "吃货", "干饭": "吃货",
    "疯": "活泼", "好动": "活泼", "精力旺盛": "活泼",
    "黏人": "粘人", "亲人": "粘人",
    "懒": "慵懒", "佛系": "慵懒", "躺平": "慵懒",
    "熊": "调皮", "皮": "调皮", "淘气": "调皮", "欠揍": "调皮",
    "乖": "温柔", "软": "温柔", "治愈": "温柔",
    "害羞": "胆小", "怂": "胆小", "怕生": "胆小",
}

SPECIES_SUFFIX = {
    "cat": ["喵", "咪", "球"], "dog": ["汪", "豆", "宝"],
    "rabbit": ["团", "毛", "蹦"], "hamster": ["米", "球", "鼠"],
    "bird": ["啾", "羽", "翎"], "fish": ["泡", "游", "水"],
    "lizard": ["爷", "鳞", "爪"], "any": ["球", "宝", "仔"],
}

MOOD_TAGLINES = {
    "高冷": ["眼神能冻住鱼缸", "只在你开罐头时现身", "视众生为铲屎官"],
    "吃货": ["听到零食袋响会瞬移", "体重是商业机密", "为一块冻干可以出卖灵魂"],
    "活泼": ["凌晨三点开运动会", "精力像永远充着电", "家里没有它够不着的高度"],
    "粘人": ["挂在你身上像只挂件", "上厕所都要押着陪", "十厘米安全距离都不许有"],
    "慵懒": ["一天睡二十小时是基本盘", "移动全靠滚", "躺平哲学十级学者"],
    "调皮": ["家里的沙发按只赔", "拆家小队自封队长", "聪明全用在捣乱上"],
    "温柔": ["摸一下心都要化了", "说话细声细气的乖宝", "全世界的好脾气都在这"],
    "胆小": ["一点响动就钻床底", "和自己的影子斗智斗勇", "需要多一点耐心守护"],
}
GENERIC_POOL = ["球球", "豆豆", "毛毛", "团团", "布丁", "麻薯", "可可", "奶昔", "小福", "多多"]
GENERIC_TAGLINES = ["一只很特别的小可爱", "名字还在试用期", "看一眼就想带回家"]


def normalize_species(raw: str):
    key = SPECIES_ALIASES.get(raw.strip())
    if key is None:
        key = raw.strip().lower()
    return key if key in SPECIES else None


def normalize_mood(raw: str) -> str:
    m = raw.strip()
    return MOOD_ALIASES.get(m, m)


def pick_names(species_key: str, mood: str, count: int, rng: random.Random) -> list:
    pool = MOOD_POOLS.get(mood, GENERIC_POOL)
    taglines = MOOD_TAGLINES.get(
        mood, ["一只很『%s』的%s" % (mood, SPECIES[species_key])] + GENERIC_TAGLINES)
    seen = set()
    out = []
    attempts = 0
    while len(out) < count and attempts < count * 200:
        attempts += 1
        roll = rng.random()
        if roll < 0.10:
            # 叠字名: 喵喵 / 汪汪 这类
            suf = rng.choice(SPECIES_SUFFIX[species_key])
            name = suf + suf
        else:
            name = rng.choice(pool)
            if roll < 0.45:
                name += rng.choice(SPECIES_SUFFIX[species_key])
        if name in seen:
            continue
        seen.add(name)
        out.append((name, rng.choice(taglines)))
    return out


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = argparse.ArgumentParser(
        description="宠物起名助手: 按物种与性格关键词生成可爱宠物名")
    parser.add_argument("--species", default=None,
                        help="cat/dog/rabbit/hamster/bird/fish/lizard/any 或中文名; 缺省随机")
    parser.add_argument("--mood", default=None,
                        help="性格关键词, 如 高冷/吃货/活泼/粘人; 缺省随机")
    parser.add_argument("--count", type=int, default=5, help="生成数量 (默认 5)")
    parser.add_argument("--seed", type=int, default=None, help="随机种子, 便于复现")
    args = parser.parse_args(argv)

    if args.count < 1:
        parser.error("--count 至少为 1")

    rng = random.Random(args.seed)
    if args.species:
        species_key = normalize_species(args.species)
        if species_key is None:
            parser.error("未知物种: %s (可选 cat/dog/rabbit/hamster/bird/fish/lizard/any 或中文名)"
                         % args.species)
    else:
        species_key = rng.choice(list(SPECIES))
    mood = normalize_mood(args.mood) if args.mood else rng.choice(list(MOOD_POOLS))

    results = pick_names(species_key, mood, args.count, rng)
    for i, (name, tagline) in enumerate(results, 1):
        print("%d. %s（%s · %s）—— %s" % (i, name, SPECIES[species_key], mood, tagline))
    return 0


if __name__ == "__main__":
    sys.exit(main())
