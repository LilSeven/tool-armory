#!/usr/bin/env python3
"""HTML 转纯文本。

剥离 HTML 标签输出纯文本：
- <h1>-<h6> 标题加 # 前缀并空行分隔
- <ul>/<ol>/<li> 保留缩进与编号
- 块级元素换行
- <a href> 与 <img src> 的 URL 收集后统一附注在文末（正文中用 [n] 标注）

用法:
    python html-to-text.py input.html [-o output.txt] [--width 80]

示例:
    python html-to-text.py page.html -o page.txt
"""
import argparse
import os
import re
import sys
from html.parser import HTMLParser

BLOCK_TAGS = {
    "p", "div", "section", "article", "header", "footer", "main", "nav",
    "blockquote", "pre", "br", "hr", "table", "tr", "figure", "figcaption",
    "address", "dl", "dt", "dd", "form",
}
HEADING_TAGS = {f"h{i}" for i in range(1, 7)}
LIST_TAGS = {"ul", "ol"}


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines = []          # 输出文本行
        self._buf = []           # 当前行的字符缓冲
        self.links = []          # [(href, text)]
        self._link_stack = []    # 记录链接文本起始 index
        self._list_stack = []    # [("ul"|"ol", 计数器)]
        self._skip = 0           # script/style 深度
        self._pre = 0

    # ---- 缓冲辅助 ----
    def _flush(self, hard=False):
        text = "".join(self._buf)
        if hard or text.strip():
            self.lines.append(text.rstrip())
        self._buf = []

    def _ensure_blank_line(self):
        if self.lines and self.lines[-1].strip() or self._buf and "".join(self._buf).strip():
            if self._buf and "".join(self._buf).strip():
                self._flush(hard=True)
            if not self.lines or self.lines[-1].strip():
                self.lines.append("")

    def _drop_leading_ws(self):
        """追加行首标记（#/序号/>）前，丢弃缓冲里仅剩的空白。"""
        if self._buf and "".join(self._buf).strip() == "":
            self._buf = []

    def _emit(self, text):
        if self._skip:
            return
        self._buf.append(text)

    # ---- 标签处理 ----
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
            return
        if self._skip:
            return
        a = dict(attrs)
        if tag == "pre":
            self._pre += 1
            self._ensure_blank_line()
        elif tag == "br":
            self._flush(hard=True)
        elif tag in HEADING_TAGS:
            self._flush()
            self._drop_leading_ws()
            self._ensure_blank_line()
            level = int(tag[1])
            self._buf.append("#" * level + " ")
        elif tag == "hr":
            self._ensure_blank_line()
            self._buf.append("-" * 40)
        elif tag == "li":
            self._drop_leading_ws()
            indent = "  " * (len(self._list_stack) - 1) if self._list_stack else ""
            marker = "• "
            if self._list_stack and self._list_stack[-1][0] == "ol":
                marker = f"{self._list_stack[-1][1]}. "
                self._list_stack[-1][1] += 1
            self._flush()
            self._buf.append(indent + marker)
        elif tag in LIST_TAGS:
            self._list_stack.append([tag, 1])
            self._ensure_blank_line()
        elif tag == "blockquote":
            self._flush()
            self._drop_leading_ws()
            self._buf.append("> ")
        elif tag in BLOCK_TAGS:
            self._flush()
        elif tag == "a":
            href = a.get("href", "").strip()
            self._link_stack.append((len(self.links), "".join(self._buf)))
            if href:
                self.links.append(href)
        elif tag == "img":
            src = a.get("src", "").strip()
            alt = a.get("alt", "").strip()
            if src:
                self._emit(f"[图:{alt}] [{len(self.links) + 1}]")
                self.links.append(src)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            if self._skip:
                self._skip -= 1
            return
        if self._skip:
            return
        if tag == "pre":
            self._pre = max(self._pre - 1, 0)
            self._flush(hard=True)
        elif tag in HEADING_TAGS:
            self._flush()
            self._ensure_blank_line()
        elif tag in LIST_TAGS:
            if self._list_stack:
                self._list_stack.pop()
            self._flush()
            self._ensure_blank_line()
        elif tag == "li":
            self._flush()
        elif tag == "a":
            if self._link_stack:
                idx, _ = self._link_stack.pop()
                if idx < len(self.links):
                    self._emit(f" [{idx + 1}]")
        elif tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        if self._pre:
            self._buf.append(data)
        else:
            self._buf.append(re.sub(r"\s+", " ", data))

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self._flush(hard=True)
        elif tag == "img":
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def get_text(self):
        self._flush(hard=True)
        # 压缩 3 个以上连续空行
        out, blanks = [], 0
        for ln in self.lines:
            if ln.strip():
                out.append(ln)
                blanks = 0
            else:
                blanks += 1
                if blanks <= 1:
                    out.append("")
        while out and not out[-1].strip():
            out.pop()
        text = "\n".join(out).rstrip()
        if self.links:
            text += "\n\n" + "-" * 40 + "\n链接:\n"
            for i, url in enumerate(self.links, 1):
                text += f"  [{i}] {url}\n"
        return text


def main():
    ap = argparse.ArgumentParser(description="HTML 剥离标签转纯文本，标题/列表结构保留，链接附注文末")
    ap.add_argument("input", help="输入 HTML 文件")
    ap.add_argument("-o", "--output", default=None, help="输出文件（默认打印到 stdout）")
    ap.add_argument("--encoding", default="utf-8", help="输入编码（默认 utf-8）")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        print(f"错误: 找不到输入文件 {args.input}", file=sys.stderr)
        return 2

    with open(args.input, "r", encoding=args.encoding, errors="replace") as f:
        html = f.read()

    p = TextExtractor()
    try:
        p.feed(html)
        p.close()
    except Exception as e:
        print(f"错误: 解析失败: {e}", file=sys.stderr)
        return 1

    text = p.get_text()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"已写入 {args.output}")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
