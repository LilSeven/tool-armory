#!/usr/bin/env python3
"""空行压缩（blank-squeeze）——把连续多个空行压缩为指定数量，或删除全部空行。

功能：
  - 默认把连续 2 个及以上的空行压缩为 1 个空行（--max N 指定保留数）
  - --remove-all 删除全部空行
  - 支持从文件或 stdin 读入，输出到 stdout 或 -o 文件；-w 原地写回输入文件
  - 含空格/制表符的"伪空行"也视为空行

用法示例：
  python blank-squeeze.py input.txt
  python blank-squeeze.py --max 2 input.txt -o out.txt
  python blank-squeeze.py --remove-all input.txt -w
  cat input.txt | python blank-squeeze.py

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

def squeeze(text, max_keep, remove_all):
    # 以 \n 逻辑行处理；文件若以 \n 结尾，最后一个空串是行终止符而非空行，
    # 先剥离、处理完再补回，避免输出丢失结尾换行。
    trailing_nl = text.endswith("\n")
    lines = text.split("\n")
    if trailing_nl:
        lines.pop()
    out = []
    blank_run = 0
    for ln in lines:
        is_blank = (ln.strip() == "")
        if is_blank:
            blank_run += 1
            if remove_all:
                continue
            if blank_run <= max_keep:
                out.append(ln)
        else:
            blank_run = 0
            out.append(ln)
    return "\n".join(out) + ("\n" if trailing_nl else "")

def main(argv=None):
    p = argparse.ArgumentParser(description="把连续多个空行压缩为指定数量，或删除全部空行")
    p.add_argument("input", nargs="?", default="-", help="输入文件，缺省为 stdin（'-'）")
    p.add_argument("-o", "--output", default="-", help="输出文件，缺省为 stdout（'-'）")
    p.add_argument("-w", "--write-inplace", action="store_true", help="把结果写回输入文件")
    p.add_argument("--max", type=int, default=1, help="连续空行最多保留的数量（默认 1）")
    p.add_argument("--remove-all", action="store_true", help="删除全部空行（优先于 --max）")
    args = p.parse_args(argv)

    if not args.remove_all and args.max < 0:
        print("错误: --max 必须 >= 0", file=sys.stderr)
        return 2
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
    write_text(args.output, squeeze(text, args.max, args.remove_all))
    return 0

if __name__ == "__main__":
    sys.exit(main())
