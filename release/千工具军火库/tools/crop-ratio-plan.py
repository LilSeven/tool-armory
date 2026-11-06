#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""裁剪比例方案（crop-ratio-plan）——按目标比例计算居中裁剪区域。

用途:
    给定图片尺寸（图像文件或 --width/--height）与目标宽高比 --ratio
    （如 16:9、1:1 或 1.7778），计算居中裁剪应保留的像素区域尺寸与
    左上角偏移（x、y 从 0 起算），并给出实际裁剪比例与保留像素占比。
    比例用分数精确计算，区域尺寸向下取整，保证不越出原图。

用法:
    python -I crop-ratio-plan.py <图像文件> --ratio 宽:高
    python -I crop-ratio-plan.py --width W --height H --ratio 宽:高

示例:
    python -I crop-ratio-plan.py --width 4000 --height 3000 --ratio 16:9
    python -I crop-ratio-plan.py photo.png --ratio 1:1
    python -I crop-ratio-plan.py photo.png --ratio 2.35 --json

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
    """把整数比化简为 a:b 形式（如 4000:3000 -> 4:3）。"""
    frac = Fraction(a, b)
    return f'{frac.numerator}:{frac.denominator}'


def parse_ratio(text):
    """解析比例字符串：'16:9'、'1.5:1' 或小数 '1.7778'，返回正分数。"""
    text = str(text).strip()
    try:
        if ':' in text:
            left, right = text.split(':', 1)
            value = Fraction(left.strip()) / Fraction(right.strip())
        else:
            value = Fraction(text)
    except (ValueError, ZeroDivisionError):
        raise argparse.ArgumentTypeError(
            f'无法解析比例：{text!r}（示例：16:9 或 1.7778）')
    if value <= 0:
        raise argparse.ArgumentTypeError(f'比例必须为正数：{text!r}')
    return value


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
        prog='crop-ratio-plan',
        description='给定目标比例，计算居中裁剪应保留的像素区域尺寸与偏移。')
    parser.add_argument('image', nargs='?',
                        help='图像文件（PNG/JPEG/GIF/BMP），读取像素尺寸')
    parser.add_argument('--width', type=_positive_int, metavar='PX',
                        help='像素宽（不给文件时与 --height 同用）')
    parser.add_argument('--height', type=_positive_int, metavar='PX',
                        help='像素高（不给文件时与 --width 同用）')
    parser.add_argument('--ratio', type=parse_ratio, required=True,
                        metavar='W:H', help='目标宽高比，如 16:9、1:1 或 1.7778')
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
    target = args.ratio
    img_ratio = Fraction(width, height)

    if img_ratio > target:
        crop_w = max(1, int(Fraction(height) * target))  # 向下取整，不越界
        crop_h = height
        direction = '保留全高，左右居中裁剪（原图比目标更宽）'
    else:
        crop_w = width
        crop_h = max(1, int(Fraction(width) / target))
        direction = '保留全宽，上下居中裁剪（原图比目标更窄或一致）'
    off_x = (width - crop_w) // 2
    off_y = (height - crop_h) // 2

    actual = Fraction(crop_w, crop_h)
    kept = crop_w * crop_h
    total = width * height

    result = {
        'file': args.image,
        'format': info['format'] if info else None,
        'width_px': width,
        'height_px': height,
        'image_ratio': float(img_ratio),
        'target_ratio': float(target),
        'target_ratio_fraction': f'{target.numerator}:{target.denominator}',
        'crop_width': crop_w,
        'crop_height': crop_h,
        'offset_x': off_x,
        'offset_y': off_y,
        'actual_ratio': float(actual),
        'kept_percent': round(kept / total * 100.0, 2),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f'原图尺寸   : {width} x {height} '
          f'(比例 {ratio_str(width, height)} ≈ {float(img_ratio):.4f})')
    print(f'目标比例   : {target.numerator}:{target.denominator} '
          f'≈ {float(target):.4f}')
    print(f'裁剪方向   : {direction}')
    print(f'保留区域   : {crop_w} x {crop_h} px')
    print(f'左上偏移   : x={off_x}, y={off_y} (从 0 起算，区域居中)')
    print(f'实际比例   : {actual.numerator}:{actual.denominator} '
          f'≈ {float(actual):.4f}')
    print(f'保留像素   : {kept / total * 100.0:.2f}% ({kept:,} / {total:,} px)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
