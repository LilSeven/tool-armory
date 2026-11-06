#!/usr/bin/env python3
"""entity-code.py — HTML 实体与明文字符双向编解码工具。

encode：把明文编码为 HTML 实体——&<>"' 转为命名实体（&amp; &lt; &gt;
        &quot; &#x27;），加 --all 时其余非 ASCII 字符转为十六进制数字实体。
decode：把 HTML 实体（命名 / 十进制 / 十六进制数字实体）解码回明文。

示例命令：
  python entity-code.py encode --text 'a < b & "引号"'
  python entity-code.py encode --all --text '中文 & <tag>'
  python entity-code.py decode --text 'a &lt; b &#x4e2d;&#25991;'
  cat page.frag | python entity-code.py decode -o plain.txt
"""

import argparse
import html
import sys


def encode_text(text: str, all_non_ascii: bool = False) -> str:
    # 先转义保留字符（命名实体）
    out = html.escape(text, quote=True)  # & < > " ' -> &amp; &lt; &gt; &quot; &#x27;
    if all_non_ascii:
        buf = []
        i = 0
        for ch in out:
            if ord(ch) > 0x7E and ch not in "&<>\"'":
                buf.append("&#x%X;" % ord(ch))
            else:
                buf.append(ch)
            i += 1
        out = "".join(buf)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="HTML 命名/数字实体与明文字符之间双向编解码。")
    ap.add_argument("mode", choices=["encode", "decode"], help="编码或解码")
    ap.add_argument("-i", "--input", help="输入文件（缺省读 stdin）")
    ap.add_argument("-o", "--output", help="输出文件（缺省写 stdout）")
    ap.add_argument("--text", help="直接指定待处理文本")
    ap.add_argument("--all", action="store_true",
                    help="encode 时把所有非 ASCII 字符也转为数字实体")
    ap.add_argument("--encoding", default="utf-8",
                    help="输入/输出编码（缺省 utf-8）")
    args = ap.parse_args()

    try:
        sys.stdin.reconfigure(encoding=args.encoding, errors="replace", newline="")
    except Exception:
        pass

    if args.text is not None:
        data = args.text
    elif args.input:
        with open(args.input, "r", encoding=args.encoding, errors="replace") as f:
            data = f.read()
    else:
        data = sys.stdin.read()

    if args.mode == "encode":
        result = encode_text(data, all_non_ascii=args.all)
    else:
        result = html.unescape(data)

    sys.stderr.write("[entity-code] mode=%s：%d 字符 -> %d 字符。\n"
                     % (args.mode, len(data), len(result)))

    if args.output:
        with open(args.output, "w", encoding=args.encoding, newline="") as f:
            f.write(result)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
