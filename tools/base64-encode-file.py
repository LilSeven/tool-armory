"""文件 Base64 编解码：在二进制文件与 Base64 文本之间互转，分块处理支持大文件。

仅使用 Python 标准库。--encode 将二进制文件编码为 Base64 文本（按行折行），
--decode 将 Base64 文本还原为二进制文件；分块读写，内存占用恒定，支持大文件。
输出文件缺省规则：编码加 .b64 后缀，解码去掉 .b64 后缀（无后缀则加 .out）。

示例:
  python base64-encode-file.py --encode photo.jpg
  python base64-encode-file.py --encode photo.jpg -o photo.b64 --wrap 0
  python base64-encode-file.py --decode photo.b64 -o restored.jpg
"""
import argparse
import base64
import binascii
import sys
from pathlib import Path

CHUNK = 3 * 1024 * 1024  # 3 MiB，编码时按 3 字节对齐分块


def encode(src: Path, dst: Path, wrap: int):
    b64 = base64.b64encode
    line_parts = []
    with src.open("rb") as fin, dst.open("w", encoding="ascii", newline="") as fout:
        while True:
            data = fin.read(CHUNK)
            if not data:
                break
            text = b64(data)
            if wrap == 0:
                fout.write(text.decode("ascii"))
            else:
                line_parts.append(text)
                pending = b"".join(line_parts)
                usable = len(pending) - (len(pending) % wrap)
                if usable:
                    fout.write(pending[:usable].decode("ascii") + "\n")
                    line_parts = [pending[usable:]]
                else:
                    line_parts = [pending]
        tail = b"".join(line_parts)
        if tail:
            fout.write(tail.decode("ascii") + "\n")


def decode(src: Path, dst: Path):
    dec = base64.b64decode
    with src.open("r", encoding="ascii", errors="strict") as fin, \
            dst.open("wb") as fout:
        for line in fin:
            stripped = "".join(line.split())
            if not stripped:
                continue
            try:
                fout.write(dec(stripped))
            except (binascii.Error, ValueError) as e:
                raise SystemExit(f"错误: 无效的 Base64 数据: {e}")


def default_output(src: Path, encoding: bool) -> Path:
    if encoding:
        return src.with_name(src.name + ".b64")
    if src.suffix == ".b64":
        return src.with_suffix("")
    return src.with_name(src.stem + ".out")


def main():
    p = argparse.ArgumentParser(description="文件与 Base64 文本互转（分块，支持大文件）")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--encode", metavar="FILE", help="二进制文件 -> Base64 文本")
    g.add_argument("--decode", metavar="FILE", help="Base64 文本 -> 二进制文件")
    p.add_argument("-o", "--output", help="输出文件路径（缺省自动推导）")
    p.add_argument("--wrap", type=int, default=76, metavar="N",
                   help="编码输出按 N 字符折行，0 表示不折行（默认 76）")
    args = p.parse_args()
    if args.wrap < 0:
        raise SystemExit("错误: --wrap 不能为负")

    if args.encode:
        src = Path(args.encode)
        if not src.is_file():
            raise SystemExit(f"错误: 输入文件不存在: {src}")
        dst = Path(args.output) if args.output else default_output(src, True)
        encode(src, dst, args.wrap)
        print(f"编码完成: {src} -> {dst}（{dst.stat().st_size} 字节）")
    else:
        src = Path(args.decode)
        if not src.is_file():
            raise SystemExit(f"错误: 输入文件不存在: {src}")
        dst = Path(args.output) if args.output else default_output(src, False)
        decode(src, dst)
        print(f"解码完成: {src} -> {dst}（{dst.stat().st_size} 字节）")


if __name__ == "__main__":
    sys.exit(main())
