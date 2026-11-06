#!/usr/bin/env python3
"""Markdown 转 HTML（自实现基础版）。

支持：ATX 标题（# ~ ######）、无序/有序列表（含嵌套缩进）、引用块（>）、
代码块（``` 围栏）、行内代码（`）、粗体（**）、斜体（*）、链接 [t](u)、
分隔线（---）、空行分段 <p>。

用法:
    python md-to-html.py input.md [-o output.html] [--title 标题]

示例:
    python md-to-html.py README.md -o README.html --title "说明"
"""
import argparse
import html
import os
import re
import sys


def render_inline(text):
    """行内元素：代码与链接先捕获占位，再全局转义，然后处理粗体/斜体，最后还原。"""
    codes, links = [], []

    def stash_code(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    def stash_link(m):
        links.append((m.group(1), m.group(2)))
        return f"\x01{len(links) - 1}\x01"

    text = re.sub(r"`([^`]+)`", stash_code, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", stash_link, text)
    text = html.escape(text, quote=False)
    # 粗体、斜体（** 先于 *）
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)

    def un_code(m):
        return "<code>" + html.escape(codes[int(m.group(1))], quote=False) + "</code>"

    def un_link(m):
        label, url = links[int(m.group(1))]
        return f'<a href="{html.escape(url, quote=True)}">{render_inline(label)}</a>'

    text = re.sub("\x01(\\d+)\x01", un_link, text)
    text = re.sub("\x00(\\d+)\x00", un_code, text)
    return text


def render(markdown):
    lines = markdown.splitlines()
    out = []
    i = 0
    n = len(lines)

    def split_list_item(line):
        m = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", line)
        if not m:
            return None
        indent = len(m.group(1).expandtabs(4))
        ordered = m.group(2) not in ("-", "*", "+")
        return indent, ordered, m.group(3)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 空行
        if not stripped:
            i += 1
            continue
        # 围栏代码块
        m = re.match(r"^```(\w*)\s*$", stripped)
        if m:
            lang = m.group(1)
            i += 1
            code = []
            while i < n and not re.match(r"^```\s*$", lines[i].strip()):
                code.append(lines[i])
                i += 1
            i += 1  # 跳过闭合 ```
            cls = f' class="language-{html.escape(lang, quote=True)}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(code))}</code></pre>")
            continue
        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{render_inline(m.group(2).strip())}</h{lvl}>")
            i += 1
            continue
        # 分隔线
        if re.match(r"^(-{3,}|\*{3,}|_{3,})\s*$", stripped) and not split_list_item(line):
            out.append("<hr>")
            i += 1
            continue
        # 引用块
        if stripped.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>\n" + render("\n".join(quote)) + "\n</blockquote>")
            continue
        # 列表（含嵌套）
        item = split_list_item(line)
        if item:
            root_indent, root_ordered, _ = item

            def parse_list(idx, indent):
                """返回 (HTML, 下一个未处理行号)。items 为 {"content":..., "extra":...}。"""
                ordered = None
                items = []
                while idx < n:
                    cur = split_list_item(lines[idx])
                    if cur is not None:
                        ind, ord_, content = cur
                        if ind > indent and items:
                            # 嵌套列表，块级 HTML 直接挂到上一项，不再参与 Markdown 渲染
                            sub, idx = parse_list(idx, ind)
                            items[-1]["extra"].append(sub)
                            continue
                        if ind < indent:
                            break
                        if ordered is None:
                            ordered = ord_
                        if ord_ == ordered and ind == indent:
                            items.append({"content": content, "extra": []})
                            idx += 1
                            continue
                        if ord_ != ordered:
                            break
                    elif not lines[idx].strip():
                        # 空行：若下一行仍是同级列表则继续，否则结束
                        if idx + 1 < n:
                            nxt = split_list_item(lines[idx + 1])
                            if nxt and nxt[0] == indent and (ordered is None or nxt[1] == ordered):
                                idx += 1
                                continue
                        break
                    else:
                        # 列表项的懒续行
                        if items:
                            items[-1]["content"] += " " + lines[idx].strip()
                            idx += 1
                            continue
                        break
                tag = "ol" if ordered else "ul"
                body = "".join(
                    "<li>" + render_inline(it["content"]) + it["extra_html"] + "</li>\n"
                    for it in ({"content": i["content"],
                                "extra_html": ("\n" + i["extra"][0]) if i["extra"] else ""}
                               for i in items))
                return f"<{tag}>\n{body}</{tag}>", idx

            block, i = parse_list(i, root_indent)
            out.append(block)
            continue
        # 普通段落（连续非空行合并）
        para = [stripped]
        i += 1
        while i < n and lines[i].strip() and not re.match(r"^(#{1,6}\s|```|>)", lines[i].strip()) \
                and not split_list_item(lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{render_inline(' '.join(para))}</p>")

    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="自实现 Markdown 基础转换器，输出 HTML")
    ap.add_argument("input", help="输入 Markdown 文件")
    ap.add_argument("-o", "--output", default=None, help="输出 HTML 文件（默认打印到 stdout）")
    ap.add_argument("--title", default="Markdown", help="HTML 页面标题")
    ap.add_argument("--standalone", action="store_true", help="输出完整 HTML 文档（默认开启）")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        print(f"错误: 找不到输入文件 {args.input}", file=sys.stderr)
        return 2

    with open(args.input, "r", encoding="utf-8", errors="replace") as f:
        md = f.read()

    try:
        body = render(md)
    except Exception as e:
        print(f"错误: 转换失败: {e}", file=sys.stderr)
        return 1

    doc = (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{html.escape(args.title)}</title>\n"
        "<style>body{max-width:820px;margin:2em auto;padding:0 1em;"
        "font-family:sans-serif;line-height:1.6}"
        "pre{background:#f5f5f5;padding:.8em;overflow:auto}"
        "code{background:#f5f5f5;padding:.1em .3em}blockquote{color:#555;"
        "border-left:4px solid #ddd;margin-left:0;padding-left:1em}</style>\n"
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n"
    )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(doc)
        print(f"已写入 {args.output}")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
        sys.stdout.write(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
