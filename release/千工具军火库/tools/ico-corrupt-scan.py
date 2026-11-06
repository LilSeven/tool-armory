#!/usr/bin/env python3
"""ICO 完整性扫描 —— 校验每个目录项声明的尺寸、位深与实际内嵌位图数据是否自洽。

检查内容:
  1. 目录头: 保留字段为 0、类型为 1(ICO)/2(CUR)、目录项数与文件大小相符;
  2. 每个目录项: bytesInRes 非 0、数据区 [imageOffset, +bytesInRes) 不越界、
     起始不落入目录区、与其他项数据区不重叠;
  3. PNG 型图示: 校验 PNG 魔数, 并比对 IHDR 实际宽高与目录声明(0 视为 256);
  4. DIB 型图示: biWidth 应等于声明宽、biHeight 应等于 2×声明高(异或+与掩码)、
     位深与目录声明一致, 并按 头+调色板+异或位图+与掩码 公式推算大小,
     与 bytesInRes 比对。

示例命令:
  python ico-corrupt-scan.py app.ico
  python ico-corrupt-scan.py a.ico b.ico
  python ico-corrupt-scan.py --selftest      # 在临时目录构造示例自测

退出码: 0=全部自洽  1=发现不一致  2=用法或 IO 错误
"""

import argparse
import os
import shutil
import struct
import sys
import tempfile
import zlib


def u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def i32(d, o):
    return struct.unpack_from("<i", d, o)[0]


def u32be(d, o):
    """大端无符号 32 位读(PNG 等网络字节序结构用)。"""
    return struct.unpack_from(">I", d, o)[0]


def check_dib(body: bytes, dw: int, dh: int, bpp_declared: int, size: int):
    """校验内嵌 DIB, 返回 (issues, lines)。"""
    issues, lines = [], []
    if len(body) < 40:
        return [f"内嵌 DIB 头仅 {len(body)} 字节, 不完整"], lines
    bi_size = u32(body, 0)
    bw = i32(body, 4)
    bh = i32(body, 8)
    bbpp = u16(body, 14)
    comp = u32(body, 16)
    clr_used = u32(body, 32) if len(body) >= 36 and bi_size >= 40 else 0
    lines.append(f"      内嵌: DIB  biSize={bi_size}  biWidth={bw}  "
                 f"biHeight={bh}  位深 {bbpp}")
    if bi_size < 40:
        issues.append(f"DIB 头大小 {bi_size} 过小, 无法核验(仅支持 >= 40)")
        return issues, lines
    if comp != 0:
        issues.append(f"内嵌 DIB 压缩类型 {comp} 异常(图标通常为 BI_RGB/0)")
    if bw != dw:
        issues.append(f"目录声明宽 {dw}, DIB biWidth={bw} 不一致")
    if bh == 2 * dh:
        lines.append(f"      尺寸: 目录 {dw}x{dh} ↔ DIB {bw}x{bh}"
                     f"(高=图像高×2, 含异或+与掩码)   [OK]")
    elif bh == dh:
        issues.append(f"目录声明高 {dh}, DIB biHeight={bh} 未包含与掩码高度"
                      f"(规范应为 2×)")
    else:
        issues.append(f"目录声明高 {dh}, DIB biHeight={bh} 与 2×({2 * dh}) 均不符")
    if bpp_declared == 0 or bpp_declared == bbpp:
        lines.append(f"      位深: {bbpp}   [OK]")
    else:
        issues.append(f"目录声明位深 {bpp_declared}, DIB 位深 {bbpp} 不一致")
    row_img = ((bw * bbpp + 31) // 32) * 4
    row_and = ((bw + 31) // 32) * 4
    pal_n = clr_used if clr_used else (0 if bbpp > 8 else 2 ** bbpp)
    expected = bi_size + pal_n * 4 + row_img * dh + row_and * dh
    detail = (f"{bi_size}(头) + {pal_n * 4}(调色板) + {row_img}×{dh}(异或位图) "
              f"+ {row_and}×{dh}(与掩码) = {expected}")
    if size < expected:
        issues.append(f"bytesInRes={size} 小于推算值 {expected}({detail}), 数据不足/损坏")
    elif size > expected:
        issues.append(f"bytesInRes={size} 大于推算值 {expected}({detail}), "
                      f"多 {size - expected} 字节")
    else:
        lines.append(f"      大小: {detail} ↔ bytesInRes {size}   [OK]")
    return issues, lines


def scan_ico(data: bytes):
    """扫描 ICO, 返回 (problems, lines)。problems 非空表示不自洽。"""
    problems = []
    lines = []
    n = len(data)
    if n < 6:
        return [f"文件仅 {n} 字节, 图标目录头不完整"], lines
    reserved = u16(data, 0)
    itype = u16(data, 2)
    count = u16(data, 4)
    type_name = {1: "ICO", 2: "CUR"}.get(itype, f"未知({itype})")
    lines.append(f"  目录: 保留={reserved} 类型={type_name} 项数={count}")
    if reserved != 0:
        problems.append(f"目录保留字段应为 0, 实际 {reserved}")
    if itype not in (1, 2):
        problems.append(f"目录类型字段应为 1(ICO)或 2(CUR), 实际 {itype}")
    dir_end = 6 + 16 * count
    if dir_end > n:
        problems.append(f"目录声明 {count} 项需 {dir_end} 字节, 超过文件大小 {n}")
        count = max(0, (n - 6) // 16)
        dir_end = 6 + 16 * count
    ranges = []
    for i in range(count):
        b = 6 + 16 * i
        w, h, colors, rsv = data[b], data[b + 1], data[b + 2], data[b + 3]
        planes = u16(data, b + 4)
        bpp = u16(data, b + 6)
        size = u32(data, b + 8)
        off = u32(data, b + 12)
        dw = 256 if w == 0 else w
        dh = 256 if h == 0 else h
        lines.append(f"  [{i}] 声明 {dw}x{dh}  位深 {bpp}  颜色数 {colors}  "
                     f"偏移 0x{off:X} ({off})  大小 {size}")
        issues = []
        if rsv != 0:
            issues.append(f"目录项保留字段应为 0, 实际 {rsv}")
        if size == 0:
            issues.append("bytesInRes 为 0, 无图示数据")
        if off < dir_end:
            issues.append(f"数据区起始 0x{off:X} 落在目录区内(目录区到 0x{dir_end:X})")
        if off + size > n:
            issues.append(f"数据区 [0x{off:X}, 0x{off + size:X}) 越界(文件 {n} 字节)")
        ranges.append((off, off + size, i))
        if not issues and size:
            body = data[off:off + size]
            if body[:8] == b"\x89PNG\r\n\x1a\n":
                lines.append("      内嵌: PNG 压缩图示")
                if len(body) >= 24:
                    pw = u32be(body, 16)
                    ph = u32be(body, 20)
                    if (pw, ph) != (dw, dh):
                        issues.append(f"目录声明 {dw}x{dh}, PNG IHDR 实际 {pw}x{ph}")
                    else:
                        lines.append(f"      尺寸: 目录 {dw}x{dh} ↔ "
                                     f"PNG IHDR {pw}x{ph}   [OK]")
            else:
                dib_issues, dib_lines = check_dib(body, dw, dh, bpp, size)
                issues.extend(dib_issues)
                lines.extend(dib_lines)
        for it in issues:
            lines.append(f"      [问题] {it}")
            problems.append(f"第 {i} 项: {it}")
    for a in range(len(ranges)):
        for c in range(a + 1, len(ranges)):
            s1, e1, i1 = ranges[a]
            s2, e2, i2 = ranges[c]
            if s1 < e2 and s2 < e1:
                problems.append(f"第 {i1} 项与第 {i2} 项数据区重叠")
                lines.append(f"  [问题] 第 {i1} 项与第 {i2} 项数据区重叠")
    return problems, lines


def report(path: str, data: bytes) -> bool:
    """打印单个文件报告, 返回是否发现不一致。"""
    problems, lines = scan_ico(data)
    print(f"文件: {path} ({len(data)} 字节)")
    for ln in lines:
        print(ln)
    if problems:
        print(f"结论: 发现 {len(problems)} 处不一致")
        return True
    print("结论: 全部自洽")
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="ico-corrupt-scan.py",
        description="校验 ICO 每个目录项声明的尺寸、位深与内嵌位图数据是否自洽")
    ap.add_argument("files", nargs="*", metavar="ICO文件", help="要扫描的 ICO 文件")
    ap.add_argument("--selftest", action="store_true", help="构造示例文件运行内置自测")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.files:
        ap.print_usage(sys.stderr)
        print("ico-corrupt-scan.py: 错误: 未提供文件, 或使用 --selftest 查看示例",
              file=sys.stderr)
        return 2
    rc = 0
    for path in args.files:
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            print(f"文件: {path}\n  [错误] 无法读取: {e}\n结论: 读取失败")
            rc = 2
            continue
        if report(path, data) and rc == 0:
            rc = 1
    return rc


# ---------------- 内置自测: 临时目录构造示例文件 ----------------

def make_png_bytes() -> bytes:
    def chunk(ctype: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + ctype + payload
                + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"\x00\x10\x20\x30"))
            + chunk(b"IEND", b""))


def make_dib(w, h, bpp) -> bytes:
    """构造合法的 ICO 内嵌 DIB(biHeight = 2*h, 含异或位图与与掩码)。"""
    xor_row = ((w * bpp + 31) // 32) * 4
    and_row = ((w + 31) // 32) * 4
    header = struct.pack("<IiiHHIIiiII", 40, w, 2 * h, 1, bpp, 0,
                         xor_row * h, 0, 0, 0, 0)
    pal_n = 0 if bpp > 8 else 2 ** bpp
    return header + bytes(pal_n * 4) + bytes(xor_row * h) + bytes(and_row * h)


def make_ico(entries) -> bytes:
    """entries: [(w, h, bpp, payload)] → 完整 ICO 字节。"""
    count = len(entries)
    out = [struct.pack("<HHH", 0, 1, count)]
    off = 6 + 16 * count
    dir_entries, blobs = [], []
    for w, h, bpp, payload in entries:
        dir_entries.append(bytes([w, h, 0, 0])
                           + struct.pack("<HHII", 1, bpp, len(payload), off))
        blobs.append(payload)
        off += len(payload)
    return b"".join(out) + b"".join(dir_entries) + b"".join(blobs)


def _write(tmp, name, blob):
    p = os.path.join(tmp, name)
    with open(p, "wb") as f:
        f.write(blob)
    return p


def selftest() -> int:
    tmp = tempfile.mkdtemp(prefix="ico-corrupt-scan-selftest-")
    checks = []
    try:
        png = make_png_bytes()
        dib32 = make_dib(16, 16, 32)
        dib8 = make_dib(8, 8, 8)
        good1 = make_ico([(16, 16, 32, dib32)])
        good2 = make_ico([(8, 8, 8, dib8), (1, 1, 32, png)])
        bad1 = bytearray(make_ico([(16, 16, 32, dib32)]))
        struct.pack_into("<I", bad1, 6 + 8, len(dib32) - 128)   # bytesInRes 少 128
        bad2 = make_ico([(16, 16, 8, dib8)])                    # 声明 16 宽, 实际 8
        bad3 = bytearray(make_ico([(16, 16, 32, dib32)]))
        struct.pack_into("<I", bad3, 6 + 12, len(dib32) + 500)  # imageOffset 越界
        p1 = _write(tmp, "good-dib32.ico", good1)
        p2 = _write(tmp, "good-dib8-plus-png.ico", good2)
        q1 = _write(tmp, "bad-bytesinres.ico", bytes(bad1))
        q2 = _write(tmp, "bad-width.ico", bad2)
        q3 = _write(tmp, "bad-offset.ico", bytes(bad3))

        print("=== 自测 1: 合法 ICO(纯 DIB / DIB+PNG 混合) (期望自洽, 退出码 0) ===")
        checks.append(main([p1, p2]) == 0)
        checks.append(scan_ico(good1)[0] == [])
        checks.append(scan_ico(good2)[0] == [])
        print("=== 自测 2: bytesInRes 不足 (期望报告问题, 退出码 1) ===")
        checks.append(main([q1]) == 1)
        checks.append(any("小于推算值" in s for s in scan_ico(bytes(bad1))[0]))
        print("=== 自测 3: 声明尺寸与 DIB 不符 (期望报告问题, 退出码 1) ===")
        checks.append(main([q2]) == 1)
        checks.append(any("不一致" in s for s in scan_ico(bad2)[0]))
        print("=== 自测 4: 数据区越界 (期望报告问题, 退出码 1) ===")
        checks.append(main([q3]) == 1)
        checks.append(any("越界" in s for s in scan_ico(bytes(bad3))[0]))
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
