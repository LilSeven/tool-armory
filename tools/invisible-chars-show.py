#!/usr/bin/env python3
"""invisible-chars-show.py — 不可见字符可视化工具。

把文本中肉眼看不见或难以分辨的字符替换为可见标记输出，便于排查排版问题：
  Tab        →  →          全角空格 U+3000 → □
  CR         →  ^M         行尾 LF        →  ↵（仅 --eol 时显示）
  半角空格   →  ·          （仅 --spaces 时显示）
  零宽/BOM/双向控制等隐形字符 → {U+XXXX} 或 {NBSP} {SHY} 等命名标记

默认只读不改：输入原样不写回，仅在 stdout 打印标记化结果；
stderr 附带图例（--no-legend 关闭）与各类字符统计。

示例命令：
  python invisible-chars-show.py -i input.txt
  cat input.txt | python invisible-chars-show.py --spaces -n
  python invisible-chars-show.py --text "a　b	c​d"

退出码：0 成功；1 读取失败；2 参数错误。
"""
import argparse
import sys
from collections import Counter

# 空白类可见标记
BLANK_MARKS = {
    "\t": "→",       # 制表符
    "\u3000": "□",   # 全角空格 IDEOGRAPHIC SPACE
    "\r": "^M",      # 回车（含 CRLF 中的 CR）
}
# 命名的隐形字符标记
NAMED_INVISIBLE = {
    "\u00a0": "{NBSP}",
    "\u00ad": "{SHY}",
    "\u180e": "{MVS}",
    "\ufeff": "{U+FEFF}",
}
# 按码点输出的隐形区间（双向控制、零宽、隐形运算符、变体选择符等）
INVISIBLE_RANGES = (
    (0x200B, 0x200F),   # 零宽空格/连接符、LRM/RLM
    (0x2028, 0x2029),   # 行/段分隔符
    (0x202A, 0x202E),   # 双向控制（含 U+202E RLO）
    (0x2060, 0x2064),   # 文字连接符、隐形运算符
    (0x2066, 0x2069),   # LRI/RLI/FSI/PDI
    (0xFE00, 0xFE0F),   # 变体选择符 VS1-VS16
    (0x061C, 0x061C),   # 阿拉伯字母方向标记
    (0xFFF9, 0xFFFB),   # 交互注音锚点
)


def _is_invisible(code: int) -> bool:
    if code < 0x20 and code not in (0x09, 0x0A, 0x0D):
        return True                      # 其余 C0 控制符
    if code == 0x7F or 0x80 <= code <= 0x9F:
        return True                      # DEL 与 C1 控制符
    return any(lo <= code <= hi for lo, hi in INVISIBLE_RANGES)


def mark_char(ch: str, spaces: bool, eol: bool) -> str:
    if ch == "\n":
        return "↵\n" if eol else "\n"
    if ch in BLANK_MARKS:
        return BLANK_MARKS[ch]
    if ch == " ":
        return "·" if spaces else " "
    if ch in NAMED_INVISIBLE:
        return NAMED_INVISIBLE[ch]
    if _is_invisible(ord(ch)):
        return "{U+%04X}" % ord(ch)
    return ch


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="把 Tab、全角空格、零宽字符、CR 等替换为可见标记，肉眼排查排版问题")
    ap.add_argument("-i", "--input", help="输入文件（缺省读 stdin）")
    ap.add_argument("--text", help="直接指定待检查文本")
    ap.add_argument("-o", "--output", help="输出文件（缺省写 stdout）")
    ap.add_argument("--spaces", action="store_true", help="同时把半角空格显示为 ·")
    ap.add_argument("--eol", action="store_true", help="行尾 LF 也显示为 ↵")
    ap.add_argument("-n", "--number", action="store_true", help="显示行号")
    ap.add_argument("--no-legend", action="store_true", help="不在 stderr 打印图例")
    ap.add_argument("--encoding", default="utf-8", help="输入/输出编码（缺省 utf-8）")
    args = ap.parse_args(argv)

    try:
        if args.text is not None:
            data = args.text
        elif args.input:
            with open(args.input, "r", encoding=args.encoding, errors="replace",
                      newline="") as f:
                data = f.read()
        else:
            try:
                sys.stdin.reconfigure(encoding=args.encoding, errors="replace",
                                      newline="")
            except Exception:
                pass
            data = sys.stdin.read()
    except OSError as e:
        print(f"错误: 读取失败: {e}", file=sys.stderr)
        return 1

    counts = Counter(ch for ch in data if ch in BLANK_MARKS or ch == " "
                     or ch in NAMED_INVISIBLE or _is_invisible(ord(ch)))
    marked = "".join(mark_char(ch, args.spaces, args.eol) for ch in data)

    if not args.no_legend:
        print("[invisible-chars-show] 图例: →=Tab  □=全角U+3000  ^M=CR  ↵=LF  "
              "·=半角空格(--spaces)  {U+XXXX}/{NBSP}/{SHY}=隐形字符",
              file=sys.stderr)
    if counts:
        desc = ", ".join(
            "{U+%04X}" % ord(ch) if ch in NAMED_INVISIBLE or _is_invisible(ord(ch))
            else repr(ch) for ch in sorted(counts, key=ord))
        print(f"[invisible-chars-show] 共发现 {sum(counts.values())} 个特殊字符: {desc}",
              file=sys.stderr)
    else:
        print("[invisible-chars-show] 未发现特殊字符。", file=sys.stderr)

    if args.number:
        lines = marked.split("\n")
        marked = "\n".join(f"{i:>4}: {ln}" for i, ln in enumerate(lines, 1))

    if args.output:
        with open(args.output, "w", encoding=args.encoding, newline="") as f:
            f.write(marked)
    else:
        sys.stdout.write(marked)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
