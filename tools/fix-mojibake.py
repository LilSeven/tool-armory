#!/usr/bin/env python3
"""乱码修复（fix-mojibake）：尝试 latin1、cp1252、GBK 等常见错误解码链路，
自动挑选能还原可读文本的方案。

用法:
    python fix-mojibake.py <文件> [-o <输出文件>] [--apply] [--show N]
示例:
    python fix-mojibake.py garbled.txt             # 仅诊断，打印最佳方案与候选
    python fix-mojibake.py garbled.txt -o fixed.txt
    python fix-mojibake.py garbled.txt --apply     # 以修复文本（UTF-8）覆盖原文件

原理:
    乱码 = 原始字节被错误的编码解码后又被保存，于是文件里存的是“错看后的文本”。
    修复 = 把当前文本用“错误编码”重新编码还原出原始字节，再用正确编码解码。
    本工具先按 utf-8/gbk/latin-1/cp1252 直接解码文件作为起点，
    再枚举两步以内的重编码链路（如 utf-8 → gbk 再编码 → utf-8 解码、
    utf-8 → latin-1 再编码 → utf-8 解码等），按可读性打分挑出最佳方案。
    评分依据：可打印字符比例、汉字/假名/谚文等特征字符、高频常用字，
    控制字符与 U+FFFD 重扣分。

退出码: 0 找到方案；1 未找到可信方案；2 用法或文件错误。
"""

import argparse
import os
import sys
import unicodedata

# 常见的“看错时用的编码”（再编码用）与“原文真正的编码”（再解码用）
WRONG = ["latin-1", "cp1252", "gbk", "big5", "shift_jis", "euc-jp", "koi8-r", "cp437"]
RIGHT = ["utf-8", "gbk", "gb18030", "big5", "shift_jis", "euc-kr", "cp1252", "latin-1"]

COMMON_CN = set(
    "的一是了我不人在他有这上们来到时大地为子中你说生国年着就那和要她出也得里"
    "后自以会家可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第"
    "样道想作种开美总从无情己面最女但现前些所同日手又行意动"
)


def score_text(text):
    """可读性打分：越高越像正常文本。"""
    n = len(text)
    if n == 0:
        return -100.0
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
    common = sum(1 for c in text if c in COMMON_CN)
    s = (n - bad) / n * 50.0 - bad / n * 150.0
    if han:
        s += min(han / n, 0.9) * 40.0 + min(common / n, 0.5) * 20.0
    if kana:
        s += min(kana / n, 0.7) * 45.0
    if hangul:
        s += min(hangul / n, 0.9) * 40.0
    if latin:
        s += min(latin / n, 0.9) * 25.0
    return s


def bad_ratio(text):
    n = len(text)
    if n == 0:
        return 1.0
    bad = 0
    for c in text:
        if c == "\ufffd" or (
            unicodedata.category(c).startswith("C") and c not in "\t\n\r\f\v"
        ):
            bad += 1
    return bad / n


def collect_candidates(data, limit=262144):
    """返回 [(得分, 文本, 链路描述)]，按得分降序。"""
    blob = data[:limit]
    starts = []
    for enc in ("utf-8", "gbk", "cp1252"):
        try:
            starts.append((blob.decode(enc), "按 %s 直接解码" % enc))
        except (UnicodeDecodeError, ValueError):
            pass
    starts.append((blob.decode("latin-1"), "按 latin-1 直接解码（有损兜底）"))

    results = {}
    for text, desc in starts:
        results.setdefault(text, desc)
        for w in WRONG:
            try:
                mid = text.encode(w)
            except (UnicodeEncodeError, LookupError):
                continue
            for g in RIGHT:
                if g == w:
                    continue
                try:
                    fixed = mid.decode(g)
                except (UnicodeDecodeError, ValueError, LookupError):
                    continue
                results.setdefault(fixed, "%s → 用 %s 再编码 → 用 %s 解码" % (desc, w, g))
    out = [(score_text(t), t, d) for t, d in results.items()]
    out.sort(key=lambda x: -x[0])
    return out


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="自动尝试常见错误解码链路修复乱码文本")
    ap.add_argument("file", help="乱码文件")
    ap.add_argument("-o", "--output", help="修复结果输出文件（UTF-8 保存）")
    ap.add_argument("--apply", action="store_true",
                    help="用修复文本（UTF-8）覆盖原文件")
    ap.add_argument("--show", type=int, default=5, help="显示候选方案条数（默认 5）")
    args = ap.parse_args(argv)

    try:
        with open(args.file, "rb") as f:
            data = f.read()
    except OSError as e:
        print("[错误] 无法读取: %s" % e, file=sys.stderr)
        return 2
    if args.apply and args.output:
        ap.error("--apply 与 -o 不能同时使用")

    cands = collect_candidates(data)
    if not cands:
        print("[失败] 没有任何解码/修复链路可行。", file=sys.stderr)
        return 1
    best_score, best_text, best_chain = cands[0]
    is_direct = "直接解码" in best_chain and "\u2192" not in best_chain  # 链路箭头 → 表示需要修复

    print("文件: %s（%d 字节）" % (args.file, len(data)))
    print("最佳方案: %s" % best_chain)
    if is_direct:
        print("（文件本身即可以该编码正常解码，可能并不需要修复）")
    print("最佳得分: %.1f，不可读字符比例: %.1f%%"
          % (best_score, bad_ratio(best_text) * 100))
    print("候选方案:")
    seen = set()
    shown = 0
    for s, t, d in cands:
        key = d
        if key in seen:
            continue
        seen.add(key)
        shown += 1
        print("  %d. 得分 %6.1f  %s" % (shown, s, d))
        if shown >= args.show:
            break

    if best_score < 40 or bad_ratio(best_text) > 0.2:
        print("[失败] 最佳方案仍不可读（得分 %.1f），未找到可信修复："
              "可能不是解码链路问题，或数据已不可逆。" % best_score,
              file=sys.stderr)
        return 1

    dest = args.file if args.apply else args.output
    if dest:
        try:
            with open(dest, "wb") as f:
                f.write(best_text.encode("utf-8", errors="replace"))
        except OSError as e:
            print("[错误] 无法写出 %s: %s" % (dest, e), file=sys.stderr)
            return 2
        print("已写出修复结果（UTF-8）: %s" % dest)
    else:
        preview = best_text if len(best_text) <= 200 else best_text[:200] + "…"
        print("修复预览:\n%s" % preview)
        print("（加 -o <文件> 保存结果，或 --apply 覆盖原文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
