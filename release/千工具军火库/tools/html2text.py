#!/usr/bin/env python3
"""HTML 提纯文本 — 剥离 HTML 标签还原可读纯文本。

用标准库 html.parser 逐标签处理：块级标签（p/div/标题/表格等）后换行，
列表项（li）按嵌套层级缩进，<br> 换行，script/style 内容整个丢弃，
实体（&amp; 等）自动解码。只使用 Python 标准库。

用法:
    python html2text.py input.html                 # 输出到 stdout
    python html2text.py input.html -o out.txt      # 输出到文件
    python html2text.py -e "<p>hi &amp; bye</p>"   # 直接转换内联 HTML

示例:
    $ python html2text.py -e "<ul><li>a</li><li>b</li></ul>"
    - a
    - b
"""

import argparse
import sys
from html.parser import HTMLParser

# 产生换行的块级标签
BLOCK_TAGS = {
    "p", "div", "section", "article", "header", "footer", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "ul", "ol", "dl",
    "pre", "hr", "li", "dd", "dt", "figcaption", "figure", "br",
}
# li/dt/dd 之后的内容需要缩进
INDENT_TAGS = {"li", "dd", "dt"}
# 列表项前缀
LIST_PREFIX = {"li": "- ", "dd": "  ", "dt": ""}


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []
        self.skip_depth = 0  # 位于 script/style 内的深度
        self.list_depth = 0  # ul/ol 嵌套层级
        self._line_open = False  # 当前行是否已有内容

    # -- 工具 --
    def _newline(self):
        if self.chunks and not (self.chunks and self.chunks[-1].endswith("\n")):
            self.chunks.append("\n")
        elif not self.chunks:
            return

    def _ensure_sep(self, space=" "):
        """行内标签之间保证一个分隔（空格），但不产生连续空格。"""
        if self.chunks and self.chunks[-1] and not self.chunks[-1].endswith(("\n", " ")):
            self.chunks.append(space)

    # -- 解析回调 --
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in ("ul", "ol"):
            self.list_depth += 1
            self._newline()
        elif tag in LIST_PREFIX:
            self._newline()
            self.chunks.append("  " * max(self.list_depth - 1, 0) + LIST_PREFIX[tag])
            self._line_open = True
        elif tag == "br":
            self._newline()
        elif tag in BLOCK_TAGS:
            self._ensure_sep()
            self._newline()

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip_depth = max(self.skip_depth - 1, 0)
            return
        if self.skip_depth:
            return
        if tag in ("ul", "ol"):
            self.list_depth = max(self.list_depth - 1, 0)
            self._newline()
        elif tag in BLOCK_TAGS:
            self._newline()

    def handle_data(self, data):
        if self.skip_depth:
            return
        text = data
        if text.strip():
            self.chunks.append(text if self._line_open else text.lstrip())
            self._line_open = True
        elif self.chunks and text:
            # 标签间空白折叠为单个空格
            self._ensure_sep()

    def handle_entityref(self, name):  # convert_charrefs=True 时基本不走这里，保险起见
        if not self.skip_depth:
            self.chunks.append(f"&{name};")

    def get_text(self):
        text = "".join(self.chunks)
        # 折叠行内多余空格、压缩 3 个以上连续换行为 2 个
        lines = [line.rstrip() for line in text.splitlines()]
        cleaned, blank = [], 0
        for line in lines:
            if line.strip():
                cleaned.append(line)
                blank = 0
            elif cleaned and blank == 0:
                cleaned.append("")
                blank = 1
        while cleaned and not cleaned[-1]:
            cleaned.pop()
        return "\n".join(cleaned)


def html_to_text(html_source):
    parser = TextExtractor()
    parser.feed(html_source)
    parser.close()
    return parser.get_text()


def main(argv=None):
    parser = argparse.ArgumentParser(description="剥离 HTML 标签还原可读纯文本（保留列表缩进与段落换行）")
    parser.add_argument("input", nargs="?", help="输入 HTML 文件路径")
    parser.add_argument("-e", "--expr", help="内联 HTML 字符串（与 input 二选一）")
    parser.add_argument("-o", "--output", help="输出文本文件路径（缺省打印到 stdout）")
    args = parser.parse_args(argv)

    if bool(args.input) == bool(args.expr):
        parser.error("必须且只能提供 input 文件或 -e 内联字符串之一")

    if args.expr:
        html_source = args.expr
    else:
        try:
            with open(args.input, "r", encoding="utf-8") as fh:
                html_source = fh.read()
        except OSError as exc:
            print(f"错误: 读取文件失败: {exc}", file=sys.stderr)
            return 1

    result = html_to_text(html_source)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(result + "\n")
        print(f"已写入 {args.output}")
    else:
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
