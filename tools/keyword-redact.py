#!/usr/bin/env python3
"""关键词打码(keyword-redact)

按词表把文本中的敏感词替换为 ***,支持整体打码或部分保留(首尾留字),
并对全角/大小写变体做归一化,防"ＴＥＳＴ"、"t e s t"之类绕过。

归一化策略:匹配前对文本做 NFKC 折叠 + 小写化来定位命中,再回映射到
原文位置打码;因此全角字母、全角数字、大写/小写都能命中。

用法:
  python keyword-redact.py <输入文件> --words 词1,词2 [-o 输出]
  python keyword-redact.py <输入文件> --words-file words.txt [-o 输出]
  cat in.txt | python keyword-redact.py --words 敏感词

选项:
  --mode whole|partial|head|tail  打码方式: 整体***; 保留首尾各1字;
                                  只保留头部1字; 只保留尾部1字 (默认 whole)
  --mask STR                      替换字符,默认 ***
  --loose                         同时允许词内字符被空白/符号隔开(如 s e c r e t)

示例:
  python keyword-redact.py post.txt --words 公司机密,项目X
  python keyword-redact.py post.txt --words-file terms.txt --mode partial
"""
import argparse
import sys
import unicodedata


def build_norm_map(text):
    """返回 (归一化后的小写文本, 每个归一化字符对应的原文下标列表)。"""
    norm_chars = []
    norm_idx = []
    for i, ch in enumerate(text):
        d = unicodedata.decomposition(ch)
        n = unicodedata.normalize('NFKC', ch).lower()
        for c in n:
            norm_chars.append(c)
            norm_idx.append(i)
    return ''.join(norm_chars), norm_idx


def strip_separators(norm_text):
    """去掉分隔符(空白/标点)便于匹配 's e c r e t' 类绕过,返回保留字符与其在 norm_text 的位置。"""
    kept = []
    for i, c in enumerate(norm_text):
        if c.isspace() or unicodedata.category(c).startswith('P'):
            continue
        kept.append((i, c))
    return ''.join(c for _, c in kept), [i for i, _ in kept]


def make_matcher(words, loose):
    """返回 match_fn(norm_text) -> 需要打码的字符集合。"""
    if loose:
        def matcher(norm_text):
            stripped, pos = strip_separators(norm_text)
            hits = set()
            for w in words:
                needle = unicodedata.normalize('NFKC', w).lower()
                needle = ''.join(c for c in needle
                                 if not c.isspace() and not unicodedata.category(c).startswith('P'))
                if not needle:
                    continue
                start = 0
                while True:
                    idx = stripped.find(needle, start)
                    if idx < 0:
                        break
                    for p in pos[idx:idx + len(needle)]:
                        hits.add(p)
                    start = idx + 1
            return hits
    else:
        def matcher(norm_text):
            hits = set()
            for w in words:
                needle = unicodedata.normalize('NFKC', w).lower()
                if not needle:
                    continue
                start = 0
                while True:
                    idx = norm_text.find(needle, start)
                    if idx < 0:
                        break
                    hits.update(range(idx, idx + len(needle)))
                    start = idx + len(needle)
            return hits
    return matcher


def redact_text(text, words, mode, mask, loose):
    norm_text, norm_idx = build_norm_map(text)
    hits = make_matcher(words, loose)(norm_text)
    # 命中的归一化位置 -> 原文下标
    hit_orig = {norm_idx[i] for i in hits if i < len(norm_idx)}
    out = []
    for i, ch in enumerate(text):
        if i not in hit_orig:
            out.append(ch)
            continue
        if mode == 'whole':
            out.append(mask)
        elif mode == 'head':
            out.append(ch)
        elif mode == 'tail':
            out.append(ch)
        elif mode == 'partial':
            out.append(ch)
    s = ''.join(out)
    if mode == 'head':
        # 保留首字,其余打码: 对每个命中区间单独处理
        s = _apply_head_tail(text, hit_orig, mask, 1, 0, loose)
    elif mode == 'tail':
        s = _apply_head_tail(text, hit_orig, mask, 0, 1, loose)
    elif mode == 'partial':
        s = _apply_head_tail(text, hit_orig, mask, 1, 1, loose)
    return s


def _is_separator(ch):
    return ch.isspace() or unicodedata.category(ch).startswith('P')


def _apply_head_tail(text, hit_orig, mask, keep_head, keep_tail, loose=False):
    """把命中下标聚成连续区间,区间内保留前 keep_head 与后 keep_tail 个字符。

    loose=True 时,命中之间只隔空白/标点的相邻段合并为同一段
    (处理 's e c r e t' 这类分隔绕过)。"""
    if not hit_orig:
        return text
    idxs = sorted(hit_orig)
    out = list(text)
    segs = []
    seg = [idxs[0]]
    for i in idxs[1:]:
        if i == seg[-1] + 1 or (loose and all(_is_separator(c) for c in text[seg[-1] + 1:i])):
            seg.append(i)
        else:
            segs.append(seg)
            seg = [i]
    segs.append(seg)
    for seg in segs:
        n = len(seg)
        for pos, i in enumerate(seg):
            if keep_head and pos < keep_head:
                continue
            if keep_tail and pos >= n - keep_tail:
                continue
            out[i] = mask
    return ''.join(out)


def main(argv=None):
    # Windows 管道下 stdin 默认用本地 ANSI 代码页(如 GBK),显式按 UTF-8 读入
    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description='按词表把文本中的敏感词打码,支持全角归一化')
    ap.add_argument('input', nargs='?', help='输入文件;缺省或 - 读 stdin')
    ap.add_argument('--words', default='', help='逗号分隔的敏感词表')
    ap.add_argument('--words-file', help='每行一个敏感词的文件')
    ap.add_argument('--mode', choices=['whole', 'partial', 'head', 'tail'],
                    default='whole', help='打码方式 (默认 whole)')
    ap.add_argument('--mask', default='***', help='替换文本 (默认 ***)')
    ap.add_argument('--loose', action='store_true', help='允许词中字符被空白/标点隔开')
    ap.add_argument('-o', '--output', help='输出文件;默认 stdout')
    args = ap.parse_args(argv)

    words = [w for w in args.words.split(',') if w]
    if args.words_file:
        with open(args.words_file, encoding='utf-8-sig') as f:
            words += [ln.strip() for ln in f if ln.strip()]
    if not words:
        print('错误: 未提供敏感词 (--words 或 --words-file)', file=sys.stderr)
        return 2

    if args.input and args.input != '-':
        with open(args.input, encoding='utf-8-sig') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = redact_text(text, words, args.mode, args.mask, args.loose)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f'已写入 {args.output}')
    else:
        sys.stdout.write(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
