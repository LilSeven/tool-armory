#!/usr/bin/env python3
"""鸡尾酒命名师 —— 把心情或天气变成一款虚构鸡尾酒(名字 + 配方)。

用途:
    输入心情(如 emo、加班、心动)或天气(如 雨、暴雪、高温),
    生成对应的虚构鸡尾酒名、英文副题与一份像模像样的配方。

用法:
    python cocktail-namer.py (--mood 关键词 | --weather 关键词) [--count N] [--seed SEED] [--virgin]

示例命令:
    python cocktail-namer.py --mood emo
    python cocktail-namer.py --weather 雨 --count 2 --seed 3
    python cocktail-namer.py --mood 加班 --virgin     # 0 酒精版

说明: 关键词中英文均可; 没命中词库时按「通配主题」处理, 仍会给出结果。
仅依赖 Python 标准库; 成功时退出码为 0。
"""

from __future__ import annotations

import argparse
import random
import sys

THEMES = [
    {
        "cn": "雨天",
        "keys": ["雨", "rain", "梅雨", "雷阵雨", "drizzle", "下雨"],
        "adj": ["雨后", "潮湿", "伞下", "雨滴", "梅雨"],
        "enadj": ["Rainy", "Petrichor", "Drizzle", "Umbrella"],
        "noun": ["情书", "圆舞曲", "慢直播", "信号", "絮语"],
        "ennoun": ["Letter", "Waltz", "Signal", "Murmur"],
        "spirit": ["金酒", "白朗姆", "伏特加"],
        "liqueur": ["接骨木花利口酒", "蓝橙利口酒", "杏子白兰地"],
        "mixer": ["柠檬汁", "青柠汁", "气泡水", "汤力水"],
        "syrup": ["蜂蜜糖浆", "接骨木花糖浆", "青柠糖浆"],
        "garnish": ["柠檬皮卷", "迷迭香一枝", "黄瓜薄片"],
        "method": ["摇和法", "直调法"],
        "glass": ["高球杯", "柯林杯", "碟形香槟杯"],
    },
    {
        "cn": "雪天",
        "keys": ["雪", "snow", "初雪", "暴雪", "下雪"],
        "adj": ["初雪", "雪落", "雪白", "呵气成霜", "绒毛"],
        "enadj": ["Snowy", "Frost", "Powder", "Flurry"],
        "noun": ["慢信", "拥抱", "棉被", "糖霜", "停电夜"],
        "ennoun": ["Letter", "Hug", "Blanket", "Icing"],
        "spirit": ["伏特加", "白朗姆"],
        "liqueur": ["椰子利口酒", "白薄荷利口酒", "巧克力利口酒"],
        "mixer": ["椰奶", "热牛奶", "柠檬汁"],
        "syrup": ["香草糖浆", "蜂蜜糖浆", "白巧克力糖浆"],
        "garnish": ["糖边", "薄荷叶", "棉花糖两颗"],
        "method": ["摇和法", "搅和法"],
        "glass": ["古典杯", "爱尔兰咖啡杯", "碟形香槟杯"],
    },
    {
        "cn": "晴天",
        "keys": ["晴", "太阳", "sunny", "阳光", "夏天", "盛夏"],
        "adj": ["阳光过剩", "正午", "盛夏", "防晒霜", "六点半的"],
        "enadj": ["Sunny", "Noon", "Solstice", "Bright"],
        "noun": ["冰镇汽水", "单车道", "白衬衫", "假期", "跳水池"],
        "ennoun": ["Soda", "Ride", "Holiday", "Pool"],
        "spirit": ["白朗姆", "龙舌兰", "金酒"],
        "liqueur": ["蜜桃利口酒", "椰子利口酒", "橙皮利口酒"],
        "mixer": ["菠萝汁", "橙汁", "椰奶", "柠檬汁"],
        "syrup": ["西瓜糖浆", "蜂蜜糖浆", "百香果糖浆"],
        "garnish": ["菠萝角", "橙片", "薄荷叶", "小纸伞"],
        "method": ["摇和法", "直调法"],
        "glass": ["飓风杯", "高球杯", "柯林杯"],
    },
    {
        "cn": "雾天",
        "keys": ["雾", "fog", "雾霾", "起雾"],
        "adj": ["起雾", "灰蓝", "晨雾", "能见度五米", "薄雾"],
        "enadj": ["Foggy", "Misty", "Hazy", "Grey"],
        "noun": ["航标", "汽笛", "旧灯塔", "远山", "慢船"],
        "ennoun": ["Beacon", "Ferry", "Lighthouse", "Harbor"],
        "spirit": ["金酒", "黑朗姆"],
        "liqueur": ["绿查特利口酒", "接骨木花利口酒", "少量苦艾酒"],
        "mixer": ["柠檬汁", "蛋清", "汤力水"],
        "syrup": ["蜂蜜糖浆", "鼠尾草糖浆"],
        "garnish": ["烟熏迷迭香", "柠檬皮卷", "海盐边"],
        "method": ["摇和法", "搅和法"],
        "glass": ["马提尼杯", "碟形香槟杯"],
    },
    {
        "cn": "暴风天",
        "keys": ["雷", "台风", "暴风", "storm", "暴雨", "大风", "狂风"],
        "adj": ["雷雨前", "风暴眼", "漆黑", "十级", "失联"],
        "enadj": ["Stormy", "Thunder", "Blackout", "Wild"],
        "noun": ["应急灯", "背风处", "汽笛", "铁皮屋顶", "停电舞会"],
        "ennoun": ["Blackout", "Shelter", "Ballroom", "Signal"],
        "spirit": ["黑朗姆", "波本", "暗朗姆"],
        "liqueur": ["咖啡利口酒", "姜味利口酒"],
        "mixer": ["姜汁汽水", "柠檬汁", "苦精数滴"],
        "syrup": ["焦糖糖浆", "黑糖糖浆"],
        "garnish": ["焦糖脆片", "黑巧克力碎", "火烤橙片"],
        "method": ["摇和法", "搅和法"],
        "glass": ["古典杯", "高球杯"],
    },
    {
        "cn": "高温天",
        "keys": ["热", "高温", "酷暑", "hot", "三伏", "热化"],
        "adj": ["高温预警", "大汗", "冰镇", "午后两点的", "空调外机旁"],
        "enadj": ["Boiling", "Scorcher", "Frozen", "Melt"],
        "noun": ["凉白开", "风扇", "西瓜中间那一口", "午觉", "泳池边"],
        "ennoun": ["Melon", "Fan", "Siesta", "Pool"],
        "spirit": ["伏特加", "白朗姆", "龙舌兰"],
        "liqueur": ["蜜桃利口酒", "椰子利口酒"],
        "mixer": ["西瓜汁", "柠檬汁", "椰子水", "薄荷苏打"],
        "syrup": ["西瓜糖浆", "百香果糖浆", "蜂蜜糖浆"],
        "garnish": ["薄荷叶一把", "西瓜球", "碎冰堆成小山"],
        "method": ["摇和法", "直调法"],
        "glass": ["飓风杯", "高球杯"],
    },
    {
        "cn": "开心",
        "keys": ["开心", "高兴", "快乐", "happy", "升职", "狂喜", "中奖", "顺利"],
        "adj": ["小确幸", "好事发生", "走路带风", "锦鲤附体", "不用上班的"],
        "enadj": ["Lucky", "Golden", "Bubbly", "Cheers"],
        "noun": ["花火", "庆祝", "转圈圈", "小汽笛", "彩带"],
        "ennoun": ["Firework", "Toast", "Confetti", "Whistle"],
        "spirit": ["金酒", "白朗姆", "起泡酒"],
        "liqueur": ["蜜桃利口酒", "橙皮利口酒", "接骨木花利口酒"],
        "mixer": ["香槟", "柠檬汁", "气泡水"],
        "syrup": ["树莓糖浆", "蜂蜜糖浆"],
        "garnish": ["食用花瓣", "糖边", "柠檬皮卷"],
        "method": ["摇和法", "直调法"],
        "glass": ["碟形香槟杯", "笛型香槟杯"],
    },
    {
        "cn": "低落",
        "keys": ["难过", "emo", "丧", "sad", "眼泪", "失恋", "blue", "哭"],
        "adj": ["蓝色", "湿透", "深夜", "没删掉的", "四点半的"],
        "enadj": ["Blue", "Salty", "Midnight", "Faded"],
        "noun": ["忧郁", "片尾曲", "未发送", "旧车票", "止不住"],
        "ennoun": ["Melody", "Draft", "Ticket", "Rain"],
        "spirit": ["黑朗姆", "波本", "咖啡利口酒"],
        "liqueur": ["咖啡利口酒", "黑巧克力利口酒"],
        "mixer": ["冷萃咖啡", "柠檬汁", "苦精数滴"],
        "syrup": ["黑糖糖浆", "海盐糖浆"],
        "garnish": ["黑巧克力屑", "柠檬皮卷", "海盐边"],
        "method": ["摇和法", "搅和法"],
        "glass": ["碟形香槟杯", "古典杯"],
    },
    {
        "cn": "愤怒",
        "keys": ["生气", "愤怒", "怒", "angry", "火大", "气死", "破防"],
        "adj": ["沸腾", "上头", "冒烟", "高压锅", "气到冒泡的"],
        "enadj": ["Boiling", "Smoky", "Furious", "Spicy"],
        "noun": ["排气阀", "反击", "战书", "冷却期", "闪电"],
        "ennoun": ["Valve", "Revenge", "Thunder", "Cooldown"],
        "spirit": ["龙舌兰", "黑朗姆", "伏特加"],
        "liqueur": ["姜味利口酒", "咖啡利口酒"],
        "mixer": ["姜汁啤酒", "柠檬汁", "苦精数滴"],
        "syrup": ["辣椒糖浆", "黑糖糖浆"],
        "garnish": ["火烤橙片", "墨西哥辣椒圈", "黑胡椒少许"],
        "method": ["摇和法", "直调法"],
        "glass": ["古典杯", "子弹杯"],
    },
    {
        "cn": "心动",
        "keys": ["心动", "恋爱", "喜欢", "love", "crush", "暧昧", "表白", "暗恋"],
        "adj": ["恋爱先兆", "心跳过速", "近距离", "偷看的", "耳根发热的"],
        "enadj": ["Blushing", "Closer", "Butterfly", "Sweet"],
        "noun": ["桃色信号", "耳语", "同频", "试探", "半糖"],
        "ennoun": ["Signal", "Whisper", "Flutter", "Bloom"],
        "spirit": ["金酒", "白朗姆"],
        "liqueur": ["蜜桃利口酒", "荔枝利口酒", "玫瑰利口酒"],
        "mixer": ["荔枝汁", "柠檬汁", "气泡水"],
        "syrup": ["玫瑰糖浆", "树莓糖浆", "蜂蜜糖浆"],
        "garnish": ["玫瑰花瓣", "草莓一颗", "粉色糖边"],
        "method": ["摇和法", "直调法"],
        "glass": ["笛型香槟杯", "碟形香槟杯", "高球杯"],
    },
    {
        "cn": "疲惫",
        "keys": ["累", "加班", "困", "tired", "burnout", "打工", "上班", "社畜"],
        "adj": ["濒临死机", "第十三小时", "带薪", "电量1%", "第二天"],
        "enadj": ["Burnout", "Overtime", "Lowbattery", "Zombie"],
        "noun": ["续命", "回血", "暂停键", "摸鱼许可", "迟到的闹钟"],
        "ennoun": ["Restart", "Pause", "Rescue", "Snooze"],
        "spirit": ["波本", "伏特加"],
        "liqueur": ["咖啡利口酒", "榛子利口酒"],
        "mixer": ["冷萃咖啡", "可乐", "柠檬汁"],
        "syrup": ["黑糖糖浆", "香草糖浆"],
        "garnish": ["咖啡豆三粒", "橙皮", "可可粉撒面"],
        "method": ["摇和法", "直调法"],
        "glass": ["古典杯", "高球杯"],
    },
    {
        "cn": "失眠",
        "keys": ["失眠", "熬夜", "insomnia", "凌晨", "睡不着", "数羊"],
        "adj": ["凌晨三点", "越夜", "睁眼", "第七只羊", "天快亮的"],
        "enadj": ["Sleepless", "Three-AM", "Dawn", "Counting"],
        "noun": ["闹钟", "数羊", "再刷一集", "天花板", "早班地铁"],
        "ennoun": ["Sheep", "Alarm", "Ceiling", "Metro"],
        "spirit": ["伏特加", "金酒"],
        "liqueur": ["咖啡利口酒", "白薄荷利口酒"],
        "mixer": ["气泡水", "柠檬汁", "热牛奶"],
        "syrup": ["蜂蜜糖浆", "薰衣草糖浆"],
        "garnish": ["柠檬皮卷", "薰衣草一小枝", "薄荷叶"],
        "method": ["摇和法", "直调法"],
        "glass": ["高球杯", "马提尼杯"],
    },
    {
        "cn": "平静",
        "keys": ["平静", "躺平", "zen", "发呆", "放松", "chill", "佛系", "微风"],
        "adj": ["佛系", "慢速", "水平面", "无风带", "午后四点的"],
        "enadj": ["Zen", "Drifting", "Still", "Breeze"],
        "noun": ["漂流", "发呆权", "午后", "白噪音", "浅滩"],
        "ennoun": ["Drift", "Nap", "Static", "Shoal"],
        "spirit": ["金酒", "白朗姆"],
        "liqueur": ["接骨木花利口酒", "蜜桃利口酒"],
        "mixer": ["黄瓜汁", "汤力水", "气泡水"],
        "syrup": ["接骨木花糖浆", "蜂蜜糖浆"],
        "garnish": ["黄瓜卷", "薄荷叶", "柠檬皮卷"],
        "method": ["直调法", "搅和法"],
        "glass": ["高球杯", "柯林杯"],
    },
]

# 没命中任何关键词时的通配主题: adj=None 表示拿关键词本身当形容词
GENERIC = {
    "cn": "通配",
    "adj": None,
    "enadj": ["Signature", "Off-menu", "Secret"],
    "noun": ["特调", "实验品", "序章", "备忘录", "临时剧本"],
    "ennoun": ["Special", "Memo", "Prelude", "Draft"],
    "spirit": ["金酒", "伏特加", "白朗姆", "波本"],
    "liqueur": ["接骨木花利口酒", "蜜桃利口酒", "咖啡利口酒"],
    "mixer": ["柠檬汁", "青柠汁", "气泡水", "汤力水"],
    "syrup": ["蜂蜜糖浆", "树莓糖浆", "香草糖浆"],
    "garnish": ["柠檬皮卷", "薄荷叶", "橙片", "糖边"],
    "method": ["摇和法", "直调法", "搅和法"],
    "glass": ["高球杯", "马提尼杯", "古典杯"],
}

VIRGIN_BASE = ["冷萃乌龙茶", "柠檬苏打水", "接骨木花气泡水", "冰滴咖啡", "椰子水"]


def match_theme(text: str):
    t = text.lower()
    for theme in THEMES:
        for key in theme["keys"]:
            if key.lower() in t:
                return theme
    return None


def build(theme: dict, adj_word: str, rng: random.Random, virgin: bool) -> tuple:
    adj = rng.choice(theme["adj"]) if theme["adj"] else adj_word
    name = "%s%s" % (adj, rng.choice(theme["noun"]))
    en = "%s %s" % (rng.choice(theme["enadj"]), rng.choice(theme["ennoun"]))
    if virgin:
        base, base_ml = rng.choice(VIRGIN_BASE), rng.choice([120, 150, 180])
    else:
        base, base_ml = rng.choice(theme["spirit"]), rng.choice([40, 45, 50, 60])
    parts = [
        "%s %dml" % (base, base_ml),
        "%s %dml" % (rng.choice(theme["liqueur"]), rng.choice([10, 15, 20])),
        "%s %dml" % (rng.choice(theme["mixer"]), rng.choice([15, 30, 45])),
        "%s %dml" % (rng.choice(theme["syrup"]), rng.choice([5, 10, 15])),
    ]
    recipe = " / ".join(parts)
    ice = "加冰" if rng.random() < 0.8 else "不加冰"
    method = "%s, 滤入%s%s" % (rng.choice(theme["method"]), rng.choice(theme["glass"]), ice)
    garnish = rng.choice(theme["garnish"])
    return name, en, recipe, method, garnish


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = argparse.ArgumentParser(
        description="鸡尾酒命名师: 把心情或天气变成虚构鸡尾酒名与配方")
    parser.add_argument("--mood", default=None, help="心情关键词, 如 emo / 加班 / 心动")
    parser.add_argument("--weather", default=None, help="天气关键词, 如 雨 / 暴雪 / 高温")
    parser.add_argument("--count", type=int, default=1, help="生成几款 (默认 1)")
    parser.add_argument("--seed", type=int, default=None, help="随机种子, 便于复现")
    parser.add_argument("--virgin", action="store_true", help="生成 0 酒精版")
    args = parser.parse_args(argv)

    keywords = [k for k in (args.mood, args.weather) if k]
    if not keywords:
        parser.error("请至少提供 --mood 或 --weather 之一, 例如 --mood emo / --weather 雨")
    if args.count < 1:
        parser.error("--count 至少为 1")

    rng = random.Random(args.seed)
    text = " ".join(keywords)
    theme = match_theme(text) or GENERIC

    results = []
    seen = set()
    attempts = 0
    while len(results) < args.count and attempts < args.count * 50:
        attempts += 1
        name, en, recipe, method, garnish = build(theme, keywords[0], rng, args.virgin)
        if name in seen:
            continue
        seen.add(name)
        results.append((name, en, recipe, method, garnish))

    for i, (name, en, recipe, method, garnish) in enumerate(results, 1):
        print("No.%d 《%s》 (%s)" % (i, name, en))
        print("    主题: %s | 关键词: %s" % (theme["cn"], text))
        print("    配方: %s" % recipe)
        print("    做法: %s" % method)
        print("    装饰: %s" % garnish)
        if args.virgin:
            print("    备注: 0 度无酒精版")
    return 0


if __name__ == "__main__":
    sys.exit(main())
