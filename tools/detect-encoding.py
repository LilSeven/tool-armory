#!/usr/bin/env python3
"""编码探测（detect-encoding）：对文件做 BOM 检查与字节分布启发式分析，
报告最可能的编码及依据。

用法:
    python detect-encoding.py <文件...> [--top N]
示例:
    python detect-encoding.py story.txt
    python detect-encoding.py a.txt b.bin --top 3

原理:
    1. 依次检查 UTF-8 / UTF-16 LE/BE / UTF-32 LE/BE 的 BOM，命中即为确定结论；
    2. 无 BOM 时先尝试 UTF-8 严格解码（含纯 ASCII 判定）；
    3. 再用 GBK/GB18030/Big5/Shift-JIS/EUC-KR/cp1252/latin-1/UTF-16 等编解码器
       逐一尝试解码，按“可打印字符比例 + 各语言特征字符加分
       + 控制字符/替换字符扣分”打分排序，输出最可能编码、置信度与依据。

退出码: 0 成功；2 用法或文件错误。
"""

import argparse
import sys
import unicodedata

BOMS = [
    ("UTF-32 LE BOM", b"\xff\xfe\x00\x00", "utf-32-le"),
    ("UTF-32 BE BOM", b"\x00\x00\xfe\xff", "utf-32-be"),
    ("UTF-8 BOM", b"\xef\xbb\xbf", "utf-8-sig"),
    ("UTF-16 LE BOM", b"\xff\xfe", "utf-16-le"),
    ("UTF-16 BE BOM", b"\xfe\xff", "utf-16-be"),
]

CANDIDATES = [
    "utf-8", "gbk", "gb18030", "big5", "shift_jis", "euc-jp", "euc-kr",
    "cp1252", "latin-1", "utf-16-le", "utf-16-be",
]

# 高频汉字样本（简体 / 繁体各一段），用于给“像人话”的解码结果加分
COMMON_CN = set(
    "的一是了我不人在他有这上们来到时大地为子中你说生国年着就那和要她出也得里"
    "后自以会家可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第"
    "样道想作种开美总从无情己面最女但现前些所同日手又行意动"
)
COMMON_TW = set(
    "的一是個人這中大來上說國和地也子時道出而要於就後下得可你年生自會那能對著"
    "心日學多沒去們當看到無點起把還只如事"
)


def classify_text(text):
    """对解码后的文本打分，返回 (得分, 依据列表)。"""
    n = len(text)
    if n == 0:
        return -100.0, ["空文本"]
    bad = 0
    for c in text:
        if c == "\ufffd":
            bad += 1
        elif unicodedata.category(c).startswith("C") and c not in "\t\n\r\f\v":
            bad += 1
    han = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    kana = sum(1 for c in text if "\u3040" <= c <= "\u30ff")
    hangul = sum(1 for c in text if "\uac00" <= c <= "\ud7af")
    latin = sum(1 for c in text if c.isascii() and c.isalnum())
    common = sum(1 for c in text if c in COMMON_CN or c in COMMON_TW)

    score = (n - bad) / n * 50.0
    score -= bad / n * 150.0
    if han:
        score += min(han / n, 0.9) * 40.0
        score += min(common / n, 0.5) * 20.0
    if kana:
        score += min(kana / n, 0.7) * 45.0
    if hangul:
        score += min(hangul / n, 0.9) * 40.0
    if latin:
        score += min(latin / n, 0.9) * 25.0

    ev = []
    if bad:
        ev.append("%d 个不可读/控制字符（扣分）" % bad)
    if han:
        ev.append("%d/%d 个汉字（其中 %d 个高频常用字）" % (han, n, common))
    if kana:
        ev.append("%d/%d 个日文假名" % (kana, n))
    if hangul:
        ev.append("%d/%d 个谚文（韩文）" % (hangul, n))
    if latin:
        ev.append("%d/%d 个 ASCII 字母数字" % (latin, n))
    if not ev:
        ev.append("无可辨识文本特征")
    return score, ev


def count_utf8_units(data):
    """统计合法 UTF-8 序元个数；发现非法字节返回 -1。"""
    i, cnt = 0, 0
    n = len(data)
    while i < n:
        b = data[i]
        if b < 0x80:
            i += 1
        elif 0xC0 <= b < 0xE0:
            i += 2
        elif 0xE0 <= b < 0xF0:
            i += 3
        elif 0xF0 <= b < 0xF8:
            i += 4
        else:
            return -1
        if i > n:
            return -1
        cnt += 1
    return cnt


def probe(data):
    """对原始字节探测，返回 (结论字典)。"""
    if not data:
        return {
            "enc": None, "confidence": "未知", "evidence": ["空文件"],
            "candidates": [],
        }
    # 1. BOM 检查（UTF-32 需在 UTF-16 之前判）
    for label, bom, codec in BOMS:
        if data.startswith(bom):
            try:
                text = data[len(bom):].decode(codec)
            except UnicodeDecodeError as e:
                return {
                    "enc": None, "confidence": "矛盾",
                    "evidence": ["检测到 %s，但按 %s 解码失败: %s" % (label, codec, e)],
                    "candidates": [],
                }
            score, ev = classify_text(text)
            return {
                "enc": codec,
                "confidence": "确定",
                "evidence": ["检测到 %s（%s）" % (label, bom.hex(" "))] + ev,
                "candidates": [(codec, score, ["有 BOM"])],
            }
    # 2. 纯 ASCII
    if all(b < 0x80 for b in data):
        return {
            "enc": "ascii",
            "confidence": "确定",
            "evidence": ["全部字节 < 0x80，纯 ASCII（与 UTF-8/latin-1/gbk 等兼容）"],
            "candidates": [("ascii", 100.0, ["纯字节"])],
        }
    # 3. 无 BOM：逐个尝试解码并打分
    cands = []
    n_units = count_utf8_units(data)
    if n_units > 0:
        try:
            text = data.decode("utf-8")
            score, ev = classify_text(text)
            score += 25.0
            ev = ["严格 UTF-8 解码成功，含 %d 个多字节序列（强证据，+25）" % n_units] + ev
            cands.append(("utf-8", score, ev))
        except UnicodeDecodeError:
            pass
    for enc in CANDIDATES:
        if enc == "utf-8":
            continue
        if enc in ("utf-16-le", "utf-16-be") and len(data) % 2 != 0:
            continue
        try:
            text = data.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
        score, ev = classify_text(text)
        cands.append((enc, score, ev))
    cands.sort(key=lambda x: -x[1])
    if not cands:
        return {
            "enc": None, "confidence": "未知",
            "evidence": ["所有候选编解码器均解码失败"], "candidates": [],
        }
    best_enc, best_score, best_ev = cands[0]
    lead = best_score - cands[1][1] if len(cands) > 1 else 999
    if best_score >= 70 and lead >= 10:
        conf = "较高"
    elif best_score >= 45:
        conf = "中等"
    else:
        conf = "存疑"
    if best_enc == "utf-8" and n_units > 0:
        conf = "较高"
    return {"enc": best_enc, "confidence": conf, "evidence": best_ev,
            "candidates": cands}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="对文件做 BOM 检查与字节分布启发式分析，报告最可能的编码")
    ap.add_argument("files", nargs="+", help="待探测文件")
    ap.add_argument("--top", type=int, default=5,
                    help="候选列表显示条数（默认 5）")
    args = ap.parse_args(argv)

    rc = 0
    for path in args.files:
        print("=" * 62)
        print("文件: %s" % path)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            print("  [错误] 无法读取: %s" % e)
            rc = 2
            continue
        r = probe(data)
        if r["enc"]:
            print("最可能编码: %s（置信度: %s）" % (r["enc"], r["confidence"]))
        else:
            print("无法确定编码（置信度: %s）" % r["confidence"])
            rc = 1
        print("依据:")
        for e in r["evidence"]:
            print("  - %s" % e)
        if r["candidates"]:
            print("候选排名:")
            for i, (enc, score, ev) in enumerate(r["candidates"][:args.top], 1):
                brief = "；".join(ev[:2])
                print("  %d. %-10s 得分 %6.1f  %s" % (i, enc, score, brief))
    return rc


if __name__ == "__main__":
    sys.exit(main())
