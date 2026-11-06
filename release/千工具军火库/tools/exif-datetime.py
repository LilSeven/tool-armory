#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXIF 日期时间 - 对比 DateTimeOriginal/DateTimeDigitized/DateTime 及其差值。

用途:
  从 JPEG 的 EXIF 中提取三个时间字段并排输出, 再计算两两差值:
    - IFD0   DateTime        (0x0132, 文件/修改时间)
    - Exif   DateTimeOriginal  (0x9003, 原始拍摄时间)
    - Exif   DateTimeDigitized (0x9004, 数字化时间)
  差值行格式 "+1d 03:30:00" / "-00:00:03", 负号表示前一时刻早于后一时刻。
  如存在 OffsetTime/OffsetTimeOriginal/OffsetTimeDigitized(时区偏移),
  会一并列出供参考(差值仍按本地 naive 时间计算)。

用法:
  python exif-datetime.py IMAGE.jpg [--json]
  python exif-datetime.py --selftest

示例:
  python exif-datetime.py photo.jpg
  python exif-datetime.py photo.jpg --json

退出码: 0 成功(至少找到一个时间字段); 1 不是 JPEG/无 EXIF/完全无时间字段;
        2 用法错误。
仅用 Python 标准库。
"""

import argparse
import datetime
import json
import os
import re
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


# ---------------- 时间字段提取与差值 ----------------

FIELDS = [
    ('DateTime',          'IFD0',     0x0132),
    ('DateTimeOriginal',  'Exif IFD', 0x9003),
    ('DateTimeDigitized', 'Exif IFD', 0x9004),
]
OFFSET_FIELDS = [
    ('OffsetTime',          'Exif IFD', 0x9010),
    ('OffsetTimeOriginal',  'Exif IFD', 0x9011),
    ('OffsetTimeDigitized', 'Exif IFD', 0x9012),
]
PAIRS = [
    ('DateTimeOriginal', 'DateTimeDigitized'),
    ('DateTime', 'DateTimeOriginal'),
    ('DateTime', 'DateTimeDigitized'),
]
_DT_RE = re.compile(r'^(\d{4})[:-](\d{2})[:-](\d{2})[ T](\d{1,2}):(\d{2}):(\d{2})')


def parse_exif_dt(s):
    """解析 EXIF 的 'YYYY:MM:DD HH:MM:SS'。失败返回 None。"""
    s = (s or '').strip()
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s, '%Y:%m:%d %H:%M:%S')
    except ValueError:
        pass
    m = _DT_RE.match(s)
    if m:
        try:
            return datetime.datetime(*[int(x) for x in m.groups()])
        except ValueError:
            return None
    return None


def fmt_delta(td):
    secs = int(round(td.total_seconds()))
    sign = '-' if secs < 0 else '+'
    secs = abs(secs)
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return '%s%dd %02d:%02d:%02d' % (sign, d, h, m, s)
    return '%s%02d:%02d:%02d' % (sign, h, m, s)


def _collect_ascii(entries, tag):
    for ent in entries:
        if ent.tag == tag and ent.type == 2:
            return fmt_ascii(ent.raw)
    return None


def run(path):
    with open(path, 'rb') as fh:
        data = fh.read()
    _app1_off, tbuf = find_exif_app1(data)
    tiff = Tiff(tbuf)
    by_name = {}
    for name, _off, entries, _nxt in walk_ifds(tiff):
        by_name[name] = entries
    ifd0 = by_name.get('IFD0', [])
    exif = by_name.get('Exif IFD', [])

    raw, parsed, loc, tags = {}, {}, {}, {}
    for fname, where, tag in FIELDS:
        entries = ifd0 if where == 'IFD0' else exif
        raw[fname] = _collect_ascii(entries, tag)
        parsed[fname] = parse_exif_dt(raw[fname])
        loc[fname] = where
        tags[fname] = tag
    if all(v is None for v in raw.values()):
        raise ExifError('no EXIF datetime tags found '
                        '(DateTime / DateTimeOriginal / DateTimeDigitized)')

    lines = [
        'File: %s' % path,
        '',
        'Field                    Location     Tag      Raw value                    Parsed',
    ]
    for fname, _where, tag in FIELDS:
        locs = '%s' % loc[fname]
        if raw[fname] is None:
            val, par = '(absent)', '-'
        elif parsed[fname] is None:
            val, par = repr(raw[fname]), '(unparseable)'
        else:
            val, par = raw[fname], parsed[fname].strftime('%Y-%m-%d %H:%M:%S')
        lines.append('  %-22s %-12s 0x%04X  %-28s %s'
                     % (fname, locs, tag, val, par))
    offsets = {}
    for fname, _where, tag in OFFSET_FIELDS:
        v = _collect_ascii(exif, tag)
        if v:
            offsets[fname] = v
    if offsets:
        lines.append('')
        lines.append('Timezone offsets (reference only, deltas below are naive):')
        for fname, v in offsets.items():
            lines.append('  %-22s %s' % (fname, v))

    deltas = []
    lines.append('')
    lines.append('Differences (A - B; negative means A is earlier than B):')
    for a, b in PAIRS:
        if parsed.get(a) and parsed.get(b):
            td = parsed[a] - parsed[b]
            deltas.append({'a': a, 'b': b, 'seconds': td.total_seconds(),
                           'text': fmt_delta(td)})
            lines.append('  %-22s - %-22s: %s' % (a, b, fmt_delta(td)))
    if not deltas:
        lines.append('  (no pair of parseable timestamps to compare)')
    obj = {
        'file': path,
        'fields': {f: {'tag': '0x%04X' % tags[f], 'location': loc[f],
                       'raw': raw[f],
                       'parsed': (parsed[f].strftime('%Y-%m-%d %H:%M:%S')
                                  if parsed[f] else None)}
                   for f, _w, _t in FIELDS},
        'offset_times': offsets,
        'deltas': deltas,
    }
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


FULL_IFDS = [
    [[0x0132, 2, ['2024:05:02 15:30:00']], [0x010F, 2, ['TestCam']],
     [0x8769, 4, [_Ptr(1)]]],
    [[0x9003, 2, ['2024:05:01 12:00:00']],
     [0x9004, 2, ['2024:05:01 12:00:03']]],
]
PARTIAL_IFDS = [
    [[0x010F, 2, ['TestCam']], [0x8769, 4, [_Ptr(1)]]],
    [[0x9003, 2, ['2024:05:01 12:00:00']]],
]


def selftest():
    tmp = tempfile.mkdtemp(prefix='exif_dt_selftest_')
    ok = True
    try:
        for endian in ('II', 'MM'):
            p = os.path.join(tmp, 'full_%s.jpg' % endian.lower())
            with open(p, 'wb') as fh:
                fh.write(wrap_exif_jpeg(endian, FULL_IFDS))
            text, obj = run(p)
            expect = {'DateTimeOriginal-DateTimeDigitized': -3.0,
                      'DateTime-DateTimeOriginal': 99000.0,
                      'DateTime-DateTimeDigitized': 98997.0}
            got = {'%s-%s' % (d['a'], d['b']): d['seconds'] for d in obj['deltas']}
            if got != expect:
                print('FAIL [%s]: deltas %r != expected %r' % (endian, got, expect))
                ok = False
            for txt in ('-00:00:03', '+1d 03:30:00', '+1d 03:29:57'):
                if txt not in text:
                    print('FAIL [%s]: missing %r in text output' % (endian, txt))
                    ok = False
            if ok:
                print('PASS [%s]: deltas -3s / +99000s / +98997s formatted correctly'
                      % endian)
        p = os.path.join(tmp, 'partial.jpg')
        with open(p, 'wb') as fh:
            fh.write(wrap_exif_jpeg('II', PARTIAL_IFDS))
        text, obj = run(p)
        if '(absent)' not in text or len(obj['deltas']) != 0:
            print('FAIL partial: expected absent fields and zero deltas')
            ok = False
        else:
            print('PASS partial: missing fields shown as (absent), no deltas')
        if ok:
            print('SELFTEST PASS')
            return 0
        print('SELFTEST FAIL')
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Compare EXIF DateTimeOriginal/DateTimeDigitized/DateTime and deltas')
    ap.add_argument('path', nargs='?', help='JPEG file with EXIF metadata')
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
