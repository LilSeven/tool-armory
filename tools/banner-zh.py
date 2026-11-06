#!/usr/bin/env python3
"""拼音横幅 —— 把中文转成拼音后, 用内置点阵字体渲染成终端大字横幅。

用途:
    读取输入文本: 汉字查内置「常用字 → 无声调拼音」映射表(约 400 字),
    英文字母/数字/常用半角标点原样保留, 全角标点自动转半角,
    然后用内置 5 行点阵字母字体放大成横幅打印。纯标准库实现,
    不依赖任何第三方分词/拼音库。

示例命令:
    python banner-zh.py 你好
    python banner-zh.py 军火库 工具箱
    python banner-zh.py -f '█' "新年快乐 2026"
    echo 中文,测试! | python banner-zh.py        # 从标准输入读入

说明:
    * 拼音输出无声调大写字母(ü 记作 V, 如 绿→LV); 多音字取常见读音。
    * 映射表未收录的字符渲染成占位块, 并在 stderr 提示。
    * 退出码: 0 = 正常(含未知字符); 2 = 参数错误。
"""

import argparse
import sys

ROWS = 5

FONT = {
    "A": (".###.", "#...#", "#####", "#...#", "#...#"),
    "B": ("####.", "#...#", "####.", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "####.", "#....", "#####"),
    "F": ("#####", "#....", "####.", "#....", "#...."),
    "G": (".###.", "#....", "#..##", "#...#", ".###."),
    "H": ("#...#", "#...#", "#####", "#...#", "#...#"),
    "I": ("###", ".#.", ".#.", ".#.", "###"),
    "J": ("..###", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "###..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "####.", "#....", "#...."),
    "Q": (".###.", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "####.", "#..#.", "#...#"),
    "S": (".####", "#....", ".###.", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", ".#.#.", "..#..", ".#.#.", "#...#"),
    "Y": ("#...#", ".#.#.", "..#..", "..#..", "..#.."),
    "Z": ("#####", "...#.", "..#..", ".#...", "#####"),
    "0": (".###.", "#..##", "#.#.#", "##..#", ".###."),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": (".###.", "#...#", "..##.", ".#...", "#####"),
    "3": ("####.", "....#", ".###.", "....#", "####."),
    "4": ("#...#", "#...#", "#####", "....#", "....#"),
    "5": ("#####", "#....", "####.", "....#", "####."),
    "6": (".###.", "#....", "####.", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", "..#.."),
    "8": (".###.", "#...#", ".###.", "#...#", ".###."),
    "9": (".###.", "#...#", ".####", "....#", ".###."),
    " ": ("...", "...", "...", "...", "..."),
    "!": ("#", "#", "#", ".", "#"),
    "?": (".###.", "#...#", "...#.", ".....", "...#."),
    ".": (".", ".", ".", ".", "#"),
    ",": ("..", "..", "..", ".#", "#."),
    "-": ("....", "....", "####", "....", "...."),
    "+": ("...", ".#.", "###", ".#.", "..."),
    "=": ("....", "####", "....", "####", "...."),
    ":": (".", "#", ".", "#", "."),
    "'": ("#", "#", ".", ".", "."),
    '"': ("#.", "#.", "..", "..", ".."),
    "(": (".#", "#.", "#.", "#.", ".#"),
    ")": ("#.", ".#", ".#", ".#", "#."),
    "/": ("....#", "...#.", "..#..", ".#...", "#...."),
    "_": ("....", "....", "....", "....", "####"),
    "*": ("..#..", "#.#.#", ".###.", "#.#.#", "..#.."),
}

UNKNOWN = (".###.", "#...#", "#.#.#", "#...#", ".###.")

# 内置「常用字 → 无声调拼音」映射表(ü 记作 v; 每个词条 = 汉字 + 拼音)
PINYIN_DATA = """
自zi 己ji 我wo 你ni 他ta 她ta 它ta 咱zan 们men 是shi 有you 没mei 无wu 不bu
在zai 去qu 来lai 到dao 从cong 向xiang 往wang 对dui 错cuo 真zhen 假jia 和he
与yu 跟gen 或huo 者zhe 且qie 而er 但dan 若ruo 如ru 果guo 虽sui 然ran 因yin
为wei 所suo 以yi 的de 了le 着zhe 得de 地di 之zhi 乎hu 个ge 这zhe 那na 哪na
什shen 么me 于yu 当dang 把ba 被bei 将jiang 已yi 让rang 使shi 可ke 需xu 要yao
能neng 会hui 应ying 该gai 就jiu 才cai 只zhi 又you 再zai 也ye 都dou 很hen
太tai 更geng 最zui 常chang 非fei 各ge 每mei 共gong 些xie 位wei 意yi 思si
零ling 一yi 二er 两liang 三san 四si 五wu 六liu 七qi 八ba 九jiu 十shi 百bai
千qian 万wan 亿yi 半ban 双shuang 第di 几ji 岁sui 年nian 月yue 日ri 天tian
时shi 分fen 秒miao 早zao 晚wan 夜ye 今jin 明ming 昨zuo 现xian 过guo 未wei
春chun 夏xia 秋qiu 冬dong 周zhou 期qi 钟zhong 号hao 上shang 下xia 中zhong
内nei 外wai 里li 东dong 西xi 南nan 北bei 前qian 后hou 左zuo 右you 间jian
处chu 边bian 旁pang 山shan 水shui 火huo 土tu 木mu 金jin 石shi 田tian 海hai
河he 湖hu 江jiang 云yun 雨yu 雪xue 风feng 电dian 光guang 声sheng 星xing
空kong 气qi 冰bing 雾wu 洋yang 人ren 男nan 女nv 孩hai 儿er 爸ba 妈ma 哥ge
姐jie 弟di 妹mei 爷ye 奶nai 朋peng 友you 老lao 师shi 生sheng 客ke 主zhu
医yi 心xin 头tou 手shou 脚jiao 眼yan 耳er 口kou 鼻bi 脸lian 毛mao 发fa
血xue 骨gu 身shen 体ti 脑nao 指zhi 牙ya 猫mao 狗gou 鸟niao 鱼yu 马ma
牛niu 羊yang 虎hu 兔tu 龙long 蛇she 鸡ji 猪zhu 鼠shu 虫chong 象xiang
像xiang 狮shi 熊xiong 花hua 草cao 树shu 叶ye 果guo 米mi 面mian 菜cai
肉rou 蛋dan 茶cha 酒jiu 糖tang 盐yan 油you 饭fan 瓜gua 豆dou 麦mai 葡pu
萄tao 苹ping 香xiang 蕉jiao 红hong 黄huang 蓝lan 绿lv 黑hei 白bai 灰hui
紫zi 粉fen 橙cheng 彩cai 亮liang 暗an 门men 窗chuang 桌zhuo 椅yi 床chuang
灯deng 车che 船chuan 机ji 网wang 线xian 书shu 笔bi 纸zhi 刀dao 盒he
袋dai 锁suo 钥yao 匙shi 钱qian 币bi 箱xiang 包bao 伞san 杯bei 碗wan
筷kuai 子zi 走zou 跑pao 跳tiao 飞fei 停ting 站zhan 坐zuo 睡shui 起qi
吃chi 喝he 看kan 听ting 说shuo 讲jiang 读du 写xie 画hua 唱chang 想xiang
知zhi 道dao 学xue 教jiao 做zuo 作zuo 用yong 拿na 给gei 送song 收shou
找zhao 买mai 卖mai 开kai 关guan 洗xi 扫sao 擦ca 修xiu 建jian 筑zhu
拆chai 装zhuang 改gai 变bian 增zeng 减jian 加jia 算suan 数shu 记ji
忘wang 问wen 答da 选xuan 试shi 测ce 验yan 玩wan 赢ying 输shu 胜sheng
负fu 平ping 比bi 赛sai 帮bang 忙mang 等deng 排pai 队dui 转zhuan 移yi
放fang 挂gua 传chuan 接jie 进jin 出chu 行hang 步bu 笑xiao 哭ku 爱ai
恨hen 怕pa 死si 活huo 力li 勇yong 敢gan 信xin 念nian 祝zhu 愿yuan 乐le
喜xi 欢huan 迎ying 临lin 谢xie 请qing 借jie 抱bao 歉qian 系xi 见jian
达da 递di 好hao 坏huai 大da 小xiao 高gao 低di 长chang 短duan 宽kuan
窄zhai 厚hou 薄bao 轻qing 重zhong 快kuai 慢man 新xin 旧jiu 冷leng 热re
温wen 干gan 湿shi 净jing 脏zang 甜tian 苦ku 酸suan 辣la 咸xian 同tong
异yi 全quan 部bu 整zheng 满man 远yuan 近jin 方fang 圆yuan 直zhi 弯wan
深shen 浅qian 强qiang 弱ruo 易yi 难nan 贵gui 富fu 穷qiong 安an 危wei
美mei 丑chou 漂piao 脑nao 话hua 码ma 代dai 程cheng 序xu 软ruan 件jian
硬ying 盘pan 终zhong 端duan 命ming 令ling 列lie 输shu 据ju 文wen 字zi
符fu 编bian 译yi 运yun 标biao 题ti 库ku 工gong 具ju 铁tie 匠jiang 军jun
药yao 病bing 图tu 格ge 框kuang 幕mu 屏ping 键jian 术shu 科ke 技ji
版ban 本ben 器qi 智zhi 国guo 家jia 城cheng 市shi 村cun 街jie 路lu
桥qiao 院yuan 校xiao 馆guan 店dian 厂chang 场chang 局ju 组zu 班ban
级ji 世shi 界jie 球qiu 京jing 广guang 州zhou 圳zhen 台tai 湾wan 港gang
英ying 法fa 德de 俄e 韩han 姓xing 名ming 民min 王wang 李li 张zhang
刘liu 陈chen 杨yang 赵zhao 吴wu 徐xu 孙sun 朱zhu 胡hu 郭guo 何he 林lin
音yin 歌ge 影ying 游you 戏xi 银yin 总zong 种zhong 事shi 成cheng 情qing
"""

PINYIN = {}
for _entry in PINYIN_DATA.split():
    if len(_entry) >= 2:
        PINYIN[_entry[0]] = _entry[1:]

# 常见全角标点 → 半角(便于用点阵字体渲染)
PUNCT_MAP = {
    "，": ",", "。": ".", "、": ",", "！": "!", "？": "?",
    "：": ":", "；": ";", "（": "(", "）": ")",
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "—": "-", "－": "-", "·": ".",
}

ASCII_OK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 !?.,+-=:/'\"()/*_")


def to_pinyin_tokens(text):
    """把一行文本转为 token 列表(拼音串/ASCII 字符/空格), 未知字符记为 None。"""
    tokens, unknown = [], []
    for ch in text:
        if ch in " \t\u3000":
            tokens.append(" ")
            continue
        up = ch.upper()
        if up in ASCII_OK:
            tokens.append(up)
            continue
        if ch in PUNCT_MAP:
            tokens.append(PUNCT_MAP[ch].upper())
            continue
        py = PINYIN.get(ch)
        if py:
            tokens.append(py.upper())
        else:
            tokens.append(None)
            if ch not in unknown:
                unknown.append(ch)
    return tokens, unknown


def render_tokens(tokens, fill="#", spacing=1):
    """把 token 列表渲染成 5 行大字横幅。"""
    glyphs = []
    for tok in tokens:
        if tok is None:
            glyphs.append(UNKNOWN)
        else:
            for c in tok:
                glyphs.append(FONT.get(c, UNKNOWN))
    gap = " " * max(0, spacing)
    rows = []
    for r in range(ROWS):
        rows.append(gap.join(
            "".join(fill if c == "#" else " " for c in g[r]) for g in glyphs
        ).rstrip())
    return "\n".join(rows)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        if not sys.stdin.isatty():      # 管道输入按 UTF-8 读, 避免 GBK 误码
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="拼音横幅: 中文转拼音后渲染成大字横幅")
    ap.add_argument("words", nargs="*", help="要渲染的文本(多个参数用空格连接)")
    ap.add_argument("-f", "--fill", default="#", help="填充字符, 默认 '#', 只取第一个字符")
    ap.add_argument("-s", "--spacing", type=int, choices=range(0, 5), default=1,
                    metavar="0-4", help="字母间空隙列数, 默认 1")
    ns = ap.parse_args(argv)

    if ns.words:
        text = " ".join(ns.words)
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        ap.print_help()
        return 0

    fill = (ns.fill or "#")[:1]
    banners, unknown = [], []
    for line in text.replace("\r", "").split("\n"):
        if not line.strip():
            continue
        tokens, unk = to_pinyin_tokens(line)
        banners.append(render_tokens(tokens, fill, ns.spacing))
        unknown.extend(u for u in unk if u not in unknown)
    if banners:
        print("\n\n".join(banners))
    else:
        print("(空输入, 无内容可渲染)")
    if unknown:
        print("[提示] 映射表未收录 %d 个字符, 已用占位块代替: %s"
              % (len(unknown), " ".join(unknown)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
