#!/usr/bin/env python3
"""EXIF 相机信息 —— 输出厂商、机型、镜头型号与固件版本等设备字段。

字段来源：IFD0 的 Make/Model/Software；Exif 子 IFD 的 BodySerialNumber、
LensMake/LensModel/LensSpecification/LensSerialNumber、ExifVersion；
固件版本来自 MakerNote 启发式解析（Canon: tag 0x0008/0x0010；其他厂商：
在 MakerNote 字节流中扫描 "Firmware Ver.x" 模式），找不到则报告未找到。
只依赖 Python 标准库；支持 JPEG（APP1/Exif 段）与 TIFF 两种容器。

用法:
    python exif-camera-info.py <图片> [更多图片...] [--json]

示例命令:
    python exif-camera-info.py IMG_0001.jpg
    python exif-camera-info.py IMG_0001.jpg --json

退出码: 0=成功  1=找不到 EXIF  2=文件或解析错误
"""

import argparse
import json
import re
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

def as_text(values):
    """把字段值规整成字符串；无值返回 None。"""
    if values is None:
        return None
    if isinstance(values, bytes):
        return values.split(b"\x00", 1)[0].decode("ascii", "replace").strip() or None
    if isinstance(values, list):
        return as_text(scalar(values))
    text = str(values).strip()
    return text or None


def fmt_lens_spec(values):
    """LensSpecification(0xA432)：4 个 RATIONAL -> “35-70 mm, f/2.8-4”。"""
    if not isinstance(values, list) or len(values) < 4:
        return None
    try:
        fmin, fmax, amin, amax = (n / d for n, d in values[:4])
    except ZeroDivisionError:
        return None
    def g(x):
        return f"{x:g}"
    return f"{g(fmin)}-{g(fmax)} mm, f/{g(amin)}-{g(amax)}"


def maker_note_firmware(tiff, exif_entries):
    """从 MakerNote(0x927C) 里启发式找固件版本，返回 (版本, 来源说明)。"""
    mn = None
    mn_offset = None
    for tag, typ, cnt, values, eo in exif_entries:
        if tag == 0x927C and isinstance(values, (bytes, bytearray)):
            mn = bytes(values)
            # MakerNote 数据本身的偏移：小值内联在条目里，大值在堆上
            total = cnt * TYPE_SIZES.get(typ, 1)
            if total <= 4:
                mn_offset = eo + 8 + (4 - total if tiff.endian == "big" else 0)
            else:
                mn_offset = tiff._uint(eo + 8, 4)
            break
    if not mn or mn_offset is None:
        return None, None
    # 1) Canon 风格：MakerNote 起点即标准 IFD（字节序同外层），值偏移相对 MakerNote。
    canon_val = None
    try:
        count = tiff._uint(mn_offset, 2)
        if 0 < count <= 256:
            pos = mn_offset + 2
            for _ in range(count):
                mtag = tiff._uint(pos, 2)
                mtyp = tiff._uint(pos + 2, 2)
                mcnt = tiff._uint(pos + 4, 4)
                if mtag in (0x0008, 0x0010) and mtyp == 2 and mcnt:
                    if mcnt <= 4:
                        base = pos + 8 + (4 - mcnt if tiff.endian == "big" else 0)
                    else:
                        base = mn_offset + tiff._uint(pos + 8, 4)
                    text = tiff._read(base, mcnt).split(b"\x00", 1)[0]
                    if text:
                        canon_val = text.decode("ascii", "replace")
                        break
                pos += 12
    except ExifError:
        canon_val = None
    if canon_val:
        return canon_val, "MakerNote (Canon tag 0x0008/0x0010)"
    # 2) 通用启发式：在 MakerNote 字节流中扫描 “Firmware [Ver.] x.y.z”。
    m = re.search(rb"(?i)firmware[\s:=]*ver\.?[\s:]*([\x21-\x7e][\x20-\x7e]{0,30})", mn)
    if not m:
        m = re.search(rb"(?i)firmware[\s:=]*([\x21-\x7e][\x20-\x7e]{0,30})", mn)
    if m:
        text = m.group(1).decode("ascii", "replace").strip()
        if text:
            return text, "MakerNote 启发式扫描"
    return None, None


def gather(path):
    """收集设备字段，返回 ([(中文标题, json键, 值)], 固件来源)。"""
    tiff = load_exif_tiff(path)
    ifd0, _next_ifd = tiff.read_ifd(tiff.ifd0_offset)
    tags0 = entry_map(ifd0)
    exif_entries = []
    ptr = scalar(tags0.get(0x8769))
    if isinstance(ptr, int) and ptr:
        exif_entries, _ = tiff.read_ifd(ptr)
    tags_exif = entry_map(exif_entries)
    fw_val, fw_src = maker_note_firmware(tiff, exif_entries)
    fields = [
        ("厂商 (Make)", "make", as_text(tags0.get(0x010F))),
        ("机型 (Model)", "model", as_text(tags0.get(0x0110))),
        ("软件 (Software)", "software", as_text(tags0.get(0x0131))),
        ("EXIF 规范版本 (ExifVersion)", "exif_version", as_text(tags_exif.get(0x9000))),
        ("固件版本 (Firmware)", "firmware", fw_val),
        ("机身序列号 (BodySerialNumber)", "body_serial", as_text(tags_exif.get(0xA431))),
        ("镜头厂商 (LensMake)", "lens_make", as_text(tags_exif.get(0xA433))),
        ("镜头型号 (LensModel)", "lens_model", as_text(tags_exif.get(0xA434))),
        ("镜头规格 (LensSpecification)", "lens_spec", fmt_lens_spec(tags_exif.get(0xA432))),
        ("镜头序列号 (LensSerialNumber)", "lens_serial", as_text(tags_exif.get(0xA435))),
    ]
    return fields, fw_src


def process(path, as_json):
    fields, fw_src = gather(path)
    if as_json:
        obj = {"file": str(path)}
        for _title, key, value in fields:
            obj[key] = value
        obj["firmware_source"] = fw_src
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return
    print(f"文件: {path}")
    for title, _key, value in fields:
        if value is None:
            print(f"  {title}: 未记录")
        elif title.startswith("固件版本"):
            print(f"  {title}: {value}  [来源: {fw_src}]")
        else:
            print(f"  {title}: {value}")


def main(argv=None):
    setup_stdio()
    parser = argparse.ArgumentParser(
        description="输出 EXIF 设备字段：厂商、机型、镜头、固件版本等")
    parser.add_argument("images", nargs="+", help="JPEG/TIFF 图片路径（可多个）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（键为英文）")
    args = parser.parse_args(argv)
    if args.json and len(args.images) > 1:
        objs = []
        rc_all = 0
        for path in args.images:
            try:
                fields, fw_src = gather(path)
            except (ExifError, OSError) as exc:
                print(f"错误: {path}: {exc}", file=sys.stderr)
                rc_all = 1
                continue
            obj = {"file": str(path)}
            for _t, key, value in fields:
                obj[key] = value
            obj["firmware_source"] = fw_src
            objs.append(obj)
        if objs or rc_all == 0:
            print(json.dumps(objs, ensure_ascii=False, indent=2))
        return rc_all
    rc = 0
    for path in args.images:
        try:
            process(path, args.json)
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
