# -*- coding: utf-8 -*-
"""中英混排空格检查（han-space-lint）

用途：
    逐行检查中英混排文本中的空格问题，输出行级报告：
      1. missing-space  汉字与西文（字母/数字）之间缺少空格
      2. extra-space    汉字与西文之间空格过多（>=2 个）或使用了全角/不间断空格
      3. inner-space    汉字内部残留空格（汉字与汉字之间出现空格）
      4. punct-space    中文标点前后有多余空格（如「你好 ，世界」「（ 说明」）

    默认发现问题也以退出码 0 结束；--strict 时发现问题返回 1。

示例命令：
    python han-space-lint.py input.txt
    python han-space-lint.py --strict input.txt          # 有问题则退出码 1
    cat input.txt | python han-space-lint.py
"""
import argparse
import re
import sys

HAN = '\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
WEST = 'A-Za-z0-9'
SPACE = ' \u00a0\u2009\u3000'
HAN_C = '[' + HAN + ']'
WEST_C = '[' + WEST + ']'
SP_C = '[' + SPACE + ']'

# 中文标点（闭口类前不应有空格，开口类后不应有空格）
CLOSE_PUNCT = '，。！？；：、）》」』】”’…—'
OPEN_PUNCT = '（《「『【“‘'

RULES = [
    # (编号, 正则, 说明)
    ('missing-space',
     re.compile('(?P<at>(' + HAN_C + WEST_C + ')|(' + WEST_C + HAN_C + '))'),
     '汉字与西文之间缺少空格'),
    ('inner-space',
     re.compile(HAN_C + SP_C + '+' + HAN_C),
     '汉字内部残留空格'),
    ('extra-space',
     re.compile('((' + HAN_C + ')|(' + WEST_C + '))[' + SPACE + ']{2,}((' + HAN_C
                + ')|(' + WEST_C + '))'),
     '中西文之间空格过多'),
    ('fw-space',
     re.compile('[' + SPACE + ']*\u3000[' + SPACE + ']*'),
     '使用了全角空格'),
    ('punct-space',
     re.compile('[' + SPACE + ']+[' + CLOSE_PUNCT + ']|[' + OPEN_PUNCT + ']['
                + SPACE + ']+'),
     '中文标点旁有多余空格'),
]


def lint_line(line: str):
    """返回该行的问题列表 [(kind, col, snippet, message)]，col 从 1 开始。"""
    issues = []
    taken = []  # 已报告的 (start, end) 区间，避免重复报告
    for kind, pat, msg in RULES:
        for m in pat.finditer(line):
            s, e = m.span()
            if any(not (e <= a or s >= b) for a, b in taken):
                continue
            taken.append((s, e))
            lo, hi = max(0, s - 8), min(len(line), e + 8)
            snippet = line[lo:hi].replace('\t', ' ')
            issues.append((kind, s + 1, snippet, msg))
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description='中英混排空格检查，输出行级报告')
    ap.add_argument('input', nargs='?', help='输入文件（缺省读 stdin）')
    ap.add_argument('--strict', action='store_true', help='发现问题则退出码为 1')
    args = ap.parse_args()

    try:
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', newline='')
    except Exception:
        pass

    if args.input:
        with open(args.input, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
    else:
        lines = sys.stdin.read().splitlines()

    total = 0
    for i, line in enumerate(lines, 1):
        for kind, col, snippet, msg in lint_line(line):
            total += 1
            print('行 %d 列 %d [%s] %s | ...%s...' % (i, col, kind, msg, snippet))
    print('共发现 %d 处问题，共 %d 行。' % (total, len(lines)))
    if args.strict and total:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
