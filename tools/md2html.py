#!/usr/bin/env python3
r"""Markdown 转 HTML — 轻量 Markdown 到 HTML 的转换器。

支持：标题 (#~######)、无序/有序列表（含嵌套缩进）、表格（| 分隔）、
围栏代码块（```）、行内样式（粗体 **x**、斜体 *x*、行内代码 `x`、链接
[text](url)）、水平线 (---) 与普通段落。只使用 Python 标准库。

用法:
    python md2html.py input.md                # 输出到 stdout
    python md2html.py input.md -o out.html    # 输出到文件
    python md2html.py -e "# 标题\n- 项目"     # 内联 Markdown（\n 解释为换行）

示例:
    $ python md2html.py -e "# Hi\n- **a** item"
    <h1>Hi</h1>
    <ul><li><strong>a</strong> item</li></ul>

注: -e 内联字符串中的 \n、\t、\r 会被解释为换行/制表/回车，\\ 表示字面反斜杠；
    文件输入不做任何转义解释。
"""

import argparse
import html
import re
import sys


def unescape_inline(text):
    r"""解释 -e 内联字符串中的转义：\n→换行、\t→制表、\r→回车、\\→反斜杠。"""
    mapping = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\"}
    out = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] in mapping:
            out.append(mapping[text[i + 1]])
            i += 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def inline(text):
    """转换行内样式：代码 > 转义 > 粗体/斜体/链接。"""
    # 先抽出行内代码占位，避免其中内容被再次处理
    codes = []

    def stash(m):
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\s][^*]*)\*(?!\*)", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def table_to_html(header_cells, align, rows):
    """header_cells/rows 已是单元格文本列表；align 是 'left/center/right/None' 列表。"""
    style = {"left": ' style="text-align:left"', "center": ' style="text-align:center"',
             "right": ' style="text-align:right"'}

    def tr(cells, tag):
        tds = "".join(f"<{tag}{style.get(a, '')}>{inline(c.strip())}</{tag}>"
                      for c, a in zip(cells, align))
        return f"<tr>{tds}</tr>"

    head = "<thead>" + tr(header_cells, "th") + "</thead>"
    body = "<tbody>" + "".join(tr(r, "td") for r in rows) + "</tbody>"
    return f"<table>{head}{body}</table>"


def split_row(line):
    """把 '| a | b |' 拆成 ['a', 'b']，容忍首尾竖线缺失。"""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c for c in line.split("|")]


def md_to_html(md_text):
    """把 Markdown 文本转换为 HTML 片段（各块级元素以换行连接）。"""
    out = []
    lines = md_text.splitlines()
    i, n = 0, len(lines)
    para = []

    def flush_para():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 围栏代码块
        if stripped.startswith("```"):
            flush_para()
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过结束 ```
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            code = html.escape("\n".join(code_lines))
            out.append(f"<pre><code{cls}>{code}</code></pre>")
            continue

        # 空行结束段落
        if not stripped:
            flush_para()
            i += 1
            continue

        # 水平线
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            flush_para()
            out.append("<hr>")
            i += 1
            continue

        # 标题
        m = re.match(r"(#{1,6})\s+(.*)", stripped)
        if m:
            flush_para()
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2).strip())}</h{level}>")
            i += 1
            continue

        # 表格：当前行含 | 且下一行是分隔行 |---|---|
        if "|" in stripped and i + 1 < n and re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", lines[i + 1]) \
                and "-" in lines[i + 1]:
            header = split_row(stripped)
            align = []
            for c in split_row(lines[i + 1]):
                c = c.strip()
                if c.startswith(":") and c.endswith(":"):
                    align.append("center")
                elif c.endswith(":"):
                    align.append("right")
                elif c.startswith(":"):
                    align.append("left")
                else:
                    align.append(None)
            rows = []
            i += 2
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(split_row(lines[i]))
                i += 1
            flush_para()
            out.append(table_to_html(header, align, rows))
            continue

        # 列表（无序 */-/+，有序 1. / 1)），支持一层缩进嵌套
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)", line)
        if m:
            flush_para()
            ordered = m.group(2)[0].isdigit()
            base_indent = len(m.group(1))
            items = []  # (indent, text)
            while i < n:
                lm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)", lines[i])
                if lm:
                    items.append((len(lm.group(1)), lm.group(3)))
                    i += 1
                elif lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) > base_indent:
                    # 续行归属最后一个列表项
                    items[-1] = (items[-1][0], items[-1][1] + " " + lines[i].strip())
                    i += 1
                else:
                    break
            tag = "ol" if ordered else "ul"
            inner = "".join(f"<li>{inline(t)}</li>" for _, t in items)
            out.append(f"<{tag}>{inner}</{tag}>")
            continue

        # 普通段落
        para.append(stripped)
        i += 1

    flush_para()
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="轻量 Markdown 到 HTML 转换（标题/列表/表格/代码块/行内样式）")
    parser.add_argument("input", nargs="?", help="输入 Markdown 文件路径")
    parser.add_argument("-e", "--expr", help="内联 Markdown 字符串（\\n 解释为换行，与 input 二选一）")
    parser.add_argument("-o", "--output", help="输出 HTML 文件路径（缺省打印到 stdout）")
    args = parser.parse_args(argv)

    if bool(args.input) == bool(args.expr):
        parser.error("必须且只能提供 input 文件或 -e 内联字符串之一")

    if args.expr:
        md_text = unescape_inline(args.expr)
    else:
        try:
            with open(args.input, "r", encoding="utf-8") as fh:
                md_text = fh.read()
        except OSError as exc:
            print(f"错误: 读取文件失败: {exc}", file=sys.stderr)
            return 1

    result = md_to_html(md_text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(result + "\n")
        print(f"已写入 {args.output}")
    else:
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
