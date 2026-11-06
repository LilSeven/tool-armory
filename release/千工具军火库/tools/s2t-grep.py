#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""简繁互搜 (s2t-grep)。

在文件中搜索关键词时自动匹配其简体/繁体字形变体, 报告命中的文件与
行号。内置常用简繁字对照表 (含一简对多繁), 对关键词逐字展开为字符
类再正则匹配, 例如搜「硬盘」可同时命中「硬盘」「硬盤」。

用法:
    python s2t-grep.py [-r] [-i] [--count] <关键词> <文件或目录>...

示例命令:
    python s2t-grep.py 硬盘 ./docs          # 目录默认只扫第一层文件
    python s2t-grep.py -r -i note ./notes   # -r 递归遍历子目录
    python s2t-grep.py --count 软件 ./src

退出码: 0 = 有匹配; 1 = 无匹配; 2 = 用法或 IO 错误。
"""

import argparse
import os
import re
import sys

# 每行: 简体 + 空格 + 一个或多个繁体写法
_PAIR_DATA = """\
爱 愛
碍 礙
袄 襖
罢 罷
摆 擺
板 闆
办 辦
帮 幫
绑 綁
宝 寶
报 報
币 幣
毕 畢
边 邊
变 變
标 標
别 彆
宾 賓
补 補
才 纔
采 採
参 參
残 殘
灿 燦
仓 倉
苍 蒼
层 層
尝 嘗
长 長
偿 償
厂 廠
车 車
彻 徹
尘 塵
陈 陳
称 稱
惩 懲
迟 遲
冲 衝 沖
丑 醜
础 礎
处 處
触 觸
传 傳
疮 瘡
闯 闖
创 創
纯 純
词 詞
辞 辭
从 從
丛 叢
凑 湊
窜 竄
错 錯
达 達
带 帶
贷 貸
单 單
担 擔
胆 膽
弹 彈
当 當 噹
党 黨
挡 擋
导 導
岛 島
祷 禱
灯 燈
敌 敵
涤 滌
递 遞
点 點
电 電
淀 澱
调 調
订 訂
东 東
动 動
冻 凍
栋 棟
斗 鬥
独 獨
读 讀
赌 賭
断 斷
缎 緞
队 隊
对 對
吨 噸
顿 頓
夺 奪
堕 墮
讹 訛
额 額
恶 惡
儿 兒
尔 爾
饿 餓
发 發 髮
罚 罰
阀 閥
范 範
纺 紡
飞 飛
废 廢
费 費
坟 墳
奋 奮
粪 糞
丰 豐
风 風
冯 馮
缝 縫
讽 諷
凤 鳳
妇 婦
复 復 複
负 負
该 該
盖 蓋
干 幹 乾
赶 趕
钢 鋼
岗 崗
纲 綱
个 個
给 給
巩 鞏
贡 貢
沟 溝
构 構
购 購
够 夠
顾 顧
剐 剮
关 關
观 觀
馆 館
惯 慣
贯 貫
广 廣
归 歸
龟 龜
规 規
贵 貴
辊 輥
锅 鍋
国 國
过 過
汉 漢
号 號
阂 閡
鹤 鶴
贺 賀
横 橫
轰 轟
红 紅
后 後
壶 壺
护 護
沪 滬
华 華
划 劃
画 畫
话 話
怀 懷
坏 壞
欢 歡
环 環
还 還
缓 緩
换 換
唤 喚
谎 謊
挥 揮
辉 輝
汇 匯 彙
会 會
讳 諱
贿 賄
秽 穢
获 獲 穫
机 機
鸡 雞
积 積
极 極
计 計
记 記
纪 紀
剂 劑
济 濟
继 繼
价 價
艰 艱
监 監
检 檢
减 減
简 簡
见 見
荐 薦
贱 賤
舰 艦
剑 劍
键 鍵
溅 濺
将 將
浆 漿
奖 獎
讲 講
酱 醬
胶 膠
阶 階
洁 潔
结 結
节 節
诫 誡
届 屆
紧 緊
谨 謹
进 進
尽 盡 儘
劲 勁
惊 驚
经 經
茎 莖
静 靜
竞 競
净 淨
径 徑
旧 舊
剧 劇
惧 懼
据 據
觉 覺
绝 絕
军 軍
开 開
凯 凱
颗 顆
壳 殼
课 課
恳 懇
抠 摳
库 庫
裤 褲
夸 誇
块 塊
亏 虧
扩 擴
蜡 蠟
腊 臘
来 來
莱 萊
兰 蘭
拦 攔
栏 欄
烂 爛
劳 勞
涝 澇
乐 樂
垒 壘
类 類
泪 淚
篱 籬
离 離
里 裡 裏
礼 禮
丽 麗
厉 厲
励 勵
历 歷 曆
隶 隸
联 聯
怜 憐
帘 簾
莲 蓮
连 連
炼 煉
练 練
粮 糧
两 兩
辆 輛
谅 諒
疗 療
辽 遼
猎 獵
临 臨
邻 鄰
鳞 鱗
灵 靈
岭 嶺
领 領
刘 劉
龙 龍
聋 聾
拢 攏
陇 隴
楼 樓
娄 婁
芦 蘆
卢 盧
炉 爐
陆 陸
虏 虜
录 錄
虑 慮
滤 濾
乱 亂
论 論
罗 羅
络 絡
骆 駱
妈 媽
马 馬
骂 罵
吗 嗎
买 買
卖 賣
迈 邁
麦 麥
脉 脈
瞒 瞞
满 滿
谩 謾
猫 貓
么 麼
门 門
闷 悶
们 們
梦 夢
谜 謎
弥 彌
面 麵
庙 廟
灭 滅
悯 憫
鸣 鳴
铭 銘
谋 謀
亩 畝
纳 納
难 難
挠 撓
脑 腦
恼 惱
闹 鬧
拟 擬
腻 膩
酿 釀
鸟 鳥
聂 聶
宁 寧
拧 擰
农 農
浓 濃
疟 瘧
盘 盤
庞 龐
赔 賠
喷 噴
鹏 鵬
骗 騙
飘 飄
频 頻
贫 貧
苹 蘋
凭 憑
评 評
泼 潑
铺 鋪
朴 樸
谱 譜
齐 齊
骑 騎
岂 豈
弃 棄
启 啟
气 氣
迁 遷
签 簽 籤
谦 謙
钱 錢
钳 鉗
浅 淺
谴 譴
枪 槍
墙 牆
抢 搶
桥 橋
侨 僑
窍 竅
窃 竊
亲 親
轻 輕
倾 傾
庆 慶
琼 瓊
穷 窮
区 區
驱 驅
龋 齲
权 權
劝 勸
让 讓
扰 擾
热 熱
认 認
韧 韌
荣 榮
绒 絨
软 軟
锐 銳
闰 閏
润 潤
洒 灑
萨 薩
赛 賽
伞 傘
丧 喪
骚 騷
涩 澀
杀 殺
筛 篩
晒 曬
删 刪
闪 閃
陕 陝
赡 贍
缮 繕
伤 傷
赏 賞
烧 燒
绍 紹
摄 攝
设 設
绅 紳
审 審
肾 腎
声 聲
胜 勝
圣 聖
师 師
湿 濕
诗 詩
时 時
识 識
实 實
蚀 蝕
势 勢
适 適
释 釋
饰 飾
视 視
试 試
寿 壽
兽 獸
枢 樞
输 輸
属 屬
树 樹
竖 豎
帅 帥
双 雙
谁 誰
顺 順
说 說
硕 碩
丝 絲
松 鬆
苏 蘇 甦
诉 訴
肃 肅
虽 雖
随 隨
岁 歲
孙 孫
损 損
缩 縮
态 態
摊 攤
谈 談
坛 壇 罎
叹 嘆
汤 湯
烫 燙
涛 濤
讨 討
腾 騰
誊 謄
体 體
条 條
铁 鐵
厅 廳
听 聽
烃 烴
铜 銅
统 統
头 頭
图 圖
涂 塗
团 團
颓 頹
蜕 蛻
脱 脫
驮 馱
洼 窪
袜 襪
弯 彎
万 萬
网 網
韦 韋
违 違
围 圍
为 為 爲
维 維
伟 偉
伪 偽
卫 衛
谓 謂
温 溫
闻 聞
问 問
稳 穩
务 務
雾 霧
误 誤
习 習
系 係 繫
戏 戲
细 細
虾 蝦
峡 峽
侠 俠
狭 狹
厦 廈
吓 嚇
纤 纖 縴
鲜 鮮
贤 賢
现 現
献 獻
县 縣
线 線
乡 鄉
详 詳
响 響
项 項
潇 瀟
销 銷
晓 曉
啸 嘯
协 協
挟 挾
携 攜
胁 脅
谐 諧
写 寫
泻 瀉
谢 謝
兴 興
须 須
许 許
绪 緒
续 續
轩 軒
悬 懸
选 選
学 學
询 詢
训 訓
讯 訊
逊 遜
压 壓
鸦 鴉
鸭 鴨
哑 啞
亚 亞
严 嚴
盐 鹽
颜 顏
阎 閻
艳 艷
厌 厭
砚 硯
谚 諺
验 驗
阳 陽
养 養
样 樣
痒 癢
谣 謠
摇 搖
尧 堯
药 藥
爷 爺
页 頁
业 業
叶 葉
医 醫
义 義
议 議
亿 億
忆 憶
异 異
阴 陰
银 銀
隐 隱
应 應
婴 嬰
樱 櫻
鹰 鷹
营 營
蝇 蠅
赢 贏
颖 穎
优 優
忧 憂
邮 郵
犹 猶
游 遊
诱 誘
与 與
屿 嶼
语 語
誉 譽
郁 鬱
预 預
驭 馭
鸳 鴛
渊 淵
园 園
员 員
圆 圓
缘 緣
远 遠
愿 願
约 約
跃 躍
钥 鑰
粤 粵
云 雲
韵 韻
杂 雜
灾 災
载 載
赞 讚 贊
脏 臟 髒
凿 鑿
枣 棗
责 責
择 擇
则 則
泽 澤
贼 賊
赠 贈
扎 紮
铡 鍘
闸 閘
诈 詐
斋 齋
债 債
战 戰
张 張
涨 漲
帐 帳
账 賬 帳
赵 趙
折 摺
这 這
针 針
侦 偵
诊 診
镇 鎮
阵 陣
挣 掙
争 爭
郑 鄭
证 證
织 織
职 職
执 執
纸 紙
挚 摯
掷 擲
帜 幟
质 質
钟 鐘 鍾
种 種
众 眾
昼 晝
骤 驟
烛 燭
铸 鑄
筑 築
专 專
转 轉
赚 賺
庄 莊
装 裝
壮 壯
状 狀
锥 錐
谆 諄
浊 濁
兹 茲
资 資
渍 漬
踪 蹤
综 綜
总 總
纵 縱
邹 鄒
诅 詛
组 組
钻 鑽
台 臺 檯 颱
制 製
表 錶
志 誌
姜 薑
准 準
只 隻 祇
谷 穀
"""


def _build_variants():
    var = {}
    for line in _PAIR_DATA.strip().splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        group = {parts[0], *parts[1:]}
        for ch in group:
            var.setdefault(ch, set()).update(group)
    return var


_VARIANTS = _build_variants()


def variants(ch):
    """返回字符 ch 的全部简繁变体 (含自身)。"""
    s = _VARIANTS.get(ch, set())
    s.add(ch)
    return s


def build_pattern(keyword, ignore_case=False):
    parts = []
    for ch in keyword:
        alts = variants(ch)
        if len(alts) == 1:
            parts.append(re.escape(ch))
        else:
            parts.append("[" + "".join(re.escape(c) for c in sorted(alts)) + "]")
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile("".join(parts), flags)


def iter_files(paths, recursive):
    for p in paths:
        if os.path.isfile(p):
            yield p, None
        elif os.path.isdir(p):
            if recursive:
                for root, dirs, files in os.walk(p):
                    dirs.sort()
                    for fn in sorted(files):
                        yield os.path.join(root, fn), None
            else:
                # 目录缺省扫描第一层文件, 不递归子目录, 也不报错
                for fn in sorted(os.listdir(p)):
                    fp = os.path.join(p, fn)
                    if os.path.isfile(fp):
                        yield fp, None
        else:
            yield None, f"不存在: {p}"


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="搜索关键词并自动匹配简繁字形变体")
    ap.add_argument("keyword", help="关键词 (可含简体或繁体字形)")
    ap.add_argument("paths", nargs="+",
                    help="文件或目录 (目录默认只扫第一层文件)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="递归遍历目录的子目录")
    ap.add_argument("-i", "--ignore-case", action="store_true",
                    help="忽略 ASCII 大小写")
    ap.add_argument("--count", action="store_true",
                    help="只输出每个文件的命中行数")
    args = ap.parse_args(argv)

    try:
        pat = build_pattern(args.keyword, args.ignore_case)
    except re.error as exc:
        print(f"错误: 无效关键词: {exc}", file=sys.stderr)
        return 2

    total = 0
    errs = 0
    for path, err in iter_files(args.paths, args.recursive):
        if err is not None:
            print(f"错误: {err}", file=sys.stderr)
            errs += 1
            continue
        try:
            with open(path, "rb") as fh:
                text = fh.read().decode("utf-8", errors="replace")
        except OSError as exc:
            print(f"错误: 无法读取 {path}: {exc}", file=sys.stderr)
            errs += 1
            continue
        count = 0
        for lineno, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                count += 1
                total += 1
                if not args.count:
                    print(f"{path}:{lineno}:{line}")
        if args.count and count:
            print(f"{path}:{count}")

    if errs and not total:
        return 2
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
