#!/usr/bin/env python3
"""u3000-normalize.py — 全角空格规范化工具。

统一 U+3000 全角空格与连续半角空格的使用：
  - 段首缩进保留：行首的 U+3000/空格缩进串原样保留（--indent-to-full 可把
    行首缩进统一折算为 U+3000，2 个半角 = 1 个全角）
  - 行中转半角：行中部出现的 U+3000 转为 1 个半角空格；默认再把连续
    2 个及以上半角空格折叠为 1 个（--no-collapse 关闭折叠）
  - 行尾删除：行尾的半角/全角空格与 Tab 一律删除（纯空白行清成空行）
  - 换行风格（\r\n / \n / \r）原样保留，CRLF 文件处理后仍是 CRLF
  - --skip-code 时跳过 ``` / ~~~ 围栏代码块内的行

示例命令：
  python u3000-normalize.py -i input.txt -o out.txt
  cat input.txt | python u3000-normalize.py
  python u3000-normalize.py --text "你好　  世界　" 
  python u3000-normalize.py -i doc.md --skip-code

退出码：0 成功；1 读取失败；2 参数错误。
"""
import argparse
import re
import sys

_LEAD_RE = re.compile(r"^[\u3000 \t\u00a0]+")
_STAT_RE = re.compile(r"^(```|~~~)")

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


def normalize_line(line: str, collapse: bool, indent_to_full: bool) -> str:
    m = _LEAD_RE.match(line)
    lead = m.group(0) if m else ""
    middle = line[len(lead):]
    if not middle:
        return ""                      # 纯空白行 -> 空行
    if indent_to_full:
        lead = "\u3000" * (len(lead.replace("\u3000", "")) // 2 + lead.count("\u3000"))
    middle = middle.replace("\u3000", " ").replace("\u00a0", " ")
    if collapse:
        middle = re.sub(" {2,}", " ", middle)
    return lead + middle.rstrip(" \t\u3000\u00a0")


def normalize_text(text: str, collapse: bool, indent_to_full: bool,
                   skip_code: bool) -> tuple[str, int, int]:
    out = []
    changed = 0
    nlines = 0
    in_fence = False
    for line, eol in iter_lines(text):
        nlines += 1
        if skip_code:
            if _STAT_RE.match(line.lstrip()):
                in_fence = not in_fence
            if in_fence:
                out.append(line + eol)
                continue
        new = normalize_line(line, collapse, indent_to_full)
        if new != line:
            changed += 1
        out.append(new + eol)
    return "".join(out), changed, nlines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="统一 U+3000 与连续半角空格：段首缩进保留、行中转半角、行尾删除")
    ap.add_argument("-i", "--input", help="输入文件（缺省读 stdin）")
    ap.add_argument("-o", "--output", help="输出文件（缺省写 stdout）")
    ap.add_argument("--text", help="直接指定待处理文本")
    ap.add_argument("--no-collapse", action="store_true",
                    help="不折叠连续半角空格（默认折叠为 1 个）")
    ap.add_argument("--indent-to-full", action="store_true",
                    help="把行首半角空格缩进折算为 U+3000（2 个半角 = 1 个全角）")
    ap.add_argument("--skip-code", action="store_true",
                    help="跳过 ``` / ~~~ 围栏代码块内的行")
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

    new_text, changed, nlines = normalize_text(
        data, collapse=not args.no_collapse, indent_to_full=args.indent_to_full,
        skip_code=args.skip_code)
    print(f"[u3000-normalize] 处理 {nlines} 行，改动 {changed} 行。",
          file=sys.stderr)

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
