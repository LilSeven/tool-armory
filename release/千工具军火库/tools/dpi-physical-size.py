#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""物理尺寸换算（dpi-physical-size）——把像素尺寸按 DPI 换算成英寸/厘米/毫米。

用途:
    优先读取图像文件内记录的分辨率（PNG pHYs、JPEG JFIF 密度、BMP 头），
    否则使用缺省 DPI（默认 96，--fallback-dpi 可改），把像素宽高换算为
    英寸、厘米、毫米的物理尺寸并给出对角线；--dpi/--dpi-x/--dpi-y 可
    覆盖文件内记录的值。

用法:
    python -I dpi-physical-size.py <图像文件> [选项]
    python -I dpi-physical-size.py --width 像素宽 --height 像素高 [选项]

示例:
    python -I dpi-physical-size.py photo.png
    python -I dpi-physical-size.py photo.png --dpi 300
    python -I dpi-physical-size.py --width 1920 --height 1080 --dpi 96
    python -I dpi-physical-size.py photo.png --json

说明:
    只用 Python 标准库；图像仅解析文件头（不解码像素），支持
    PNG/JPEG/GIF/BMP，最多读取文件前 8 MiB。
"""
import argparse
import json
import math
import struct
import sys

INCH_MM = 25.4
DEFAULT_DPI = 96.0
HEADER_WINDOW = 8 * 1024 * 1024


# ---------------------------------------------------------------------------
# 图像头解析：仅用标准库解析 PNG/JPEG/GIF/BMP 的宽高、DPI、位深（不解码像素）
# ---------------------------------------------------------------------------
_PNG_SIG = b'\x89PNG\r\n\x1a\n'


def _parse_png(data):
    """解析 PNG：IHDR 宽高与位深 + pHYs 物理分辨率（像素/米 → DPI）。"""
    if data[:8] != _PNG_SIG or len(data) < 33:
        return None
    width, height = struct.unpack('>II', data[16:24])
    bit_depth, color_type = data[24], data[25]
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    bpp = bit_depth * channels if channels else None
    dpi_x = dpi_y = None
    pos = 8
    while pos + 8 <= len(data):
        (length,) = struct.unpack('>I', data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        if ctype == b'IDAT':
            break
        cdata = data[pos + 8:pos + 8 + length]
        if ctype == b'pHYs' and length == 9:
            ppm_x, ppm_y, unit = struct.unpack('>IIB', cdata)
            if unit == 1 and ppm_x and ppm_y:
                dpi_x, dpi_y = ppm_x * 0.0254, ppm_y * 0.0254
        pos += 12 + length
    return {'format': 'PNG', 'width': width, 'height': height,
            'dpi_x': dpi_x, 'dpi_y': dpi_y, 'bits_per_pixel': bpp}


def _parse_jpeg(data):
    """解析 JPEG：SOF 段宽高 + JFIF APP0 密度（units 1=点/英寸，2=点/厘米）。"""
    if data[:2] != b'\xff\xd8':
        return None
    width = height = dpi_x = dpi_y = None
    pos, n = 2, len(data)
    while pos + 4 <= n:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker == 0xFF:
            pos += 1
            continue
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        if marker in (0xD9, 0xDA):  # EOI / SOS：头信息到此为止
            break
        (seg_len,) = struct.unpack('>H', data[pos + 2:pos + 4])
        if seg_len < 2 or pos + 2 + seg_len > n:
            break
        seg = data[pos + 4:pos + 2 + seg_len]
        if marker == 0xE0 and seg[:5] == b'JFIF\x00' and len(seg) >= 12:
            units = seg[7]
            xd, yd = struct.unpack('>HH', seg[8:12])
            if xd and yd:
                if units == 1:
                    dpi_x, dpi_y = float(xd), float(yd)
                elif units == 2:
                    dpi_x, dpi_y = xd * 2.54, yd * 2.54
        elif (0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC)
              and len(seg) >= 5):
            height, width = struct.unpack('>HH', seg[1:5])
        pos += 2 + seg_len
    if width is None or height is None:
        return None
    return {'format': 'JPEG', 'width': width, 'height': height,
            'dpi_x': dpi_x, 'dpi_y': dpi_y, 'bits_per_pixel': None}


def _parse_gif(data):
    """解析 GIF 逻辑屏幕描述块（GIF 不记录 DPI）。"""
    if data[:6] not in (b'GIF87a', b'GIF89a') or len(data) < 10:
        return None
    width, height = struct.unpack('<HH', data[6:10])
    return {'format': 'GIF', 'width': width, 'height': height,
            'dpi_x': None, 'dpi_y': None, 'bits_per_pixel': 8}


def _parse_bmp(data):
    """解析 BMP 信息头（仅支持 biSize>=40 的常见格式）。"""
    if data[:2] != b'BM' or len(data) < 54:
        return None
    (header_size,) = struct.unpack('<I', data[14:18])
    if header_size < 40:
        return None
    width, height = struct.unpack('<ii', data[18:26])
    (bpp,) = struct.unpack('<H', data[28:30])
    xppm, yppm = struct.unpack('<ii', data[38:46])
    return {'format': 'BMP', 'width': abs(width), 'height': abs(height),
            'dpi_x': xppm * 0.0254 if xppm > 0 else None,
            'dpi_y': yppm * 0.0254 if yppm > 0 else None,
            'bits_per_pixel': bpp or None}


def read_image_info(path):
    """读取图像基本信息：宽、高、DPI、每像素比特数（未知则为 None）。

    只解析文件头，不解码像素；最多读取文件前 8 MiB；无法识别返回 None。
    """
    with open(path, 'rb') as fh:
        data = fh.read(HEADER_WINDOW)
    for parser in (_parse_png, _parse_jpeg, _parse_gif, _parse_bmp):
        info = parser(data)
        if info:
            return info
    return None


# ---------------------------------------------------------------------------
def _positive_int(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError('需要整数：%r' % text)
    if value <= 0:
        raise argparse.ArgumentTypeError('需要正整数：%r' % text)
    return value


def _positive_float(text):
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError('需要数字：%r' % text)
    if not (value > 0):
        raise argparse.ArgumentTypeError('需要正数：%r' % text)
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        prog='dpi-physical-size',
        description='把像素尺寸按 DPI 换算为英寸/厘米/毫米物理尺寸。')
    parser.add_argument('image', nargs='?',
                        help='图像文件（PNG/JPEG/GIF/BMP），读取像素尺寸与 DPI')
    parser.add_argument('--width', type=_positive_int, metavar='PX',
                        help='像素宽（不给文件时与 --height 同用；给了则覆盖文件宽）')
    parser.add_argument('--height', type=_positive_int, metavar='PX',
                        help='像素高（不给文件时与 --width 同用；给了则覆盖文件高）')
    parser.add_argument('--dpi', type=_positive_float,
                        help='同时覆盖横向与纵向 DPI')
    parser.add_argument('--dpi-x', type=_positive_float, help='覆盖横向 DPI')
    parser.add_argument('--dpi-y', type=_positive_float, help='覆盖纵向 DPI')
    parser.add_argument('--fallback-dpi', type=_positive_float,
                        default=DEFAULT_DPI, metavar='DPI',
                        help='文件未记录 DPI 时的缺省值（默认 %(default)s）')
    parser.add_argument('--json', action='store_true', help='以 JSON 格式输出')
    return parser


def resolve(args):
    """返回 (info 或 None, 宽, 高)。尺寸以命令行 --width/--height 优先。"""
    info = None
    if args.image:
        info = read_image_info(args.image)
        if info is None:
            raise SystemExit('错误：无法识别的图像文件：%s' % args.image)
    if args.width and args.height:
        return info, args.width, args.height
    if info:
        return info, info['width'], info['height']
    raise SystemExit('错误：请提供图像文件，或同时给出 --width 与 --height。')


def choose_dpi(args, info):
    """DPI 来源优先级：--dpi-x/--dpi-y/--dpi > 文件内记录 > 缺省值。"""
    file_x = info['dpi_x'] if info else None
    file_y = info['dpi_y'] if info else None
    if args.dpi_x is not None:
        dpi_x, src_x = args.dpi_x, '命令行 --dpi-x'
    elif args.dpi is not None:
        dpi_x, src_x = args.dpi, '命令行 --dpi'
    elif file_x:
        dpi_x, src_x = file_x, '文件内记录'
    else:
        dpi_x, src_x = args.fallback_dpi, '缺省 %g' % args.fallback_dpi
    if args.dpi_y is not None:
        dpi_y, src_y = args.dpi_y, '命令行 --dpi-y'
    elif args.dpi is not None:
        dpi_y, src_y = args.dpi, '命令行 --dpi'
    elif file_y:
        dpi_y, src_y = file_y, '文件内记录'
    else:
        dpi_y, src_y = args.fallback_dpi, '缺省 %g' % args.fallback_dpi
    return dpi_x, dpi_y, src_x, src_y


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass
    args = build_parser().parse_args(argv)
    info, width, height = resolve(args)
    dpi_x, dpi_y, src_x, src_y = choose_dpi(args, info)

    w_in = width / dpi_x
    h_in = height / dpi_y
    diag_in = math.hypot(w_in, h_in)
    result = {
        'file': args.image,
        'format': info['format'] if info else None,
        'width_px': width,
        'height_px': height,
        'dpi_x': round(dpi_x, 4),
        'dpi_y': round(dpi_y, 4),
        'dpi_source_x': src_x,
        'dpi_source_y': src_y,
        'width_inch': round(w_in, 4),
        'height_inch': round(h_in, 4),
        'width_cm': round(w_in * 2.54, 3),
        'height_cm': round(h_in * 2.54, 3),
        'width_mm': round(w_in * INCH_MM, 2),
        'height_mm': round(h_in * INCH_MM, 2),
        'diagonal_inch': round(diag_in, 4),
        'diagonal_cm': round(diag_in * 2.54, 3),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    fmt_label = info['format'] if info else '命令行像素值'
    print(f'像素尺寸 : {width} x {height} px ({fmt_label})')
    print(f'DPI      : x={dpi_x:.4f} ({src_x}) , y={dpi_y:.4f} ({src_y})')
    print(f'宽度     : {w_in:.4f} in | {result["width_cm"]:.3f} cm | '
          f'{result["width_mm"]:.2f} mm')
    print(f'高度     : {h_in:.4f} in | {result["height_cm"]:.3f} cm | '
          f'{result["height_mm"]:.2f} mm')
    print(f'对角线   : {diag_in:.4f} in | {result["diagonal_cm"]:.3f} cm')
    return 0


if __name__ == '__main__':
    sys.exit(main())
