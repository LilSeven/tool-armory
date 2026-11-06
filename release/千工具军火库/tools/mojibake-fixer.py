#!/usr/bin/env python3
"""乱码修复器 - 对疑似乱码文本尝试多种往返重编码组合并推荐最优解。

用途
    典型乱码是「文本被按错误编码解码」造成的。本工具把输入文本按一系列
    组合做「先编码回字节、再按另一个编码解码」的往返尝试，例如：
      latin-1 -> utf-8   (UTF-8 被 Latin-1 误读)
      latin-1 -> gbk     (GBK 被 Latin-1 误读)
      cp1252  -> utf-8
      gbk     -> utf-8
      utf-8   -> gbk     (GBK 文本被 UTF-8 误读, 双重转码)
      utf-8   -> big5
    每个候选按可读性评分（常用汉字/ASCII 占比、替换符与怪符号惩罚），
    推荐得分最高者。支持修复整层（--depth 2）双重乱码。

只用 Python 标准库。默认只报告，不改文件；指定 -o/--in-place 时写回。

示例命令
    python -I mojibake-fixer.py bad.txt
    python -I mojibake-fixer.py --text "æµ‹è¯•æ–‡æœ¬"
    python -I mojibake-fixer.py bad.txt -o fixed.txt
    python -I mojibake-fixer.py bad.txt --in-place --yes --depth 2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CHAINS = [
    ("latin-1", "utf-8"), ("latin-1", "gbk"), ("latin-1", "gb18030"),
    ("latin-1", "big5"), ("latin-1", "shift_jis"),
    ("cp1252", "utf-8"), ("cp1252", "gbk"),
    ("utf-8", "gbk"), ("utf-8", "gb18030"), ("utf-8", "big5"),
    ("gbk", "utf-8"), ("gb18030", "utf-8"),
    ("shift_jis", "utf-8"), ("big5", "utf-8"),
]

CJ_RANGES = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0x3000, 0x303F), (0xFF00, 0xFFEF))
ASCII_OK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 \t\r\n")
PUNCT_OK = set("，。、；：？！“”‘’（）《》【】—…·,.:;!?()[]{}'\"-_/\\+=*&^%$#@~`<>|")


def score(text: str) -> float:
    """0~1，越高越像正常文本。"""
    if not text:
        return 0.0
    s = 0.0
    for ch in text:
        cp = ord(ch)
        if ch in ASCII_OK or ch in PUNCT_OK:
            s += 1.0
        elif any(lo <= cp <= hi for lo, hi in CJ_RANGES):
            s += 1.0
        elif 0xA0 <= cp <= 0x24F or 0x2000 <= cp <= 0x206F:
            s += 0.5
        elif cp == 0xFFFD:
            s -= 1.0
        else:
            s += 0.1
    s /= len(text)
    # 大量替换符直接判负
    if text.count("\ufffd") > len(text) * 0.05:
        s = min(s, 0.05)
    return max(0.0, min(1.0, s))


def fix_once(text: str):
    """单层修复：返回 [(得分, 源误读编码, 真实编码, 修复文本), ...]。"""
    out = []
    for src, dst in CHAINS:
        try:
            fixed = text.encode(src, errors="strict").decode(dst, errors="strict")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if fixed == text:
            continue
        out.append((score(fixed), src, dst, fixed))
    return out


def best_fix(text: str, depth: int = 1):
    """在 depth 层内搜索，返回 (总得分, 链路描述, 修复文本)。"""
    best = (score(text), "(原文，无需修复)", text)
    frontier = [(score(text), "", text)]
    for _ in range(max(1, depth)):
        nxt = []
        for _, chain, t in frontier:
            for sc, src, dst, fixed in fix_once(t):
                desc = (chain + " ; " if chain else "") + f"{src}->x{dst}"
                sc_total = sc if not chain else best[0] * 0.5 + sc * 0.5
                if sc_total > best[0] + 1e-9:
                    best = (sc_total, desc, fixed)
                nxt.append((sc, desc, fixed))
        frontier = sorted(nxt, key=lambda x: -x[0])[:8]
    return best


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="尝试多种往返重编码组合修复乱码文本")
    ap.add_argument("file", nargs="?", help="疑似乱码的文本文件")
    ap.add_argument("--text", help="直接传入文本（优先于 file）")
    ap.add_argument("-o", "--output", help="把推荐修复结果写入该文件")
    ap.add_argument("--in-place", action="store_true", help="把修复结果写回原文件")
    ap.add_argument("--yes", action="store_true", help="配合 --in-place 跳过确认（本工具无交互，保留参数以兼容）")
    ap.add_argument("--depth", type=int, default=1, choices=[1, 2], help="搜索层数（2=尝试双重乱码）")
    ap.add_argument("--show-all", action="store_true", help="显示所有单层候选")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    if not args.text and not args.file:
        ap.error("需要 --text 或一个输入文件")
    if args.text is not None:
        text = args.text
        src_path = None
    else:
        path = Path(args.file)
        if not path.is_file():
            print(f"[错误] {path}: 不是文件或不存在")
            return 2
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("gb18030")
            except UnicodeDecodeError:
                text = raw.decode("utf-8", errors="replace")
        src_path = path

    total, chain, fixed = best_fix(text, args.depth)
    print(f"原文长度: {len(text)} 字符")
    print(f"原文预览: {text[:60]!r}")
    if chain.startswith("(原文"):
        print(f"结论: {chain}（得分 {total:.2f}）")
        fixed_out = None
    else:
        print(f"推荐修复: {chain}")
        print(f"修复得分: {total:.2f}")
        print(f"修复预览: {fixed[:60]!r}")
        fixed_out = fixed

    if args.show_all:
        print("\n单层候选:")
        for sc, src, dst, t in sorted(fix_once(text), key=lambda x: -x[0]):
            print(f"  {sc:.2f}  {src} -> {dst}: {t[:40]!r}")

    if fixed_out is None:
        return 1 if not chain.startswith("(原文") else 0

    if args.output:
        Path(args.output).write_text(fixed_out, encoding="utf-8")
        print(f"[完成] 已写入 {args.output}")
    if args.in_place:
        if src_path is None:
            print("[错误] --in-place 需要输入文件而非 --text")
            return 2
        src_path.write_text(fixed_out, encoding="utf-8")
        print(f"[完成] 已写回 {src_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
