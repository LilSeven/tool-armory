#!/usr/bin/env python3
"""EXIF 缩略图提取 —— 定位 IFD1 的 JPEGInterchangeFormat 数据，
把内嵌缩略图另存为独立 JPEG。

定位过程：IFD0 的 next-IFD 指针 -> IFD1；取 Compression(0x0103) 校验为 6
(JPEG)，再取 JPEGInterchangeFormat(0x0201) 偏移与
JPEGInterchangeFormatLength(0x0202) 长度，切出 FFD8..FFD9 字节另存。
只依赖 Python 标准库；支持 JPEG（APP1/Exif 段）与 TIFF 两种容器。

用法:
    python exif-thumbnail-extract.py <图片> [-o 输出.jpg]

示例命令:
    python exif-thumbnail-extract.py IMG_0001.jpg
    python exif-thumbnail-extract.py IMG_0001.tiff -o thumb.jpg

退出码: 0=成功提取  1=无内嵌缩略图  2=文件或解析错误
"""

import argparse
import struct
import sys
from pathlib import Path

# ---------- 公共解析核心（单文件工具，核心代码在各工具间有意重复） ----------

TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8,
              11: 4, 12: 8, 13: 4}


class ExifError(Exception):
    """EXIF/TIFF 解析错误。"""


class TiffReader:
    """只读 TIFF/EXIF 结构解析器（TIFF 6.0 常用类型）。"""

    def __init__(self, data):
        if len(data) < 8:
            raise ExifError("TIFF 数据不足 8 字节")
        if data[:2] == b"II":
            self.endian = "little"
        elif data[:2] == b"MM":
            self.endian = "big"
        else:
            raise ExifError("缺少 TIFF 字节序标记 (II/MM)")
        if int.from_bytes(data[2:4], self.endian) != 42:
            raise ExifError("TIFF 魔数不是 42")
        self.data = data
        self.ifd0_offset = int.from_bytes(data[4:8], self.endian)
        if not 8 <= self.ifd0_offset < len(data):
            raise ExifError(f"IFD0 偏移越界: {self.ifd0_offset}")

    def _read(self, offset, size):
        if offset < 0 or offset + size > len(self.data):
            raise ExifError(f"TIFF 读取越界: offset={offset} size={size}")
        return self.data[offset:offset + size]

    def _uint(self, offset, size):
        return int.from_bytes(self._read(offset, size), self.endian)

    def read_ifd(self, offset):
        """解析一个 IFD，返回 ([(tag, type, count, values, entry_offset)], next_ifd)。"""
        count = self._uint(offset, 2)
        if count == 0 or count > 4096:
            raise ExifError(f"IFD 条目数异常: {count}")
        entries = []
        pos = offset + 2
        for _ in range(count):
            tag = self._uint(pos, 2)
            typ = self._uint(pos + 2, 2)
            cnt = self._uint(pos + 4, 4)
            entries.append((tag, typ, cnt, self._read_values(pos, typ, cnt), pos))
            pos += 12
        return entries, self._uint(pos, 4)

    def _read_values(self, entry_offset, typ, count):
        unit = TYPE_SIZES.get(typ)
        if unit is None or count == 0:
            return None
        total = unit * count
        if total <= 4:
            base = entry_offset + 8 + (4 - total if self.endian == "big" else 0)
        else:
            base = self._uint(entry_offset + 8, 4)
        raw = self._read(base, total)
        if typ == 2:
            return raw.split(b"\x00", 1)[0].decode("ascii", "replace")
        if typ in (1, 6, 7):
            return bytes(raw)
        bo = ">" if self.endian == "big" else "<"
        if typ == 3:
            return list(struct.unpack(f"{bo}{count}H", raw))
        if typ == 8:
            return list(struct.unpack(f"{bo}{count}h", raw))
        if typ in (4, 13):
            return list(struct.unpack(f"{bo}{count}I", raw))
        if typ == 9:
            return list(struct.unpack(f"{bo}{count}i", raw))
        if typ in (5, 10):
            fmt = "i" if typ == 10 else "I"
            nums = struct.unpack(f"{bo}{count * 2}{fmt}", raw)
            return [(nums[i * 2], nums[i * 2 + 1]) for i in range(count)]
        if typ == 11:
            return list(struct.unpack(f"{bo}{count}f", raw))
        if typ == 12:
            return list(struct.unpack(f"{bo}{count}d", raw))
        return None


def entry_map(entries):
    """IFD 条目 -> {tag: values}（同 tag 保留第一个）。"""
    out = {}
    for tag, _typ, _cnt, values, _eo in entries:
        out.setdefault(tag, values)
    return out


def scalar(values):
    """单值化：list 取第一个，bytes/None 原样返回。"""
    if isinstance(values, list):
        return values[0] if values else None
    return values


def iter_jpeg_segments(data):
    """遍历 JPEG 段，产出 (marker, payload)；扫到 SOS/EOI 即止。"""
    if data[:2] != b"\xff\xd8":
        raise ExifError("不是 JPEG 文件（缺少 SOI 标记）")
    pos, n = 2, len(data)
    while pos < n:
        if data[pos] != 0xFF:
            raise ExifError(f"JPEG 标记流损坏: offset={pos}")
        while pos < n and data[pos] == 0xFF:
            pos += 1
        if pos >= n:
            break
        marker = data[pos]
        pos += 1
        if marker == 0x00 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker in (0xD8, 0xD9, 0xDA):
            return
        if pos + 2 > n:
            raise ExifError("JPEG 在段长度字段处被截断")
        seg_len = int.from_bytes(data[pos:pos + 2], "big")
        if seg_len < 2:
            raise ExifError(f"JPEG 段长度异常: {seg_len}")
        payload = data[pos + 2:pos + seg_len]
        if len(payload) < seg_len - 2:
            raise ExifError("JPEG 段内容被截断")
        yield marker, payload
        pos += seg_len


def load_exif_tiff(path):
    """读取文件并返回 Exif 的 TiffReader。支持 JPEG(APP1/Exif) 与 TIFF 容器。"""
    data = Path(path).read_bytes()
    if data[:4] in (b"II\x2a\x00", b"MM\x00\x2a"):
        return TiffReader(data)
    if data[:2] == b"\xff\xd8":
        for marker, payload in iter_jpeg_segments(data):
            if marker == 0xE1 and payload[:6] == b"Exif\x00\x00":
                return TiffReader(payload[6:])
        raise ExifError("未找到 EXIF 数据（JPEG 中没有 APP1/Exif 段）")
    raise ExifError("无法识别的容器格式：只支持 JPEG 或 TIFF")


def setup_stdio():
    """Windows 控制台下尽量用 UTF-8 输出，避免中文乱码或编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.encoding and stream.encoding.lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

# ---------- 本工具逻辑 ----------

def default_output(path):
    src = Path(path)
    return src.with_name(src.stem + "_thumb.jpg")


def extract(path, out_path):
    """提取 IFD1 缩略图并写出，返回 (字节数, 信息 dict)。"""
    tiff = load_exif_tiff(path)
    ifd0, next_ifd = tiff.read_ifd(tiff.ifd0_offset)
    if not next_ifd:
        raise ExifError("IFD0 之后没有 IFD1（该文件未内嵌缩略图）")
    ifd1, _ = tiff.read_ifd(next_ifd)
    tags = entry_map(ifd1)
    compression = scalar(tags.get(0x0103))
    offset = scalar(tags.get(0x0201))
    length = scalar(tags.get(0x0202))
    if not isinstance(offset, int) or not isinstance(length, int):
        raise ExifError("IFD1 缺少 JPEGInterchangeFormat(0x0201/0x0202) 指针")
    if compression is not None and compression != 6:
        raise ExifError(f"IFD1 缩略图不是 JPEG 编码 (Compression={compression})，"
                        "本工具只支持 Compression=6 (JPEG)")
    blob = tiff._read(offset, length)
    if blob[:2] != b"\xff\xd8" or blob[-2:] != b"\xff\xd9":
        raise ExifError("缩略图数据不符合 JPEG 结构（应为 FFD8..FFD9）")
    Path(out_path).write_bytes(blob)

    width = scalar(tags.get(0x0100))
    height = scalar(tags.get(0x0101))
    info = {
        "ifd1_offset": next_ifd,
        "jpeg_offset": offset,
        "length": length,
        "size": f"{width}x{height}" if isinstance(width, int) and isinstance(height, int)
                and width > 0 and height > 0 else None,
    }
    return len(blob), info


def process(path, out_path):
    size, info = extract(path, out_path)
    print(f"输入: {path}")
    print(f"  IFD1 偏移: {info['ifd1_offset']}，JPEGInterchangeFormat: "
          f"offset={info['jpeg_offset']} length={info['length']} (Compression=6 JPEG)")
    if info["size"]:
        print(f"  缩略图尺寸 (IFD1): {info['size']}")
    print(f"  已提取 {size} 字节 -> {out_path}")


def main(argv=None):
    setup_stdio()
    parser = argparse.ArgumentParser(
        description="从 EXIF IFD1 提取内嵌缩略图另存为独立 JPEG")
    parser.add_argument("image", help="JPEG/TIFF 图片路径")
    parser.add_argument("-o", "--output", help="输出 JPEG 路径"
                        "（缺省为 <输入名>_thumb.jpg）")
    args = parser.parse_args(argv)
    out_path = args.output or default_output(args.image)
    if Path(out_path).resolve() == Path(args.image).resolve():
        print("错误: 输出路径不能与输入文件相同", file=sys.stderr)
        return 2
    try:
        process(args.image, out_path)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {args.image}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    except ExifError as exc:
        print(f"错误: {args.image}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
