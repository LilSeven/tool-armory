# -*- coding: utf-8 -*-
"""一简对多繁检测：找出文本中一简对多繁的敏感字并输出上下文。

后、发、里、干、台 等简体字在转繁体时对应多个繁体字形
（后→後/后，发→發/髮，干→乾/幹/干……），机器无法凭单字判断，
需人工看上下文定字形。本工具扫描文本，对每个敏感字出现处
列出候选繁体及提示词，并给出前后文窗口，供人工定夺。
配合 s2t-custom-map 的自定义词库可逐词落实转换。

示例命令：
    python one-sim-many-trad.py input.txt
    python one-sim-many-trad.py input.txt --context 12 --json
    echo 皇后的头发干了 | python one-sim-many-trad.py --only 后,干
    python one-sim-many-trad.py --list
"""
import argparse
import json
import sys

# 敏感字 -> [(候选繁体, 用法提示), ...]
AMBIG_TABLE = {
    "后": [("後", "前後/以後/後面"), ("后", "皇后/太后/后羿")],
    "发": [("發", "出發/發展/理發"), ("髮", "頭髮/白髮/理髮")],
    "里": [("裏", "裏面(港標)"), ("裡", "裡面(台標)"), ("里", "公里/里弄/故里")],
    "干": [("乾", "乾燥/乾淨/乾杯"), ("幹", "幹活/樹幹/骨幹"), ("干", "干涉/干支/干犯")],
    "台": [("臺", "平臺/舞臺/窗臺"), ("檯", "寫字檯/櫃檯"), ("颱", "颱風"), ("台", "台州/天台山(地名山名)")],
    "系": [("係", "關係/係數"), ("繫", "聯繫/維繫/繫鞋帶"), ("系", "系統/系列/中文系")],
    "历": [("歷", "經歷/歷史"), ("曆", "日曆/曆法/農曆")],
    "复": [("復", "恢復/往復"), ("複", "複雜/複印/複製")],
    "钟": [("鐘", "時鐘/鬧鐘/鐘聲"), ("鍾", "鍾情/姓鍾")],
    "表": [("錶", "手錶/電子錶"), ("表", "表面/表格/代表")],
    "志": [("誌", "雜誌/日誌/墓誌"), ("志", "志向/志氣/同志")],
    "制": [("製", "製造/製作/監製"), ("制", "制度/限制/制止")],
    "面": [("麵", "麵條/麵包/粉麵"), ("面", "面孔/表面/見面")],
    "松": [("鬆", "鬆開/放鬆/稀鬆"), ("松", "松樹/松柏")],
    "谷": [("穀", "稻穀/穀物/五穀"), ("谷", "山谷/谷地/姓")],
    "郁": [("鬱", "憂鬱/鬱悶"), ("郁", "姓郁/馥郁")],
    "冲": [("衝", "衝突/衝刺/要衝"), ("沖", "沖洗/沖茶/沖印")],
    "只": [("隻", "一隻/隻身"), ("只", "只有/只是/只能")],
    "征": [("徵", "特徵/徵求/象徵"), ("征", "長征/征途/出征")],
    "余": [("餘", "剩餘/多餘/業餘"), ("余", "姓余/文言第一人称")],
    "云": [("雲", "白雲/雲彩/雲端"), ("云", "人云亦云/詩云")],
    "汇": [("匯", "匯款/外匯/匯率"), ("彙", "彙總/彙編/詞彙")],
    "尽": [("盡", "盡力/盡頭"), ("儘", "儘管/儘快/儘量")],
    "苏": [("蘇", "蘇州/蘇醒/江蘇"), ("囌", "嚕囌")],
    "坛": [("壇", "花壇/天壇/論壇"), ("罎", "酒罎/罎罐")],
    "须": [("鬚", "鬍鬚/鬚根"), ("須", "必須/須知/務須")],
    "恶": [("惡", "罪惡/惡劣/可惡"), ("噁", "噁心")],
    "团": [("團", "團結/社團/兵團"), ("糰", "飯糰/湯糰")],
    "几": [("幾", "幾個/幾乎"), ("几", "茶几/條几(傢俱)")],
    "姜": [("薑", "生薑/薑湯"), ("姜", "姜姓/姜子牙")],
    "舍": [("捨", "捨棄/捨得/取捨"), ("舍", "宿舍/旅舍/寒舍")],
    "划": [("劃", "計劃/劃分/策劃"), ("划", "划船/划算")],
    "板": [("闆", "老闆/闆娘"), ("板", "木板/黑板")],
    "咸": [("鹹", "鹹菜/鹹淡"), ("咸", "老少咸宜(皆)/咸豐")],
    "获": [("獲", "捕獲/獲得/俘獲"), ("穫", "收穫")],
    "卷": [("捲", "捲起/捲簾/捲心菜"), ("卷", "試卷/書卷/卷宗")],
    "蒙": [("濛", "細雨濛濛/迷濛"), ("懞", "懞懂"), ("蒙", "啟蒙/蒙古/蒙騙")],
    "摆": [("擺", "擺放/搖擺/擺脫"), ("襬", "裙襬/下襬")],
    "向": [("嚮", "嚮導/嚮往"), ("向", "方向/向日葵")],
    "卜": [("蔔", "蘿蔔"), ("卜", "占卜/姓卜")],
    "党": [("黨", "政黨/黨員"), ("党", "党項(古族)/姓")],
    "涂": [("塗", "塗抹/糊塗/塗鴉"), ("涂", "涂姓/涂水(地名)")],
    "游": [("遊", "旅遊/遊戲/遊覽"), ("游", "游泳/上游/姓游")],
    "涌": [("湧", "湧現/波濤洶湧"), ("涌", "涌泉(地名)")],
    "吁": [("籲", "呼籲/籲請"), ("吁", "气喘吁吁/長吁短嘆")],
    "帘": [("簾", "窗簾/門簾/垂簾"), ("帘", "酒帘(古)旗幌")],
    "荡": [("蕩", "動蕩/掃蕩/蕩漾"), ("盪", "盪滌/盪鞦韆")],
    "伙": [("夥", "夥伴/同夥/夥計"), ("伙", "伙食/家伙")],
}


def read_text(path):
    if path == "-":
        data = sys.stdin.buffer.read()
    else:
        with open(path, "rb") as fh:
            data = fh.read()
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def scan(text, targets, context):
    """返回命中列表 (char, lineno, col, before, after)。"""
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for col, ch in enumerate(line, 1):
            if ch in targets:
                lo = max(0, col - 1 - context)
                hi = min(len(line), col - 1 + 1 + context)
                hits.append((ch, lineno, col, line[lo:col - 1],
                             line[col:hi]))
    return hits


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="检测一简对多繁的敏感字并输出上下文")
    parser.add_argument("inputs", nargs="*", default=["-"],
                        help="输入文本文件，缺省或 - 读 stdin")
    parser.add_argument("--context", type=int, default=8,
                        help="上下文窗口前后各 N 个字符（缺省 8）")
    parser.add_argument("--only", default="",
                        help="只查这些字，逗号分隔，如 后,发,干")
    parser.add_argument("--json", action="store_true",
                        help="输出 JSON 结构")
    parser.add_argument("--fail-on-found", action="store_true",
                        help="发现敏感字时退出码取 1（供流水线把关）")
    parser.add_argument("--list", action="store_true",
                        help="列出敏感字表后退出")
    parser.add_argument("-o", "--output", default="-",
                        help="输出文件，缺省 stdout")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace",
                               newline="")

    if args.list:
        for ch in sorted(AMBIG_TABLE):
            cands = " ".join("%s(%s)" % (t, h)
                             for t, h in AMBIG_TABLE[ch])
            print("%s -> %s" % (ch, cands))
        return 0

    targets = AMBIG_TABLE
    if args.only:
        keys = [c.strip() for c in args.only.split(",") if c.strip()]
        bad = [c for c in keys if c not in AMBIG_TABLE]
        if bad:
            print("错误：不认识的敏感字 %s（--list 可查全部）"
                  % "、".join(bad), file=sys.stderr)
            return 2
        targets = {c: AMBIG_TABLE[c] for c in keys}

    text = "".join(read_text(p) for p in args.inputs)
    hits = scan(text, targets, max(0, args.context))

    out = sys.stdout
    if args.json:
        payload = {
            "total_hits": len(hits),
            "chars": {},
            "hits": [
                {"char": ch, "line": ln, "col": col,
                 "candidates": [t for t, _ in targets[ch]],
                 "context": before + "[" + ch + "]" + after}
                for ch, ln, col, before, after in hits
            ],
        }
        for ch, _, _, _, _ in hits:
            payload["chars"][ch] = payload["chars"].get(ch, 0) + 1
        out.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        if not hits:
            out.write("未发现敏感字（共扫描 %d 字符）\n" % len(text))
        for ch, ln, col, before, after in hits:
            cands = " / ".join("%s〔%s〕" % (t, h)
                               for t, h in targets[ch])
            out.write("行%d 列%d [%s] 候选：%s\n  上下文：%s[%s]%s\n"
                      % (ln, col, ch, cands, before, ch, after))
        if hits:
            summary = {}
            for ch, _, _, _, _ in hits:
                summary[ch] = summary.get(ch, 0) + 1
            out.write("共 %d 处：%s\n"
                      % (len(hits), "，".join("%s×%d" % (c, n)
                                              for c, n
                                              in sorted(summary.items(),
                                                        key=lambda x: (-x[1], x[0])))))

    return 1 if (args.fail_on_found and hits) else 0


if __name__ == "__main__":
    sys.exit(main())
