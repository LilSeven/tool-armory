#!/usr/bin/env python3
r"""相似文件名匹配器 (fuzzy-name-match)。

用途:
    递归扫描目录, 用 difflib.SequenceMatcher 找出文件名高度相似的文件对,
    并专门识别 “xxx 副本.txt” “xxx (1).txt” “xxx - Copy.jpg” 这类复制粘贴
    产生的冗余命名, 帮助定位同一文件被反复复制出来的垃圾副本。
    只读分析, 不改动任何文件。

示例:
    python fuzzy-name-match.py "K:\downloads"
    python fuzzy-name-match.py "K:\downloads" --threshold 0.90
    python fuzzy-name-match.py "K:\downloads" --flat --max-pairs 50

退出码:
    0 = 正常 (无论是否发现候选对); 2 = 参数或目录错误。
"""

import argparse
import os
import re
import sys
from difflib import SequenceMatcher

# 文件名主干以 “(数字)” 结尾 —— 资源管理器连续复制的典型命名
NUM_TAIL_RE = re.compile(r"^(?P<base>.+?)[\s._-]*\(\d+\)$")
# 文件名主干以 copy/副本/备份 等词结尾 (后面可再带编号)
WORD_TAIL_RE = re.compile(
    r"^(?P<base>.+?)[\s._-]*(?:copies|copy|副本|复件|备份|backup|bak)(?:[\s._-]*\(\d+\))?$",
    re.IGNORECASE,
)
# 两两模糊比对的文件数上限 (超过则只做 “副本模式” 匹配, 避免平方级开销)
FUZZY_MAX_FILES = 20000


def _setup_stdio():
    """Windows 下把输出流固定为 UTF-8, 避免中文输出在管道中触发编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def iter_files(root, flat):
    """产出 (显示路径, 所在目录, 文件名)。flat=True 时只扫描顶层。"""
    if flat:
        try:
            with os.scandir(root) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            return
        for e in entries:
            if e.is_file():
                yield os.path.join(root, e.name), root, e.name
    else:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for name in sorted(filenames):
                yield os.path.join(dirpath, name), dirpath, name


def canonical_stem(stem):
    """返回 (去掉副本后缀的主干, 命中的模式名或 None)。"""
    m = NUM_TAIL_RE.match(stem)
    if m:
        return m.group("base").rstrip(" ._-"), "编号副本 (n)"
    m = WORD_TAIL_RE.match(stem)
    if m:
        return m.group("base").rstrip(" ._-"), "copy/副本/备份"
    return stem, None


def build_pairs(files, threshold):
    """返回 [(相似度, 标签, 路径A, 路径B), ...]。"""
    pairs = []
    seen = set()

    # 1) “副本模式”: 同目录内 xxx 副本.ext / xxx (1).ext <-> xxx.ext
    by_dir = {}
    for disp, d, name in files:
        by_dir.setdefault(d, {})[name.lower()] = disp
    for disp, d, name in files:
        stem, ext = os.path.splitext(name)
        base, tag = canonical_stem(stem)
        if not tag:
            continue
        other = by_dir.get(d, {}).get((base + ext).lower())
        if other and other != disp:
            key = frozenset((disp, other))
            if key not in seen:
                seen.add(key)
                ratio = SequenceMatcher(None, name.lower(), (base + ext).lower()).ratio()
                pairs.append((ratio, tag, disp, other))

    # 2) 全局两两模糊相似比对
    if len(files) <= FUZZY_MAX_FILES:
        infos = sorted((disp, name.lower(), len(name)) for disp, _d, name in files)
        n = len(infos)
        for i in range(n):
            disp_i, low_i, len_i = infos[i]
            for j in range(i + 1, n):
                disp_j, low_j, len_j = infos[j]
                if disp_j == disp_i:
                    continue
                # 相似度上界剪枝: ratio = 2*M/T, 而 M <= min(l1, l2)
                if 2.0 * min(len_i, len_j) / (len_i + len_j) < threshold:
                    continue
                key = frozenset((disp_i, disp_j))
                if key in seen:
                    continue
                sm = SequenceMatcher(None, low_i, low_j)
                if sm.quick_ratio() < threshold:
                    continue
                ratio = sm.ratio()
                if ratio >= threshold:
                    seen.add(key)
                    pairs.append((ratio, "相似", disp_i, disp_j))
    else:
        print(f"(文件数超过 {FUZZY_MAX_FILES}, 已跳过两两模糊比对, 仅做副本模式匹配)")

    pairs.sort(key=lambda t: (0 if t[1] != "相似" else 1, -t[0], t[2], t[3]))
    return pairs


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog="fuzzy-name-match",
        description="用 difflib 找出文件名高度相似的文件对, 并识别 “副本 (1)” 类冗余命名。",
    )
    ap.add_argument("directory", metavar="目录", help="要扫描的目录")
    ap.add_argument("--threshold", type=float, default=0.85, help="相似度阈值 0~1 (默认 0.85)")
    ap.add_argument("--flat", action="store_true", help="只扫描顶层目录, 不递归")
    ap.add_argument("--max-pairs", type=int, default=200, help="最多显示的文件对数 (默认 200)")
    args = ap.parse_args(argv)

    if not 0.0 < args.threshold <= 1.0:
        print("错误: --threshold 必须在 (0, 1] 区间", file=sys.stderr)
        return 2
    root = os.path.abspath(args.directory)
    if not os.path.isdir(root):
        print(f"错误: 目录不存在: {root}", file=sys.stderr)
        return 2

    files = list(iter_files(root, args.flat))
    print("== 相似文件名匹配报告 ==")
    print(f"目录: {root}")
    print(f"范围: {'仅顶层' if args.flat else '递归'}  文件数: {len(files)}  阈值: {args.threshold:.2f}")
    if not files:
        print("结果: 目录下没有任何文件。")
        return 0

    pairs = build_pairs(files, args.threshold)
    if not pairs:
        print("结果: 未发现相似命名或 “副本” 式命名的文件对。")
        return 0

    limit = args.max_pairs if args.max_pairs and args.max_pairs > 0 else len(pairs)
    shown = pairs[:limit]
    print(f"结果: 共 {len(pairs)} 对候选 (按相似度降序, 显示 {len(shown)} 对):\n")
    n_pattern = 0
    for ratio, tag, a, b in shown:
        if tag != "相似":
            n_pattern += 1
        print(f"[{ratio:.2f}] ({tag})")
        print(f"    {a}")
        print(f"    {b}")
    tail = f" (其余 {len(pairs) - len(shown)} 对未显示)" if len(shown) < len(pairs) else ""
    print(f"\n小结: 副本式命名 {n_pattern} 对, 普通相似 {len(shown) - n_pattern} 对{tail}。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
