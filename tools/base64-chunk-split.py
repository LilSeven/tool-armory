"""Base64 分块美化 —— 把长 Base64 串按定长分块、加引号或反斜杠续行, 便于粘贴进代码。

用途:
    读入一段可能非常长的 Base64(字符串/文件/stdin), 去掉原有空白后按固定宽度
    切成若干块, 每行一块; 可按目标语言加修饰:
      plain      每行裸块
      quote      每行 "块"   —— C/JS 相邻字符串字面量, 拼接即原文
      comma      每行 "块",  —— JS 数组 / Python 列表元素
      backslash  每行块尾加 \ —— shell / Python 反斜杠续行(最后一行不加)
    输入若含 Base64 字符集之外的字符, 会照常切块但在 stderr 给出警告。

示例命令:
    python base64-chunk-split.py --string "SGVsbG8sIHdvcmxkIQ==" --width 8 --style comma
    python base64-chunk-split.py long.b64 --style quote --indent 4
    cat long.b64 | python base64-chunk-split.py --width 64 --style backslash

退出码: 0 成功; 1 输入读取失败; 2 参数错误。

仅依赖 Python 标准库。
"""

import argparse
import pathlib
import string
import sys

STYLES = ("plain", "quote", "comma", "backslash")
B64_CHARS = set(string.ascii_letters + string.digits + "+/=")


def read_text(args):
    if args.string is not None:
        return args.string
    path = args.in_file or args.file
    if path:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    if sys.stdin.isatty():
        raise ValueError("没有输入: 请用 --string、--in/位置参数文件或 stdin 提供内容")
    return sys.stdin.read()


def prettify(text, width, style, indent):
    """返回 (结果文本, 非法字符集合, 总字符数, 块数)。"""
    compact = "".join(text.split())
    illegal = sorted({c for c in compact if c not in B64_CHARS})
    if not compact:
        return "", illegal, 0, 0
    chunks = [compact[i:i + width] for i in range(0, len(compact), width)]
    lines = []
    for idx, chunk in enumerate(chunks):
        body = chunk.replace("\\", "\\\\").replace('"', '\\"')
        if style == "quote":
            piece = '"%s"' % body
        elif style == "comma":
            piece = '"%s",' % body
        elif style == "backslash":
            piece = body + ("" if idx == len(chunks) - 1 else "\\")
        else:
            piece = body
        lines.append(indent + piece)
    return "\n".join(lines), illegal, len(compact), len(chunks)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="把长 Base64 按定长分块并加引号/续行符, 便于粘贴进代码")
    parser.add_argument("file", nargs="?", help="包含 Base64 的文本文件(省略则读 stdin)")
    parser.add_argument("--in", dest="in_file", help="输入文件路径(优先于位置参数)")
    parser.add_argument("--string", help="直接传入 Base64 字符串")
    parser.add_argument("--width", type=int, default=76, help="每块字符数(默认 76)")
    parser.add_argument("--style", choices=STYLES, default="plain",
                        help="行修饰风格(默认 plain)")
    parser.add_argument("--indent", type=int, default=0, help="每行缩进空格数(默认 0)")
    parser.add_argument("--out", help="结果写入文件(默认打印到 stdout)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if args.width < 1 or args.indent < 0:
        parser.error("--width 必须 >= 1 且 --indent 必须 >= 0")

    try:
        text = read_text(args)
    except Exception as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1

    result, illegal, total, nchunks = prettify(
        text, args.width, args.style, " " * args.indent)
    if illegal:
        shown = "".join(illegal[:8])
        print("警告: 输入含 %d 个 Base64 字符集之外的字符(%s%s), 已按原样切块"
              % (len(illegal), shown, "..." if len(illegal) > 8 else ""), file=sys.stderr)
    if args.out:
        pathlib.Path(args.out).write_text(result + "\n", encoding="utf-8")
        print("已写入 %s" % args.out, file=sys.stderr)
    else:
        print(result)
    print("# 共 %d 字符 → %d 块(每块 <= %d), 风格 %s"
          % (total, nchunks, args.width, args.style), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
