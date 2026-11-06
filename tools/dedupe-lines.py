#!/usr/bin/env python3
"""行去重（dedupe-lines）——去除重复行，保留首次出现；支持忽略大小写与出现次数统计。

功能：
  - 逐行去重，只保留每行首次出现（保持原有顺序）
  - -i/--ignore-case 忽略大小写判重（输出仍为首次出现的原样）
  - --count 输出 "次数<TAB>行" 的统计（按首次出现顺序）
  - 支持从文件或 stdin 读入，输出到 stdout 或 -o 文件；-w 原地写回输入文件

用法示例：
  python dedupe-lines.py input.txt
  python dedupe-lines.py -i input.txt -o unique.txt
  python dedupe-lines.py --count input.txt
  cat input.txt | python dedupe-lines.py

退出码：0 成功；1 输入文件不存在等错误；2 参数错误。
"""
import argparse
import sys

def read_text(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        return f.read()

def write_text(path, text):
    if path == "-":
        out = getattr(sys.stdout, "buffer", None)
        data = text.encode(sys.stdout.encoding or "utf-8", errors="replace")
        if out is not None:
            out.write(data)
            out.flush()
        else:
            sys.stdout.write(text)
    else:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)

def dedupe(text, ignore_case, count_mode):
    # 文件若以 \n 结尾，split 出的最后一个空串是行终止符而非真实行，
    # 先剥离、统计完再补回，避免 --count 多出一行幻影空行。
    trailing_nl = text.endswith("\n")
    lines = text.split("\n")
    if trailing_nl:
        lines.pop()
    seen = {}          # key -> [original_line, count]
    order = []         # key 按首次出现顺序
    for ln in lines:
        key = ln.casefold() if ignore_case else ln
        if key in seen:
            seen[key][1] += 1
        else:
            seen[key] = [ln, 1]
            order.append(key)
    if count_mode:
        out = [f"{seen[k][1]}\t{seen[k][0]}" for k in order]
    else:
        out = [seen[k][0] for k in order]
    result = "\n".join(out) + ("\n" if trailing_nl else "")
    return result, len(lines), len(order)

def main(argv=None):
    p = argparse.ArgumentParser(description="去除重复行保留首次出现，支持忽略大小写、统计每行出现次数")
    p.add_argument("input", nargs="?", default="-", help="输入文件，缺省为 stdin（'-'）")
    p.add_argument("-o", "--output", default="-", help="输出文件，缺省为 stdout（'-'）")
    p.add_argument("-w", "--write-inplace", action="store_true", help="把结果写回输入文件")
    p.add_argument("-i", "--ignore-case", action="store_true", help="忽略大小写判重")
    p.add_argument("--count", action="store_true", help="输出 '次数<TAB>行' 统计而非去重结果")
    args = p.parse_args(argv)

    if args.write_inplace:
        if args.input == "-":
            print("错误: -w 需要指定输入文件", file=sys.stderr)
            return 2
        args.output = args.input
    try:
        text = read_text(args.input)
    except OSError as e:
        print(f"错误: 无法读取 {args.input}: {e}", file=sys.stderr)
        return 1
    result, total, uniq = dedupe(text, args.ignore_case, args.count)
    write_text(args.output, result)
    if args.output != "-":
        print(f"{args.input}: {total} 行 -> {uniq} 行", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
