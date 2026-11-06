#!/usr/bin/env python3
"""非 ASCII 字符清洗 —— 把文本转成纯 ASCII（全角→半角、弯引号→直引号、剥离变音符等）。

处理规则（按顺序）：
  1. unicodedata.normalize('NFKD') 分解字符，剥离组合变音符号（é → e）；
  2. 其余非 ASCII 字符经翻译表映射：全角字母数字标点→半角、弯引号/省略号/破折号→
     直引号/.../--、不间断空格→空格、不可映射字符可按 --drop 丢弃或替换为 '?'；
  3. 结果保证 100% ASCII。

用法：
  python translit-ascii.py -i in.txt -o out.txt
  python translit-ascii.py --text "你好，Ｗｏｒｌｄ！café — “quoted”"
  cat in.txt | python translit-ascii.py > out.txt

示例命令：
  python translit-ascii.py -i sample-utf8.txt -o sample-ascii.txt --errors replace

选项：
  -i, --input PATH    输入文件（默认 utf-8）；缺省读 stdin
  -o, --output PATH   输出文件；缺省写 stdout
  --encoding ENC      读写字符集（默认 utf-8）
  --errors MODE       读取错误处理：strict/replace/ignore（默认 replace）
  --drop              不可映射字符直接丢弃（默认替换为 '?'）
  --strip-controls    同时删除 C0/C1 控制字符（保留 \\t \\n \\r）
"""

import argparse
import sys
import unicodedata

# 弯引号 / 特殊标点 → ASCII 映射（NFKD 之后仍残留的部分）
PUNCT_MAP = {
    "“": '"', "”": '"', "„": '"', "‟": '"', "❝": '"', "❞": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "ʼ": "'",
    "«": '"', "»": '"', "‹": "'", "›": "'",
    "—": "--", "–": "-", "―": "-", "−": "-",
    "…": "...", "‥": "..",
    "•": "*", "·": "*", "‧": "*", "●": "*",
    " ": " ", " ": " ", "　": " ",
    "：": ":", "；": ";", "，": ",", "。": ".", "！": "!", "？": "?",
    "（": "(", "）": ")", "【": "[", "】": "]", "《": "<", "》": ">",
    "「": '"', "」": '"', "『": '"', "』": '"',
    "¥": "Y", "¢": "c", "£": "L", "€": "E", "©": "(c)", "®": "(r)",
    "™": "(TM)", "°": " deg", "±": "+/-", "×": "x", "÷": "/", "§": "S",
    "¶": "P", "†": "+", "‡": "++", "¼": "1/4", "½": "1/2", "¾": "3/4",
    "¹": "1", "²": "2", "³": "3", "⅓": "1/3", "⅔": "2/3",
}


def translit(text: str, drop: bool = False) -> str:
    # 1) NFKD 分解 + 去组合记号（兼得全角→半角的大部分效果）
    decomposed = unicodedata.normalize("NFKD", text)
    chars = []
    for ch in decomposed:
        if unicodedata.combining(ch):
            continue
        if ord(ch) < 128:
            chars.append(ch)
        else:
            mapped = PUNCT_MAP.get(ch)
            if mapped is not None:
                chars.append(mapped)
            else:
                # 2) NFKC 兼容映射兜底（如剩余全角字符、上标等）
                alt = unicodedata.normalize("NFKC", ch)
                if alt.isascii():
                    chars.append(alt)
                elif drop:
                    pass  # 直接丢弃
                else:
                    chars.append("?")
    out = "".join(chars)
    # 3) 最终兜底：确保纯 ASCII
    if not out.isascii():
        out = "".join(c if ord(c) < 128 else ("?" if not drop else "")
                      for c in out)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="translit-ascii", description="把文本清洗为纯 ASCII")
    p.add_argument("-i", "--input", help="输入文件，缺省读 stdin")
    p.add_argument("--text", help="直接处理该字符串（忽略 -i / stdin）")
    p.add_argument("-o", "--output", help="输出文件，缺省写 stdout")
    p.add_argument("--encoding", default="utf-8", metavar="ENC")
    p.add_argument("--errors", default="replace",
                   choices=["strict", "replace", "ignore"])
    p.add_argument("--drop", action="store_true",
                   help="不可映射字符直接丢弃（默认替换为 '?'）")
    p.add_argument("--strip-controls", action="store_true",
                   help="同时删除控制字符（保留 \\t \\n \\r）")
    a = p.parse_args(argv)

    if a.text is not None:
        text = a.text
    else:
        if a.input is None:
            data = sys.stdin.buffer.read()
        else:
            with open(a.input, "rb") as f:
                data = f.read()
        text = data.decode(a.encoding, a.errors)

    out = translit(text, drop=a.drop)
    if a.strip_controls:
        out = "".join(
            c for c in out
            if c in "\t\n\r" or not unicodedata.category(c).startswith("C")
        )

    payload = out.encode("ascii", "strict")
    if a.output is None:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    else:
        with open(a.output, "wb") as f:
            f.write(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
