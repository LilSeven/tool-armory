# -*- coding: utf-8 -*-
"""映射表导出工具：把内置简→繁单字映射导出为 CSV。

内置一份常用字一级简繁对照（一对一无歧义的常用字子集，
一简对多繁的敏感字如 后/发/里/干/台 等故意不收录，
请配合 one-sim-many-trad 工具人工定字形），导出为 CSV，
便于人工增删改后，再喂给 s2t-custom-map 做自定义转换。

示例命令：
    python s2t-map-export.py                          # 导出到 stdout
    python s2t-map-export.py -o s2t.csv               # 导出到文件（utf-8-sig，Excel 友好）
    python s2t-map-export.py --encoding utf-8 -o plain.csv

CSV 格式（无 BOM 时第一行是表头）：
    简体,繁体
    爱,愛
    马,馬
"""
import argparse
import csv
import sys

# 简体在前，繁体在后，两两一组，空格分隔。仅收录一对一常用字。
BASE_PAIRS = """
爱愛 碍礙 袄襖 坝壩 罢罷 摆擺 败敗 办辦 帮幫 宝寶 报報 币幣 毕畢 边邊 变變
标標 别別 宾賓 补補 参參 惨慘 灿燦 苍蒼 层層 尝嘗 长長 偿償 厂廠 车車 彻徹
尘塵 陈陳 称稱 惩懲 迟遲 础礎 处處 触觸 传傳 闯闖 创創 纯純 词詞 辞辭 从從
丛叢 凑湊 窜竄 错錯 达達 带帶 贷貸 单單 担擔 胆膽 弹彈 当當 党黨 挡擋 导導
岛島 灯燈 敌敵 递遞 点點 电電 独獨 读讀 断斷 锻鍛 队隊 对對 吨噸 顿頓 夺奪
堕墮 讹訛 恶惡 儿兒 尔爾 饿餓 罚罰 阀閥 范範 饭飯 访訪 纺紡 飞飛 废廢 费費
坟墳 奋奮 粪糞 丰豐 风風 冯馮 凤鳳 妇婦 复復 负負 该該 盖蓋 赶趕 刚剛 钢鋼
岗崗 纲綱 给給 巩鞏 沟溝 构構 购購 够夠 蛊蠱 顾顧 关關 观觀 馆館 惯慣 广廣
归歸 龟龜 规規 贵貴 国國 过過 汉漢 号號 鹤鶴 贺賀 轰轟 红紅 华華 划劃 画畫
话話 怀懷 坏壞 欢歡 环環 还還 换換 挥揮 辉輝 汇匯 会會 讳諱 贿賄 秽穢 浑渾
获獲 机機 鸡雞 积積 极極 击擊 讥譏 级級 挤擠 几幾 蓟薊 剂劑 济濟 计計 记記
际際 继繼 纪紀 价價 驾駕 歼殲 艰艱 监監 见見 舰艦 剑劍 检檢 荐薦 贱賤 减減
简簡 讲講 奖獎 将將 酱醬 胶膠 阶階 洁潔 结結 节節 诫誡 届屆 紧緊 谨謹 进進
尽盡 劲勁 惊驚 经經 静靜 竞競 净淨 径徑 旧舊 剧劇 惧懼 据據 觉覺 决決 绝絕
军軍 开開 凯凱 颗顆 壳殼 课課 垦墾 恳懇 夸誇 块塊 亏虧 扩擴 兰蘭 蓝藍 拦攔
栏欄 烂爛 劳勞 类類 泪淚 篱籬 离離 礼禮 丽麗 励勵 历歷 厉厲 隶隸 联聯 怜憐
帘簾 莲蓮 连連 炼煉 练練 粮糧 两兩 辆輛 疗療 辽遼 猎獵 临臨 鳞鱗 灵靈 岭嶺
领領 刘劉 龙龍 楼樓 娄婁 芦蘆 卢盧 炉爐 陆陸 虏虜 录錄 虑慮 滤濾 乱亂 论論
罗羅 络絡 骆駱 妈媽 马馬 骂罵 吗嗎 买買 卖賣 迈邁 麦麥 脉脈 瞒瞞 满滿 谩謾
猫貓 么麼 门門 闷悶 们們 梦夢 谜謎 弥彌 觅覓 绵綿 缅緬 庙廟 灭滅 悯憫 鸣鳴
谋謀 亩畝 难難 恼惱 脑腦 闹鬧 拟擬 腻膩 酿釀 鸟鳥 聂聶 宁寧 农農 浓濃 疟瘧
盘盤 赔賠 喷噴 鹏鵬 骗騙 飘飄 频頻 贫貧 苹蘋 凭憑 评評 泼潑 铺鋪 仆僕 朴樸
谱譜 齐齊 骑騎 岂豈 启啟 弃棄 气氣 迁遷 签簽 谦謙 钱錢 浅淺 谴譴 枪槍 抢搶
桥橋 侨僑 窍竅 亲親 轻輕 倾傾 庆慶 琼瓊 穷窮 区區 驱驅 龋齲 权權 劝勸 确確
让讓 扰擾 热熱 认認 韧韌 荣榮 绒絨 软軟 锐銳 润潤 洒灑 萨薩 赛賽 伞傘 丧喪
骚騷 涩澀 杀殺 纱紗 筛篩 晒曬 删刪 闪閃 陕陝 伤傷 赏賞 烧燒 绍紹 设設 绅紳
审審 肾腎 声聲 胜勝 圣聖 师師 时時 湿濕 实實 诗詩 蚀蝕 势勢 视視 试試 寿壽
兽獸 书書 属屬 术術 树樹 帅帥 双雙 谁誰 税稅 顺順 说說 硕碩 丝絲 饲飼 松鬆
讼訟 颂頌 苏蘇 诉訴 虽雖 随隨 岁歲 孙孫 损損 缩縮 锁鎖 态態 摊攤 谈談 坛壇
叹嘆 汤湯 烫燙 涛濤 讨討 腾騰 题題 体體 条條 铁鐵 厅廳 听聽 统統 头頭 图圖
团團 驼駝 洼窪 袜襪 弯彎 万萬 网網 韦韋 违違 围圍 为為 维維 伟偉 纬緯 卫衛
闻聞 稳穩 问問 涡渦 无無 务務 雾霧 误誤 牺犧 习習 戏戲 细細 虾蝦 吓嚇 峡峽
侠俠 狭狹 厦廈 鲜鮮 纤纖 咸鹹 显顯 险險 现現 献獻 县縣 宪憲 线線 乡鄉 详詳
响響 项項 萧蕭 销銷 晓曉 啸嘯 协協 胁脅 谐諧 写寫 泻瀉 谢謝 兴興 须須 许許
绪緒 续續 轩軒 悬懸 选選 学學 询詢 训訓 讯訊 逊遜 压壓 哑啞 亚亞 严嚴 盐鹽
颜顏 阎閻 艳艷 厌厭 验驗 阳陽 杨楊 养養 痒癢 样樣 摇搖 尧堯 药藥 爷爺 业業
页頁 叶葉 医醫 义義 亿億 忆憶 议議 异異 译譯 阴陰 银銀 隐隱 应應 婴嬰 樱櫻
鹰鷹 赢贏 颖穎 忧憂 优優 邮郵 犹猶 诱誘 与與 屿嶼 语語 誉譽 预預 驭馭 鸳鴛
渊淵 园園 员員 圆圓 缘緣 远遠 愿願 跃躍 约約 钥鑰 悦悅 阅閱 云雲 运運 韵韻
杂雜 灾災 载載 赞贊 脏臟 凿鑿 枣棗 责責 择擇 则則 泽澤 贼賊 赠贈 诈詐 斋齋
债債 战戰 张張 涨漲 帐帳 账賬 胀脹 赵趙 这這 针針 侦偵 诊診 镇鎮 阵陣 挣掙
争爭 郑鄭 证證 织織 职職 执執 纸紙 挚摯 掷擲 帜幟 质質 钟鐘 种種 众眾 昼晝
骤驟 诸諸 烛燭 嘱囑 筑築 铸鑄 专專 转轉 赚賺 庄莊 装裝 壮壯 状狀 锥錐 谆諄
浊濁 兹茲 资資 渍漬 踪蹤 综綜 总總 纵縱 邹鄒 诅詛 组組 钻鑽
"""

HEADER = ("简体", "繁体")


def build_pairs():
    """解析内置映射串，返回 [(简, 繁), ...]，跳过格式异常的词组。"""
    pairs = []
    for token in BASE_PAIRS.split():
        if len(token) != 2:
            print("warning: 跳过异常词条 %r" % token, file=sys.stderr)
            continue
        pairs.append((token[0], token[1]))
    return pairs


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="把内置简→繁单字映射导出为 CSV")
    parser.add_argument("-o", "--output", default="-",
                        help="输出文件路径，缺省写到 stdout")
    parser.add_argument("--encoding", default="utf-8-sig",
                        help="输出编码，缺省 utf-8-sig（Excel 友好）")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace",
                               newline="")

    pairs = build_pairs()
    if args.output == "-":
        writer = csv.writer(sys.stdout, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(pairs)
    else:
        with open(args.output, "w", encoding=args.encoding, newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(HEADER)
            writer.writerows(pairs)
        print("已导出 %d 条映射到 %s" % (len(pairs), args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
