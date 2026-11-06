# -*- coding: utf-8 -*-
"""语境标点归一（cn-punct-normalize）

用途：
    按所在语境自动归一中英混排文本中「可宽度切换」标点的全/半角：
      · 中文语境 → 全角：，。！？：；（）
        （判定：左侧紧邻汉字/中文标点，或右侧紧邻中文且左侧不是西文字母/数字）
      · 纯英文/数字片段（两侧都是西文字母或数字）→ 半角：, . ! ? : ; ( )
      · 其余情况保持原样（如 URL、句首悬空标点）
    全角转半角时，逗号/分号/冒号后若紧跟字母数字则补一个半角空格。
    成对 ASCII 引号内含汉字时转换为中文弯引号“”‘’。
    连续两个以上的句点/句号（省略号形态）保持原样，请用 ellipsis-normalize 处理。
    小数 3.14、千分位 1,000、URL、时间 12:30 等因两侧均为数字/西文而自动保留半角。

示例命令：
    python cn-punct-normalize.py input.txt
    python cn-punct-normalize.py input.txt -o out.txt
    python cn-punct-normalize.py --in-place input.txt
    cat input.txt | python cn-punct-normalize.py
"""
import argparse
import re
import sys

HAN = '\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
# 「中文侧」：汉字、常用中文标点、全角字母数字
HANISH = re.compile('[' + HAN + '，。！？；：、…—～·（）《》〈〉“”‘’「」『』【】'
                    '０-９Ａ-Ｚａ-ｚ]')
WEST = re.compile('[A-Za-z0-9]')
HALF2FULL = {',': '，', '.': '。', '!': '！', '?': '？', ';': '；', ':': '：',
             '(': '（', ')': '）'}
FULL2HALF = {v: k for k, v in HALF2FULL.items()}
AMBIG = set(HALF2FULL) | set(FULL2HALF)
BLANKS = ' \t\u00a0\u3000'
QUOTE_OPEN = {'"': '“', "'": '‘'}
QUOTE_CLOSE = {'"': '”', "'": '’'}


def nearest(text, start, step):
    """从 start 沿 step 方向找最近的非空白字符；找不到返回 None。"""
    i = start
    while 0 <= i < len(text):
        if text[i] not in BLANKS:
            return text[i]
        i += step
    return None


def is_hanish(ch):
    return bool(ch) and bool(HANISH.match(ch))


def is_west(ch):
    return bool(ch) and bool(WEST.match(ch))


def convert_punct(text):
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in AMBIG:
            j = i
            while j < n and text[j] in AMBIG:
                j += 1
            run = text[i:j]
            # 省略号形态（两个以上句点/句号，可混用）不动，交给 ellipsis-normalize
            if len(run) >= 2 and set(run) <= {'.', '。', '\uff0e', '\uff61'}:
                out.append(run)
                i = j
                continue
            l = nearest(text, i - 1, -1)
            r = nearest(text, j, 1)
            buf = []
            for ch in run:
                if is_hanish(l):                      # 左侧是中文 → 全角
                    t = 'full'
                elif is_hanish(r) and not is_west(l):  # 右侧中文且左侧非西文
                    t = 'full'
                elif is_west(l) and is_west(r):        # 两侧皆西文 → 半角
                    t = 'half'
                else:
                    t = None
                if t == 'full' and ch in HALF2FULL:
                    buf.append(HALF2FULL[ch])
                elif t == 'half' and ch in FULL2HALF:
                    buf.append(FULL2HALF[ch])
                else:
                    buf.append(ch)
            piece = ''.join(buf)
            out.append(piece)
            # 确实发生了全角→半角转换，且半角句读后紧跟字母数字时补空格
            nxt = text[j] if j < n else ''
            if (piece != run and piece and piece[-1] in ',.;:!?'
                    and (nxt.isalnum() or nxt in HALF2FULL)):
                out.append(' ')
            i = j
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def convert_quotes(line):
    """成对 ASCII 引号内含汉字 → 中文弯引号。"""
    res = list(line)
    for q, op in QUOTE_OPEN.items():
        positions = [k for k, ch in enumerate(line) if ch == q]
        k = 0
        while k + 1 < len(positions):
            a, b = positions[k], positions[k + 1]
            if any(HANISH.match(ch) for ch in line[a + 1:b]):
                res[a] = op
                res[b] = QUOTE_CLOSE[q]
            k += 2
    return ''.join(res)


def process(text):
    out = []
    for line in text.splitlines(keepends=True):
        body = line
        ends = ''
        while body and body[-1] in '\r\n':
            ends = body[-1] + ends
            body = body[:-1]
        out.append(convert_quotes(convert_punct(body)) + ends)
    return ''.join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description='语境标点归一：中文语句用全角，纯英文/数字片段用半角')
    ap.add_argument('input', nargs='?', help='输入文件（缺省读 stdin）')
    ap.add_argument('-o', '--output', help='输出文件（缺省写 stdout）')
    ap.add_argument('--in-place', action='store_true', help='原地覆写输入文件')
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

    result = process(text)

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
