#!/usr/bin/env python3
"""JSON 格式化与压缩。

- 默认美化输出：--indent 指定缩进（默认 2），--sort-keys 按键排序
- --minify 输出无空白的单行 JSON
- --check 仅校验不输出；语法错误时报告 行:列 与错误原因，退出码 1

用法:
    python json-format.py input.json [--indent 2] [--sort-keys] [--minify] [--check]
    cat data.json | python json-format.py - [--minify]

示例:
    python json-format.py config.json --indent 4 --sort-keys -o pretty.json
    python json-format.py data.json --check
"""
import argparse
import json
import sys


def find_error_position(text):
    """用原始扫描定位 JSONDecodeError 的真实 行:列（若缺失则自行计算）。"""
    try:
        json.loads(text)
        return None
    except json.JSONDecodeError as e:
        lineno, colno = e.lineno, e.colno
        if lineno is None or colno is None:
            upto = text[: e.pos] if e.pos is not None else text
            lineno = upto.count("\n") + 1
            colno = len(upto.rsplit("\n", 1)[-1]) + 1
        line = text.split("\n")[lineno - 1] if lineno - 1 < len(text.split("\n")) else ""
        pointer = " " * (colno - 1) + "^"
        return {
            "msg": e.msg,
            "lineno": lineno,
            "colno": colno,
            "line_text": line[:200],
            "pointer": pointer[:200],
        }


def main():
    ap = argparse.ArgumentParser(description="JSON 美化/最小化/校验")
    ap.add_argument("input", help="输入 JSON 文件；'-' 表示从 stdin 读")
    ap.add_argument("-o", "--output", default=None, help="输出文件（默认打印到 stdout）")
    ap.add_argument("--indent", type=int, default=2, help="美化缩进空格数（默认 2）")
    ap.add_argument("--sort-keys", action="store_true", help="按键排序")
    ap.add_argument("--minify", action="store_true", help="最小化为单行")
    ap.add_argument("--check", action="store_true", help="仅校验，不输出格式化结果")
    ap.add_argument("--ensure-ascii", action="store_true", help="非 ASCII 字符转义（默认原样输出）")
    args = ap.parse_args()

    if args.input == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(args.input, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"错误: 无法读取 {args.input}: {e}", file=sys.stderr)
            return 2

    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        err = find_error_position(text)
        if err:
            print(f"语法错误（{err['msg']}）位于 行 {err['lineno']}, 列 {err['colno']}:",
                  file=sys.stderr)
            print(f"  {err['line_text']}", file=sys.stderr)
            print(f"  {err['pointer']}", file=sys.stderr)
        else:
            print("语法错误", file=sys.stderr)
        return 1

    if args.check:
        print("JSON 有效。")
        return 0

    if args.minify:
        out = json.dumps(obj, ensure_ascii=args.ensure_ascii,
                         separators=(",", ":"), sort_keys=args.sort_keys)
    else:
        if args.indent < 0:
            print("错误: --indent 不能为负", file=sys.stderr)
            return 2
        out = json.dumps(obj, ensure_ascii=args.ensure_ascii,
                         indent=args.indent, sort_keys=args.sort_keys)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out + "\n")
        print(f"已写入 {args.output}")
    else:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
