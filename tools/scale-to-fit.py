#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""等比缩放计算（scale-to-fit）——等比缩放到恰好放进目标框。

用途:
    给定图片尺寸（图像文件或 --width/--height）与目标框宽高 --box，
    计算等比缩放后恰好放入目标框的新尺寸：缩放系数取
    min(框宽/图宽, 框高/图高)，用分数精确计算并向下取整，保证结果不
    超出目标框；--no-upscale 可限制只缩小不放大。

用法:
    python -I scale-to-fit.py <图像文件> --box 框宽 框高 [--no-upscale]
    python -I scale-to-fit.py --width W --height H --box 框宽 框高 [--no-upscale]

示例:
    python -I scale-to-fit.py --width 1920 --height 1080 --box 1280 720
    python -I scale-to-fit.py photo.png --box 800 600 --no-upscale
    python -I scale-to-fit.py photo.png --box 800 600 --json

说明:
    只用 Python 标准库（fractions 做精确比例运算）；图像仅解析文件头
    （不解码像素），支持 PNG/JPEG/GIF/BMP，最多读取文件前 8 MiB。
"""
import argparse
import json
import struct
import sys
from fractions import Fraction

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
def ratio_str(a, b):
    """把整数比化简为 a:b 形式（如 1920:1080 -> 16:9）。"""
    frac = Fraction(a, b)
    return f'{frac.numerator}:{frac.denominator}'


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
        prog='scale-to-fit',
        description='给定目标框宽高，计算图片等比缩放后恰好的新尺寸。')
    parser.add_argument('image', nargs='?',
                        help='图像文件（PNG/JPEG/GIF/BMP），读取像素尺寸')
    parser.add_argument('--width', type=_positive_int, metavar='PX',
                        help='像素宽（不给文件时与 --height 同用）')
    parser.add_argument('--height', type=_positive_int, metavar='PX',
                        help='像素高（不给文件时与 --width 同用）')
    parser.add_argument('--box', nargs=2, type=_positive_int, required=True,
                        metavar=('BOX_W', 'BOX_H'), help='目标框 宽 高（两个正整数）')
    parser.add_argument('--no-upscale', dest='no_upscale', action='store_true',
                        help='仅缩小不放大：原图已在框内时保持原尺寸')
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
    box_w, box_h = args.box

    sx = Fraction(box_w, width)
    sy = Fraction(box_h, height)
    scale = min(sx, sy)
    clamped = False
    if args.no_upscale and scale > 1:
        scale = Fraction(1)
        clamped = True
    # 用精确分数计算后向下取整，保证不超出目标框；至少保留 1 像素。
    new_w = max(1, int(width * scale))
    new_h = max(1, int(height * scale))

    if clamped:
        mode = '仅缩小模式：原图未超出目标框，保持原尺寸'
    elif sx == sy:
        mode = '宽高同时受限（原图与目标框比例一致）'
    elif sx < sy:
        mode = '宽度受限'
    else:
        mode = '高度受限'

    result = {
        'file': args.image,
        'format': info['format'] if info else None,
        'width_px': width,
        'height_px': height,
        'box_w': box_w,
        'box_h': box_h,
        'scale': float(scale),
        'scale_fraction': f'{scale.numerator}/{scale.denominator}',
        'new_width': new_w,
        'new_height': new_h,
        'mode': mode,
        'no_upscale': args.no_upscale,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f'原图尺寸   : {width} x {height} '
          f'(比例 {ratio_str(width, height)} ≈ {width / height:.4f})')
    print(f'目标框     : {box_w} x {box_h} '
          f'(比例 {ratio_str(box_w, box_h)} ≈ {box_w / box_h:.4f})')
    print(f'缩放系数   : {scale.numerator}/{scale.denominator} '
          f'≈ {float(scale):.6f}  ({mode})')
    print(f'新尺寸     : {new_w} x {new_h} '
          f'(等比、向下取整，不超出目标框)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
