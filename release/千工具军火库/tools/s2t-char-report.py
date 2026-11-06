#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s2t-char-report —— 简繁差异字频报告

统计文档中所有会因简繁转换而变化的字及其出现频次，生成差异字清单
（含词级差异，如 头发→頭髮）。

示例命令:
  python -I s2t-char-report.py 文档.txt
  python -I s2t-char-report.py -t "简体文本"
  python -I s2t-char-report.py 文档.txt --top 20

仅用 Python 标准库；内置常用简繁字表与词表（覆盖有限，非专业级转换）。
"""
import argparse
import sys

# ---------------------------------------------------------------------------
# 内置简繁数据（覆盖常用字/词，非专业级全量词表）
# ---------------------------------------------------------------------------
PAIRS_DATA = "爱愛碍礙袄襖罢罷摆擺败敗办辦帮幫宝寶报報币幣毕畢边邊变變标標宾賓补補参參惨慘灿燦苍蒼层層缠纏尝嘗长長偿償厂廠车車彻徹尘塵陈陳衬襯称稱惩懲迟遲础礎处處传傳疮瘡闯闖创創纯純词詞辞辭从從丛叢凑湊窜竄错錯达達带帶贷貸单單担擔胆膽弹彈当當党黨挡擋导導岛島祷禱灯燈邓鄧敌敵涤滌递遞点點电電动動独獨读讀断斷缎緞队隊对對吨噸顿頓夺奪堕墮鹅鵝额額恶惡儿兒尔爾饿餓罚罰阀閥范範饭飯访訪纺紡飞飛废廢费費坟墳奋奮粪糞丰豐风風冯馮凤鳳妇婦复復盖蓋刚剛岗崗纲綱钢鋼个個给給巩鞏贡貢沟溝构構购購够夠蛊蠱顾顧关關观觀馆館惯慣广廣归歸规規龟龜国國过過韩韓汉漢号號阂閡鹤鶴贺賀轰轟红紅壶壺护護沪滬华華画畫话話怀懷坏壞欢歡环環还還换換唤喚会會讳諱贿賄秽穢浑渾伙夥获獲货貨祸禍击擊机機鸡雞积積极極计計记記际際剂劑济濟挤擠价價驾駕歼殲艰艱监監检檢见見舰艦剑劍键鍵溅濺将將浆漿讲講奖獎桨槳酱醬胶膠阶階洁潔结結节節诚誠诫誡届屆紧緊谨謹进進尽盡惊驚经經静靜竞競净淨径徑旧舊剧劇惧懼据據觉覺绝絕军軍开開凯凱颗顆壳殼课課垦墾恳懇夸誇块塊亏虧扩擴阔闊兰蘭拦攔栏欄烂爛劳勞涝澇乐樂类類泪淚篱籬离離礼禮丽麗励勵历歷厉厲隶隸联聯怜憐帘簾莲蓮连連练練炼煉粮糧两兩辆輛疗療辽遼猎獵临臨邻鄰鳞鱗灵靈岭嶺领領刘劉龙龍楼樓娄婁芦蘆卢盧炉爐鲁魯陆陸录錄虑慮滤濾乱亂论論罗羅络絡骆駱妈媽马馬骂罵吗嗎买買卖賣迈邁麦麥脉脈瞒瞞满滿谩謾猫貓么麼门門闷悶们們梦夢弥彌谜謎觅覓绵綿缅緬庙廟灭滅悯憫鸣鳴谋謀亩畝纳納难難恼惱脑腦闹鬧拟擬腻膩酿釀鸟鳥聂聶宁寧农農浓濃疟瘧欧歐殴毆呕嘔盘盤庞龐赔賠喷噴骗騙飘飄频頻贫貧苹蘋凭憑评評泼潑铺鋪仆僕朴樸谱譜齐齊骑騎岂豈启啟弃棄气氣迁遷签簽谦謙钱錢浅淺谴譴枪槍抢搶桥橋侨僑窍竅窃竊亲親轻輕倾傾请請庆慶琼瓊穷窮区區驱驅趋趨龋齲权權劝勸确確让讓扰擾热熱认認韧韌荣榮绒絨软軟锐銳润潤洒灑萨薩赛賽伞傘丧喪骚騷涩澀杀殺纱紗筛篩晒曬删刪闪閃陕陝伤傷赏賞烧燒绍紹设設绅紳审審肾腎声聲绳繩胜勝圣聖师師时時湿濕实實诗詩识識势勢视視适適释釋寿壽兽獸书書属屬术術树樹帅帥双雙谁誰顺順说說硕碩丝絲松鬆苏蘇诉訴虽雖随隨岁歲孙孫损損缩縮态態摊攤谈談坛壇叹嘆汤湯烫燙涛濤讨討腾騰题題体體条條铁鐵厅廳听聽统統头頭图圖涂塗团團脱脫驮馱洼窪袜襪弯彎万萬网網韦韋违違围圍为為维維伟偉伪偽卫衛闻聞问問稳穩务務雾霧误誤牺犧习習戏戲细細虾蝦吓嚇峡峽侠俠狭狹厦廈鲜鮮纤纖现現献獻乡鄉详詳响響项項萧蕭销銷晓曉啸嘯协協胁脅谐諧写寫泻瀉谢謝兴興须須许許绪緒续續轩軒悬懸选選学學询詢训訓讯訊逊遜压壓鸦鴉哑啞亚亞严嚴盐鹽颜顏阎閻艳艷厌厭验驗阳陽养養样樣痒癢谣謠药藥爷爺页頁业業叶葉医醫仪儀义義议議亿億忆憶异異阴陰银銀隐隱应應婴嬰樱櫻鹰鷹营營蝇蠅赢贏优優忧憂邮郵犹猶诱誘与與语語誉譽郁鬱预預驭馭鸳鴛渊淵园園员員圆圓缘緣远遠愿願约約跃躍钥鑰粤粵云雲韵韻杂雜载載赞讚凿鑿责責择擇则則泽澤贼賊赠贈铡鍘诈詐斋齋债債战戰张張涨漲帐帳账賬这這针針侦偵诊診阵陣挣掙争爭郑鄭证證织織职職执執纸紙挚摯掷擲帜幟质質钟鐘种種众眾昼晝骤驟猪豬诸諸烛燭嘱囑瞩矚贮貯铸鑄筑築专專转轉赚賺庄莊装裝壮壯状狀锥錐谆諄浊濁兹茲资資渍漬踪蹤综綜总總纵縱邹鄒诅詛组組钻鑽虫蟲荡蕩丑醜触觸聪聰捣搗讹訛疯瘋讽諷缝縫尴尷刮颳挂掛骇駭挥揮辉輝汇匯荐薦冻凍栋棟锻鍛钉釘订訂厕廁厢廂县縣叁參吁籲吕呂呜嗚咏詠崭嶄侥僥储儲兑兌冈岡况況凉涼减減几幾夹夾垄壟垫墊宠寵宪憲宫宮宽寬寻尋屡屢屿嶼运運来來贵貴财財贝貝举舉产產仓倉东東乔喬丢丟乌烏无無俭儉佣傭侧側伦倫撑撐搀攙馋饞忏懺橱櫥锤錘懒懶冲衝划劃剐剮劲勁勋勳匀勻别別内內场場坚堅坝壩数數并並湾灣温溫线線库庫"
_S2T_PAIRS = [PAIRS_DATA[i:i + 2] for i in range(0, len(PAIRS_DATA), 2)]
S2T_CHAR = {p[0]: p[1] for p in _S2T_PAIRS}
T2S_CHAR = {p[1]: p[0] for p in _S2T_PAIRS}
for _k, _v in {'髮': '发', '麵': '面', '裡': '里', '裏': '里', '颱': '台', '乾': '干', '隻': '只', '於': '于', '餘': '余'}.items():
    T2S_CHAR.setdefault(_k, _v)

S2T_WORDS = [('头发', '頭髮'), ('理发', '理髮'), ('发型', '髮型'), ('假发', '假髮'), ('干净', '乾淨'), ('干燥', '乾燥'), ('干杯', '乾杯'), ('干脆', '乾脆'), ('面条', '麵條'), ('面包', '麵包'), ('面粉', '麵粉'), ('皇后', '皇后'), ('太后', '太后'), ('王后', '王后'), ('母后', '母后'), ('这里', '這裡'), ('那里', '那裡'), ('哪里', '哪裡'), ('心里', '心裡'), ('里面', '裡面'), ('家里', '家裡'), ('复杂', '複雜'), ('复制', '複製'), ('重复', '重複'), ('制作', '製作'), ('制造', '製造'), ('台风', '颱風'), ('台湾', '臺灣'), ('松树', '松樹'), ('松林', '松林'), ('松果', '松果'), ('松鼠', '松鼠'), ('轻松', '輕鬆'), ('放松', '放鬆'), ('批准', '批准'), ('标准', '標準'), ('准确', '準確'), ('冲突', '衝突'), ('冲动', '衝動'), ('计划', '計劃'), ('策划', '策劃'), ('一只', '一隻'), ('多余', '多餘'), ('其余', '其餘'), ('剩余', '剩餘'), ('余额', '餘額')]
T2S_WORDS = [(t, s) for s, t in S2T_WORDS] + [('乾坤', '乾坤')]

_HAN_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF),
               (0xF900, 0xFAFF), (0x20000, 0x2FA1F))


def is_han(ch):
    """是否为汉字（CJK 统一表意文字及其扩展区）"""
    o = ord(ch)
    return any(a <= o <= b for a, b in _HAN_RANGES)


def _convert(text, word_pairs, char_map):
    """逐位置转换，返回 (结果文本, 变更列表)。
    变更项为 (起始下标, 结束下标, 原文, 译文, 原因)。
    词表优先于单字（长词优先匹配）；与原文相同的词表项用于阻断单字映射。
    """
    word_map = dict(word_pairs)
    lens = sorted({len(w) for w, _ in word_pairs}, reverse=True)
    out = []
    changes = []
    i, n = 0, len(text)
    while i < n:
        hit = None
        for L in lens:
            seg = text[i:i + L]
            t = word_map.get(seg)
            if t is not None:
                hit = (L, seg, t)
                break
        if hit is not None:
            L, seg, t = hit
            out.append(t)
            if t != seg:
                changes.append((i, i + L, seg, t, "词表"))
            i += L
            continue
        ch = text[i]
        t = char_map.get(ch)
        out.append(t if t is not None else ch)
        if t is not None:
            changes.append((i, i + 1, ch, t, "单字"))
        i += 1
    return "".join(out), changes


def s2t(text):
    """简体 -> 繁体，返回 (结果, 变更列表)"""
    return _convert(text, S2T_WORDS, S2T_CHAR)


def t2s(text):
    """繁体 -> 简体，返回 (结果, 变更列表)"""
    return _convert(text, T2S_WORDS, T2S_CHAR)


def classify_char(ch):
    """汉字字形分类: 'S'=简体专用字形, 'T'=繁体专用字形, 'N'=中性/其他"""
    if ch in S2T_CHAR:
        return "S"
    if ch in T2S_CHAR:
        return "T"
    return "N"


def decode_guess(raw):
    """字节流解码：utf-8-sig / utf-8 / gb18030 依次尝试"""
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def read_text(path):
    """读文件并按 utf-8-sig / utf-8 / gb18030 依次尝试解码"""
    with open(path, "rb") as f:
        return decode_guess(f.read())


def get_input_text(args, path_attr="path"):
    """取输入文本：-t/--text 优先，其次文件路径，最后 stdin。
    stdin 走二进制缓冲区读原始字节，再用 decode_guess 探测解码，
    规避 Windows 管道下 sys.stdin.encoding=gbk 把 UTF-8 内容解成乱码的问题
    （python -I 含 -E，PYTHONIOENCODING/PYTHONUTF8 均无效，无法外部补救）。
    """
    if getattr(args, "text", None) is not None:
        return args.text
    path = getattr(args, path_attr, None)
    if path:
        return read_text(path)
    buf = getattr(sys.stdin, "buffer", None)
    if buf is not None:
        return decode_guess(buf.read())
    return sys.stdin.read()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="简繁差异字频报告：统计文档中所有会因简繁转换而变化的字/词"
                    "及其出现频次，生成差异字清单。")
    ap.add_argument("path", nargs="?", help="输入文件（缺省读 stdin）")
    ap.add_argument("-t", "--text", help="直接指定待统计文本")
    ap.add_argument("--top", type=int, default=0, help="只显示频次前 N 项（默认全部）")
    args = ap.parse_args(argv)
    text = get_input_text(args)
    counter = {}
    for line in text.split("\n"):
        _out, changes = s2t(line)
        for _s, _e, src, dst, reason in changes:
            key = (reason, src, dst)
            counter[key] = counter.get(key, 0) + 1
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0][1]))
    shown = items if args.top <= 0 else items[:args.top]
    print("频次  差异              来源")
    for (reason, src, dst), cnt in shown:
        print("%5d  %s → %s  [%s]" % (cnt, src, dst, reason))
    chars = sum(c for (r, _s, _d), c in items if r == "单字")
    words = sum(c for (r, _s, _d), c in items if r == "词表")
    nchar_keys = sum(1 for (r, _s, _d), _c in items if r == "单字")
    nword_keys = sum(1 for (r, _s, _d), _c in items if r == "词表")
    print("--")
    print("差异字 %d 个（共 %d 次），差异词 %d 个（共 %d 次）"
          % (nchar_keys, chars, nword_keys, words))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
