#!/usr/bin/env python3
"""indent-normalize.py — 中文段首缩进规范工具。

为每个段落统一添加或移除两个全角空格（U+3000 U+3000）的中文段首缩进：
  - --add    （默认）段落首行缩进统一为恰好两个全角空格：
             原本无缩进则补上；已有 1-3 个半角空格或若干全角空格等
             不规范缩进则归一为两个全角空格
  - --remove 移除段落首行的段首缩进（半角/全角空格与 Tab 一律去掉）

自动跳过（不参与缩进，也不打断段落边界判断的语义）：
  Markdown 标题 #、列表项 - * + 1. 1)、引用 >、表格 |、水平线、
  ``` / ~~~ 围栏代码块、以 4 个半角空格或 Tab 起始的缩进代码块。
段落以空行分隔；段落内非首行（续行）不做任何改动。
换行风格（\r\n / \n / \r）原样保留；空行按去除行尾 \r 后判断，
因此 CRLF 文件的空行同样正确视为段落边界，不会被误加缩进。

示例命令：
  python indent-normalize.py --add -i input.md -o out.md
  python indent-normalize.py --remove -i input.md
  cat input.md | python indent-normalize.py --add

退出码：0 成功；1 读取失败；2 参数错误。
"""
import argparse
import re
import sys

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_SKIP_RE = re.compile(
    r"^\s*(?:#{1,6}\s"                    # 标题
    r"|[-*+]\s"                           # 无序列表
    r"|\d+[.)]\s"                         # 有序列表
    r"|>"                                 # 引用
    r"|\|"                                # 表格
    r"|([-*_])[ \t]*\1[ \t]*\1[\s\1]*$)")  # 水平线
_CODE_RE = re.compile(r"^(?: {4,}|\t)\S")
_LEAD_RE = re.compile(r"^[\u3000 \t]+")

_LINE_RE = re.compile(r"([^\r\n]*)(\r\n|\r|\n)?")


def iter_lines(text: str):
    """按 \\r\\n、\\r、\\n 切行，逐行 yield (行体, 行尾符)。

    行尾符原样保留（不把 U+2028 等其它字符当换行），因此处理行体时
    不会碰到残留的 \\r——这正是 newline="" 读入下 CRLF 文件的坑。
    """
    pos, n = 0, len(text)
    while pos < n:
        m = _LINE_RE.match(text, pos)
        yield m.group(1), m.group(2) or ""
        pos = m.end()


def _is_blank(line: str) -> bool:
    return line.strip(" \t\u3000\u00a0") == ""


def normalize_text(text: str, add: bool) -> tuple[str, int]:
    out = []
    changed = 0
    in_fence = False
    in_code = False
    pending = True                      # 下一个正文行是段落首行
    for line, eol in iter_lines(text):
        if _is_blank(line):
            in_code = False
            pending = True
            out.append(line + eol)
            continue
        if in_fence:
            out.append(line + eol)
            if _FENCE_RE.match(line):
                in_fence = False
                pending = True
            continue
        if _FENCE_RE.match(line):
            in_fence = True
            out.append(line + eol)
            continue
        if in_code or _CODE_RE.match(line):
            in_code = True              # 缩进代码块持续到空行
            out.append(line + eol)
            continue
        if _SKIP_RE.match(line):
            pending = True              # 跳过结构后开启新段落
            out.append(line + eol)
            continue
        if not pending:                 # 段内续行不动
            out.append(line + eol)
            continue
        pending = False
        m = _LEAD_RE.match(line)
        lead = m.group(0) if m else ""
        body = line[len(lead):]
        if add:
            new = "\u3000\u3000" + body
        else:
            new = body
        if new != line:
            changed += 1
        out.append(new + eol)
    return "".join(out), changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="为每段统一添加或移除两个全角空格的中文段首缩进（跳过列表/标题/代码）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--add", action="store_true", default=True,
                   help="添加缩进：段落首行统一为两个全角空格（默认）")
    g.add_argument("--remove", action="store_true",
                   help="移除段落首行缩进")
    ap.add_argument("-i", "--input", help="输入文件（缺省读 stdin）")
    ap.add_argument("-o", "--output", help="输出文件（缺省写 stdout）")
    ap.add_argument("--text", help="直接指定待处理文本")
    ap.add_argument("--encoding", default="utf-8", help="输入/输出编码（缺省 utf-8）")
    args = ap.parse_args(argv)

    try:
        if args.text is not None:
            data = args.text
        elif args.input:
            with open(args.input, "r", encoding=args.encoding, errors="replace",
                      newline="") as f:
                data = f.read()
        else:
            try:
                sys.stdin.reconfigure(encoding=args.encoding, errors="replace",
                                      newline="")
            except Exception:
                pass
            data = sys.stdin.read()
    except OSError as e:
        print(f"错误: 读取失败: {e}", file=sys.stderr)
        return 1

    new_text, changed = normalize_text(data, add=not args.remove)
    print(f"[indent-normalize] 模式={'add' if not args.remove else 'remove'}，"
          f"改动 {changed} 个段落首行。", file=sys.stderr)

    try:
        if args.output:
            with open(args.output, "w", encoding=args.encoding, newline="") as f:
                f.write(new_text)
        else:
            sys.stdout.write(new_text)
    except OSError as e:
        print(f"错误: 写出失败: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
