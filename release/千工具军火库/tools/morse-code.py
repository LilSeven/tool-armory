#!/usr/bin/env python3
"""摩斯电码互转：拉丁字母数字与摩斯电码之间双向转换。

自动识别输入方向：输入含 . 或 - 视为摩斯码（解码为文本），
否则视为明文（编码为摩斯码）。多语言短语中的非 A-Z/0-9 字符
按规则处理：空格保留为词分隔，其他字符可用 --keep/--skip 控制。

用法:
    python morse-code.py "SOS"
    python morse-code.py "... --- ..."
    echo "CQ CQ DE BG7ABC" | python morse-code.py
    python morse-code.py --decode "... --- ..."
    python morse-code.py "HELLO 123" --sep "/" --word-sep " / "

示例命令:
    python morse-code.py "HELLO WORLD"
    python morse-code.py ".... . .-.. .-.. --- / .-- --- .-. .-.. -.." --decode
"""
import argparse
import sys

MORSE = {
    "A": ".-",    "B": "-...",  "C": "-.-.",  "D": "-..",
    "E": ".",     "F": "..-.",  "G": "--.",   "H": "....",
    "I": "..",    "J": ".---",  "K": "-.-",   "L": ".-..",
    "M": "--",    "N": "-.",    "O": "---",   "P": ".--.",
    "Q": "--.-",  "R": ".-.",   "S": "...",   "T": "-",
    "U": "..-",   "V": "...-",  "W": ".--",   "X": "-..-",
    "Y": "-.--",  "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--",
    "4": "....-", "5": ".....", "6": "-....", "7": "--...",
    "8": "---..", "9": "----.",
}
REVERSE = {v: k for k, v in MORSE.items()}


def encode(text: str, sep: str, word_sep: str, skip: bool) -> str:
    words = text.upper().split(" ")
    out_words = []
    for word in words:
        letters = []
        for ch in word:
            if ch in MORSE:
                letters.append(MORSE[ch])
            elif skip:
                continue
            else:
                raise SystemExit(f"错误: 无法编码字符 {ch!r}（可用 --skip 跳过）")
        if letters:
            out_words.append(sep.join(letters))
    return word_sep.join(out_words)


def decode(text: str, sep: str, word_sep: str, skip: bool) -> str:
    wsep = word_sep.strip() or "/"
    ssep = sep.strip()
    words = [w for w in text.strip().split(wsep) if w.strip()]
    out_words = []
    for word in words:
        letters = []
        codes = word.split() if not ssep else [c.strip() for c in word.split(ssep) if c.strip()]
        for code in codes:
            if code in REVERSE:
                letters.append(REVERSE[code])
            elif skip:
                continue
            else:
                raise SystemExit(f"错误: 无法识别摩斯码 {code!r}（可用 --skip 跳过）")
        if letters:
            out_words.append("".join(letters))
    return " ".join(out_words)


def main() -> int:
    ap = argparse.ArgumentParser(description="拉丁字母数字与摩斯电码双向转换")
    ap.add_argument("text", nargs="?", help="输入文本；缺省从 stdin 读取")
    ap.add_argument("-d", "--decode", action="store_true",
                    help="强制按摩斯码解码（缺省自动检测）")
    ap.add_argument("-e", "--encode", action="store_true",
                    help="强制按明文编码")
    ap.add_argument("--sep", default=" ", help="字符分隔符（默认空格）")
    ap.add_argument("--word-sep", default=" / ", help="词分隔符（默认 ' / '）")
    ap.add_argument("--skip", action="store_true",
                    help="跳过无法转换的字符而不是报错")
    args = ap.parse_args()

    text = args.text if args.text is not None else sys.stdin.read()
    text = text.rstrip("\n")
    if not text:
        print("错误: 无输入", file=sys.stderr)
        return 2

    mode = "decode" if args.decode else ("encode" if args.encode else
          ("decode" if set(".-") & set(text) else "encode"))
    if mode == "decode":
        print(decode(text, args.sep, args.word_sep, args.skip))
    else:
        print(encode(text, args.sep, args.word_sep, args.skip))
    return 0


if __name__ == "__main__":
    sys.exit(main())
