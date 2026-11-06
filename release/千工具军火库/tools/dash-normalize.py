# -*- coding: utf-8 -*-
"""破折号连字符规范（dash-normalize）

用途：
    把 --、–、—、———、－、‐、−、〜 等横线写法按场景归一：
      · 破折号场景 → 中文破折号「——」（两个 U+2014）：中文语境下的双连字符
        --、em/en 短横连用（——、———）、单个 – / — / ／－ 等；
        归一时去掉紧贴破折号两侧的空格（如「文本 —— 注释」→「文本——注释」）。
      · 连接号/区间场景 → 区间号「～」（U+FF5E）：数字之间的短横
        （100-200、2013–2015、12:30-14:00）；2020-01-01、010-12345678、
        10-20-30 这类长数字链/链式写法保持原样；减号 − 不作区间处理。
      · 纯英文语境（两侧均为西文字母/数字）保持原样，如 well--known、a -- b；
        --force 无视语境强制转换。
      · 汉字之间的 ASCII 短横线连接号（如「中-英词典」）按 GB/T 15834 保留。

示例命令：
    python dash-normalize.py input.txt
    python dash-normalize.py --force input.txt
    python dash-normalize.py input.txt -o out.txt
    cat input.txt | python dash-normalize.py
"""
import argparse
import re
import sys

HAN = '\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
HANISH = re.compile('[' + HAN + '，。！？；：、…—～·（）《》〈〉“”‘’「」『』【】]')
WEST = re.compile('[A-Za-z0-9]')
DASHES = set('-\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d')
MINUS = '\u2212'                       # − 减号不参与区间归一
WAVE = re.compile('[\u301c\u3030]')    # 〜 〰 → ～
BLANKS = ' \t\u00a0\u3000'


def is_hanish(ch):
    return bool(ch) and bool(HANISH.match(ch))


def digits_before(text, i):
    """统计位置 i 之前紧邻的连续数字个数，返回 (个数, 停止位置)。"""
    p, cnt = i - 1, 0
    while p >= 0 and text[p].isdigit():
        cnt += 1
        p -= 1
    return cnt, p


def digits_after(text, j):
    """统计位置 j 起紧邻的连续数字个数，返回 (个数, 停止位置)。"""
    k, cnt = j, 0
    while k < len(text) and text[k].isdigit():
        cnt += 1
        k += 1
    return cnt, k


def normalize(text, force=False):
    text = WAVE.sub('～', text)
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c not in DASHES:
            out.append(c)
            i += 1
            continue
        j = i
        while j < n and text[j] in DASHES:
            j += 1
        run = text[i:j]
        # 吸收两侧紧邻空格，用于语境判断
        ks = j
        while ks < n and text[ks] in BLANKS:
            ks += 1
        pe = i - 1
        while pe >= 0 and text[pe] in BLANKS:
            pe -= 1
        l = text[pe] if pe >= 0 else None
        r = text[ks] if ks < n else None
        chinese = is_hanish(l) or is_hanish(r)
        repl = None
        # 数字之间的单根短横 → 区间号
        if len(run) == 1 and l and r and l.isdigit() and r.isdigit() and run != MINUS:
            if run == '-':
                lc, pl = digits_before(text, i)
                rc, kr = digits_after(text, j)
                if (0 < lc <= 4 and 0 < rc <= 4
                        and not (pl >= 0 and text[pl] == '-')
                        and not (kr < n and text[kr] == '-')):
                    repl = '～'
            else:
                repl = '～'   # – — － ‐ 等在数字之间一律视作区间
        # 破折号场景
        if repl is None and (chinese or force):
            multi = len(run) >= 2
            single_special = (len(run) == 1 and run != '-')
            if multi or single_special:
                repl = '——'
        if repl is not None:
            while out and out[-1] in BLANKS:   # 去掉紧贴破折号的空格
                out.pop()
            out.append(repl)
            i = ks                             # 连同其后紧邻空格一起跳过
        else:
            out.append(run)
            i = j
    return ''.join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description='破折号连字符规范：统一为「——」或区间号「～」')
    ap.add_argument('input', nargs='?', help='输入文件（缺省读 stdin）')
    ap.add_argument('-o', '--output', help='输出文件（缺省写 stdout）')
    ap.add_argument('--in-place', action='store_true', help='原地覆写输入文件')
    ap.add_argument('--force', action='store_true', help='英文语境也强制转换')
    args = ap.parse_args()

    try:
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', newline='')
    except Exception:
        pass

    if args.input:
        with open(args.input, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = normalize(text, force=args.force)

    if args.in_place and args.input:
        with open(args.input, 'w', encoding='utf-8', newline='') as f:
            f.write(result)
    elif args.output:
        with open(args.output, 'w', encoding='utf-8', newline='') as f:
            f.write(result)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
