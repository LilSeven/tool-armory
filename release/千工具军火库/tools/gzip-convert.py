"""压缩格式互转：在 gzip、bz2、xz 三种压缩格式之间转换单个文件，可选压缩级别。

仅使用 Python 标准库。根据源文件扩展名自动识别格式（.gz/.bz2/.xz），
--to 指定目标格式与级别（如 xz:9），转出文件加相应后缀；解压输出去后缀；
源文件默认保留，加 --rm 转换成功后删除。

示例:
  python gzip-convert.py data.txt --to gz:9
  python gzip-convert.py data.txt.gz --to xz        # 自动识别 .gz 并解压再压为 xz
  python gzip-convert.py data.txt.xz --to bz2:5 --rm
"""
import argparse
import bz2
import gzip
import lzma
import shutil
import sys
from pathlib import Path

FORMATS = {
    "gz": {"suffix": ".gz", "open": gzip.open, "levels": (1, 9)},
    "bz2": {"suffix": ".bz2", "open": bz2.open, "levels": (1, 9)},
    "xz": {"suffix": ".xz", "open": lzma.open, "levels": (0, 9)},
}
COPY_BUF = 1 << 20


def detect_format(path: Path) -> str:
    """按扩展名识别压缩格式，无法识别则视为未压缩（返回 None）。"""
    for name, info in FORMATS.items():
        if path.suffix.lower() == info["suffix"]:
            return name
    return None


def parse_target(spec: str):
    parts = spec.split(":", 1)
    fmt = parts[0].lower()
    if fmt not in FORMATS:
        raise SystemExit(f"错误: 目标格式须为 gz/bz2/xz，得到 '{fmt}'")
    level = None
    if len(parts) == 2:
        try:
            level = int(parts[1])
        except ValueError:
            raise SystemExit(f"错误: 压缩级别须为整数，得到 '{parts[1]}'")
        lo, hi = FORMATS[fmt]["levels"]
        if not lo <= level <= hi:
            raise SystemExit(f"错误: {fmt} 压缩级别须在 {lo}..{hi}")
    return fmt, level


LEVEL_KWARG = {"gz": "compresslevel", "bz2": "compresslevel", "xz": "preset"}


def convert(src: Path, dst: Path, src_fmt, dst_fmt, level):
    src_open = FORMATS[src_fmt]["open"] if src_fmt else open
    dst_open = FORMATS[dst_fmt]["open"]
    # gzip/bz2 用 compresslevel，lzma/xz 用 preset
    kwargs = {LEVEL_KWARG[dst_fmt]: level} if level is not None else {}
    with src_open(src, "rb") as fin, dst_open(dst, "wb", **kwargs) as fout:
        shutil.copyfileobj(fin, fout, COPY_BUF)


def main():
    p = argparse.ArgumentParser(description="gzip/bz2/xz 压缩格式互转")
    p.add_argument("input", help="输入文件（.gz/.bz2/.xz 或未压缩文件）")
    p.add_argument("--to", required=True, metavar="FMT[:LEVEL]",
                   help="目标格式 gz|bz2|xz，可加压缩级别，如 xz:9")
    p.add_argument("-o", "--output", help="输出文件路径（缺省自动加/去后缀）")
    p.add_argument("--rm", action="store_true", help="转换成功后删除源文件")
    args = p.parse_args()

    src = Path(args.input)
    if not src.is_file():
        raise SystemExit(f"错误: 输入文件不存在: {src}")
    dst_fmt, level = parse_target(args.to)
    src_fmt = detect_format(src)
    if src_fmt == dst_fmt and level is None:
        raise SystemExit(f"错误: 源已是 {dst_fmt} 格式，未指定新级别，无事可做")

    if args.output:
        dst = Path(args.output)
    elif src_fmt:
        dst = src.with_suffix(FORMATS[dst_fmt]["suffix"])
    else:
        dst = src.with_name(src.name + FORMATS[dst_fmt]["suffix"])
    if dst.resolve() == src.resolve():
        raise SystemExit("错误: 输出路径与输入相同，请用 -o 指定其他文件")

    if level is None:
        level = 6  # 各格式统一默认级别 6（xz 对应 preset 6）

    convert(src, dst, src_fmt, dst_fmt, level)
    print(f"转换完成: {src}({src_fmt or 'plain'}) -> {dst}({dst_fmt}, "
          f"level={level})，{dst.stat().st_size} 字节")
    if args.rm:
        src.unlink()
        print(f"已删除源文件: {src}")


if __name__ == "__main__":
    sys.exit(main())
