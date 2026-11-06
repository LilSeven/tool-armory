# -*- coding: utf-8 -*-
"""省略号规范化（ellipsis-normalize）

用途：
    把 ...、。。。、………、…‥ 等省略号写法统一为标准中文省略号「……」（两个 U+2026）：
      · 连续句点 ... / ....（中文语境）→ ……
      · 连续句号 。。 / 。。。 → ……
      · 单个或连续 … / ‥（含混用）→ ……
    并按 GB/T 15834 处理与句末标点的组合：省略号之后的点号（句号/逗号/顿号/
    分号/冒号）删除，问号/叹号保留（如「……？」「……！」），引号夹层同样处理。
    默认仅在中文语境转换连续句点（西文 "Wait..." 保留）；--force 无视语境全部转换。

示例命令：
    python ellipsis-normalize.py input.txt
    python ellipsis-normalize.py --force input.txt
    python ellipsis-normalize.py input.txt -o out.txt
    cat input.txt | python ellipsis-normalize.py
"""
import argparse
import re
import sys

HAN = '\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
HANISH = re.compile('[' + HAN + '，。！？；：、…—～·（）《》〈〉“”‘’「」『』【】]')
DOTS = set('.。\u2026\u2025\uff0e\uff61')  # . 。 … ‥ ． ｡
ELL = set('\u2026\u2025')                  # … ‥
IDEO = set('。\uff61')                     # 。
BLANKS = ' \t\u00a0\u3000'
# 省略号后不应再接点号（引号夹层也处理）
TRAIL_DOT = re.compile('……([”’」』】〕]?)[。．，、；：]')


def nearest(text, start, step):
    i = start
    while 0 <= i < len(text):
        if text[i] not in BLANKS:
            return text[i]
        i += step
    return None


def normalize(text, force=False):
    out = []
    i, n = 0, len(text)
    while i < n:
        if text[i] in DOTS:
            j = i
            while j < n and text[j] in DOTS:
                j += 1
            run = text[i:j]
            if len(run) == 1:
                # 单个句点/句号是正常标点，保持原样（单个 … / ‥ 不是标准写法）
                if text[i] in ELL:
                    out.append('……')
                else:
                    out.append(text[i])
            else:
                if any(ch in ELL for ch in run) or any(ch in IDEO for ch in run):
                    out.append('……')          # 含 …/‥/。 的连续串直接归一
                else:
                    # 全是半角句点的连续串：仅中文语境转换，西文 "..." 保留
                    l = nearest(text, i - 1, -1)
                    r = nearest(text, j, 1)
                    if force or (l and HANISH.match(l)) or (r and HANISH.match(r)):
                        out.append('……')
                    else:
                        out.append(run)
            i = j
        else:
            out.append(text[i])
            i += 1
    # 省略号后点号清理（可能连续多个，循环至不再变化）
    res = ''.join(out)
    prev = None
    while prev != res:
        prev = res
        res = TRAIL_DOT.sub(r'……\1', res)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description='省略号规范化：统一为标准「……」')
    ap.add_argument('input', nargs='?', help='输入文件（缺省读 stdin）')
    ap.add_argument('-o', '--output', help='输出文件（缺省写 stdout）')
    ap.add_argument('--in-place', action='store_true', help='原地覆写输入文件')
    ap.add_argument('--force', action='store_true', help='西文 ... 也强制转换')
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
