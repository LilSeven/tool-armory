#!/usr/bin/env python3
"""空白规范化（ws-normalize）——把文本做可配置的空白规范化后输出。

功能：
  - 折叠连续空白（空格/制表符串）为单个空格（--no-collapse 关闭）
  - 清理行首、行尾空白（--no-strip 关闭）
  - 制表符统一：--tabs space(默认,当作单空格参与折叠) / expand(按 --tab-width 展开) / keep(保留)
  - 支持从文件或 stdin 读入，输出到 stdout 或 -o 指定文件；-w 原地写回输入文件

用法示例：
  python ws-normalize.py input.txt
  python ws-normalize.py input.txt -o clean.txt
  python ws-normalize.py --tabs expand --tab-width 4 input.txt -w
  cat input.txt | python ws-normalize.py

退出码：0 成功；1 输入文件不存在等错误；2 参数错误。
"""
import argparse
import sys

def build_argparser():
    p = argparse.ArgumentParser(description="把连续空白折叠为单空格、清理行首尾空白、统一制表符")
    p.add_argument("input", nargs="?", default="-", help="输入文件，缺省为 stdin（'-'）")
    p.add_argument("-o", "--output", default="-", help="输出文件，缺省为 stdout（'-'）")
    p.add_argument("-w", "--write-inplace", action="store_true", help="把结果写回输入文件")
    p.add_argument("--tabs", choices=("space", "expand", "keep"), default="space",
                   help="制表符处理：space=当作单空格；expand=按宽度展开；keep=保留（默认 space）")
    p.add_argument("--tab-width", type=int, default=4, help="--tabs expand 时的制表位宽度（默认 4）")
    p.add_argument("--no-collapse", action="store_true", help="不折叠行内连续空白")
    p.add_argument("--no-strip", action="store_true", help="不清理行首尾空白")
    return p

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

def normalize_line(line, args):
    # 行内容不含换行符
    if args.tabs == "expand":
        line = line.expandtabs(args.tab_width)
    elif args.tabs == "space":
        line = line.replace("\t", " ")
    if not args.no_collapse:
        parts = line.split()  # 按任意空白切分再重组，天然折叠
        line = " ".join(parts)
    if not args.no_strip:
        line = line.strip(" \t\x0b\x0c\r")
    return line

def main(argv=None):
    args = build_argparser().parse_args(argv)
    if args.write_inplace:
        if args.input == "-":
            print("错误: -w 需要指定输入文件", file=sys.stderr)
            return 2
        args.output = args.input
    if args.tabs == "expand" and args.tab_width < 1:
        print("错误: --tab-width 必须 >= 1", file=sys.stderr)
        return 2
    try:
        text = read_text(args.input)
    except OSError as e:
        print(f"错误: 无法读取 {args.input}: {e}", file=sys.stderr)
        return 1
    lines = text.split("\n")
    out_lines = [normalize_line(ln, args) for ln in lines]
    write_text(args.output, "\n".join(out_lines))
    return 0

if __name__ == "__main__":
    sys.exit(main())
