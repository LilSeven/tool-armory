#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""流式简繁管道转换：stdin/stdout 逐行转换，内存占用与文件大小无关，适合管道处理超大文件。

内置常用简繁字级对照表 + 常见歧义词级对照表（词级最长优先，先于字级应用），
纯标准库、离线可用。可另接 -g 词库 CSV（如 s2t-glossary-align 导出的对照表）。

示例命令：
  cat big.txt | python -I s2t-stream.py -d t > big_trad.txt
  python -I s2t-stream.py -d t -g glossary.csv < in.txt > out.txt
  python -I s2t-stream.py -d s < trad.txt > simp.txt
参数：
  -d {t,s}  t=简转繁（默认），s=繁转简
  -g FILE   附加词库 CSV，两列：简,繁（表头自动跳过）
"""
import argparse
import csv
import sys

# CHARMAP-BEGIN
# 简繁一对一常用字（每项两个字：简+繁，仅收录无歧义的映射）
PAIRS = """
爱愛 碍礙 袄襖 罢罷 摆擺 败敗 办辦 帮幫 宝寶 报報
币幣 边邊 变變 标標 别別 宾賓 补補 参參 惨慘 灿燦
层層 尝嘗 长長 偿償 厂廠 场場 车車 彻徹 尘塵 陈陳
衬襯 称稱 惩懲 迟遲 冲衝 础礎 处處 触觸 传傳 闯闖
创創 纯純 词詞 辞辭 从從 丛叢 凑湊 窜竄 错錯 达達
带帶 单單 担擔 胆膽 弹彈 当當 党黨 挡擋 岛島 灯燈
敌敵 涤滌 递遞 点點 电電 垫墊 调調 东東 动動 冻凍
栋棟 独獨 读讀 队隊 对對 吨噸 顿頓 夺奪 堕墮 鹅鵝
讹訛 恶惡 儿兒 尔爾 饿餓 发發 罚罰 阀閥 饭飯 访訪
纺紡 飞飛 废廢 费費 坟墳 奋奮 风風 冯馮 凤鳳 妇婦
负負 档檔 该該 盖蓋 冈岡 刚剛 钢鋼 岗崗 纲綱 柜櫃
个個 宫宮 贡貢 沟溝 构構 购購 够夠 顾顧 关關 观觀
馆館 惯慣 广廣 归歸 规規 龟龜 国國 过過 华華 画畫
话話 怀懷 坏壞 欢歡 环環 还還 换換 唤喚 挥揮 辉輝
会會 汇匯 讳諱 贿賄 秽穢 获獲 机機 鸡雞 极極 级級
挤擠 几幾 计計 记記 际際 剂劑 济濟 继繼 价價 驾駕
歼殲 监監 艰艱 检檢 减減 简簡 见見 荐薦 剑劍 键鍵
舰艦 节節 洁潔 结結 届屆 紧緊 谨謹 进進 尽盡 惊驚
经經 静靜 旧舊 剧劇 惧懼 据據 觉覺 决決 绝絕 军軍
开開 凯凱 颗顆 壳殼 课課 恳懇 夸誇 块塊 亏虧 扩擴
阔闊 蜡蠟 来來 兰蘭 拦攔 栏欄 烂爛 劳勞 乐樂 类類
泪淚 离離 礼禮 丽麗 厉厲 励勵 历歷 联聯 怜憐 帘簾
莲蓮 连連 练練 炼煉 粮糧 两兩 辆輛 疗療 辽遼 猎獵
临臨 邻鄰 灵靈 岭嶺 领領 刘劉 龙龍 楼樓 陆陸 录錄
虑慮 乱亂 论論 罗羅 络絡 妈媽 马馬 骂罵 吗嗎 买買
卖賣 迈邁 麦麥 脉脈 满滿 猫貓 么麼 门門 闷悶 们們
梦夢 觅覓 绵綿 缅緬 庙廟 灭滅 鸣鳴 谋謀 亩畝 纳納
难難 恼惱 脑腦 闹鬧 内內 拟擬 酿釀 鸟鳥 宁寧 农農
浓濃 疟瘧 欧歐 呕嘔 盘盤 赔賠 喷噴 骗騙 飘飄 频頻
贫貧 苹蘋 凭憑 泼潑 铺鋪 仆僕 朴樸 谱譜 齐齊 骑騎
岂豈 启啟 弃棄 气氣 迁遷 签簽 谦謙 钱錢 潜潛 浅淺
谴譴 枪槍 抢搶 桥橋 侨僑 窍竅 窃竊 亲親 轻輕 倾傾
庆慶 琼瓊 穷窮 区區 驱驅 趋趨 权權 劝勸 让讓 扰擾
热熱 认認 韧韌 荣榮 绒絨 软軟 锐銳 润潤 洒灑 萨薩
赛賽 伞傘 丧喪 涩澀 杀殺 筛篩 晒曬 删刪 闪閃 陕陝
伤傷 赏賞 烧燒 绍紹 设設 绅紳 肾腎 声聲 胜勝 圣聖
师師 湿濕 诗詩 时時 实實 识識 势勢 适適 释釋 饰飾
视視 试試 寿壽 兽獸 书書 属屬 术術 树樹 帅帥 双雙
谁誰 税稅 顺順 说說 硕碩 丝絲 讼訟 颂頌 苏蘇 诉訴
虽雖 随隨 岁歲 孙孫 损損 缩縮 锁鎖 态態 摊攤 谈談
坛壇 叹嘆 汤湯 烫燙 涛濤 讨討 腾騰 题題 体體 条條
铁鐵 厅廳 听聽 铜銅 统統 头頭 图圖 涂塗 团團 驼駝
洼窪 袜襪 弯彎 万萬 网網 韦韋 违違 围圍 为為 维維
伟偉 卫衛 温溫 闻聞 稳穩 问問 无無 务務 雾霧 误誤
牺犧 习習 戏戲 细細 虾蝦 吓嚇 峡峽 侠俠 狭狹 厦廈
鲜鮮 纤纖 咸鹹 显顯 险險 现現 献獻 县縣 宪憲 线線
乡鄉 详詳 响響 项項 萧蕭 销銷 晓曉 协協 胁脅 谐諧
写寫 泻瀉 谢謝 兴興 须須 许許 绪緒 续續 悬懸 选選
学學 询詢 寻尋 训訓 讯訊 逊遜 压壓 鸭鴨 哑啞 亚亞
严嚴 盐鹽 颜顏 艳艷 厌厭 验驗 阳陽 杨楊 养養 样樣
谣謠 摇搖 药藥 爷爺 页頁 业業 叶葉 医醫 仪儀 义義
议議 亿億 忆憶 异異 阴陰 银銀 隐隱 应應 婴嬰 樱櫻
鹰鷹 赢贏 拥擁 佣傭 踊踴 忧憂 优優 犹猶 邮郵 诱誘
与與 屿嶼 语語 誉譽 预預 渊淵 园園 员員 圆圓 缘緣
远遠 愿願 约約 跃躍 悦悅 阅閱 云雲 运運 韵韻 杂雜
灾災 载載 赞讚 脏臟 凿鑿 责責 择擇 则則 泽澤 赠贈
闸閘 诈詐 债債 战戰 张張 涨漲 帐帳 账賬 这這 侦偵
诊診 阵陣 争爭 郑鄭 证證 织織 职職 执執 纸紙 掷擲
帜幟 质質 钟鐘 终終 种種 众眾 昼晝 骤驟 猪豬 诸諸
烛燭 嘱囑 筑築 铸鑄 专專 转轉 赚賺 庄莊 装裝 壮壯
状狀 谆諄 浊濁 资資 渍漬 踪蹤 综綜 总總 纵縱 组組
钻鑽 伪偽 妆妝 钉釘 订訂 浇澆 骄驕 娇嬌 缴繳 溃潰
馈饋 绘繪 览覽 揽攬 缆纜 榄欖 湾灣 诞誕 杠槓 笋筍
鳄鱷 鲤鯉 鲫鯽 鲨鯊 鲸鯨 鸠鳩 鸢鳶 鸥鷗 鹃鵑 鹏鵬
鹤鶴 缤繽 纷紛 讽諷 着著 间間 闷悶 问问 闻聞 阔闊
""".split()

# 仅用于繁->简方向的补充映射（简->繁有歧义，故不放进双向表）
T2S_EXTRA = """
後后 髮发 麵面 乾干 鬥斗 醜丑 穀谷 鬆松 鬚须 裡里
裏里 臺台 颱台 於于 穀谷 餘余 捨舍 採采 錶表 唸念
湧涌 樑梁 藉借 託托 鑑鉴
""".split()

# 词级对照，用于消歧；T2S 方向里“著作/著名”是保护词（避免 著->着 误转）
WORDS = [
    ("发展", "發展"), ("发现", "發現"), ("发表", "發表"),
    ("发明", "發明"), ("发挥", "發揮"), ("发出", "發出"),
    ("发生", "發生"), ("出发", "出發"), ("头发", "頭髮"),
    ("理发", "理髮"), ("长发", "長髮"), ("后来", "後來"),
    ("以后", "以後"), ("然后", "然後"), ("后面", "後面"),
    ("落后", "落後"), ("最后", "最後"), ("之后", "之後"),
    ("干净", "乾淨"), ("干燥", "乾燥"), ("干活", "幹活"),
    ("干劲", "幹勁"), ("才干", "才幹"), ("能干", "能幹"),
    ("干部", "幹部"), ("树干", "樹幹"), ("干线", "幹線"),
    ("主干", "主幹"), ("面条", "麵條"), ("面包", "麵包"),
    ("泡面", "泡麵"), ("面粉", "麵粉"), ("面食", "麵食"),
    ("拉面", "拉麵"), ("里面", "裡面"), ("老板", "老闆"),
    ("台湾", "臺灣"), ("台北", "臺北"), ("台风", "颱風"),
    ("斗争", "鬥爭"), ("奋斗", "奮鬥"), ("战斗", "戰鬥"),
    ("标准", "標準"), ("著作", "著作"), ("著名", "著名"),
    ("土著", "土著"),
]
# CHARMAP-END

_S2T = None
_T2S = None
_WS2T = None
_WT2S = None


def _init_maps():
    global _S2T, _T2S, _WS2T, _WT2S
    if _S2T is not None:
        return
    s2t, t2s = {}, {}
    for p in PAIRS:
        if len(p) == 2 and p[0] != p[1]:
            s2t.setdefault(p[0], p[1])
            t2s.setdefault(p[1], p[0])
    for p in T2S_EXTRA:
        if len(p) == 2:
            t2s.setdefault(p[0], p[1])  # 条目形如“後后”：繁在前，简在后
    ws2t, wt2s = {}, {}
    for s, t in WORDS:
        if s != t:
            ws2t.setdefault(s, t)
            wt2s.setdefault(t, s)
        else:  # 保护词：T->S 方向锁定原样
            wt2s.setdefault(t, s)
    _S2T, _T2S, _WS2T, _WT2S = s2t, t2s, ws2t, wt2s


def _buckets(wordmap):
    """按首字分组，组内按词条长度降序，供最长优先扫描。"""
    b = {}
    for w in sorted(wordmap, key=len, reverse=True):
        b.setdefault(w[0], []).append((w, wordmap[w]))
    return b


def get_context(direction, gloss=None):
    """返回 (word_buckets, charmap)。gloss 为 [(term, replacement), ...] 附加词库。"""
    _init_maps()
    if direction == "t":
        words, charmap = dict(_WS2T), _S2T
        for s, t in gloss or []:
            words[s] = t
    else:
        words, charmap = dict(_WT2S), _T2S
        for s, t in gloss or []:
            words[t] = s
    return _buckets(words), charmap


def convert(text, direction="t", ctx=None):
    buckets, charmap = ctx if ctx else get_context(direction)
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        bucket = buckets.get(ch)
        hit = None
        if bucket:
            for w, rep in bucket:
                if text.startswith(w, i):
                    hit = w
                    out.append(rep)
                    break
        if hit is not None:
            i += len(hit)
        else:
            out.append(charmap.get(ch, ch))
            i += 1
    return "".join(out)


def load_gloss(path, direction="t"):
    """读取两列 CSV 词库（简,繁），返回 [(term, replacement), ...]。"""
    gloss = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row or len(row) < 2:
                continue
            if row[0].strip() == "简" and row[1].strip() == "繁":
                continue  # 跳过表头
            term, repl = row[0].strip(), row[1].strip()
            if not term or not repl:
                continue
            gloss.append((term, repl))
    return gloss


def main(argv=None):
    ap = argparse.ArgumentParser(description="流式简繁管道转换（stdin->stdout）")
    ap.add_argument("-d", "--direction", choices=["t", "s"], default="t",
                    help="t=简转繁(默认)，s=繁转简")
    ap.add_argument("-g", "--glossary", help="附加词库 CSV（两列：简,繁）")
    args = ap.parse_args(argv)

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")

    gloss = load_gloss(args.glossary, args.direction) if args.glossary else []
    ctx = get_context(args.direction, gloss)
    for line in sys.stdin:
        sys.stdout.write(convert(line, args.direction, ctx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
