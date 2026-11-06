#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ebook-cleaner —— 电子书文本清洗：一键清除 TXT 中的页眉页脚、广告行与多余空行。

用途：
    清洗网上下载的电子书 TXT，输出干净正文：
      * 纯页码行：“12”“- 3 -”“第 8 页”“[24/300]”“12/300”；
      * 网址/水印行：含 http(s)://、www. 的行，或整行就是一个域名；
      * 章节间广告行：“手机用户请访问…”“本章未完，点击下一页”“笔趣阁”“求月票”等
        推广语（仅对 40 字以内的短行生效，避免误伤正文）；
      * 装饰分隔行：“------”“****”等纯符号行；
      * 重复页眉页脚：按“相同行出现次数”判定（出现次数 >= max(--min-repeat,
        正文行数 x --ratio) 且不含句末标点、长度 <= 50 的行）；
      * 多余空行：连续空行压缩为一个，去掉首尾空行；
      * 顺带清理零宽字符、不间断空格与行尾空白。
    输出统一为 UTF-8 编码、LF 换行；输入编码自动识别（UTF-8/GB18030/Big5）。
    误伤时可加 --keep-regex 保护匹配行，或 --no-frequency 关闭频次规则。

示例命令：
    python ebook-cleaner.py book.txt                    # 清洗后输出到屏幕
    python ebook-cleaner.py book.txt -o clean.txt       # 写入新文件
    python ebook-cleaner.py book.txt --stats            # 额外在 stderr 显示清洗统计
    python ebook-cleaner.py book.txt --in-place         # 就地覆盖原文件
    python ebook-cleaner.py book.txt --keep-regex "^第.+卷"   # 保护匹配行不删
    python ebook-cleaner.py book.txt --no-frequency     # 只按规则删，不按出现次数删
"""

import argparse
import math
import re
import sys

ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")

PAGE_NUM_RES = [
    re.compile(r"^[-–—~～=＝]?\s*\d{1,6}\s*[-–—~～=＝]?$"),
    re.compile(r"^第\s*\d{1,6}\s*页(\s*[,，]?\s*共\s*\d{1,6}\s*页)?$"),
    re.compile(r"^[\[（(]\s*\d{1,6}\s*[\]）)]$"),
    re.compile(r"^[\[（(]\s*\d{1,6}\s*[/／]\s*\d{1,6}\s*[\]）)]$"),
    re.compile(r"^\d{1,6}\s*[/／]\s*\d{1,6}$"),
]
URL_ANY_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
DOMAIN_LINE_RE = re.compile(
    r"^[\w.\-]+\.(?:com|cn|net|org|cc|info|xyz|top|vip|moe|me|tv|la|io)(?:[/:]\S*)?$",
    re.IGNORECASE)
AD_RE = re.compile(
    "笔趣阁|顶点小说|最新章节|手机用户|手机阅读|移动阅读|点击下一页|本章未完|未完待续|"
    "加入书签|方便阅读|求收藏|求月票|求推荐票|求订阅|求打赏|投推荐票|本书来自|转载请注明|"
    "无弹窗|请记住本书|版权所有|盗版必究|扫码关注|公众号|微信关注|下载APP|APP下载|"
    "更多精彩|第一时间更新|谢谢阅读|谢谢观赏")
SEPARATOR_RE = re.compile(r"^[\s\-–—~=＝*＊#＃•·_＿+＋|｜]{3,}$")
# 频次规则保护：行尾为句末标点的行通常是正文，不按出现次数删除；
# 注意不含后括号/后引号——“【xx书屋】”这类横幅正是最常见的页眉形式
FREQ_PROTECT_END_CHARS = set("。！？!?…‥⋯")


def _setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")
        except Exception:
            pass


def _decode_auto(data):
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return data.decode("utf-32")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_text(path, encoding=None):
    if path in ("-", None):
        data = sys.stdin.buffer.read()
    else:
        with open(path, "rb") as fh:
            data = fh.read()
    if encoding:
        return data.decode(encoding, errors="replace")
    return _decode_auto(data)


def write_text(text, out_path):
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def clean_lines(text, min_repeat=3, ratio=0.02, use_frequency=True,
                use_ads=True, keep_res=()):
    """清洗文本，返回 (输出行列表, 统计 dict)。"""
    text = ZERO_WIDTH_RE.sub("", text).replace("\xa0", " ")
    lines = [ln.rstrip() for ln in text.splitlines()]
    stats = {"page": 0, "url": 0, "ad": 0, "sep": 0, "repeat": 0, "blank": 0}
    protected = [any(rx.search(ln) for rx in keep_res) for ln in lines]

    # 第一轮：按明确规则删除
    removed = set()
    for i, ln in enumerate(lines):
        body = ln.strip()
        if not body or protected[i]:
            continue
        if any(rx.match(body) for rx in PAGE_NUM_RES):
            removed.add(i)
            stats["page"] += 1
        elif URL_ANY_RE.search(body) or DOMAIN_LINE_RE.match(body):
            removed.add(i)
            stats["url"] += 1
        elif use_ads and len(body) <= 40 and AD_RE.search(body):
            removed.add(i)
            stats["ad"] += 1
        elif SEPARATOR_RE.match(body):
            removed.add(i)
            stats["sep"] += 1

    # 第二轮：频次规则——反复出现的短行视为页眉页脚/水印
    if use_frequency:
        rest = [(i, ln.strip()) for i, ln in enumerate(lines)
                if i not in removed and ln.strip() and not protected[i]]
        threshold = max(min_repeat, int(math.ceil(ratio * max(len(rest), 1))))
        seen = {}
        for i, body in rest:
            if len(body) <= 50 and body[-1] not in FREQ_PROTECT_END_CHARS:
                seen.setdefault(body, []).append(i)
        for body, idxs in seen.items():
            if len(idxs) >= threshold:
                for i in idxs:
                    removed.add(i)
                    stats["repeat"] += 1

    # 第三轮：删行 + 压缩空行
    out = []
    blank_run = 0
    for i, ln in enumerate(lines):
        if i in removed:
            continue
        if not ln.strip():
            blank_run += 1
            if blank_run == 1:
                out.append("")
            else:
                stats["blank"] += 1
        else:
            blank_run = 0
            out.append(ln)
    while out and out[0] == "":
        out.pop(0)
        stats["blank"] += 1
    while out and out[-1] == "":
        out.pop()
        stats["blank"] += 1
    return out, stats


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ebook-cleaner",
        description="电子书文本清洗：清除 TXT 的页眉页脚、广告行、页码、分隔线与多余空行。",
    )
    parser.add_argument("input", nargs="?", default="-",
                        help="输入 TXT 文件；缺省或 '-' 表示 stdin")
    parser.add_argument("-o", "--output",
                        help="输出文件（UTF-8/LF）；缺省输出到 stdout")
    parser.add_argument("--in-place", action="store_true",
                        help="就地覆盖原文件（不能与 -o 同用）")
    parser.add_argument("--encoding",
                        help="指定输入编码；缺省自动识别 UTF-8/GB18030/Big5")
    parser.add_argument("--stats", action="store_true",
                        help="在 stderr 显示清洗统计")
    parser.add_argument("--min-repeat", type=int, default=3,
                        help="频次规则的最少出现次数，默认 3")
    parser.add_argument("--ratio", type=float, default=0.02,
                        help="频次阈值占非空行数的比例，默认 0.02")
    parser.add_argument("--no-frequency", action="store_true",
                        help="关闭按出现次数删除页眉页脚")
    parser.add_argument("--no-ads", action="store_true",
                        help="关闭广告关键词删除")
    parser.add_argument("--keep-regex", action="append", default=[],
                        help="匹配该正则的行绝不删除（可多次给出）")
    args = parser.parse_args(argv)

    keep_res = []
    for pat in args.keep_regex:
        try:
            keep_res.append(re.compile(pat))
        except re.error as exc:
            print("ebook-cleaner: --keep-regex 无效：%s" % exc, file=sys.stderr)
            return 2

    if args.in_place and args.output:
        print("ebook-cleaner: --in-place 与 -o 不能同时使用", file=sys.stderr)
        return 2
    if args.in_place and args.input in ("-", None):
        print("ebook-cleaner: --in-place 需要指定输入文件", file=sys.stderr)
        return 2

    try:
        text = read_text(args.input, args.encoding)
    except OSError as exc:
        print("ebook-cleaner: 无法读取输入：%s" % exc, file=sys.stderr)
        return 2

    out, stats = clean_lines(text,
                             min_repeat=args.min_repeat,
                             ratio=args.ratio,
                             use_frequency=not args.no_frequency,
                             use_ads=not args.no_ads,
                             keep_res=keep_res)

    if args.stats:
        print("ebook-cleaner: 删除 页码行 %d、网址/水印行 %d、广告行 %d、"
              "装饰分隔线 %d、重复页眉页脚 %d、多余空行 %d"
              % (stats["page"], stats["url"], stats["ad"],
                 stats["sep"], stats["repeat"], stats["blank"]),
              file=sys.stderr)
        print("ebook-cleaner: 输出 %d 行（原 %d 行）" % (len(out), len(text.splitlines())),
              file=sys.stderr)

    out_text = "\n".join(out)
    if out_text:
        out_text += "\n"
    target = args.input if args.in_place else args.output
    try:
        write_text(out_text, target)
    except OSError as exc:
        print("ebook-cleaner: 无法写出结果：%s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
