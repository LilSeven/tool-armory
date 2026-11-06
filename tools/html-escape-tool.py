#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTML 实体转义/还原：特殊字符与命名/数字实体(&amp; &#65;)互相转换。

escape:   标准库 html.escape，把 & < > " ' 转为 &amp; &lt; &gt; &quot; &#x27;
          （--no-quote 可保留引号不转义）；
unescape: 标准库 html.unescape，还原全部 HTML5 命名实体与 &#NNN; / &#xHH; 数字实体。

用法:
    python html-escape-tool.py <escape|unescape> [文本]
    echo '文本' | python html-escape-tool.py escape

注意: 在 Git Bash/MSYS 下，以 < 或 > 组成的参数可能被路径转换改写
     （如 '<b>' 变成 'C:/Program Files/Git/b'），此类文本建议经 stdin 传入。

示例:
    $ python html-escape-tool.py escape '<a href="x">A&B</a>'
    &lt;a href=&quot;x&quot;&gt;A&amp;B&lt;/a&gt;
    $ python html-escape-tool.py unescape '&lt;p&gt;&#65;&amp;&#x27;'
    <p>A&'
"""

from __future__ import annotations

import argparse
import html
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="HTML 特殊字符与命名/数字实体（&amp; &#65;）互相转换",
    )
    parser.add_argument("action", choices=("escape", "unescape"),
                        help="escape=转义为实体; unescape=实体还原为字符")
    parser.add_argument("text", nargs="?", default=None,
                        help="待处理文本；省略时从 stdin 读取")
    parser.add_argument("--no-quote", dest="quote", action="store_false",
                        default=True,
                        help="escape 时保留引号不转义(默认引号也转义)")
    args = parser.parse_intermixed_args(argv)

    text = args.text
    if text is None:
        if sys.stdin.isatty():
            parser.error("未提供文本：请用参数传入，或通过管道从 stdin 读取")
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")

    if args.action == "escape":
        print(html.escape(text, quote=args.quote))
    else:
        print(html.unescape(text))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
