"""十六进制转储与还原：生成 hexdump 样式的 偏移+十六进制+ASCII 文本，也可从该格式逆向还原二进制文件。

仅使用 Python 标准库。--dump 生成类似 xxd 的文本（每行 16 字节：
8 位十六进制偏移 + 16 个十六进制字节 + 可打印 ASCII），--restore 解析此格式还原二进制。
输出文件缺省规则：转储加 .hex.txt 后缀，还原去掉 .hex.txt（无后缀则加 .out）。

示例:
  python hex-dump-convert.py --dump firmware.bin
  python hex-dump-convert.py --dump firmware.bin -o dump.txt --cols 8
  python hex-dump-convert.py --restore dump.txt -o rebuilt.bin
"""
import argparse
import re
import sys
from pathlib import Path


def dump(src: Path, dst: Path, cols: int):
    printable = set(range(0x20, 0x7F))
    offset = 0
    with src.open("rb") as fin, dst.open("w", encoding="ascii", newline="") as fout:
        while True:
            chunk = fin.read(cols)
            if not chunk:
                break
            hx = " ".join(f"{b:02x}" for b in chunk)
            asc = "".join(chr(b) if b in printable else "." for b in chunk)
            fout.write(f"{offset:08x}  {hx:<{cols*3-1}}  |{asc}|\n")
            offset += len(chunk)
    return offset


# 匹配: 偏移 + 任意分隔 + 成对的十六进制字节（容忍省略 ASCII 列或行内截断）。
# 始终取十六进制列还原，因为 ASCII 列的 "." 掩码无法区分 0x2e 与不可打印字节。
HEX_LINE = re.compile(
    r"^\s*(?:[0-9A-Fa-f]{4,16})\s+((?:[0-9A-Fa-f]{2}\s*)+)")


def restore(src: Path, dst: Path):
    count = 0
    with src.open("r", encoding="utf-8", errors="replace") as fin, \
            dst.open("wb") as fout:
        for lineno, line in enumerate(fin, 1):
            m = HEX_LINE.match(line)
            if not m:
                continue
            try:
                data = bytes.fromhex(m.group(1))
            except ValueError:
                raise SystemExit(f"错误: 第 {lineno} 行十六进制数据无效: "
                                 f"{line.strip()!r}")
            fout.write(data)
            count += len(data)
    return count


def default_output(src: Path, dumping: bool) -> Path:
    if dumping:
        return src.with_name(src.name + ".hex.txt")
    stem = src.name[:-7] if src.name.endswith(".hex.txt") else src.stem
    return src.with_name(stem + ".out")


def main():
    p = argparse.ArgumentParser(description="hexdump 样式转储与逆向还原")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dump", metavar="FILE", help="二进制文件 -> hexdump 文本")
    g.add_argument("--restore", metavar="FILE", help="hexdump 文本 -> 二进制文件")
    p.add_argument("-o", "--output", help="输出文件路径（缺省自动推导）")
    p.add_argument("--cols", type=int, default=16, metavar="N",
                   help="转储每行字节数（默认 16）")
    args = p.parse_args()
    if args.cols <= 0:
        raise SystemExit("错误: --cols 必须为正整数")

    if args.dump:
        src = Path(args.dump)
        if not src.is_file():
            raise SystemExit(f"错误: 输入文件不存在: {src}")
        dst = Path(args.output) if args.output else default_output(src, True)
        total = dump(src, dst, args.cols)
        print(f"转储完成: {src} -> {dst}（共 {total} 字节）")
    else:
        src = Path(args.restore)
        if not src.is_file():
            raise SystemExit(f"错误: 输入文件不存在: {src}")
        dst = Path(args.output) if args.output else default_output(src, False)
        count = restore(src, dst)
        print(f"还原完成: {src} -> {dst}（共 {count} 字节）")


if __name__ == "__main__":
    sys.exit(main())
