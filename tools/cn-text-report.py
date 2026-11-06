#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文排版体检报告 — 一键运行多项检查（标点、空格、全半角、零宽、简繁混用）
并汇总为一份体检报告。

包含检查项（分节展示）：
  zero-width   零宽字符（U+200B/200C/200D/FEFF/2060/00AD）
  cn-en-space  中西文之间缺空格
  punct        标点全半角（中文语境半角标点 / 英文语境全角标点 / 重复标点）
  fw-alnum     全角字母与数字（Ａ ｂ ０ ９）
  s2t          简繁混用（常见单字简繁对照的启发式检查）

Markdown 感知：.md/.markdown 文件默认自动跳过围栏代码块、行内代码、URL 与
链接目标；其他文件按纯文本处理。可用 --md on/off/auto 覆盖（默认 auto）。

示例命令：
  python cn-text-report.py article.txt
  python cn-text-report.py a.md b.txt --out report.txt
  python cn-text-report.py article.txt --json       # 输出 JSON 数组
  python cn-text-report.py article.txt --max 10     # 每节最多展示 10 条
  python cn-text-report.py article.txt --strict     # 有发现时退出码 1（CI 用）

退出码：0 完成（无论有无发现）；1 有发现且加 --strict；2 读取失败。
"""

import argparse
import json
import re
import sys

# ---------- 字符类 ----------
CJK = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
CJK_PUNCT = "，。、；：？！…—·“”‘’「」『』（）《》〈〉【】～"
HALF2FULL = {",": "，", ".": "。", ";": "；", ":": "：", "?": "？", "!": "！"}
FULL_PUNCT = "，。；：？！"
REPEAT_PUNCT = "，。；：？！、"
FW_ALNUM = "\uff10-\uff19\uff21-\uff3a\uff41-\uff5a"
ZW_CHARS = {
    "\u200b": "零宽空格 U+200B",
    "\u200c": "零宽不连字 U+200C",
    "\u200d": "零宽连接符 U+200D",
    "\ufeff": "零宽不换行空格 U+FEFF",
    "\u2060": "字词连接符 U+2060",
    "\u00ad": "软连字符 U+00AD",
}

RE_CJK = re.compile("[" + CJK + "]")
RE_CJKISH = re.compile("[" + CJK + CJK_PUNCT + "]")
RE_ZW = re.compile("[" + "".join(ZW_CHARS) + "]")
RE_BOUNDARY = re.compile(
    "(?<=[%(c)s])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[%(c)s])" % {"c": CJK})
RE_HALF_PUNCT = re.compile("[,.;:?!]")
RE_FULL_PUNCT = re.compile("[" + FULL_PUNCT + "]")
RE_REPEAT = re.compile("([" + REPEAT_PUNCT + "])\\1+")
RE_FW_ALNUM = re.compile("[" + FW_ALNUM + "]")

RE_PROTECT = re.compile(
    r"https?://[^\s)\]}>'\"，。；！？]+"
    r"|`+[^`\n]*`+"
    r"|\]\([^)\n]*\)"
    r"|<[^>\n\s]*>"
)
RE_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")

# 简繁混用：常见单字对照（简体在前，繁体在后），启发式
_S2T_SRC = (
    "这這 时時 说說 为為 与與 后後 开開 关關 么麼 个個 们們 来來 对對 门門 东東 "
    "车車 长長 书書 学學 国國 会會 电電 机機 网網 体體 点點 内內 区區 处處 见見 "
    "风風 龙龍 汉漢 语語 试試 证證 华華 广廣 历歷 动動 无無 从從 众眾 优優 传傳 "
    "术術 当當 画畫 号號 苏蘇 庆慶 币幣 职職 软軟 经經 产產 应應 层層 属屬 岛島 "
    "师師 张張 强強 录錄 忆憶 态態 愿願 战戰 择擇 换換 损損 摆擺 摄攝 敌敵 数數 "
    "满滿 灭滅 灯燈 爱愛 献獻 环環 监監 离離 种種 积積 笔筆 类類 级級 线線 组組 "
    "细細 织織 终終 绍紹 维維 缩縮 罗羅 译譯 诗詩 质質 购購 费費 资資 赠贈 转轉 "
    "轮輪 载載 输輸 达達 过過 运運 还還 进進 远遠 连連 迟遲 适適 选選 递遞 邮郵 "
    "钟鐘 钢鋼 铁鐵 银銀 键鍵 镜鏡 闪閃 问問 间間 闻聞 阅閱 队隊 阶階 际際 陆陸 "
    "难難 顶頂 项項 顺順 顾顧 飞飛 馆館 马馬 驱驅 驶駛 驾駕 骗騙 鲜鮮 鸡雞 齐齊 "
    "买買 卖賣 实實 导導 尽盡 乐樂 云雲 现現"
)
S2T_PAIRS = []
for _tok in _S2T_SRC.split():
    if len(_tok) == 2 and (_tok[0], _tok[1]) not in S2T_PAIRS:
        S2T_PAIRS.append((_tok[0], _tok[1]))
S2T_PARTNER = {}
for _s, _t in S2T_PAIRS:
    S2T_PARTNER[_s] = _t
    S2T_PARTNER[_t] = _s

SEC_OF = {
    "zero-width": ("zero-width", "零宽字符"),
    "cn-en-space": ("cn-en-space", "中西文空格"),
    "punct-half": ("punct", "标点全半角"),
    "punct-full": ("punct", "标点全半角"),
    "punct-repeat": ("punct", "标点全半角"),
    "fw-alnum": ("fw-alnum", "全角字母数字"),
    "s2t": ("s2t", "简繁混用"),
}
SEC_ORDER = ["zero-width", "cn-en-space", "punct", "fw-alnum", "s2t"]

READ_ORDER = ("utf-8", "gb18030", "big5", "latin-1")


def split_free(line):
    parts = []
    pos = 0
    for m in RE_PROTECT.finditer(line):
        if m.start() > pos:
            parts.append((pos, line[pos:m.start()], False))
        parts.append((m.start(), m.group(0), True))
        pos = m.end()
    if pos < len(line):
        parts.append((pos, line[pos:], False))
    return parts


def iter_fenced(lines):
    """逐行产出 (下标, 行, 是否在代码块内)。"""
    fence_char = None
    fence_len = 0
    for i, line in enumerate(lines):
        m = RE_FENCE.match(line)
        if fence_char is None:
            if m:
                fence_char, fence_len = m.group(1)[0], len(m.group(1))
                yield i, line, True
            else:
                yield i, line, False
        else:
            if (m and m.group(1)[0] == fence_char
                    and len(m.group(1)) >= fence_len
                    and not m.group(2).strip()):
                fence_char = None
            yield i, line, True


def check_line(ln, line, findings):
    """对一行的可自由文本段执行各项检查。"""
    for start, seg, protected in split_free(line):
        if protected:
            continue
        for m in RE_ZW.finditer(seg):
            findings.append({"rule": "zero-width", "line": ln,
                             "col": start + m.start() + 1,
                             "message": "零宽字符：%s（建议删除）"
                                        % ZW_CHARS[m.group(0)]})
        for m in RE_BOUNDARY.finditer(seg):
            findings.append({"rule": "cn-en-space", "line": ln,
                             "col": start + m.start() + 1,
                             "message": "中西文之间建议加一个半角空格"})
        for m in RE_HALF_PUNCT.finditer(seg):
            j = m.start()
            prev = seg[j - 1] if j > 0 else ""
            nxt = seg[j + 1] if j + 1 < len(seg) else ""
            if RE_CJKISH.match(prev) or RE_CJKISH.match(nxt):
                findings.append({"rule": "punct-half", "line": ln,
                                 "col": start + j + 1,
                                 "message": "中文语境应使用全角标点：%s → %s"
                                            % (m.group(0), HALF2FULL[m.group(0)])})
        for m in RE_FULL_PUNCT.finditer(seg):
            j = m.start()
            ctx = seg[max(0, j - 8):j] + seg[j + 1:j + 9]
            if not RE_CJK.search(ctx):
                findings.append({"rule": "punct-full", "line": ln,
                                 "col": start + j + 1,
                                 "message": "英文/数字语境疑似应使用半角标点：%s"
                                            % m.group(0)})
        for m in RE_REPEAT.finditer(seg):
            findings.append({"rule": "punct-repeat", "line": ln,
                             "col": start + m.start() + 1,
                             "message": "全角标点重复：“%s”" % m.group(0)})
        for m in RE_FW_ALNUM.finditer(seg):
            ch = m.group(0)
            findings.append({"rule": "fw-alnum", "line": ln,
                             "col": start + m.start() + 1,
                             "message": "全角字母/数字：%s → %s"
                                        % (ch, chr(ord(ch) - 0xFEE0))})


def inspect_text(text, md_aware):
    """返回 (findings 列表, 使用的检查模式说明)。"""
    findings = []
    lines = text.splitlines()
    mode = "markdown（跳过代码块/行内代码/URL）" if md_aware else "纯文本"
    s2t_seen = {}     # 字符 -> 首次出现的行号
    for i, line, is_code in iter_fenced(lines):
        ln = i + 1
        if md_aware and is_code:
            continue
        check_line(ln, line, findings)
        segs = split_free(line) if md_aware else [(0, line, False)]
        for _start, seg, protected in segs:
            if protected:
                continue
            for ch in seg:
                if ch in S2T_PARTNER and ch not in s2t_seen:
                    s2t_seen[ch] = ln
    # 简繁混用：同一文档中同时出现一对简/繁字形
    reported = set()
    for s, t in S2T_PAIRS:
        if s in s2t_seen and t in s2t_seen:
            key = tuple(sorted((s, t)))
            if key in reported:
                continue
            reported.add(key)
            late, early = (t, s) if s2t_seen[t] >= s2t_seen[s] else (s, t)
            findings.append({
                "rule": "s2t", "line": s2t_seen[late], "col": 1,
                "message": "简繁混用：“%s”（首见 L%d）与“%s”（首见 L%d）同时出现"
                           % (late, s2t_seen[late], early, s2t_seen[early])})
    findings.sort(key=lambda f: (f["line"], f["col"]))
    return findings, mode


def decode_best(raw):
    last = None
    for enc in READ_ORDER:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError as exc:
            last = exc
    raise last


def build_report(name, text, enc, md_aware):
    findings, mode = inspect_text(text, md_aware)
    grouped = {}
    for f in findings:
        grouped.setdefault(SEC_OF[f["rule"]][0], []).append(f)
    sections = []
    label_of = {"zero-width": "零宽字符", "cn-en-space": "中西文空格",
                "punct": "标点全半角", "fw-alnum": "全角字母数字", "s2t": "简繁混用"}
    for sec_id in SEC_ORDER:
        items = grouped.get(sec_id, [])
        sections.append({"id": sec_id, "label": label_of[sec_id],
                         "count": len(items), "items": items})
    total = len(findings)
    score = max(0, 100 - 2 * total)
    return {
        "file": name, "encoding": enc, "mode": mode,
        "lines": len(text.splitlines()), "chars": len(text),
        "total": total, "score": score, "sections": sections,
    }


def render_report(rep, max_items):
    out = []
    out.append("=" * 56)
    out.append("中文排版体检报告：%s" % rep["file"])
    out.append("  编码 %s ｜ %d 行 ｜ %d 字符 ｜ 模式：%s"
               % (rep["encoding"], rep["lines"], rep["chars"], rep["mode"]))
    for sec in rep["sections"]:
        out.append("-" * 56)
        out.append("【%s】%d 处" % (sec["label"], sec["count"]))
        shown = sec["items"] if max_items <= 0 else sec["items"][:max_items]
        for it in shown:
            out.append("  L%-5d C%-5d %s" % (it["line"], it["col"], it["message"]))
        hidden = sec["count"] - len(shown)
        if hidden > 0:
            out.append("  …（另有 %d 条未显示，可用 --max 0 查看）" % hidden)
    out.append("-" * 56)
    out.append("汇总：%d 处发现，体检得分 %d / 100（每处 −2，最低 0 分）"
               % (rep["total"], rep["score"]))
    return "\n".join(out)


def _setup_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="一键运行多项中文排版检查，汇总为一份体检报告")
    ap.add_argument("files", nargs="+", help="待体检的文本/Markdown 文件")
    ap.add_argument("--out", help="把报告写入该文件（UTF-8）")
    ap.add_argument("--json", action="store_true", help="输出 JSON 数组（每文件一项）")
    ap.add_argument("--max", type=int, default=30, metavar="N",
                    help="每节最多展示 N 条（0 = 不限，默认 30）")
    ap.add_argument("--md", choices=["auto", "on", "off"], default="auto",
                    help="Markdown 感知模式（默认 auto：按扩展名判断）")
    ap.add_argument("--strict", action="store_true",
                    help="有发现时退出码置 1（CI 用）")
    args = ap.parse_args(argv)
    _setup_utf8_stdio()

    reports = []
    hard_errors = 0
    for name in args.files:
        try:
            with open(name, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            print("%s: 错误：无法读取（%s）" % (name, exc), file=sys.stderr)
            hard_errors += 1
            continue
        try:
            text, enc = decode_best(raw)
        except UnicodeDecodeError as exc:
            print("%s: 错误：无法解码（%s）" % (name, exc), file=sys.stderr)
            hard_errors += 1
            continue
        if args.md == "on":
            md_aware = True
        elif args.md == "off":
            md_aware = False
        else:
            md_aware = name.lower().endswith((".md", ".markdown", ".mdown"))
        reports.append(build_report(name, text, enc, md_aware))

    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        blocks = [render_report(r, args.max) for r in reports]
        print("\n\n".join(blocks) if blocks else "（没有可体检的文件）")
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8", newline="") as fh:
                if args.json:
                    fh.write(json.dumps(reports, ensure_ascii=False, indent=2))
                else:
                    fh.write("\n\n".join(render_report(r, args.max)
                                         for r in reports) + "\n")
            print("[cn-text-report] 报告已写入 %s" % args.out, file=sys.stderr)
        except OSError as exc:
            print("错误：报告写入失败（%s）" % exc, file=sys.stderr)
            hard_errors += 1

    found = any(r["total"] for r in reports)
    if args.strict and found:
        return 1
    return 2 if hard_errors else 0


if __name__ == "__main__":
    sys.exit(main())
