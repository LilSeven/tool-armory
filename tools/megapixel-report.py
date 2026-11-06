#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""像素量报告（megapixel-report）——像素总数、百万像素与未压缩内存估算。

用途:
    输出图像（或给定像素宽高）的像素总数与百万像素值，并按位深估算
    未压缩位图的内存占用：位深优先取 --bits，其次读文件内位深
    （PNG 按位深x颜色通道数、GIF 按 8、BMP 按头内 bpp；JPEG 头记录不了，
    缺省 24），最后附常见位深对照表。估算按“行内不填充”计：
    字节数 = ceil(像素总数 x 位深 / 8)，1 KiB = 1024 B。

用法:
    python -I megapixel-report.py <图像文件> [--bits N]
    python -I megapixel-report.py --width W --height H [--bits N]

示例:
    python -I megapixel-report.py photo.png
    python -I megapixel-report.py --width 3840 --height 2160 --bits 24
    python -I megapixel-report.py photo.png --json

说明:
    只用 Python 标准库；图像仅解析文件头（不解码像素），支持
    PNG/JPEG/GIF/BMP，最多读取文件前 8 MiB。
"""
import argparse
import json
import struct
import sys

HEADER_WINDOW = 8 * 1024 * 1024
TABLE_DEPTHS = (1, 4, 8, 16, 24, 32, 48, 64)


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
def uncompressed_bytes(pixels, bits):
    """按位深估算未压缩位图字节数（行内不填充）。"""
    return (pixels * bits + 7) // 8


def human_size(nbytes):
    """把字节数格式化为 B/KiB/MiB/GiB/TiB（二进制单位，1 KiB = 1024 B）。"""
    value = float(nbytes)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024.0 or unit == 'TiB':
            if unit == 'B':
                return f'{int(nbytes)} B'
            return f'{value:.2f} {unit}'
        value /= 1024.0
    return f'{nbytes} B'


def _positive_int(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError('需要整数：%r' % text)
    if value <= 0:
        raise argparse.ArgumentTypeError('需要正整数：%r' % text)
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        prog='megapixel-report',
        description='输出像素总数、百万像素值及按位深估算的未压缩位图内存占用。')
    parser.add_argument('image', nargs='?',
                        help='图像文件（PNG/JPEG/GIF/BMP），读取像素尺寸与位深')
    parser.add_argument('--width', type=_positive_int, metavar='PX',
                        help='像素宽（不给文件时与 --height 同用）')
    parser.add_argument('--height', type=_positive_int, metavar='PX',
                        help='像素高（不给文件时与 --width 同用）')
    parser.add_argument('--bits', type=_positive_int, metavar='N',
                        help='覆盖估算位深（bpp），如 8/24/32')
    parser.add_argument('--json', action='store_true', help='以 JSON 格式输出')
    return parser


def resolve(args):
    """返回 (info 或 None, 宽, 高)。"""
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


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass
    args = build_parser().parse_args(argv)
    info, width, height = resolve(args)
    pixels = width * height

    if args.bits is not None:
        bits, bits_src = args.bits, f'命令行 --bits {args.bits}'
    elif info and info['bits_per_pixel']:
        bits, bits_src = info['bits_per_pixel'], f'文件内记录（{info["format"]}）'
    else:
        bits, bits_src = 24, '缺省值 24'

    total = uncompressed_bytes(pixels, bits)
    result = {
        'file': args.image,
        'format': info['format'] if info else None,
        'width_px': width,
        'height_px': height,
        'pixels': pixels,
        'megapixels': round(pixels / 1e6, 4),
        'bits_per_pixel': bits,
        'bits_source': bits_src,
        'uncompressed_bytes': total,
        'uncompressed_human': human_size(total),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f'像素尺寸   : {width} x {height}')
    print(f'像素总数   : {pixels:,} px')
    print(f'百万像素   : {pixels / 1e6:.2f} MP')
    print(f'位深       : {bits} bpp ({bits_src})')
    print(f'未压缩占用 : {total:,} 字节 ({human_size(total)})')
    print()
    print('常见位深对照（未压缩估算，每行不做字节对齐填充）:')
    for depth in sorted(set(TABLE_DEPTHS) | {bits}):
        size = uncompressed_bytes(pixels, depth)
        mark = '  <- 采用' if depth == bits else ''
        print(f'  {depth:>2} bpp : {size:>14,} 字节 ({human_size(size):>10}){mark}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
