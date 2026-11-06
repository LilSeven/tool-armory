#!/usr/bin/env python3
"""邮件转文本：用标准库 email 模块解析 .eml 邮件文件，提取头部字段与正文（含解码附件名），存为纯文本。

用法:
    python email-to-text.py input.eml -o output.txt
    python email-to-text.py input.eml            # 输出到 stdout

说明:
    - 头部字段做 RFC2047 编码词解码（Subject 等）。
    - 正文按 text/plain -> text/html 优先提取；HTML 简单去标签。
    - 附件列出文件名（解码后）、类型与大小。

示例:
    python email-to-text.py sample.eml -o sample.txt
"""

import argparse
import email
import email.policy
import html.parser
import io
import re
import sys


class _HTMLText(html.parser.HTMLParser):
    """极简 HTML 去标签，保留文本与块级换行。"""

    _BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in self._BLOCK:
            self.parts.append("\n")

    def text(self):
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t]*\n[ \t]*", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip() + "\n"


def html_to_text(html_src):
    p = _HTMLText()
    try:
        p.feed(html_src)
        p.close()
        out = p.text()
        return out if out.strip() else html_src
    except Exception:
        return html_src


def decode_header_value(value):
    """解码 RFC2047 编码词头部值（兼容 policy 默认未解码的情况）。"""
    if value is None:
        return ""
    try:
        from email.header import decode_header, make_header
        return str(make_header(decode_header(str(value))))
    except Exception:
        return str(value)


def get_decoded_filename(part):
    for key in ("Content-Disposition", "Content-Type"):
        raw = part.get(key, "")
        if not raw:
            continue
        # 先解码整个头的编码词，再取 filename 参数
        decoded = decode_header_value(raw)
        m = re.search(r'filename\*?=(?:utf-8\'\'|"?)([^";]+)', decoded, re.I)
        if m:
            name = m.group(1).strip().strip('"')
            try:
                from urllib.parse import unquote
                name = unquote(name)
            except Exception:
                pass
            if name:
                return name
    return part.get_filename() or "(unnamed)"


def parse_eml(path, encoding="utf-8"):
    with open(path, "rb") as f:
        raw = f.read()
    msg = email.message_from_bytes(raw)

    lines = []
    # ---- 头部 ----
    important = ["From", "To", "Cc", "Bcc", "Subject", "Date", "Message-ID"]
    shown = set()
    lines.append("=" * 60)
    lines.append("HEADERS")
    lines.append("=" * 60)
    for key in important:
        val = msg.get(key)
        if val is not None:
            lines.append("%s: %s" % (key, decode_header_value(val)))
            shown.add(key.lower())
    # 其余头部（跳过冗长的 Received 链，仅保留第一条）
    for key, val in msg.items():
        if key.lower() in shown:
            continue
        if key.lower() == "received":
            continue
        lines.append("%s: %s" % (key, decode_header_value(val)))

    # ---- 正文 ----
    lines.append("")
    lines.append("=" * 60)
    lines.append("BODY")
    lines.append("=" * 60)

    attachments = []
    body_text = None
    body_html = None
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        ctype = part.get_content_type()
        disp = (part.get_content_disposition() or "").lower()
        if disp == "attachment":
            payload = part.get_payload(decode=True) or b""
            attachments.append((get_decoded_filename(part), ctype, len(payload)))
            continue
        if ctype == "text/plain":
            if body_text is None:
                body_text = part.get_payload(decode=True)
                if body_text is not None:
                    cs = part.get_content_charset() or "utf-8"
                    try:
                        body_text = body_text.decode(cs, "replace")
                    except LookupError:
                        body_text = body_text.decode("utf-8", "replace")
        elif ctype == "text/html":
            if body_html is None:
                body_html = part.get_payload(decode=True)
                if body_html is not None:
                    cs = part.get_content_charset() or "utf-8"
                    try:
                        body_html = body_html.decode(cs, "replace")
                    except LookupError:
                        body_html = body_html.decode("utf-8", "replace")

    body = None
    if body_text and body_text.strip():
        body = body_text
    elif body_html:
        body = html_to_text(body_html)
    lines.append(body if body else "(no text body)")

    # ---- 附件 ----
    if attachments:
        lines.append("")
        lines.append("=" * 60)
        lines.append("ATTACHMENTS (%d)" % len(attachments))
        lines.append("=" * 60)
        for name, ctype, size in attachments:
            lines.append("- %s  [%s, %d bytes]" % (name, ctype, size))

    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="解析 .eml 邮件为纯文本")
    ap.add_argument("input", help="输入 .eml 文件")
    ap.add_argument("-o", "--output", help="输出文本文件（缺省打印到 stdout）")
    args = ap.parse_args(argv)

    text = parse_eml(args.input)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print("written: %s" % args.output)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
