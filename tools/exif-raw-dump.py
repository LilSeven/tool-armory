#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXIF 原始转储 - 按 tag 编号/类型/计数/原始字节十六进制转储 EXIF 条目。

用途:
  面向调试的 EXIF 低层查看器: 定位 JPEG 的 EXIF APP1, 解析 TIFF 结构,
  对每个 IFD 的每条目输出 tag 编号、已知标签名、字段类型、计数、
  值存放方式(内联 in-entry 或偏移解引用)以及解析出的原始字节十六进制
  (+ 可打印 ASCII 侧栏), 便于辨认未知名标签的真实字节内容。

用法:
  python exif-raw-dump.py IMAGE.jpg [--max N] [--ifd IFD0,Exif,GPS] [--no-ascii] [--json]
  python exif-raw-dump.py --selftest

示例:
  python exif-raw-dump.py photo.jpg
  python exif-raw-dump.py photo.jpg --max 64
  python exif-raw-dump.py photo.jpg --ifd GPS

选项:
  --max N     每条目最多显示 N 个原始字节; 0 表示全部(默认 32)
  --ifd LIST  仅显示名称含 LIST(逗号分隔) 的 IFD, 如 IFD0,Exif,GPS,IFD1
  --no-ascii  不显示 ASCII 侧栏

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

# ---------------- EXIF/TIFF 解析核心(与 exif-read 同一套最小实现) ----------------

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


def fmt_ascii(raw):
    s = raw.split(b'\x00', 1)[0]
    try:
        return s.decode('utf-8')
    except UnicodeDecodeError:
        return s.decode('latin-1')


def find_exif_app1(data):
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
        if marker in (0xD9, 0xDA):
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
            return struct.unpack(tiff.e + 'I', ent.raw)[0]
    return None


def walk_ifds(tiff):
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


# ---------------- 标签名 ----------------

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


def tag_name(tag, ifd_label):
    d = TAGS_GPS if ifd_label.startswith('GPS') else (
        TAGS_EXIF if ifd_label.startswith(('Exif', 'Interop')) else TAGS_MAIN)
    return d.get(tag) or TAGS_MAIN.get(tag) or 'Unknown'


# ---------------- 主逻辑 ----------------

def run(path, ifd_filter=None, max_bytes=32, show_ascii=True):
    with open(path, 'rb') as fh:
        data = fh.read()
    app1_off, tbuf = find_exif_app1(data)
    tiff = Tiff(tbuf)
    endian = 'II (little-endian)' if tiff.e == '<' else 'MM (big-endian)'
    lines = [
        'File      : %s' % path,
        'Size      : %d bytes' % len(data),
        'EXIF APP1 : offset 0x%X, TIFF payload %d bytes, byte order %s'
        % (app1_off, len(tbuf), endian),
        'IFD0 at TIFF+0x%04X; value offsets shown relative to TIFF header start'
        % tiff.ifd0_offset,
        '',
    ]
    obj = {'file': path, 'size': len(data), 'byte_order': tiff.e, 'sections': []}
    for name, off, entries, nxt in walk_ifds(tiff):
        if ifd_filter and not any(f in name.lower() for f in ifd_filter):
            continue
        lines.append('== %s @ TIFF+0x%04X : %d entries, next=0x%04X =='
                     % (name, off, len(entries), nxt))
        jd = {'name': name, 'offset': off, 'next': nxt, 'entries': []}
        for i, ent in enumerate(entries, 1):
            nm = tag_name(ent.tag, name)
            cap = max_bytes if max_bytes and max_bytes > 0 else len(ent.raw)
            hexs = ' '.join('%02X' % c for c in ent.raw[:cap])
            trunc = (' (+%d more bytes)' % (len(ent.raw) - cap)
                     if len(ent.raw) > cap else '')
            loc = 'inline' if ent.inline else 'off=TIFF+0x%04X' % ent.value_offset
            tail = ''
            if show_ascii and ent.raw:
                vis = ''.join(chr(c) if 32 <= c < 127 else '.'
                              for c in ent.raw[:cap])
                tail = '  |%s' % vis
            lines.append('  #%02d 0x%04X %-24s %-10s count=%-6d %-16s bytes=%-5d %s%s%s'
                         % (i, ent.tag, nm, TYPE_NAMES.get(ent.type, '?'),
                            ent.count, loc, len(ent.raw), hexs, trunc, tail))
            jd['entries'].append({
                'index': i, 'tag': '0x%04X' % ent.tag, 'name': nm,
                'type': TYPE_NAMES.get(ent.type), 'type_code': ent.type,
                'count': ent.count, 'inline': ent.inline,
                'value_offset': (None if ent.inline else '0x%04X' % ent.value_offset),
                'hex': hexs, 'truncated': bool(trunc),
                'ascii': ''.join(chr(c) if 32 <= c < 127 else '.'
                                 for c in ent.raw[:cap])})
        obj['sections'].append(jd)
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
    [                                   # IFD0
        [0x010F, 2, ['TestCam']],       # ASCII, 8 字节外置 -> off=
        [0x0112, 3, [1]],               # SHORT, 内联
        [0x8769, 4, [_Ptr(1)]],
        [0x8825, 4, [_Ptr(2)]],
    ],
    [                                   # Exif IFD, 含未知名标签 0x9999
        [0x9003, 2, ['2024:05:01 12:00:00']],
        [0x9999, 7, list(range(10))],   # UNDEFINED, 10 字节外置
    ],
    [                                   # GPS IFD
        [0x0001, 2, ['N']],
        [0x0002, 5, [(39, 1), (54, 1), (3000, 100)]],
    ],
]


def selftest():
    tmp = tempfile.mkdtemp(prefix='exif_raw_selftest_')
    ok = True
    try:
        for endian in ('II', 'MM'):
            p = os.path.join(tmp, 'exif_%s.jpg' % endian.lower())
            with open(p, 'wb') as fh:
                fh.write(wrap_exif_jpeg(endian, SELFTEST_IFDS))
            text, obj = run(p)
            checks = ['0x010F', 'Make', '54 65 73 74 43 61 6D 00',
                      '0x9999', 'UNDEFINED', 'inline', 'off=TIFF+0x',
                      '0x0002', 'GPSLatitude']
            for c in checks:
                if c not in text:
                    print('FAIL [%s]: missing %r in output' % (endian, c))
                    ok = False
            # 截断逻辑: --max 4 时 10 字节条目应显示 (+6 more bytes)
            _t2, obj2 = run(p, max_bytes=4)
            ent9999 = None
            for sec in obj2['sections']:
                for ent in sec['entries']:
                    if ent['tag'] == '0x9999':
                        ent9999 = ent
            if ent9999 is None or not ent9999['truncated']:
                print('FAIL [%s]: --max 4 truncation not applied to 0x9999' % endian)
                ok = False
            else:
                print('PASS [%s]: 0x9999 truncated at 4 bytes (+6 more)' % endian)
            if ok and len(obj['sections']) != 3:
                print('FAIL [%s]: expected 3 sections' % endian)
                ok = False
            else:
                print('PASS [%s]: %d sections dumped (IFD0/Exif/GPS), %s'
                      % (endian, len(obj['sections']),
                         'raw hex of TestCam present' if '54 65 73 74 43 61 6D 00' in text
                         else 'ERROR'))
        if ok:
            print('SELFTEST PASS')
            return 0
        print('SELFTEST FAIL')
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Raw-dump EXIF entries: tag id, type, count and hex bytes')
    ap.add_argument('path', nargs='?', help='JPEG file with EXIF metadata')
    ap.add_argument('--max', type=int, default=32, metavar='N',
                    help='max raw bytes shown per entry; 0 = all (default 32)')
    ap.add_argument('--ifd', default=None, metavar='LIST',
                    help='only dump IFDs whose name contains one of LIST (comma-separated)')
    ap.add_argument('--no-ascii', action='store_true', help='hide ASCII sidebar')
    ap.add_argument('--json', action='store_true', help='output JSON instead of text')
    ap.add_argument('--selftest', action='store_true',
                    help='build synthetic EXIF JPEGs in a temp dir and verify')
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
    filters = [f.strip().lower() for f in args.ifd.split(',')] if args.ifd else None
    try:
        text, obj = run(args.path, ifd_filter=filters,
                        max_bytes=args.max, show_ascii=not args.no_ascii)
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
