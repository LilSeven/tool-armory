#!/usr/bin/env python3
"""XMP 提取 —— 在 JPEG/PNG/TIFF 中定位 XMP 元数据包并原样输出其 XML 文本。

定位方式：
  JPEG  APP1 段，命名空间 "http://ns.adobe.com/xap/1.0/"（另支持扩展 XMP
        "http://ns.adobe.com/xmp/extension/" 的分片重组）；
  PNG   iTXt 块，关键字 "XML:com.adobe.xmp"（含 zlib 压缩变体）；
  TIFF  IFD0 的 XMLPacket 标签 0x02BC；
  兜底  在整份文件中扫描 <?xpacket ...?> 包或 <x:xmpmeta> 元素。
XML 字节原样写出（不重排、不改码），默认打到 stdout，可用 -o 存盘。
只依赖 Python 标准库。

用法:
    python xmp-extract.py <文件> [-o 输出.xml]

示例命令:
    python xmp-extract.py IMG_0001.jpg
    python xmp-extract.py design.png -o sidecar.xmp

退出码: 0=找到并输出  1=未找到 XMP  2=文件或解析错误
"""

import argparse
import struct
import sys
import zlib
from pathlib import Path

# ---------- 公共解析核心（单文件工具，核心代码在各工具间有意重复） ----------

TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8,
              11: 4, 12: 8, 13: 4}


class ExifError(Exception):
    """解析错误。"""


class TiffReader:
    """只读 TIFF 结构解析器（TIFF 6.0 常用类型）。"""

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


def setup_stdio():
    """Windows 控制台下尽量用 UTF-8 输出，避免中文乱码或编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.encoding and stream.encoding.lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

# ---------- 本工具逻辑 ----------

XMP_STD_NS = b"http://ns.adobe.com/xap/1.0/\x00"
XMP_EXT_NS = b"http://ns.adobe.com/xmp/extension/\x00"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
XMPMETA_END = b"</x:xmpmeta>"


def extract_from_jpeg(data):
    """JPEG APP1：标准 XMP 段；没有标准段时尝试重组扩展 XMP 分片。"""
    standard = None
    ext_parts = {}
    for marker, payload in iter_jpeg_segments(data):
        if marker != 0xE1:
            continue
        if payload.startswith(XMP_STD_NS):
            standard = payload[len(XMP_STD_NS):]
        elif payload.startswith(XMP_EXT_NS):
            rest = payload[len(XMP_EXT_NS):]
            if len(rest) >= 40:
                _guid = rest[:32]
                _total = int.from_bytes(rest[32:36], "big")
                offset = int.from_bytes(rest[36:40], "big")
                ext_parts[offset] = rest[40:]
    if standard is not None:
        return standard, "JPEG APP1 (http://ns.adobe.com/xap/1.0/)"
    if ext_parts:
        joined = b"".join(ext_parts[k] for k in sorted(ext_parts))
        return joined, "JPEG APP1 (扩展 XMP 分片重组)"
    return None, None


def extract_from_png(data):
    """PNG iTXt 块：关键字 XML:com.adobe.xmp，支持压缩标志=1 的 zlib 变体。"""
    pos = 8
    n = len(data)
    while pos + 8 <= n:
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if len(body) < length:
            raise ExifError("PNG 数据块被截断")
        if ctype == b"iTXt":
            keyword, _, rest = body.partition(b"\x00")
            if keyword == b"XML:com.adobe.xmp" and len(rest) >= 2:
                comp_flag, _comp_method = rest[0], rest[1]
                tail = rest[2:].split(b"\x00", 2)
                text = tail[2] if len(tail) == 3 else b""
                if comp_flag == 1:
                    try:
                        text = zlib.decompress(text)
                    except zlib.error as exc:
                        raise ExifError(f"PNG iTXt 中 XMP 解压失败: {exc}") from exc
                return text, "PNG iTXt (XML:com.adobe.xmp)"
        if ctype == b"IEND":
            break
        pos += 12 + length
    return None, None


def extract_from_tiff(data):
    """TIFF IFD0 的 XMLPacket 标签 0x02BC（BYTE/UNDEFINED）。"""
    tiff = TiffReader(data)
    ifd0, _next_ifd = tiff.read_ifd(tiff.ifd0_offset)
    for tag, typ, _count, values, _eo in ifd0:
        if tag == 0x02BC and isinstance(values, (bytes, bytearray)):
            xml = bytes(values).rstrip(b"\x00")
            return xml, f"TIFF tag 0x02BC XMLPacket (type={typ})"
    return None, None


def scan_raw(data):
    """兜底：在整份文件中扫描 xpacket 包或 x:xmpmeta 元素。"""
    i = data.find(b"<?xpacket begin=")
    if i >= 0:
        j = data.find(b"<?xpacket end", i + 16)
        if j >= 0:
            k = data.find(b"?>", j)
            if k >= 0:
                return data[i:k + 2], "原始字节扫描 (xpacket 包)"
    i = data.find(b"<x:xmpmeta")
    if i >= 0:
        j = data.find(XMPMETA_END, i)
        if j >= 0:
            return data[i:j + len(XMPMETA_END)], "原始字节扫描 (x:xmpmeta 元素)"
    return None, None


def extract(path):
    """按容器类型提取 XMP，返回 (xml字节, 来源说明)。找不到返回 (None, None)。"""
    data = Path(path).read_bytes()
    xml = source = None
    if data[:2] == b"\xff\xd8":
        xml, source = extract_from_jpeg(data)
    elif data[:8] == PNG_MAGIC:
        xml, source = extract_from_png(data)
    elif data[:4] in (b"II\x2a\x00", b"MM\x00\x2a"):
        xml, source = extract_from_tiff(data)
    if xml is None:
        xml, source = scan_raw(data)
    return xml, source


def main(argv=None):
    setup_stdio()
    parser = argparse.ArgumentParser(
        description="定位 JPEG/PNG/TIFF 中的 XMP 包并原样输出 XML 文本")
    parser.add_argument("file", help="JPEG/PNG/TIFF 文件路径")
    parser.add_argument("-o", "--output", help="把 XML 写入该文件（缺省打到 stdout）")
    args = parser.parse_args()
    try:
        xml, source = extract(args.file)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {args.file}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    except (ExifError, struct.error) as exc:
        print(f"错误: {args.file}: {exc}", file=sys.stderr)
        return 2
    if xml is None:
        print(f"错误: {args.file}: 未找到 XMP 元数据包", file=sys.stderr)
        return 1
    if not xml.endswith(b"\n"):
        xml += b"\n"
    if args.output:
        Path(args.output).write_bytes(xml)
        print(f"已提取 XMP（来源: {source}，{len(xml)} 字节）-> {args.output}")
    else:
        sys.stdout.buffer.write(xml)
        sys.stdout.buffer.flush()
        print(f"[来源: {source}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
