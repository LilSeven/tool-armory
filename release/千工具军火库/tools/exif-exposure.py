#!/usr/bin/env python3
"""EXIF 曝光参数 —— 输出光圈、快门、ISO、焦距、曝光补偿与闪光是否触发。

字段来源：Exif 子 IFD 的 FNumber(0x829D)、ExposureTime(0x829A)、
ISOSpeedRatings(0x8827)、FocalLength(0x920A)、ExposureBias(0x9204)、
Flash(0x9209)；另附 35mm 等效焦距(0xA405) 与曝光程序(0x8822) 供参考。
快门以 1/250 s 分数形式显示，闪光灯按位解码（触发/模式/回光/防红眼）。
只依赖 Python 标准库；支持 JPEG（APP1/Exif 段）与 TIFF 两种容器。

用法:
    python exif-exposure.py <图片> [更多图片...]

示例命令:
    python exif-exposure.py IMG_0001.jpg
    python exif-exposure.py IMG_0001.jpg IMG_0002.tiff

退出码: 0=成功（缺字段时显示“未记录”）  1=找不到 EXIF  2=文件或解析错误
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


def rational(values):
    """RATIONAL/SRATIONAL -> 浮点；无效返回 None。"""
    pair = scalar(values)
    if isinstance(pair, tuple) and len(pair) == 2 and pair[1] != 0:
        return pair[0] / pair[1]
    if isinstance(pair, (int, float)):
        return float(pair)
    return None


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

EXPOSURE_PROGRAMS = {
    0: "未定义", 1: "手动", 2: "程序自动", 3: "光圈优先", 4: "快门优先",
    5: "创意(慢速)程序", 6: "动作(高速)程序", 7: "人像", 8: "风景",
    9: "B 门", 10: "创意程序 B",
}


def fmt_shutter(sec):
    """快门时间 -> “1/250 s” 或 “2 s”。"""
    if sec is None or sec <= 0:
        return None
    if sec >= 1:
        return f"{sec:g} s"
    denom = round(1.0 / sec)
    if denom > 0 and abs(1.0 / denom - sec) / sec <= 0.02:
        return f"1/{denom} s"
    return f"{sec:.4f} s"


def fmt_ev(value):
    """曝光补偿 -> “-0.33 EV” 样式（去掉多余的 0）。"""
    text = f"{value:+.2f}".rstrip("0")
    if text.endswith(("+", "-", ".")):
        text += "0"
    return f"{text} EV"


def decode_flash(value):
    """按 EXIF 规范逐位解码 Flash 字段。"""
    if not isinstance(value, int) or value < 0:
        return None
    fired = value & 0x01
    ret = (value >> 1) & 0x03
    mode = (value >> 3) & 0x03
    no_func = (value >> 5) & 0x01
    redeye = (value >> 6) & 0x01
    parts = ["触发" if fired else "未触发"]
    mode_text = {1: "强制闪光", 2: "强制未闪光", 3: "自动"}.get(mode)
    if mode_text:
        parts.append(f"模式={mode_text}")
    if fired and ret == 2:
        parts.append("未检测到回光")
    elif fired and ret == 3:
        parts.append("检测到回光")
    if no_func:
        parts.append("相机无闪光功能")
    if redeye:
        parts.append("防红眼")
    return "，".join(parts)


def process(path):
    tiff = load_exif_tiff(path)
    ifd0, _next_ifd = tiff.read_ifd(tiff.ifd0_offset)
    ptr = scalar(entry_map(ifd0).get(0x8769))
    if not (isinstance(ptr, int) and ptr):
        raise ExifError("IFD0 没有 Exif 子 IFD 指针 (0x8769)，无曝光参数")
    exif_entries, _ = tiff.read_ifd(ptr)
    tags = entry_map(exif_entries)

    aperture = rational(tags.get(0x829D))
    shutter = fmt_shutter(rational(tags.get(0x829A)))
    iso = scalar(tags.get(0x8827))
    if isinstance(iso, list):
        iso = ", ".join(str(x) for x in iso) if iso else None
    focal = rational(tags.get(0x920A))
    focal35 = scalar(tags.get(0xA405))
    bias = rational(tags.get(0x9204))
    flash = decode_flash(scalar(tags.get(0x9209)))
    program = scalar(tags.get(0x8822))

    print(f"文件: {path}")
    print(f"  光圈 (FNumber): f/{aperture:g}" if aperture and aperture > 0
          else "  光圈 (FNumber): 未记录")
    print(f"  快门 (ExposureTime): {shutter}" if shutter
          else "  快门 (ExposureTime): 未记录")
    print(f"  感光度 (ISO): ISO {iso}" if iso is not None
          else "  感光度 (ISO): 未记录")
    if focal and focal > 0:
        line = f"  焦距 (FocalLength): {focal:g} mm"
        if isinstance(focal35, int) and focal35 > 0:
            line += f"（35mm 等效: {focal35} mm）"
        print(line)
    else:
        print("  焦距 (FocalLength): 未记录")
    print(f"  曝光补偿 (ExposureBias): {fmt_ev(bias)}" if bias is not None
          else "  曝光补偿 (ExposureBias): 未记录")
    print(f"  闪光灯 (Flash): {flash}" if flash
          else "  闪光灯 (Flash): 未记录")
    if isinstance(program, int) and program in EXPOSURE_PROGRAMS:
        print(f"  曝光程序 (ExposureProgram): {EXPOSURE_PROGRAMS[program]}")


def main(argv=None):
    setup_stdio()
    parser = argparse.ArgumentParser(
        description="输出 EXIF 曝光参数：光圈、快门、ISO、焦距、曝光补偿、闪光")
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
