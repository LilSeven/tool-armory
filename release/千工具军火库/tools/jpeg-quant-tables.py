#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JPEG 量化表报告 - 转储 DQT 量化表并按 IJG 标准公式估算压缩质量。

用途:
  解析 JPEG 文件的 DQT 段, 转储其中每张量化表(精度/表编号/64 个系数,
  同时给出 zigzag 序与 8x8 自然序两种视图), 并用 libjpeg(IJG) 的标准
  质量缩放公式反推该表对应的压缩质量分数(1-100)。

  标准公式 (libjpeg jpeg_quality_scaling / jpeg_set_quality):
      scale    = 5000 // quality            (quality < 50)
      scale    = 200 - quality * 2          (quality >= 50)
      table[i] = clamp((base[i]*scale + 50) // 100, 1, 255)
  本工具以 base=标准亮度表/标准色度表 各扫描 quality=1..100, 取系数匹配
  最多的一组作为估计值; 64/64 全匹配即精确还原编码端使用的 quality。

用法:
  python jpeg-quant-tables.py IMAGE.jpg [--json]
  python jpeg-quant-tables.py --selftest     # 构造合成 JPEG 自测

示例:
  python jpeg-quant-tables.py photo.jpg
  python jpeg-quant-tables.py photo.jpg --json

退出码: 0 成功; 1 不是 JPEG / 无 DQT / 解析失败; 2 用法错误。
仅用 Python 标准库。
"""

import argparse
import json
import os
import shutil
import struct
import sys
import tempfile

# JPEG 规范 Annex K / libjpeg 标准量化表(8x8 自然行优先序)
STD_LUMA = [
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77,
    24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101,
    72, 92, 95, 98, 112, 100, 103, 99,
]
STD_CHROMA = [
    17, 18, 24, 47, 99, 99, 99, 99,
    18, 22, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99,
    47, 66, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
]
# zigzag 扫描序的第 k 个元素 = 该系数在 8x8 自然序(行优先)中的下标
ZIGZAG = [
    0,  1,  8, 16,  9,  2,  3, 10,
    17, 24, 32, 25, 18, 11,  4,  5,
    12, 19, 26, 33, 40, 48, 41, 34,
    27, 20, 13,  6,  7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36,
    29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46,
    53, 60, 61, 54, 47, 55, 62, 63,
]

MARKER_NAMES = {
    0xC0: 'SOF0', 0xC1: 'SOF1', 0xC2: 'SOF2', 0xC3: 'SOF3',
    0xC4: 'DHT', 0xC5: 'SOF5', 0xC6: 'SOF6', 0xC7: 'SOF7',
    0xC8: 'JPG', 0xC9: 'SOF9', 0xCA: 'SOF10', 0xCB: 'SOF11',
    0xCC: 'DAC', 0xCD: 'SOF13', 0xCE: 'SOF14', 0xCF: 'SOF15',
    0xD9: 'EOI', 0xDA: 'SOS', 0xDB: 'DQT', 0xDC: 'DNL',
    0xDD: 'DRI', 0xDE: 'DHP', 0xDF: 'EXP', 0xFE: 'COM',
}
for _i in range(16):
    MARKER_NAMES[0xE0 + _i] = 'APP%d' % _i


class JpegError(ValueError):
    """JPEG 解析错误。"""


def marker_name(m):
    return MARKER_NAMES.get(m, '0x%02X' % m)


def parse_dqt(payload, seg_off, tables):
    """解析一个 DQT 段负载, 可含多张表。结果写入 tables[tq]。"""
    p = 0
    while p < len(payload):
        pqtq = payload[p]
        p += 1
        pq, tq = pqtq >> 4, pqtq & 0x0F
        if pq > 1:
            raise JpegError('DQT precision field invalid: Pq=%d' % pq)
        if tq > 3:
            raise JpegError('DQT table id invalid: Tq=%d' % tq)
        nbytes = 128 if pq else 64
        if p + nbytes > len(payload):
            raise JpegError('DQT table %d data truncated' % tq)
        if pq == 0:
            vals = list(payload[p:p + 64])
        else:
            vals = list(struct.unpack_from('>64H', payload, p))
        tables[tq] = {'id': tq, 'precision': 8 if pq == 0 else 16,
                      'zigzag': vals, 'offset': seg_off}
        p += nbytes


def parse_jpeg(data):
    """扫描 SOI..SOS 之间的段。返回 (tables, markers)。
    tables: {table_id: {'precision','zigzag','offset'}}; markers: [(marker, off, len)]
    """
    if len(data) < 2 or data[0] != 0xFF or data[1] != 0xD8:
        raise JpegError('not a JPEG file (missing SOI marker FFD8)')
    tables = {}
    markers = []
    pos = 2
    while pos < len(data):
        if data[pos] != 0xFF:
            raise JpegError('unexpected byte 0x%02X at offset 0x%X (before SOS)'
                            % (data[pos], pos))
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            raise JpegError('truncated file: marker byte missing at EOF')
        marker = data[pos]
        pos += 1
        if marker == 0xD8:                       # SOI
            continue
        if marker == 0xD9:                       # EOI
            markers.append((marker, pos - 2, 0))
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:   # TEM / RSTn, 无长度域
            markers.append((marker, pos - 2, 0))
            continue
        if pos + 2 > len(data):
            raise JpegError('truncated segment header (marker FF%02X)' % marker)
        seg_len = struct.unpack_from('>H', data, pos)[0]
        if seg_len < 2 or pos + seg_len > len(data):
            raise JpegError('bad segment length %d at offset 0x%X (marker FF%02X)'
                            % (seg_len, pos - 2, marker))
        if marker == 0xDB:
            parse_dqt(data[pos + 2:pos + seg_len], pos - 2, tables)
        markers.append((marker, pos - 2, seg_len))
        pos += seg_len
        if marker == 0xDA:                       # SOS 之后是熵编码数据, 停止
            break
    if not tables:
        raise JpegError('no DQT (quantization table) segment found')
    return tables, markers


def dezigzag(zigzag_vals):
    """zigzag 序 64 值 -> 8x8 自然序矩阵。"""
    mat = [[0] * 8 for _ in range(8)]
    for k, nat in enumerate(ZIGZAG):
        mat[nat // 8][nat % 8] = zigzag_vals[k]
    return mat


def scaled_table(base, quality):
    """IJG 标准公式: 由标准表 + quality 生成编码端量化表。"""
    scale = 5000 // quality if quality < 50 else 200 - quality * 2
    return [max(1, min(255, (b * scale + 50) // 100)) for b in base]


def estimate_quality(natural_vals):
    """按标准公式扫描 quality=1..100, 返回 (quality, matches, base_name)。
    luminance 表在平局时优先; 同一 base 内平局取更大的 quality(覆盖 q=99/100
    产生全 1 表的情形)。"""
    best = None                    # (matches, quality, base_name)
    for base, name, strict in ((STD_LUMA, 'luminance', False),
                               (STD_CHROMA, 'chrominance', True)):
        for q in range(1, 101):
            t = scaled_table(base, q)
            m = sum(1 for a, b in zip(t, natural_vals) if a == b)
            if best is None or (m > best[0] if strict else m >= best[0]):
                best = (m, q, name)
    return best[1], best[0], best[2]


def run(path):
    """分析一个 JPEG 文件, 返回 (报告文本, JSON对象)。"""
    with open(path, 'rb') as fh:
        data = fh.read()
    tables, markers = parse_jpeg(data)
    chain = ' '.join('%s(%dB)' % (marker_name(m), L) for m, _o, L in markers)
    lines = [
        'File    : %s' % path,
        'Size    : %d bytes' % len(data),
        'Markers : %s' % chain,
        '',
    ]
    results = []
    for tq in sorted(tables):
        t = tables[tq]
        mat = dezigzag(t['zigzag'])
        natural = [v for row in mat for v in row]
        q, matches, base = estimate_quality(natural)
        slot = {0: 'luminance slot', 1: 'chrominance slot'}.get(tq, 'slot %d' % tq)
        exact = 'exact match' if matches == 64 else 'closest match %d/64 values' % matches
        lines.append('--- DQT table #%d (%s), %d-bit precision, segment @ file offset 0x%X ---'
                     % (tq, slot, t['precision'], t['offset']))
        lines.append('  zigzag order : %s' % ', '.join(str(v) for v in t['zigzag']))
        lines.append('  8x8 matrix (natural row-major order):')
        for row in mat:
            lines.append('    ' + ''.join('%5d' % v for v in row))
        lines.append('  quality estimate: %d  (IJG formula vs standard %s table, %s)'
                     % (q, base, exact))
        lines.append('')
        results.append({'id': tq, 'precision': t['precision'], 'offset': t['offset'],
                        'zigzag': t['zigzag'], 'matrix': mat, 'quality': q,
                        'matches': matches, 'base_table': base})
    if any(r['id'] == 0 for r in results):
        overall = next(r['quality'] for r in results if r['id'] == 0)
        src = 'table #0'
    else:
        overall = int(round(sum(r['quality'] for r in results) / len(results)))
        src = 'mean of all tables'
    note = ''
    if len({r['quality'] for r in results}) > 1:
        note = '  (tables disagree: %s)' % ', '.join(
            '#%d->%d' % (r['id'], r['quality']) for r in results)
    lines.append('Estimated JPEG quality: %d  [from %s]%s' % (overall, src, note))
    obj = {'file': path, 'size': len(data), 'tables': results,
           'overall_quality': overall}
    return '\n'.join(lines) + '\n', obj


# ---------------- 自测: 构造合成 JPEG ----------------

def _seg(marker, payload):
    return bytes((0xFF, marker)) + struct.pack('>H', len(payload) + 2) + payload


def build_test_jpeg(kind):
    """构造带 DQT/SOF0/DHT/SOS/EOI 的合成 JPEG。
    kind: q85 / q50 / q100 / wide16(额外 16-bit 精度表) / flat4(非标准表)"""
    out = bytearray(b'\xff\xd8')
    out += _seg(0xE0, b'JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00')
    q = {'q85': 85, 'q50': 50, 'q100': 100, 'wide16': 85}.get(kind)
    if kind == 'flat4':
        t0 = [4] * 64
        t1 = [4] * 64
    else:
        t0 = scaled_table(STD_LUMA, q)
        t1 = scaled_table(STD_CHROMA, q)
    out += _seg(0xDB, bytes([0x00]) + bytes(t0[i] for i in ZIGZAG)
                + bytes([0x01]) + bytes(t1[i] for i in ZIGZAG))
    if kind == 'wide16':
        out += _seg(0xDB, bytes([0x12]) + struct.pack('>64H', *(t0[i] for i in ZIGZAG)))
    sof = (bytes([8]) + struct.pack('>HH', 16, 8) + bytes([3])
           + bytes([1, 0x11, 0, 2, 0x11, 1, 3, 0x11, 1]))
    out += _seg(0xC0, sof)
    out += _seg(0xC4, bytes([0x00, 1]) + bytes(15) + bytes([0x00])
                + bytes([0x10, 1]) + bytes(15) + bytes([0x00]))
    out += _seg(0xDA, bytes([3, 1, 0x00, 2, 0x00, 3, 0x00, 0, 63, 0]))
    out += b'\x12\x34\x00'
    out += b'\xff\xd9'
    return bytes(out)


def selftest():
    tmp = tempfile.mkdtemp(prefix='jpeg_qt_selftest_')
    ok = True
    try:
        for kind, want in (('q85', 85), ('q50', 50), ('q100', 100), ('wide16', 85)):
            p = os.path.join(tmp, kind + '.jpg')
            with open(p, 'wb') as fh:
                fh.write(build_test_jpeg(kind))
            text, obj = run(p)
            t0 = next((t for t in obj['tables'] if t['id'] == 0), None)
            if t0 is None or t0['quality'] != want or t0['matches'] != 64:
                print('FAIL %s: got %r' % (kind, t0 and (t0['quality'], t0['matches'])))
                ok = False
            else:
                print('PASS %s: quality=%d, match=64/64, base=%s'
                      % (kind, t0['quality'], t0['base_table']))
            if kind == 'wide16':
                t2 = next((t for t in obj['tables'] if t['id'] == 2), None)
                if t2 is None or t2['precision'] != 16:
                    print('FAIL wide16: 16-bit table not parsed')
                    ok = False
                else:
                    print('PASS wide16: 16-bit table #2 parsed, quality=%d' % t2['quality'])
        p = os.path.join(tmp, 'flat4.jpg')
        with open(p, 'wb') as fh:
            fh.write(build_test_jpeg('flat4'))
        _text, obj = run(p)
        t0 = obj['tables'][0]
        if t0['matches'] >= 64:
            print('FAIL flat4: non-standard table reported as exact match')
            ok = False
        else:
            print('PASS flat4: custom table -> closest match %d/64 at q=%d'
                  % (t0['matches'], t0['quality']))
        if ok:
            print('SELFTEST PASS')
            return 0
        print('SELFTEST FAIL')
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Dump JPEG DQT quantization tables and estimate quality (IJG formula)')
    ap.add_argument('path', nargs='?', help='JPEG file to analyze')
    ap.add_argument('--json', action='store_true', help='output JSON instead of text')
    ap.add_argument('--selftest', action='store_true',
                    help='build synthetic JPEGs in a temp dir and verify the parser')
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
    except (JpegError, OSError, struct.error) as exc:
        print('ERROR: %s' % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(obj, indent=2))
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
