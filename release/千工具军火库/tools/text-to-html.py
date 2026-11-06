#!/usr/bin/env python3
"""纯文本转 HTML 网页。

把 .txt 按空行分段，每段做 HTML 转义并包成 <p>，生成带基本样式的完整网页。
段内换行用 <br> 保留。

用法:
    python text-to-html.py input.txt [-o output.html] [--title 标题]

示例:
    python text-to-html.py notes.txt -o notes.html --title "我的笔记"
"""
import argparse
import html
import os
import re
import sys

STYLE = (
    "body{max-width:760px;margin:2em auto;padding:0 1em;"
    "font-family:Georgia,'Songti SC',serif;line-height:1.7;color:#222}"
    "p{margin:0 0 1em}h1{border-bottom:2px solid #eee;padding-bottom:.3em}"
)


def build_document(title, paragraphs):
    body = []
    for para in paragraphs:
        # 段内保留换行
        body.append("<p>" + "<br>".join(html.escape(ln) for ln in para.split("\n")) + "</p>")
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{html.escape(title)}</title>\n"
        f"<style>{STYLE}</style>\n</head>\n<body>\n"
        f"<h1>{html.escape(title)}</h1>\n"
        + "\n".join(body) + "\n</body>\n</html>\n"
    )


def main():
    ap = argparse.ArgumentParser(description="纯文本按空行分段转 HTML，带基本样式")
    ap.add_argument("input", help="输入 .txt 文件")
    ap.add_argument("-o", "--output", default=None, help="输出 HTML 文件（默认 <输入名>.html）")
    ap.add_argument("--title", default=None, help="页面标题（默认为输入文件名）")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        print(f"错误: 找不到输入文件 {args.input}", file=sys.stderr)
        return 2

    with open(args.input, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    # 统一换行并按空行分段
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip("\n") for p in re.split(r"\n\s*\n", text) if p.strip()]
    title = args.title or os.path.splitext(os.path.basename(args.input))[0]

    doc = build_document(title, paragraphs)
    out = args.output or os.path.splitext(args.input)[0] + ".html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"共 {len(paragraphs)} 段，已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
