#!/usr/bin/env python3
"""尾部附加数据报告 —— 报告各图片正式结构结束点之后的附加数据大小并猜测其类型。

各格式"正式结构结束点"定义:
  JPEG      : EOI(FF D9) 之后(SOI..EOI 结构化遍历, 失败时按最后一个 FFD9 估计)
  PNG       : IEND 块结束(块类型+CRC)之后
  GIF       : 结束符 0x3B 之后
  BMP       : bfOffBits + 行公式推算的未压缩数据区之后(压缩格式按 bfSize 估计)
  ICO       : 目录项声明的最后一个数据区(offset+size)之后
  WEBP      : RIFF 声明大小(8 字节头 + 4 字节处长度)之后
  HEIF/AVIF : 顶层 ISO-BMFF box 链走完之后
对结束点之后的字节按起始魔数/可打印率/零填充猜测类型
(ZIP/EXE/PDF/内嵌图片/文本/零填充等)。

示例命令:
  python trailing-data-report.py pic.png
  python trailing-data-report.py a.jpg b.png
  python trailing-data-report.py ./shots          # 扫描目录(非递归)
  python trailing-data-report.py -r ./uploads     # 递归扫描
  python trailing-data-report.py --selftest       # 在临时目录构造示例自测

退出码: 0=全部干净  1=发现附加数据或结构异常  2=用法或 IO 错误
"""

import argparse
import io
import shutil
import struct
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path


def u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def i32(d, o):
    return struct.unpack_from("<i", d, o)[0]


def u64(d, o):
    return struct.unpack_from("<Q", d, o)[0]


def guess_tail(b: bytes) -> str:
    """对尾部附加数据做粗略类型猜测。"""
    if not b:
        return "无"
    head = b[:16]
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return "ZIP 压缩包"
    if head[:2] == b"MZ":
        return "EXE/DLL 可执行文件"
    if head[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7-Zip 压缩包"
    if head[:4] == b"Rar!":
        return "RAR 压缩包"
    if head[:2] == b"\x1f\x8b":
        return "GZIP"
    if head[:5] == b"%PDF-":
        return "PDF 文档"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "内嵌 PNG"
    if head[:3] == b"\xff\xd8\xff":
        return "内嵌 JPEG"
    if head[:2] == b"BM":
        return "内嵌 BMP"
    if head[:4] == b"RIFF":
        return "RIFF 容器(WEBP/WAV 等)"
    sample = b[:256]
    if sample and sample.count(0) == len(sample):
        return "零填充"
    printable = sum(1 for x in sample if 32 <= x < 127 or x in (9, 10, 13))
    if printable / len(sample) > 0.85:
        return "文本/脚本"
    return "未知(随机或加密数据?)"


# ---------------- JPEG: 结构化遍历定位 EOI ----------------

STANDALONE_MARKERS = {0x01, 0xC8} | set(range(0xD0, 0xD8))


def walk_jpeg(data: bytes) -> dict:
    """结构化遍历 JPEG 标记段链, 返回 eoi_offset 等。"""
    res = {"size": len(data), "is_jpeg": False, "eoi_offset": None, "problems": []}
    n = res["size"]
    problems = res["problems"]
    if n < 4 or data[:2] != b"\xff\xd8":
        problems.append("缺少 SOI(FF D8) 起始标记, 不是 JPEG 数据")
        return res
    res["is_jpeg"] = True
    pos = 2
    while True:
        if pos >= n:
            problems.append("遍历到文件末尾仍未遇到 EOI(FF D9)")
            break
        if data[pos] != 0xFF:
            problems.append(f"偏移 0x{pos:X}: 段间出现杂散字节, 段链不连续")
            break
        while pos < n and data[pos] == 0xFF:
            pos += 1
        if pos >= n:
            problems.append("文件在标记填充字节处截断, 未见 EOI")
            break
        marker = data[pos]
        pos += 1
        if marker == 0xD9:
            res["eoi_offset"] = pos - 2
            break
        if marker in STANDALONE_MARKERS:
            continue
        if marker == 0xD8:
            problems.append(f"偏移 0x{pos - 2:X}: 出现多余的 SOI(FF D8)")
            continue
        if pos + 2 > n:
            problems.append(f"标记 FF {marker:02X} 的段长度字段被截断")
            break
        seglen = (data[pos] << 8) | data[pos + 1]
        if seglen < 2 or pos + seglen > n:
            problems.append(f"标记 FF {marker:02X} 段长 {seglen} 非法或越界")
            break
        pos += seglen
        if marker == 0xDA:  # SOS 之后的熵编码扫描数据
            while pos < n - 1:
                if data[pos] != 0xFF:
                    pos += 1
                    continue
                nxt = data[pos + 1]
                if nxt == 0x00 or 0xD0 <= nxt <= 0xD7:
                    pos += 2
                else:
                    break
            if pos == n - 2 and data[pos:pos + 2] == b"\xff\xd9":
                res["eoi_offset"] = pos
                break
            if pos >= n - 1:
                problems.append("熵编码扫描数据直到文件末尾也没有 EOI(FF D9)")
                break
    return res


def jpeg_end(data: bytes):
    r = walk_jpeg(data)
    if r["eoi_offset"] is not None:
        return r["eoi_offset"] + 2, ""
    idx = data.rfind(b"\xff\xd9")
    if idx >= 0:
        return idx + 2, "结构遍历失败, 按最后一个 FFD9 估计"
    return None, "未找到 EOI(FF D9)"


# ---------------- PNG / GIF / BMP / ICO / WEBP / HEIF ----------------

def png_end(data: bytes):
    idx = data.rfind(b"IEND")
    if idx < 8:
        return None, "未找到 IEND 块, PNG 结构不完整"
    return idx + 8, ""  # 块类型(4) + CRC(4)


def gif_end(data: bytes):
    if data[-1:] == b"\x3b":
        return len(data), ""
    idx = data.rfind(b"\x3b")
    if idx <= 0:
        return None, "未找到 GIF 结束符 0x3B"
    return idx + 1, "按最后一个 0x3B 估计"


def bmp_end(data: bytes):
    if len(data) < 18:
        return None, "BMP 头被截断, 无法定位数据区"
    off = u32(data, 10)
    bi_size = u32(data, 14)
    if bi_size == 12:  # BITMAPCOREHEADER
        if len(data) < 26:
            return None, "BITMAPCOREHEADER 被截断"
        w, h, bpp, comp = u16(data, 18), u16(data, 20), u16(data, 24), 0
    elif bi_size >= 40:
        if len(data) < 34:
            return None, "BITMAPINFOHEADER 被截断"
        w, h = i32(data, 18), i32(data, 22)
        bpp, comp = u16(data, 28), u32(data, 30)
    else:
        return None, f"DIB 头大小 {bi_size} 无法识别"
    if comp not in (0, 3):
        bf_size = u32(data, 2)
        if 0 < bf_size <= len(data):
            return bf_size, f"压缩类型 {comp}, 按 bfSize 估计"
        return None, f"压缩类型 {comp} 且 bfSize 不可信"
    rowsize = ((w * bpp + 31) // 32) * 4
    end = off + rowsize * abs(h)
    if end > len(data):
        return None, f"公式推算数据区应到 {end} 字节, 超过文件大小 {len(data)}(截断)"
    return end, ""


def ico_end(data: bytes):
    if len(data) < 6:
        return None, "ICO 目录头不完整"
    count = u16(data, 4)
    end = 0
    for i in range(count):
        b = 6 + 16 * i
        if b + 16 > len(data):
            return None, "目录项越界, ICO 结构损坏"
        end = max(end, u32(data, b + 8) + u32(data, b + 12))
    if end == 0:
        return None, "目录项数为 0, 无图示数据"
    if end > len(data):
        return None, "目录项声明的数据区超出文件(截断)"
    return end, ""


def riff_end(data: bytes):
    size = u32(data, 4)
    end = 8 + size
    if end > len(data):
        return None, f"RIFF 声明大小 {size}+8 超过文件大小 {len(data)}(截断)"
    return end, ""


def box_end(data: bytes):
    """HEIF/AVIF: 遍历顶层 ISO-BMFF box。"""
    pos, n = 0, len(data)
    while pos < n:
        if pos + 8 > n:
            return pos, f"剩余 {n - pos} 字节不足以构成 box 头, 视为附加数据"
        size = u32(data, pos)
        if size == 0:
            return n, ""  # box 延伸到文件尾
        if size == 1:
            if pos + 16 > n:
                return pos, f"剩余 {n - pos} 字节不足以构成 64 位 box 头, 视为附加数据"
            size = u64(data, pos + 8)
        if size < 8:
            return pos, (f"偏移 0x{pos:X} 处 box 大小 {size} 非法, "
                         f"之后 {n - pos} 字节视为附加数据")
        if pos + size > n:
            return None, f"偏移 0x{pos:X} 处 box 声明大小 {size} 超出文件(结构截断)"
        pos += size
    return n, ""


def analyze(data: bytes):
    """返回 (fmt, end_offset 或 None, note)。"""
    if data[:2] == b"\xff\xd8":
        fmt = "JPEG"
        end, note = jpeg_end(data)
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        fmt = "PNG"
        end, note = png_end(data)
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        fmt = "GIF"
        end, note = gif_end(data)
    elif data[:2] == b"BM":
        fmt = "BMP"
        end, note = bmp_end(data)
    elif data[:4] == b"\x00\x00\x01\x00":
        fmt = "ICO"
        end, note = ico_end(data)
    elif data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        fmt = "WEBP"
        end, note = riff_end(data)
    elif len(data) >= 12 and data[4:8] == b"ftyp":
        fmt = "HEIF/AVIF"
        end, note = box_end(data)
    else:
        return None, None, "无法识别的图片格式"
    return fmt, end, note


def report(path: str, data: bytes) -> bool:
    """打印单个文件报告, 返回是否发现附加数据或异常。"""
    fmt, end, note = analyze(data)
    print(f"文件: {path} ({len(data)} 字节)")
    if fmt is None or end is None:
        print(f"  [问题] {note}")
        print("结论: 无法确定正式结构结束点")
        return True
    note_sfx = f" ({note})" if note else ""
    if end >= len(data):
        print(f"  格式: {fmt}   正式结构结束点: 0x{end:X} ({end}) = 文件末尾{note_sfx}")
        print("  尾部附加数据: 无   [OK]")
        print("结论: 干净")
        return False
    tail = len(data) - end
    print(f"  格式: {fmt}   正式结构结束点: 0x{end:X} ({end}){note_sfx}")
    print(f"  尾部附加数据: {tail} 字节   [发现]")
    print(f"  类型猜测: {guess_tail(data[end:])}   开头: {data[end:end + 8].hex(' ')}")
    print("结论: 发现尾部附加数据")
    return True


def run_scan(targets, recursive: bool) -> int:
    """扫描目标并打印报告, 返回进程退出码。"""
    files, missing, read_err = [], False, False
    for t in targets:
        p = Path(t)
        if p.is_dir():
            try:
                it = p.rglob("*") if recursive else p.iterdir()
                files.extend(str(q) for q in it if q.is_file())
            except OSError as e:
                print(f"[错误] 无法枚举目录 {t}: {e}")
                missing = True
        elif p.is_file():
            files.append(str(p))
        else:
            print(f"[错误] 目标不存在: {t}")
            missing = True
    clean = bad = 0
    for fp in sorted(files):
        try:
            data = Path(fp).read_bytes()
        except OSError as e:
            print(f"文件: {fp}\n  [错误] 无法读取: {e}\n结论: 读取失败")
            read_err = True
            continue
        if report(fp, data):
            bad += 1
        else:
            clean += 1
    print(f"合计: 干净 {clean} / 发现附加数据或异常 {bad}")
    if missing or read_err:
        return 2
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="trailing-data-report.py",
        description="报告图片正式结构结束点之后的附加数据大小并猜测其类型")
    ap.add_argument("targets", nargs="*", metavar="目录或文件",
                    help="要检查的图片文件或目录")
    ap.add_argument("-r", "--recursive", action="store_true", help="递归扫描子目录")
    ap.add_argument("--selftest", action="store_true", help="构造示例文件运行内置自测")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.targets:
        ap.print_usage(sys.stderr)
        print("trailing-data-report.py: 错误: 未提供目标, 或使用 --selftest 查看示例",
              file=sys.stderr)
        return 2
    return run_scan(args.targets, args.recursive)


# ---------------- 内置自测: 临时目录构造示例文件 ----------------

def make_png_bytes() -> bytes:
    def chunk(ctype: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + ctype + payload
                + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
            + chunk(b"IEND", b""))


def make_bmp_bytes() -> bytes:
    row = ((3 * 24 + 31) // 32) * 4
    dib = struct.pack("<IiiHHIIiiII", 40, 3, 2, 1, 24, 0, row * 2, 0, 0, 0, 0)
    fhdr = b"BM" + struct.pack("<IHHI", 14 + 40 + row * 2, 0, 0, 54)
    return fhdr + dib + bytes(row * 2)


def make_clean_jpeg() -> bytes:
    def seg(m, p=b""):
        return bytes([0xFF, m]) + (len(p) + 2).to_bytes(2, "big") + p

    scan = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55])
    return (b"\xff\xd8" + seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
            + seg(0xDB, b"\x00" * 65) + seg(0xC0, b"\x00" * 15)
            + seg(0xDA, b"\x00\x01\x01\x00\x00\x3F\x00") + scan + b"\xff\xd9")


def make_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("payload.txt", "appended payload")
    return buf.getvalue()


def make_min_ico() -> bytes:
    payload = b"\x00" * 64
    entry = bytes([16, 16, 0, 0]) + struct.pack("<HHII", 1, 32, len(payload), 22)
    return struct.pack("<HHH", 0, 1, 1) + entry + payload


def make_min_webp() -> bytes:
    rest = b"VP8 \x00\x00\x00\x00"
    return b"RIFF" + struct.pack("<I", 4 + len(rest)) + b"WEBP" + rest


def selftest() -> int:
    tmp = tempfile.mkdtemp(prefix="trailing-data-report-selftest-")
    checks = []
    try:
        d = Path(tmp)
        jpg_clean = make_clean_jpeg()
        png_clean = make_png_bytes()
        bmp_clean = make_bmp_bytes()
        zip_bytes = make_zip_bytes()
        (d / "clean.png").write_bytes(png_clean)
        (d / "clean.jpg").write_bytes(jpg_clean)
        (d / "clean.bmp").write_bytes(bmp_clean)
        (d / "trailing.png").write_bytes(png_clean + zip_bytes)
        (d / "trailing.jpg").write_bytes(jpg_clean + b"Hello, trailing text!")
        (d / "trailing.bmp").write_bytes(bmp_clean + b"\x00" * 32)

        print("=== 自测 1: 干净文件 (期望全部干净, 退出码 0) ===")
        checks.append(run_scan([str(d / "clean.png"), str(d / "clean.jpg"),
                                str(d / "clean.bmp")], False) == 0)
        print("=== 自测 2: 含附加数据目录 (期望报告 3 个, 退出码 1) ===")
        checks.append(run_scan([str(d)], False) == 1)

        fmt, end, _ = analyze(png_clean)
        checks.append(fmt == "PNG" and end == len(png_clean))
        fmt, end, _ = analyze(jpg_clean)
        checks.append(fmt == "JPEG" and end == len(jpg_clean))
        fmt, end, _ = analyze(bmp_clean)
        checks.append(fmt == "BMP" and end == len(bmp_clean))
        fmt, end, _ = analyze(make_min_ico())
        checks.append(fmt == "ICO" and end == len(make_min_ico()))
        fmt, end, _ = analyze(make_min_webp())
        checks.append(fmt == "WEBP" and end == len(make_min_webp()))
        dirty = png_clean + zip_bytes
        fmt, end, _ = analyze(dirty)
        checks.append(fmt == "PNG" and len(dirty) - end == len(zip_bytes))
        dirty_jpg = jpg_clean + b"Hello, trailing text!"
        fmt, end, _ = analyze(dirty_jpg)
        checks.append(fmt == "JPEG" and len(dirty_jpg) - end == 21)
        gif_dirty = b"GIF89a" + b"\x00" * 10 + b"\x3b" + b"JUNK"
        fmt, end, note = analyze(gif_dirty)
        checks.append(fmt == "GIF" and len(gif_dirty) - end == 4 and "0x3B" in note)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if all(checks):
        print(f"[自测] {len(checks)} 项断言全部通过")
        return 0
    print(f"[自测] 失败: {checks}")
    return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
