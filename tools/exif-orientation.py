#!/usr/bin/env python3
"""EXIF 方向读取 —— 读取 JPEG/TIFF 的 EXIF Orientation(0x0112) 标志，并翻译成
“需顺时针旋转 90°”等具体的显示修正说明。

只依赖 Python 标准库；支持 JPEG（APP1/Exif 段）与 TIFF 两种容器。
Orientation 取值 1-8 的含义按 EXIF 规范翻译：1=正常、2=水平镜像、3=旋转 180°、
4=垂直镜像、5/7=对角线转置、6=顺时针转 90°、8=逆时针转 90°。

用法:
    python exif-orientation.py <图片> [更多图片...]

示例命令:
    python exif-orientation.py IMG_0001.jpg
    python exif-orientation.py IMG_0001.jpg IMG_0002.tiff

退出码: 0=成功（无 Orientation 标签时按 1/正常 处理）  1=找不到 EXIF  2=文件或解析错误
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

ORIENTATION_INFO = {
    1: ("Horizontal (normal)", "拍摄方向正常（0 行=顶部，0 列=左侧）",
        "无需修正，按存储方向直接显示", False),
    2: ("Mirror horizontal", "画面左右镜像（0 行=顶部，0 列=右侧）",
        "需水平翻转（左右镜像）后显示", False),
    3: ("Rotate 180", "画面上下颠倒（0 行=底部，0 列=右侧）",
        "需旋转 180° 后显示", False),
    4: ("Mirror vertical", "画面上下镜像（0 行=底部，0 列=左侧）",
        "需垂直翻转（上下镜像）后显示", False),
    5: ("Mirror horizontal and rotate 270 CW", "画面沿主对角线转置（0 行=左侧，0 列=顶部）",
        "需先水平翻转，再逆时针旋转 90°（宽高互换）", True),
    6: ("Rotate 90 CW", "拍摄时相机顺时针竖握：0 行为视觉右侧、0 列为视觉顶部",
        "需顺时针旋转 90°（宽高互换）", True),
    7: ("Mirror horizontal and rotate 90 CW", "画面沿反对角线转置（0 行=右侧，0 列=底部）",
        "需先水平翻转，再顺时针旋转 90°（宽高互换）", True),
    8: ("Rotate 270 CW", "拍摄时相机逆时针竖握：0 行为视觉左侧、0 列为视觉底部",
        "需逆时针旋转 90°（即顺时针 270°，宽高互换）", True),
}


def process(path):
    tiff = load_exif_tiff(path)
    ifd0, _next_ifd = tiff.read_ifd(tiff.ifd0_offset)
    tags = entry_map(ifd0)
    raw = scalar(tags.get(0x0112))
    print(f"文件: {path}")
    if raw is None:
        print("  方向标志: 未找到 Orientation 标签")
        print("  显示修正: 无需修正，按 1（Horizontal normal）处理")
        return
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = -1
    info = ORIENTATION_INFO.get(val)
    if info is None:
        print(f"  方向标志: {raw!r}（超出 1-8 合法范围，无法翻译）")
        return
    name, meaning, fix, swap = info
    print(f"  方向标志: {val} ({name})")
    print(f"  拍摄状态: {meaning}")
    print(f"  显示修正: {fix}")
    w = scalar(tags.get(0x0100))
    h = scalar(tags.get(0x0101))
    if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
        if swap:
            print(f"  尺寸变化: {w}x{h} -> {h}x{w}")
        else:
            print(f"  尺寸保持: {w}x{h}")


def main(argv=None):
    setup_stdio()
    parser = argparse.ArgumentParser(
        description="读取 EXIF Orientation 标志并翻译成具体显示修正说明")
    parser.add_argument("images", nargs="+", help="JPEG/TIFF 图片路径（可多个）")
    args = parser.parse_args(argv)
    rc = 0
    for path in args.images:
        try:
            process(path)
        except FileNotFoundError:
            print(f"错误: 找不到文件 {path}", file=sys.stderr)
            rc = 2
        except OSError as exc:
            print(f"错误: {path}: {exc}", file=sys.stderr)
            rc = 2
        except ExifError as exc:
            print(f"错误: {path}: {exc}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
