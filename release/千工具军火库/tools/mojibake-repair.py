#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""乱码修复还原 — 自动尝试常见「错误解码链」，还原被错解码的中文乱码文本。

原理：
  乱码 = 正确文本的字节流被用错误编码解码的产物。修复就是反向走一遍：
  把当前文本用「当初误用的编码」重新编码回字节流，再用「真正的编码」解码。
  工具枚举常见链（GBK/GB18030/Big5/Latin-1/CP1252 到 UTF-8/GBK 等，并支持
  链套用两次以修复双重乱码），按「中文可读性」打分（常用汉字与标点得分高、
  生僻字/控制符/U+FFFD 得分低）自动挑选最优结果。

示例命令：
  python mojibake-repair.py bad.txt                 # 最佳还原结果打印到 stdout
  python mojibake-repair.py bad.txt --list          # 列出全部候选及得分
  python mojibake-repair.py bad.txt --out good.txt  # 结果写入指定文件
  python mojibake-repair.py bad.txt --write         # 用结果覆盖输入文件
  cat bad.txt | python mojibake-repair.py > good.txt

退出码：0 成功（含「未找到更优结果」）；2 参数/读取/写入失败。
"""

import argparse
import sys

# (当初误用的解码器, 文本真正的编码)
CHAINS = [
    ("gbk", "utf-8"), ("gbk", "gb18030"), ("gbk", "big5"),
    ("gb18030", "utf-8"), ("gb18030", "gbk"), ("gb18030", "big5"),
    ("big5", "utf-8"), ("big5", "gb18030"), ("big5", "gbk"),
    ("latin-1", "utf-8"), ("latin-1", "gb18030"), ("latin-1", "big5"),
    ("cp1252", "utf-8"), ("cp1252", "gb18030"),
    ("utf-8", "gb18030"), ("utf-8", "gbk"), ("utf-8", "big5"),
]
READ_ORDER = ("utf-8", "gb18030", "big5")

GOOD_ASCII = set(" \t\r\n.,;:!?()[]{}'\"@#%&*+=/\\_<>~$^|`-")
GOOD_PUNCT = set("，。、；：？！“”‘’「」『』（）《》〈〉【】…—·～％")
# 常用字白名单（把常用汉字与乱码产生的生僻汉字区分开，约 400 个高频字）
COMMON_CN = set(
    "的一是不了在人有我他这个们中来上大为和国地到以说时要就出会可也你对生能而"
    "子那得于着下自之年过发后作里用道行所然家种事成方多经么去法学如都同现当没"
    "动面起看定天分还进好小部其些主样理心她本前开但因只从想实日军者意无力它与"
    "长把机十民第公此已工使情明性知全三又关点正业外将两高间由问很最重并物手应"
    "战向头文体政美相见被利什二等产或新己制身果加西斯月话合回特代内信表化老给"
    "世位次度门任常先海通教儿原东声提立及比员解水名真论处走义各入几口认条平系"
    "气题活尔更别打女变四神总何电数安少报才结反受目太量再感建务做接必场件计管"
    "期市直德资命山金指克许统区保至队形社便空决治展马科司五基眼书非则听白却界"
    "达光放强即像难且权思王象完设式色路记南品住告类求据程北边死张该交规万取拉"
    "格望觉术领共确传师观清今切院让识候带导争运笑飞风步改收根干造言联持组每济"
    "车亲极林服快办议往元英士证近失转夫令准布始怎呢存未远叫台单影具罗字爱击流"
    "备兵连调深商算质团集百需价花党华城石级整府离况亚请技际约示复病息究线似官"
    "火断精满支视消越器容照须九增研写称企八功吗包片史委乎查易按试修检验证链输"
    "标准内容段落工具运行良好双乱码束库"
)


def quality(text):
    """估计一段文本「像正常中文」的程度，返回 0~1 的分数。

    按每字符满分 3.0 归一（而非按好字符占比），这样全由生僻汉字组成的
    GBK 类乱码（约 0.27）无法与真正的中文（0.6~1.0）打平。
    """
    good = bad = 0.0
    for ch in text:
        o = ord(ch)
        if o == 0xFFFD:                       # 替换符：原始字节已丢失
            bad += 4.0
        elif 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF:
            good += 3.0 if ch in COMMON_CN else 0.8   # 生僻汉字多为乱码产物
        elif ch in GOOD_PUNCT:
            good += 3.0
        elif 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF:
            good += 2.0
        elif ch.isascii():
            good += 1.0 if (ch.isalnum() or ch in GOOD_ASCII) else 0.1
        elif 0xE000 <= o <= 0xF8FF:           # 私有区：常见于错误解码
            bad += 4.0
        elif o < 32:
            bad += 3.0
        else:
            bad += 0.5                        # 罕见符号/其他文字区
    if not text:
        return 0.0
    return max(0.0, (good - bad) / (3.0 * len(text)))


def one_round(text):
    """对文本套用一轮全部修复链，返回 [(链名, 还原结果)]。"""
    out = []
    for wrong, true in CHAINS:
        try:
            raw = text.encode(wrong)
        except (UnicodeEncodeError, LookupError):
            continue
        try:
            fixed = raw.decode(true)
        except UnicodeDecodeError:
            continue
        if fixed != text:
            out.append(("%s→%s" % (wrong, true), fixed))
    return out


def all_candidates(text):
    """返回 [(链名, 文本)]，含原文；链最多套用两轮（可修复双重乱码）。"""
    cands = [("原文", text)]
    seen = {text}
    frontier = [text]
    for rnd in (1, 2):
        nxt = []
        for src in frontier:
            for label, fixed in one_round(src):
                if fixed in seen:
                    continue
                seen.add(fixed)
                tag = label if rnd == 1 else label + " ×2"
                nxt.append(fixed)
                cands.append((tag, fixed))
        frontier = nxt
        if not nxt:
            break
    return cands


def preview(text, limit=40):
    s = text.replace("\n", "⏎").replace("\r", "")
    return s[:limit] + ("…" if len(s) > limit else "")


def _setup_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace", newline="")
            except Exception:
                pass


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="自动还原被错解码的中文乱码文本（按可读性挑最优链）")
    ap.add_argument("file", nargs="?", help="输入文件；缺省读 stdin")
    ap.add_argument("--list", action="store_true",
                    help="列出全部候选还原结果及得分，不输出文本")
    ap.add_argument("--out", help="把最佳结果写入该文件（UTF-8）")
    ap.add_argument("--write", action="store_true", help="用最佳结果覆盖输入文件")
    args = ap.parse_args(argv)
    _setup_utf8_stdio()

    if args.write and args.out:
        print("错误：--write 与 --out 不能同时使用", file=sys.stderr)
        return 2

    if args.file:
        try:
            with open(args.file, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            print("错误：无法读取 %s（%s）" % (args.file, exc), file=sys.stderr)
            return 2
    else:
        raw = sys.stdin.buffer.read()

    best = None            # (得分, 链名, 文本)
    primary_text = None    # 第一个成功解码的原文（用于提示与 --list）
    primary_enc = None
    for reader in READ_ORDER:
        try:
            text = raw.decode(reader)
        except UnicodeDecodeError:
            continue
        if primary_text is None:
            primary_text, primary_enc = text, reader
        for label, cand in all_candidates(text):
            sc = quality(cand)
            if best is None or sc > best[0] + 1e-9:
                best = (sc, label, cand)
    if best is None:
        print("错误：无法解码输入（试过：%s）" % ", ".join(READ_ORDER), file=sys.stderr)
        return 2

    score, label, text = best
    orig_score = quality(primary_text)
    if args.list:
        cands = all_candidates(primary_text)
        ranked = sorted(((quality(t), lab, t) for lab, t in cands),
                        key=lambda x: -x[0])
        print("候选还原结果（按中文可读性得分降序；输入按 %s 读取）：" % primary_enc)
        for i, (sc, lab, t) in enumerate(ranked[:20], 1):
            print("  #%-2d %.3f  %-16s  %s" % (i, sc, lab, preview(t)))
        return 0

    n_fffd = primary_text.count("\ufffd")
    print("[mojibake-repair] 输入按 %s 读取；原文得分 %.3f，最佳链：%s（得分 %.3f）"
          % (primary_enc, orig_score, label, score), file=sys.stderr)
    if n_fffd:
        print("[mojibake-repair] 警告：原文含 %d 个 U+FFFD，部分原始字节已丢失，"
              "结果可能不完整" % n_fffd, file=sys.stderr)
    if label == "原文":
        print("[mojibake-repair] 未找到更优还原链，输入可能本就是正常文本",
              file=sys.stderr)

    if args.write:
        if not args.file:
            print("错误：--write 需要指定输入文件", file=sys.stderr)
            return 2
        try:
            with open(args.file, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        except OSError as exc:
            print("错误：写入失败（%s）" % exc, file=sys.stderr)
            return 2
        print("[mojibake-repair] 已用最佳结果覆盖 %s" % args.file, file=sys.stderr)
    elif args.out:
        try:
            with open(args.out, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        except OSError as exc:
            print("错误：写入失败（%s）" % exc, file=sys.stderr)
            return 2
        print("[mojibake-repair] 最佳结果已写入 %s" % args.out, file=sys.stderr)
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
