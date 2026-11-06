#!/usr/bin/env python3
"""邮件正文提取 (eml2txt) —— 解析 .eml 邮件文件，处理头部编码
(RFC 2047) 与 multipart 结构，输出发件人 / 主题 / 纯文本正文。

只用 Python 标准库 (email 包)。优先抽取 text/plain 部件；
仅存在 text/html 时做极简标签剥离。

用法:
    python eml2txt.py 邮件.eml [输出.txt]
    python eml2txt.py 邮件.eml            # 无输出文件则打印到 stdout
示例:
    python eml2txt.py sample.eml out.txt
"""

import re
import sys
from email import policy
from email.parser import BytesParser
from email.header import decode_header, make_header


def decode_header_value(value):
    """解码 RFC 2047 编码的头部值（=?utf-8?B?...?= 等）。"""
    if value is None:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def strip_html(html):
    """极简 HTML -> 纯文本：去 script/style、标签、压缩空行。"""
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p>", "\n\n", html)
    text = re.sub(r"(?s)<[^>]+>", "", html)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_body(msg):
    """遍历 multipart，返回 (纯文本正文, 是否来自 HTML 降级)。"""
    if msg.is_multipart():
        plain, html = None, None
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", "")).lower()
            if "attachment" in disp:
                continue
            if ctype == "text/plain" and plain is None:
                plain = get_payload_text(part)
            elif ctype == "text/html" and html is None:
                html = get_payload_text(part)
        if plain is not None:
            return plain.strip(), False
        if html is not None:
            return strip_html(html), True
        return "", False
    ctype = msg.get_content_type()
    payload = get_payload_text(msg)
    if ctype == "text/html":
        return strip_html(payload), True
    return payload.strip(), False


def get_payload_text(part):
    """按声明字符集解码部件负载，失败时逐个回退。"""
    payload = part.get_payload(decode=True)
    if payload is None:
        return part.get_payload() or ""
    charset = part.get_content_charset() or "utf-8"
    for cs in (charset, "utf-8", "gb18030", "latin-1"):
        try:
            return payload.decode(cs)
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__.strip())
        return 2
    src = argv[1]
    with open(src, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    from_ = decode_header_value(msg.get("From", ""))
    subject = decode_header_value(msg.get("Subject", ""))
    date_ = msg.get("Date", "")
    body, from_html = get_body(msg)

    lines = [
        f"发件人: {from_}",
        f"主题: {subject}",
    ]
    if date_:
        lines.append(f"日期: {date_}")
    lines.append("-" * 40)
    if from_html:
        lines.append("[提示: 无 text/plain 部件，正文由 HTML 降级提取]")
    lines.append(body)

    out = "\n".join(lines) + "\n"
    if len(argv) == 3:
        with open(argv[2], "w", encoding="utf-8") as f:
            f.write(out)
        print(f"已写入 {argv[2]}")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
