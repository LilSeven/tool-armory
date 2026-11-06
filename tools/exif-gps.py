#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXIF GPS 提取 - 解析 GPS IFD 经纬度, 转十进制度并生成地图链接。

用途:
  从 JPEG 的 EXIF GPS IFD 中读取 GPSLatitude/GPSLongitude(度/分/秒
  有理数三元组)及其 N/S/E/W 参考方向, 换算为十进制度(南纬/西经为负),
  输出 DMS 与小数两种形式, 并生成 Google Maps / Bing Maps /
  OpenStreetMap 的定位链接。同时给出海拔、GPS 版本、基准坐标系与
  GPS 日期时间(GPSDateStamp + GPSTimeStamp, UTC)。

用法:
  python exif-gps.py IMAGE.jpg [--json]
  python exif-gps.py --selftest

示例:
  python exif-gps.py photo.jpg
  python exif-gps.py photo.jpg --json

退出码: 0 成功; 1 不是 JPEG / 无 GPS / 缺经纬度; 2 用法错误。
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


def decode_values(entry, tiff):
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
    if tc == 4:
        return list(struct.unpack(e + '%dI' % cnt, raw))
    if tc in (5, 10):
        fmt = e + ('%dI' if tc == 5 else '%di')
        nums = struct.unpack(fmt % (cnt * 2), raw)
        return [(nums[i * 2], nums[i * 2 + 1]) for i in range(cnt)]
    raise ExifError('cannot decode type %d in GPS context' % tc)


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


# ---------------- GPS 换算 ----------------

def fmt_num(x):
    if x is None:
        return 'n/a'
    if abs(x) < 1e15 and x == int(x):
        return str(int(x))
    return ('%.6f' % x).rstrip('0').rstrip('.')


def rationals_to_floats(ent, tiff):
    """RATIONAL 条目 -> 浮点列表(分母 0 视为 None)。"""
    vals = decode_values(ent, tiff)
    return [(n / d if d else None) for n, d in vals]


def dms_to_deg(parts):
    """[度] / [度,分] / [度,分,秒] -> 十进制度。"""
    mult = (1.0, 1.0 / 60.0, 1.0 / 3600.0)
    return sum((p or 0.0) * m for p, m in zip(parts, mult))


def fmt_dms(parts, ref):
    deg = parts[0] if len(parts) > 0 else 0.0
    minute = parts[1] if len(parts) > 1 else 0.0
    sec = parts[2] if len(parts) > 2 else 0.0
    return '%s deg %s\' %.2f" %s' % (fmt_num(deg), fmt_num(minute), sec, ref or '?')


def make_links(lat, lon):
    la, lo = '%.6f' % lat, '%.6f' % lon
    return {
        'google_maps': 'https://maps.google.com/?q=%s,%s' % (la, lo),
        'bing_maps': 'https://www.bing.com/maps?cp=%s~%s&lvl=16' % (la, lo),
        'openstreetmap': ('https://www.openstreetmap.org/?mlat=%s&mlon=%s'
                          '#map=16/%s/%s' % (la, lo, la, lo)),
    }


def run(path):
    with open(path, 'rb') as fh:
        data = fh.read()
    app1_off, tbuf = find_exif_app1(data)
    tiff = Tiff(tbuf)
    gps = None
    for name, _off, entries, _nxt in walk_ifds(tiff):
        if name.startswith('GPS'):
            gps = entries
            break
    if gps is None:
        raise ExifError('no GPS IFD found in this file (EXIF exists but no GPS)')

    def g(tag, types):
        for ent in gps:
            if ent.tag == tag and ent.type in types:
                return ent
        return None

    lat_ent = g(0x0002, (5, 10))
    lon_ent = g(0x0004, (5, 10))
    latref = fmt_ascii(g(0x0001, (2,)).raw) if g(0x0001, (2,)) else ''
    lonref = fmt_ascii(g(0x0003, (2,)).raw) if g(0x0003, (2,)) else ''
    lat_parts = rationals_to_floats(lat_ent, tiff) if lat_ent else None
    lon_parts = rationals_to_floats(lon_ent, tiff) if lon_ent else None
    lat = dms_to_deg(lat_parts) if lat_parts else None
    lon = dms_to_deg(lon_parts) if lon_parts else None
    if lat is not None and latref in ('S', 's'):
        lat = -lat
    if lon is not None and lonref in ('W', 'w'):
        lon = -lon

    lines = ['File      : %s' % path,
             'EXIF APP1 : offset 0x%X, GPS IFD entries: %d' % (app1_off, len(gps))]
    ver_ent = g(0x0000, (1,))
    if ver_ent:
        lines.append('GPS Version: %s' % '.'.join(str(c) for c in decode_values(ver_ent, tiff)))
    datum = g(0x0012, (2,))
    if datum:
        lines.append('Map Datum  : %s' % fmt_ascii(datum.raw))
    status = g(0x0009, (2,))
    if status:
        lines.append('GPS Status : %s' % fmt_ascii(status.raw))

    obj = {'file': path, 'gps_ifd_entries': len(gps)}

    if lat is None and lon is None:
        raise ExifError('GPS IFD found (%d entries) but no latitude/longitude tags'
                        % len(gps))

    if lat_parts is not None:
        lat_line = "Latitude   : %s" % fmt_dms(lat_parts, latref or '?')
        if lat is not None:
            lat_line += '  -> %.6f' % lat
        if not latref:
            lat_line += '  (ref missing, sign not applied)'
        lines.append(lat_line)
    if lon_parts is not None:
        lon_line = "Longitude  : %s" % fmt_dms(lon_parts, lonref or '?')
        if lon is not None:
            lon_line += '  -> %.6f' % lon
        if not lonref:
            lon_line += '  (ref missing, sign not applied)'
        lines.append(lon_line)
    obj['latitude'] = lat
    obj['longitude'] = lon
    obj['latitude_ref'] = latref or None
    obj['longitude_ref'] = lonref or None
    obj['latitude_dms'] = fmt_dms(lat_parts, latref) if lat_parts else None
    obj['longitude_dms'] = fmt_dms(lon_parts, lonref) if lon_parts else None

    alt_ent = g(0x0006, (5, 10))
    if alt_ent is not None:
        fvals = rationals_to_floats(alt_ent, tiff)
        alt = fvals[0] if fvals else None
        altref = g(0x0005, (1,))
        below = bool(altref and altref.raw and altref.raw[0] == 1)
        if alt is not None:
            alt = -abs(alt) if below else alt
            lines.append('Altitude   : %s m (%s sea level)'
                         % (fmt_num(alt), 'below' if below else 'above'))
            obj['altitude_m'] = alt
            obj['altitude_below_sea_level'] = below

    ts_ent = g(0x0007, (5, 10))
    ds_ent = g(0x001D, (2,))
    if ts_ent is not None:
        tp = (rationals_to_floats(ts_ent, tiff) + [0.0, 0.0, 0.0])[:3]
        h, m, s = int(tp[0] or 0), int(tp[1] or 0), float(tp[2] or 0.0)
        sec_str = ('%02d' % int(round(s))) if abs(s - round(s)) < 1e-9 else '%06.3f' % s
        tstr = '%02d:%02d:%s' % (h, m, sec_str)
        if ds_ent is not None:
            ds = fmt_ascii(ds_ent.raw)
            iso = '-'.join(ds.split(':')[:3]) if ':' in ds else ds
            lines.append('GPS Time   : %s %s UTC (GPSDateStamp + GPSTimeStamp)'
                         % (iso, tstr))
            obj['gps_datetime_utc'] = '%s %s' % (iso, tstr)
        else:
            lines.append('GPS Time   : %s UTC (GPSTimeStamp)' % tstr)
            obj['gps_time_utc'] = tstr

    if (lat is None) != (lon is None):
        lines.append('')
        lines.append('WARNING: only one of latitude/longitude present; '
                     'no coordinate or map links generated.')
        obj['links'] = None
    else:
        lines.append('')
        lines.append('Decimal coordinates: %.6f, %.6f' % (lat, lon))
        links = make_links(lat, lon)
        obj['links'] = links
        lines.append('')
        lines.append('Map links:')
        lines.append('  Google Maps   : %s' % links['google_maps'])
        lines.append('  Bing Maps     : %s' % links['bing_maps'])
        lines.append('  OpenStreetMap : %s' % links['openstreetmap'])
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


def gps_ifd(latref, lonref):
    return [
        [0x0000, 1, [2, 3, 0, 0]],
        [0x0001, 2, [latref]],
        [0x0002, 5, [(39, 1), (54, 1), (3000, 100)]],    # 39 deg 54' 30.00"
        [0x0003, 2, [lonref]],
        [0x0004, 5, [(116, 1), (23, 1), (3000, 100)]],   # 116 deg 23' 30.00"
        [0x0005, 1, [0]],
        [0x0006, 5, [(87, 2)]],                          # 43.5 m
        [0x0007, 5, [(4, 1), (5, 1), (6, 1)]],           # 04:05:06 UTC
        [0x0012, 2, ['WGS-84']],
        [0x001D, 2, ['2024:05:01']],
    ]


def selftest():
    tmp = tempfile.mkdtemp(prefix='exif_gps_selftest_')
    ok = True
    # 期望: 39 + 54/60 + 30/3600 = 39.908333..., 116 + 23/60 + 30/3600 = 116.391666...
    exp_lat, exp_lon = 39 + 54 / 60.0 + 30 / 3600.0, 116 + 23 / 60.0 + 30 / 3600.0
    try:
        for endian, latref, lonref, sign in (('II', 'N', 'E', 1),
                                             ('MM', 'S', 'W', -1)):
            p = os.path.join(tmp, 'gps_%s.jpg' % endian.lower())
            with open(p, 'wb') as fh:
                fh.write(wrap_exif_jpeg(endian, [
                    [[0x010F, 2, ['TestCam']], [0x8825, 4, [_Ptr(1)]]],
                    gps_ifd(latref, lonref)]))
            text, obj = run(p)
            want_lat, want_lon = sign * exp_lat, sign * exp_lon
            if obj['latitude'] is None or abs(obj['latitude'] - want_lat) > 1e-9:
                print('FAIL [%s]: latitude %r != %.6f' % (endian, obj['latitude'], want_lat))
                ok = False
            elif abs(obj['longitude'] - want_lon) > 1e-9:
                print('FAIL [%s]: longitude %r != %.6f' % (endian, obj['longitude'], want_lon))
                ok = False
            else:
                print('PASS [%s]: lat=%.6f lon=%.6f (ref %s/%s)'
                      % (endian, obj['latitude'], obj['longitude'], latref, lonref))
            for txt in ("39 deg 54' 30.00\" %s" % latref,
                        '43.5 m (above sea level)', 'WGS-84',
                        '2024-05-01 04:05:06 UTC',
                        'maps.google.com/?q=%.6f,%.6f' % (want_lat, want_lon),
                        'openstreetmap.org' if ok else ''):
                if txt and txt not in text:
                    print('FAIL [%s]: missing %r in output' % (endian, txt))
                    ok = False
        if ok:
            print('SELFTEST PASS')
            return 0
        print('SELFTEST FAIL')
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Extract GPS latitude/longitude from EXIF, '
                    'convert to decimal degrees and print map links')
    ap.add_argument('path', nargs='?', help='JPEG file with GPS EXIF metadata')
    ap.add_argument('--json', action='store_true', help='output JSON instead of text')
    ap.add_argument('--selftest', action='store_true',
                    help='build synthetic GPS EXIF JPEGs (N/E and S/W) and verify')
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
