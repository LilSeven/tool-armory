"""批量行数统计 —— 统计各文本文件的行数、字数、字节数，输出逐文件与汇总表格。

用法:
    python count-lines.py <文件或目录...> [--glob <模式>] [--encoding <编码>] [--sort <字段>]

示例:
    python count-lines.py notes.txt
    python count-lines.py ./src --glob "*.py"
    python count-lines.py ./docs --sort lines

说明:
    - 行数: 按换行符计；字数: 按空白分隔的非空词计；字节数: 文件实际字节数。
    - 末尾输出汇总行（合计）。无法按文本解码的文件会跳过并警告。退出码 0 表示成功。
"""

import argparse
import fnmatch
import os
import sys


def iter_files(targets, pattern):
    seen = set()
    files = []
    for t in targets:
        if os.path.isdir(t):
            for dirpath, _dirnames, filenames in os.walk(t):
                for fn in filenames:
                    if pattern is None or fnmatch.fnmatch(fn, pattern):
                        f = os.path.join(dirpath, fn)
                        if f not in seen:
                            seen.add(f)
                            files.append(f)
        elif os.path.isfile(t):
            if t not in seen:
                seen.add(t)
                files.append(t)
        else:
            print(f"警告: 跳过不存在的路径: {t}", file=sys.stderr)
    return files


def count_file(path, encoding):
    """返回 (行数, 字数, 字节数)；解码失败返回 None。"""
    size = os.path.getsize(path)
    lines = words = 0
    try:
        with open(path, "r", encoding=encoding, newline="") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"跳过 {path}: {e}", file=sys.stderr)
        return None
    if text:
        lines = text.count("\n")
        if not text.endswith("\n"):
            lines += 1
        words = len(text.split())
    return lines, words, size


def fmt_int(n):
    return f"{n:,}"


def main(argv=None):
    p = argparse.ArgumentParser(description="统计文本文件行数/字数/字节数并输出表格")
    p.add_argument("targets", nargs="+", help="文件或目录")
    p.add_argument("--glob", dest="pattern", default=None, help="目录模式下文件名过滤，如 *.txt")
    p.add_argument("--encoding", default="utf-8", help="文本编码（默认 utf-8）")
    p.add_argument("--sort", choices=["name", "lines", "words", "bytes"], default="name",
                   help="排序字段（默认按文件名）")
    args = p.parse_args(argv)

    files = iter_files(args.targets, args.pattern)
    results = []
    for f in files:
        r = count_file(f, args.encoding)
        if r is not None:
            results.append((f, *r))

    if args.sort != "name":
        key_idx = {"lines": 1, "words": 2, "bytes": 3}[args.sort]
        results.sort(key=lambda r: r[key_idx], reverse=True)
    else:
        results.sort(key=lambda r: r[0].lower())

    if not results:
        print("没有可统计的文件。")
        return 0

    width = max(len(r[0]) for r in results)
    width = max(width, len("文件"), len("汇总"))
    header = f"{'文件':<{width}}  {'行数':>10}  {'字数':>10}  {'字节':>12}"
    print(header)
    print("-" * len(header))
    totals = [0, 0, 0]
    for f, lines, words, size in results:
        print(f"{f:<{width}}  {fmt_int(lines):>10}  {fmt_int(words):>10}  {fmt_int(size):>12}")
        totals[0] += lines
        totals[1] += words
        totals[2] += size
    print("-" * len(header))
    print(f"{'汇总 (' + str(len(results)) + ' 个文件)':<{width}}  "
          f"{fmt_int(totals[0]):>10}  {fmt_int(totals[1]):>10}  {fmt_int(totals[2]):>12}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
