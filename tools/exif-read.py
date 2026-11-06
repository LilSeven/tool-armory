#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXIF 读取 - 解析 JPEG APP1 中的 TIFF 结构, 列出 IFD0/Exif/GPS 全部标签。

用途:
  定位 JPEG 文件中的 EXIF APP1 段, 解析其内嵌 TIFF 结构, 依次遍历 IFD0、
  Exif IFD、(Interop IFD)、GPS IFD 以及缩略图 IFD 链, 以
  "标签名 (tag 编号 类型 计数): 可读值" 的形式逐项输出
  (数值型标签附常见枚举释义, 有理数附小数值)。

用法:
  python exif-read.py IMAGE.jpg [--json]
  python exif-read.py --selftest     # 构造合成 EXIF JPEG 自测(II 与 MM 两种字节序)

示例:
  python exif-read.py photo.jpg
  python exif-read.py photo.jpg --json

退出码: 0 成功; 1 不是 JPEG / 无 EXIF / 解析失败; 2 用法错误。
仅用 Python 标准库。
"""

import argparse
import json
import os
import shutil
import struct
import sys
import tempfile

# ---------------- EXIF/TIFF 解析核心 ----------------

TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1,
              8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
TYPE_NAMES = {1: 'BYTE', 2: 'ASCII', 3: 'SHORT', 4: 'LONG', 5: 'RATIONAL',
              6: 'SBYTE', 7: 'UNDEFINED', 8: 'SSHORT', 9: 'SLONG',
              10: 'SRATIONAL', 11: 'FLOAT', 12: 'DOUBLE'}


class ExifError(ValueError):
    """EXIF/TIFF 解析错误。"""


class Entry(object):
    __slots__ = ('tag', 'type', 'count', 'raw', 'inline', 'value_offset')

    def __init__(self, tag, ftype, count, raw, inline, value_offset):
        self.tag = tag
        self.type = ftype
        self.count = count
        self.raw = raw
        self.inline = inline
        self.value_offset = value_offset


class Tiff(object):
    """最小 TIFF 读取器(缓冲区从 TIFF 头开始, 偏移均相对它)。"""

    def __init__(self, buf):
        if len(buf) < 8:
            raise ExifError('TIFF header shorter than 8 bytes')
        self.buf = buf
        bom = bytes(buf[:2])
        if bom == b'II':
            self.e = '<'
        elif bom == b'MM':
            self.e = '>'
        else:
            raise ExifError('bad TIFF byte-order mark %r' % bom)
        if self.u16(2) != 42:
            raise ExifError('bad TIFF magic (not 42)')
        self.ifd0_offset = self.u32(4)

    def u16(self, off):
        if off < 0 or off + 2 > len(self.buf):
            raise ExifError('TIFF offset out of range: 0x%X' % off)
        return struct.unpack_from(self.e + 'H', self.buf, off)[0]

    def u32(self, off):
        if off < 0 or off + 4 > len(self.buf):
            raise ExifError('TIFF offset out of range: 0x%X' % off)
        return struct.unpack_from(self.e + 'I', self.buf, off)[0]

    def read_ifd(self, off):
        """读取一个 IFD, 返回 (entries, next_ifd_offset)。"""
        n = self.u16(off)
        if n > (len(self.buf) - off - 2) // 12:
            raise ExifError('IFD @0x%X: entry count %d out of range' % (off, n))
        entries = []
        p = off + 2
        for _ in range(n):
            tag = self.u16(p)
            ftype = self.u16(p + 2)
            count = self.u32(p + 4)
            size = TYPE_SIZES.get(ftype)
            if size is None:
                raise ExifError('unknown field type %d (tag 0x%04X)' % (ftype, tag))
            total = size * count
            if total <= 4:
                raw = bytes(self.buf[p + 8:p + 8 + total])
                entries.append(Entry(tag, ftype, count, raw, True, None))
            else:
                voff = self.u32(p + 8)
                if voff + total > len(self.buf):
                    raise ExifError('value offset out of range (tag 0x%04X)' % tag)
                raw = bytes(self.buf[voff:voff + total])
                entries.append(Entry(tag, ftype, count, raw, False, voff))
            p += 12
        nxt = self.u32(p)
        return entries, nxt


def decode_values(entry, tiff):
    """把条目的原始字节按类型解码为 Python 值列表。"""
    tc, cnt, raw = entry.type, entry.count, entry.raw
    e = tiff.e
    if cnt == 0:
        return []
    if tc in (1, 6, 7):
        return list(raw)
    if tc == 2:
        return [raw]
    if tc == 3:
        return list(struct.unpack(e + '%dH' % cnt, raw))
    if tc == 8:
        return list(struct.unpack(e + '%dh' % cnt, raw))
    if tc == 4:
        return list(struct.unpack(e + '%dI' % cnt, raw))
    if tc == 9:
        return list(struct.unpack(e + '%di' % cnt, raw))
    if tc == 11:
        return list(struct.unpack(e + '%df' % cnt, raw))
    if tc == 12:
        return list(struct.unpack(e + '%dd' % cnt, raw))
    if tc in (5, 10):
        fmt = e + ('%dI' if tc == 5 else '%di')
        nums = struct.unpack(fmt % (cnt * 2), raw)
        return [(nums[i * 2], nums[i * 2 + 1]) for i in range(cnt)]
    raise ExifError('cannot decode type %d' % tc)


def fmt_ascii(raw):
    s = raw.split(b'\x00', 1)[0]
    try:
        return s.decode('utf-8')
    except UnicodeDecodeError:
        return s.decode('latin-1')


def find_exif_app1(data):
    """扫描段结构, 返回 (app1偏移, APP1 内 Exif\\0\\0 之后的 TIFF 字节)。"""
    if data[:2] != b'\xff\xd8':
        raise ExifError('not a JPEG file (missing SOI marker)')
    pos = 2
    while pos < len(data):
        if data[pos] != 0xFF:
            raise ExifError('unexpected byte 0x%02X at offset 0x%X' % (data[pos], pos))
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            break
        marker = data[pos]
        pos += 1
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker in (0xD9, 0xDA):        # EOI / SOS: EXIF 必在其前
            break
        if pos + 2 > len(data):
            break
        seg_len = struct.unpack_from('>H', data, pos)[0]
        if seg_len < 2:
            break
        payload = data[pos + 2:pos + seg_len]
        if marker == 0xE1 and payload[:6] == b'Exif\x00\x00':
            return pos - 2, bytes(payload[6:])
        pos += seg_len
    raise ExifError('no EXIF APP1 segment found')


def _pointer(entries, tiff, tag):
    for ent in entries:
        if ent.tag == tag and ent.type == 4 and ent.count >= 1:
            return decode_values(ent, tiff)[0]
    return None


def walk_ifds(tiff):
    """按常见顺序遍历 IFD。返回 [(名称, 偏移, entries, next_offset), ...]"""
    sections = []
    seen = set()
    entries, nxt = tiff.read_ifd(tiff.ifd0_offset)
    seen.add(tiff.ifd0_offset)
    sections.append(('IFD0', tiff.ifd0_offset, entries, nxt))
    exif_off = _pointer(entries, tiff, 0x8769)
    gps_off = _pointer(entries, tiff, 0x8825)
    if exif_off is not None and exif_off not in seen:
        seen.add(exif_off)
        ee, _n = tiff.read_ifd(exif_off)
        sections.append(('Exif IFD', exif_off, ee, 0))
        interop = _pointer(ee, tiff, 0xA005)
        if interop is not None and interop not in seen:
            seen.add(interop)
            ie, _n2 = tiff.read_ifd(interop)
            sections.append(('Interop IFD', interop, ie, 0))
    if gps_off is not None and gps_off not in seen:
        seen.add(gps_off)
        ge, _n3 = tiff.read_ifd(gps_off)
        sections.append(('GPS IFD', gps_off, ge, 0))
    noff, n = nxt, 1
    while noff and noff not in seen and n <= 8:
        seen.add(noff)
        ne, nxt2 = tiff.read_ifd(noff)
        sections.append(('IFD%d (thumbnail)' % n, noff, ne, nxt2))
        noff = nxt2
        n += 1
    return sections


# ---------------- 标签名与枚举释义 ----------------

TAGS_MAIN = {
    0x0100: 'ImageWidth', 0x0101: 'ImageLength', 0x0102: 'BitsPerSample',
    0x0103: 'Compression', 0x0106: 'PhotometricInterpretation',
    0x010E: 'ImageDescription', 0x010F: 'Make', 0x0110: 'Model',
    0x0111: 'StripOffsets', 0x0112: 'Orientation', 0x0115: 'SamplesPerPixel',
    0x011A: 'XResolution', 0x011B: 'YResolution', 0x011C: 'PlanarConfiguration',
    0x0128: 'ResolutionUnit', 0x0131: 'Software', 0x0132: 'DateTime',
    0x013B: 'Artist', 0x0201: 'JPEGInterchangeFormat',
    0x0202: 'JPEGInterchangeFormatLength', 0x8298: 'Copyright',
    0x8769: 'ExifIFDPointer', 0x8825: 'GPSInfoIFDPointer',
    0x9C9B: 'XPTitle', 0x9C9C: 'XPComment', 0x9C9D: 'XPAuthor',
    0x9C9E: 'XPKeywords', 0x9C9F: 'XPSubject',
}
TAGS_EXIF = {
    0x829A: 'ExposureTime', 0x829D: 'FNumber', 0x8822: 'ExposureProgram',
    0x8824: 'SpectralSensitivity', 0x8827: 'ISOSpeedRatings',
    0x8830: 'SensitivityType', 0x9000: 'ExifVersion', 0x9003: 'DateTimeOriginal',
    0x9004: 'DateTimeDigitized', 0x9010: 'OffsetTime',
    0x9011: 'OffsetTimeOriginal', 0x9012: 'OffsetTimeDigitized',
    0x9101: 'ComponentsConfiguration', 0x9102: 'CompressedBitsPerPixel',
    0x9201: 'ShutterSpeedValue', 0x9202: 'ApertureValue',
    0x9203: 'BrightnessValue', 0x9204: 'ExposureBiasValue',
    0x9205: 'MaxApertureValue', 0x9206: 'SubjectDistance',
    0x9207: 'MeteringMode', 0x9208: 'LightSource', 0x9209: 'Flash',
    0x920A: 'FocalLength', 0x927C: 'MakerNote', 0x9286: 'UserComment',
    0xA000: 'FlashpixVersion', 0xA001: 'ColorSpace', 0xA002: 'PixelXDimension',
    0xA003: 'PixelYDimension', 0xA004: 'RelatedSoundFile',
    0xA005: 'InteropIFDPointer', 0xA20B: 'FlashEnergy',
    0xA215: 'ExposureIndex', 0xA217: 'SensingMethod', 0xA300: 'FileSource',
    0xA301: 'SceneType', 0xA302: 'CFAPattern', 0xA402: 'ExposureMode',
    0xA403: 'WhiteBalance', 0xA404: 'DigitalZoomRatio',
    0xA405: 'FocalLengthIn35mmFilm', 0xA406: 'SceneCaptureType',
    0xA407: 'GainControl', 0xA408: 'Contrast', 0xA409: 'Saturation',
    0xA40A: 'Sharpness', 0xA420: 'ImageUniqueID', 0xA430: 'OwnerName',
    0xA431: 'BodySerialNumber', 0xA432: 'LensSpecification',
    0xA433: 'LensMake', 0xA434: 'LensModel', 0xA435: 'LensSerialNumber',
}
TAGS_GPS = {
    0x0000: 'GPSVersionID', 0x0001: 'GPSLatitudeRef', 0x0002: 'GPSLatitude',
    0x0003: 'GPSLongitudeRef', 0x0004: 'GPSLongitude', 0x0005: 'GPSAltitudeRef',
    0x0006: 'GPSAltitude', 0x0007: 'GPSTimeStamp', 0x0008: 'GPSSatellites',
    0x0009: 'GPSStatus', 0x000A: 'GPSMeasureMode', 0x000B: 'GPSDOP',
    0x000C: 'GPSSpeedRef', 0x000D: 'GPSSpeed', 0x000E: 'GPSTrackRef',
    0x000F: 'GPSTrack', 0x0010: 'GPSImgDirectionRef', 0x0011: 'GPSImgDirection',
    0x0012: 'GPSMapDatum', 0x0013: 'GPSDestLatitudeRef',
    0x0014: 'GPSDestLatitude', 0x0015: 'GPSDestLongitudeRef',
    0x0016: 'GPSDestLongitude', 0x001B: 'GPSProcessingMethod',
    0x001C: 'GPSAreaInformation', 0x001D: 'GPSDateStamp',
    0x001E: 'GPSDifferential', 0x001F: 'GPSHPositioningError',
}

ORIENTATION = {1: 'top-left (normal)', 2: 'top-right (mirror)',
               3: 'bottom-right (rotate 180)', 4: 'bottom-left (mirror)',
               5: 'left-top (transpose)', 6: 'right-top (rotate 90 CW)',
               7: 'right-bottom (transverse)', 8: 'left-bottom (rotate 90 CCW)'}
RES_UNIT = {1: '(no unit)', 2: 'inch', 3: 'cm'}
COMPRESSION = {1: 'uncompressed', 6: 'JPEG (old-style thumbnail)', 7: 'JPEG'}
EXP_PROGRAM = {0: 'not defined', 1: 'manual', 2: 'program AE',
               3: 'aperture-priority AE', 4: 'shutter-priority AE',
               5: 'creative', 6: 'action', 7: 'portrait', 8: 'landscape'}
METERING = {0: 'unknown', 1: 'average', 2: 'center-weighted average',
            3: 'spot', 4: 'multi-spot', 5: 'pattern', 6: 'partial',
            255: 'other'}
FLASH = {0: 'off, did not fire', 1: 'fired', 5: 'fired, return not detected',
         7: 'fired, return detected', 8: 'on, did not fire', 9: 'on, fired',
         16: 'off, no flash function', 24: 'auto, did not fire',
         25: 'auto, fired'}
COLORSPACE = {1: 'sRGB', 2: 'Adobe RGB (deprecated)', 65535: 'uncalibrated'}
EXP_MODE = {0: 'auto', 1: 'manual', 2: 'auto bracket'}
WB_MODE = {0: 'auto', 1: 'manual'}
SCENE_TYPE = {0: 'standard', 1: 'landscape', 2: 'portrait', 3: 'night'}
POINTER_TAGS = (0x8769, 0x8825, 0xA005)


def fmt_num(x):
    if x is None:
        return 'n/a'
    if abs(x) < 1e15 and x == int(x):
        return str(int(x))
    return ('%.6f' % x).rstrip('0').rstrip('.')


def hex_preview(raw, limit=16):
    hx = ' '.join('%02X' % c for c in raw[:limit])
    if len(raw) > limit:
        hx += ' ...'
    return '<%d bytes: %s>' % (len(raw), hx)


def tag_name(tag, ifd_label):
    d = TAGS_GPS if ifd_label.startswith('GPS') else (
        TAGS_EXIF if ifd_label.startswith(('Exif', 'Interop')) else TAGS_MAIN)
    return d.get(tag) or TAGS_MAIN.get(tag) or 'Unknown'


def _int_tag_note(tag, v):
    if tag == 0x0112:
        return ORIENTATION.get(v, '?')
    if tag == 0x0128:
        return RES_UNIT.get(v, '?')
    if tag == 0x0103:
        return COMPRESSION.get(v, '?')
    if tag == 0x8822:
        return EXP_PROGRAM.get(v, '?')
    if tag == 0x9207:
        return METERING.get(v, '?')
    if tag == 0x9209:
        return FLASH.get(v, '?')
    if tag == 0xA001:
        return COLORSPACE.get(v, '?')
    if tag == 0xA402:
        return EXP_MODE.get(v, '?')
    if tag == 0xA403:
        return WB_MODE.get(v, '?')
    if tag == 0xA406:
        return SCENE_TYPE.get(v, '?')
    if tag == 0xA405:
        return '35mm equivalent'
    if tag == 0x8827:
        return 'ISO speed'
    if tag == 0x0201:
        return 'thumbnail data offset'
    if tag == 0x0202:
        return 'thumbnail bytes'
    return None


def format_value(tiff, ent, ifd_label):
    """把条目格式化为可读字符串。"""
    tag, tc = ent.tag, ent.type
    if tc == 2:
        return fmt_ascii(ent.raw)
    if tc == 7:
        if tag == 0x9286 and len(ent.raw) >= 8:      # UserComment, 8 字节字符集前缀
            return fmt_ascii(ent.raw[8:])
        if tag in (0x9000, 0xA000):                  # ExifVersion / FlashpixVersion
            try:
                return ent.raw.decode('ascii')
            except UnicodeDecodeError:
                pass
        return hex_preview(ent.raw)
    vals = decode_values(ent, tiff)
    if tc in (5, 10):
        s = ', '.join('%d/%d' % (n, d) for n, d in vals)
        fvals = [(n / d if d else None) for n, d in vals]
        if len(vals) == 1:
            s += ' (=%s)' % fmt_num(fvals[0])
            f1 = fvals[0]
            if tag == 0x829A and f1:                 # ExposureTime
                s = ('%d/%d (1/%g s)' % (vals[0][0], vals[0][1], round(1.0 / f1, 4))
                     if f1 < 1 else '%g s' % f1)
            elif tag == 0x829D and f1 is not None:   # FNumber
                s = 'f/%s' % fmt_num(f1)
            elif tag == 0x920A and f1 is not None:   # FocalLength
                s = '%s mm' % fmt_num(f1)
            elif tag == 0x9204 and f1 is not None:   # ExposureBiasValue
                s = '%s EV' % fmt_num(f1)
        return s
    if tc in (3, 4, 8, 9):
        s = ', '.join(str(v) for v in vals)
        if len(vals) == 1:
            if tag in POINTER_TAGS:
                s = '%d (-> sub-IFD)' % vals[0]
            else:
                note = _int_tag_note(tag, vals[0])
                if note:
                    s = '%d (%s)' % (vals[0], note)
        return s
    return ', '.join(fmt_num(v) for v in vals)      # FLOAT / DOUBLE


# ---------------- 主逻辑 ----------------

def run(path):
    with open(path, 'rb') as fh:
        data = fh.read()
    app1_off, tbuf = find_exif_app1(data)
    tiff = Tiff(tbuf)
    lines = [
        'File      : %s' % path,
        'Size      : %d bytes' % len(data),
        'EXIF APP1 : offset 0x%X, TIFF payload %d bytes, byte order %s'
        % (app1_off, len(tbuf),
           'II (little-endian)' if tiff.e == '<' else 'MM (big-endian)'),
    ]
    obj = {'file': path, 'size': len(data), 'byte_order': tiff.e, 'ifds': []}
    for name, off, entries, _nxt in walk_ifds(tiff):
        lines.append('')
        lines.append('=== %s (TIFF+0x%04X, %d entries) ===' % (name, off, len(entries)))
        jd = {'name': name, 'offset': off, 'entries': []}
        for ent in entries:
            nm = tag_name(ent.tag, name)
            val = format_value(tiff, ent, name)
            lines.append('  %-24s (0x%04X %-9s n=%-4d) : %s'
                         % (nm, ent.tag, TYPE_NAMES.get(ent.type, '?'),
                            ent.count, val))
            jd['entries'].append({'tag': '0x%04X' % ent.tag, 'name': nm,
                                  'type': TYPE_NAMES.get(ent.type),
                                  'count': ent.count, 'value': val})
        obj['ifds'].append(jd)
    return '\n'.join(lines) + '\n', obj


# ---------------- 自测: 构造合成 EXIF JPEG ----------------

class _Ptr(object):
    def __init__(self, idx):
        self.idx = idx


def _pack_vals(e, tc, vals):
    if tc == 2:
        b = b''.join(v.encode('utf-8') if isinstance(v, str) else bytes(v)
                     for v in vals)
        return b + b'\x00'
    if tc in (1, 6, 7):
        return bytes(bytearray(vals))
    if tc == 3:
        return struct.pack(e + '%dH' % len(vals), *vals)
    if tc == 4:
        return struct.pack(e + '%dI' % len(vals), *vals)
    if tc == 5:
        flat = [x for pair in vals for x in pair]
        return struct.pack(e + '%dI' % len(flat), *flat)
    if tc == 10:
        flat = [x for pair in vals for x in pair]
        return struct.pack(e + '%di' % len(flat), *flat)
    raise ValueError('selftest builder: unsupported type %d' % tc)


def build_exif_tiff(e, ifds, next_map=None):
    """两遍扫描构造最小 TIFF(仅供 --selftest)。_Ptr(k) 引用第 k 个 IFD 偏移。"""
    next_map = dict(next_map or {})
    pos, ifd_off = 8, []
    for entries in ifds:
        ifd_off.append(pos)
        pos += 2 + 12 * len(entries) + 4
        for _tag, tc, vals in entries:
            L = len(_pack_vals(e, tc, [0 if isinstance(v, _Ptr) else v for v in vals]))
            if L > 4:
                pos += L
    out = bytearray((b'II' if e == '<' else b'MM') + struct.pack(e + 'HI', 42, 8))
    for i, entries in enumerate(ifds):
        ext = bytearray()
        rows = []
        for tag, tc, vals in entries:
            rv = [ifd_off[v.idx] if isinstance(v, _Ptr) else v for v in vals]
            b = _pack_vals(e, tc, rv)
            cnt = len(b) if tc == 2 else len(rv)
            if len(b) <= 4:
                field = b + b'\x00' * (4 - len(b))
            else:
                field = struct.pack(e + 'I', ifd_off[i] + 2 + 12 * len(entries) + 4 + len(ext))
                ext += b
            rows.append(struct.pack(e + 'HHI', tag, tc, cnt) + field)
        out += struct.pack(e + 'H', len(entries))
        out += b''.join(rows)
        out += struct.pack(e + 'I', ifd_off[next_map[i]] if i in next_map else 0)
        out += ext
    return bytes(out)


def wrap_exif_jpeg(endian, ifds, next_map=None):
    e = '<' if endian == 'II' else '>'
    payload = b'Exif\x00\x00' + build_exif_tiff(e, ifds, next_map)
    if len(payload) + 2 > 0xFFFF:
        raise ValueError('APP1 payload too large')
    return (b'\xff\xd8' + b'\xff\xe1' + struct.pack('>H', len(payload) + 2)
            + payload + b'\xff\xd9')


SELFTEST_IFDS = [
    [                                            # IFD0
        [0x010F, 2, ['TestCam']],
        [0x0110, 2, ['Armory M1']],
        [0x0112, 3, [6]],
        [0x0132, 2, ['2024:05:02 15:30:00']],
        [0x8769, 4, [_Ptr(1)]],
        [0x8825, 4, [_Ptr(2)]],
    ],
    [                                            # Exif IFD
        [0x9000, 7, list(b'0231')],
        [0x829A, 5, [(1, 250)]],
        [0x829D, 5, [(28, 10)]],
        [0x8827, 3, [400]],
        [0x9003, 2, ['2024:05:01 12:00:00']],
        [0x9004, 2, ['2024:05:01 12:00:03']],
        [0x920A, 5, [(50, 1)]],
        [0x9286, 7, list(b'ASCII\x00\x00\x00Hello EXIF')],
    ],
    [                                            # GPS IFD
        [0x0001, 2, ['N']],
        [0x0002, 5, [(39, 1), (54, 1), (3000, 100)]],
        [0x0003, 2, ['E']],
        [0x0004, 5, [(116, 1), (23, 1), (3000, 100)]],
    ],
]


def selftest():
    tmp = tempfile.mkdtemp(prefix='exif_read_selftest_')
    ok = True
    try:
        for endian in ('II', 'MM'):
            p = os.path.join(tmp, 'exif_%s.jpg' % endian.lower())
            with open(p, 'wb') as fh:
                fh.write(wrap_exif_jpeg(endian, SELFTEST_IFDS))
            text, obj = run(p)
            checks = ['TestCam', 'Armory M1', 'Exif IFD', 'GPS IFD',
                      '2024:05:01 12:00:00', '1/250', 'f/2.8',
                      '39/1, 54/1, 3000/100', 'Hello EXIF', '0231']
            for c in checks:
                if c not in text:
                    print('FAIL [%s]: missing %r in output' % (endian, c))
                    ok = False
            if len(obj['ifds']) != 3:
                print('FAIL [%s]: expected 3 IFDs, got %d' % (endian, len(obj['ifds'])))
                ok = False
            else:
                print('PASS [%s]: IFD0=%d entries, Exif=%d, GPS=%d, byte order %s'
                      % (endian, len(obj['ifds'][0]['entries']),
                         len(obj['ifds'][1]['entries']),
                         len(obj['ifds'][2]['entries']), obj['byte_order']))
        if ok:
            print('SELFTEST PASS')
            return 0
        print('SELFTEST FAIL')
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Read all EXIF tags (IFD0/Exif/GPS IFD) from a JPEG file')
    ap.add_argument('path', nargs='?', help='JPEG file with EXIF metadata')
    ap.add_argument('--json', action='store_true', help='output JSON instead of text')
    ap.add_argument('--selftest', action='store_true',
                    help='build synthetic EXIF JPEGs (II and MM) in a temp dir and verify')
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    if args.selftest:
        return selftest()
    if not args.path:
        ap.error('a JPEG path is required (or use --selftest)')
    try:
        text, obj = run(args.path)
    except (ExifError, OSError, struct.error) as exc:
        print('ERROR: %s' % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(obj, indent=2))
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
