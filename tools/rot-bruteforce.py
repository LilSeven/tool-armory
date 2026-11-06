#!/usr/bin/env python3
"""ROT 全量尝试 (rot-bruteforce) —— 26 个凯撒移位按英文可读度排序.

用途:
    对文本尝试全部 26 个凯撒移位 (仅英文字母循环移位, 大小写保留, 非字母
    不变), 按英文可读度打分排序展示: 字母频率对数似然 + 常用英文词命中
    加成。shift=13 即 ROT13, shift=0 即原文; 第一名 (带 *) 为最可能原文。

退出码: 0=成功, 2=参数或数据错误。

示例:
    python -I rot-bruteforce.py --text "Uryyb, Jbeyq!"
    python -I rot-bruteforce.py --input cipher.txt --top 5
    echo "Gur synt vf va gur onfrzrag" | python -I rot-bruteforce.py --top 3
"""
import argparse
import math
import re
import sys


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_FREQ_PCT = {
    "e": 12.702, "t": 9.056, "a": 8.167, "o": 7.507, "i": 6.966,
    "n": 6.749, "s": 6.327, "h": 6.094, "r": 5.987, "d": 4.253,
    "l": 4.025, "c": 2.782, "u": 2.758, "m": 2.406, "w": 2.360,
    "f": 2.228, "g": 2.015, "y": 1.974, "p": 1.929, "b": 1.492,
    "v": 0.978, "k": 0.772, "j": 0.153, "x": 0.150, "q": 0.095, "z": 0.074,
}
_FREQ_LOG = {ch: math.log10(p / 100.0) for ch, p in _FREQ_PCT.items()}
_SPACE_LOG = math.log10(0.16)
_WORD_BONUS = 4.0
_COMMON_WORDS = frozenset("""
the be to of and a in that have it for not on with he as you do at this but his
by from they we say her she or an will my one all would there their what so up
out if about who get which go me when make can like time no just him know take
people into year your good some could them see other than then now look only
come its over think also back after use two how our work first well way even
new want because any these give day most us is are was were been has had am
hello world flag secret test key message attack dawn code pass words
""".split())


def caesar(text: str, shift: int) -> str:
    out = []
    for ch in text:
        o = ord(ch)
        if 97 <= o <= 122:
            out.append(chr((o - 97 + shift) % 26 + 97))
        elif 65 <= o <= 90:
            out.append(chr((o - 65 + shift) % 26 + 65))
        else:
            out.append(ch)
    return "".join(out)


def score_text(text: str) -> float:
    total = 0.0
    for ch in text:
        o = ord(ch)
        if 97 <= o <= 122:
            total += _FREQ_LOG[ch]
        elif 65 <= o <= 90:
            total += _FREQ_LOG[ch.lower()]
        elif ch == " ":
            total += _SPACE_LOG
        elif ch in ".,'\"!?;:-()":
            total += -2.5
        elif ch in "\t\n\r":
            total += -3.0
        elif ch.isdigit():
            total += -3.0
        elif 32 <= o <= 126:
            total += -3.5
        else:
            total += -8.0
    for tok in re.findall(r"[A-Za-z]+", text):
        if tok.lower() in _COMMON_WORDS:
            total += _WORD_BONUS
    return total


def render(text: str, limit: int = 0) -> str:
    shown = text[:limit] if limit else text
    parts = []
    for ch in shown:
        o = ord(ch)
        if ch == "\n":
            parts.append("\\n")
        elif ch == "\t":
            parts.append("\\t")
        elif 32 <= o <= 126:
            parts.append(ch)
        elif o < 256:
            parts.append(f"\\x{o:02x}")
        else:
            parts.append(f"\\u{o:04x}")
    tail = "..." if limit and len(text) > limit else ""
    return "".join(parts) + tail


def _read_text(args) -> str:
    if args.text is not None:
        return args.text
    if args.input is not None:
        if args.input == "-":
            return sys.stdin.read()
        with open(args.input, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    return sys.stdin.read()


def main(argv=None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="rot-bruteforce",
        description="对文本尝试全部 26 个凯撒移位, 按英文可读度排序展示。",
    )
    parser.add_argument("--text", help="要分析的文本")
    parser.add_argument("--input", help="文本文件 ('-' 读 stdin); 两者都缺省时读 stdin")
    parser.add_argument("--top", type=int, default=26,
                        help="展示前 N 个移位, 缺省 26 (全部)")
    args = parser.parse_args(argv)
    try:
        text = _read_text(args).rstrip("\r\n")
        if not text:
            raise ValueError("输入为空")
        if not any(c.isascii() and c.isalpha() for c in text):
            print("警告: 输入不含英文字母, 各移位得分相同", file=sys.stderr)
        rows = []
        for shift in range(26):
            decoded = caesar(text, shift)
            rows.append((score_text(decoded), shift, decoded))
        rows.sort(key=lambda t: (-t[0], t[1]))
        top = max(1, min(args.top, 26))
        print(f"输入: {len(text)} 字符; 已尝试 26 个移位, 按英文可读度排序 (前 {top}):")
        print("  名次  shift    得分  解码文本")
        for rank, (score, shift, decoded) in enumerate(rows[:top], 1):
            mark = "*" if rank == 1 else " "
            print(f"{mark} {rank:>4}  {shift:>4}  {score:8.2f}  {render(decoded, 120)}")
        best_score, best_shift, best_dec = rows[0]
        print(f"最可能: shift={best_shift} (得分 {best_score:.2f}) "
              f'-> "{render(best_dec, 120)}"')
        return 0
    except (ValueError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
