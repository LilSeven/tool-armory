#!/usr/bin/env python3
"""BMP 行校验 —— 按公式核验 BMP 每行字节数(含 4 字节对齐填充)与图像数据区总长。

核心公式: row_size = ((biWidth * biBitCount + 31) // 32) * 4
          (BMP 规范要求每行按 4 字节对齐, 行尾不足补零)
数据区总长 = row_size * |biHeight|。本工具核验:
  1. 文件实际数据区(文件大小 - bfOffBits)与公式值是否吻合;
  2. bfOffBits 是否与 14 字节文件头 + DIB 头 + 调色板(及掩码)大小相符;
  3. biSizeImage / bfSize 与公式推算值或文件大小是否一致。
仅对未压缩格式(BI_RGB / BI_BITFIELDS)做行公式核验; 压缩格式仅核验文件长度。

示例命令:
  python bmp-row-verify.py pic.bmp
  python bmp-row-verify.py a.bmp b.bmp
  python bmp-row-verify.py --selftest      # 在临时目录构造示例自测

退出码: 0=全部吻合  1=发现不吻合  2=用法或 IO 错误
"""

import argparse
import os
import shutil
import struct
import sys
import tempfile

COMP_NAMES = {0: "BI_RGB", 1: "BI_RLE8", 2: "BI_RLE4",
              3: "BI_BITFIELDS", 4: "BI_JPEG", 5: "BI_PNG",
              6: "BI_ALPHABITFIELDS"}


def parse_bmp(data: bytes):
    """解析 BMP 头, 返回 (dict, "") 或 (None, 原因)。"""
    if len(data) < 14 or data[:2] != b"BM":
        return None, "不是 BMP 文件(缺少 'BM' 文件头)"
    info = {
        "bf_size": struct.unpack_from("<I", data, 2)[0],
        "bf_off": struct.unpack_from("<I", data, 10)[0],
    }
    if len(data) < 18:
        return None, "文件头之后内容不足, DIB 头被截断"
    bi_size = struct.unpack_from("<I", data, 14)[0]
    info["bi_size"] = bi_size
    if bi_size == 12:  # BITMAPCOREHEADER (OS/2 1.x)
        if len(data) < 26:
            return None, "BITMAPCOREHEADER 被截断"
        info.update(w=struct.unpack_from("<H", data, 18)[0],
                    h=struct.unpack_from("<h", data, 20)[0],
                    bpp=struct.unpack_from("<H", data, 24)[0],
                    comp=0, size_image=0, clr_used=0)
    elif bi_size >= 40:
        if len(data) < 54:
            return None, "BITMAPINFOHEADER 被截断"
        info.update(w=struct.unpack_from("<i", data, 18)[0],
                    h=struct.unpack_from("<i", data, 22)[0],
                    bpp=struct.unpack_from("<H", data, 28)[0],
                    comp=struct.unpack_from("<I", data, 30)[0],
                    size_image=struct.unpack_from("<I", data, 34)[0],
                    clr_used=struct.unpack_from("<I", data, 46)[0]
                    if len(data) >= 50 else 0)
    else:
        return None, f"DIB 头大小 {bi_size} 无法识别"
    return info, ""


def verify_bmp(data: bytes):
    """核验 BMP, 返回 (issues, lines)。issues 非空表示不吻合。"""
    info, err = parse_bmp(data)
    if err:
        return [err], None
    issues = []
    lines = []
    comp = info["comp"]
    comp_name = COMP_NAMES.get(comp, f"未知({comp})")
    rows = abs(info["h"])
    order = "自下而上" if info["h"] >= 0 else "自上而下(负高)"
    lines.append(f"  头: bfSize={info['bf_size']}  bfOffBits={info['bf_off']}  "
                 f"DIB头={info['bi_size']}  压缩={comp_name}")
    lines.append(f"  图像: {info['w']}x{info['h']} ({order})  位深 {info['bpp']}")
    if info["w"] <= 0:
        issues.append(f"biWidth={info['w']} 非法(应 > 0)")
    if rows == 0:
        issues.append(f"biHeight={info['h']} 非法(不应为 0)")
    if comp not in (0, 3):
        lines.append(f"  压缩格式 {comp_name}: 行公式不适用, 仅核验文件长度")
        if info["bf_size"] and info["bf_size"] != len(data):
            issues.append(f"bfSize={info['bf_size']} 与文件大小 {len(data)} 不一致")
        if info["bf_off"] > len(data):
            issues.append(f"bfOffBits={info['bf_off']} 超过文件大小 {len(data)}")
        return issues, lines
    row = ((info["w"] * info["bpp"] + 31) // 32) * 4
    raw = info["w"] * info["bpp"] // 8
    pad = row - raw
    expected = row * rows
    lines.append(f"  每行字节数: (({info['w']}*{info['bpp']}+31)//32)*4 = {row} "
                 f"(行数据 {raw} + 对齐填充 {pad})")
    if info["bf_off"] > len(data):
        issues.append(f"bfOffBits={info['bf_off']} 超过文件大小 {len(data)}")
        avail = 0
    else:
        avail = len(data) - info["bf_off"]
    lines.append(f"  数据区: 公式 {row}*{rows} = {expected} 字节 | 文件实际 {avail} 字节")
    if avail != expected:
        issues.append(f"数据区实际 {avail} 字节, 按公式应为 {expected} 字节"
                      f"(相差 {avail - expected:+d})")
    if info["size_image"] == 0:
        lines.append("  biSizeImage=0(合法, 未填写)")
    elif info["size_image"] != expected:
        issues.append(f"biSizeImage={info['size_image']} 与公式值 {expected} 不一致")
    if info["bf_size"] == 0:
        lines.append("  bfSize=0(合法, 未填写)")
    elif info["bf_size"] != len(data):
        issues.append(f"bfSize={info['bf_size']} 与文件大小 {len(data)} 不一致")
    # bfOffBits 与 头+DIB+调色板(+掩码) 的一致性
    pal_n = info["clr_used"] if info["clr_used"] else \
        (0 if info["bpp"] > 8 else 2 ** info["bpp"])
    pal_entry = 3 if info["bi_size"] == 12 else 4  # 核心头调色板每项 3 字节
    masks = 12 if (comp == 3 and info["bi_size"] == 40) else 0
    want_off = 14 + info["bi_size"] + masks + pal_n * pal_entry
    off_desc = (f"头14+DIB{info['bi_size']}"
                f"{'+掩码12' if masks else ''}+调色板{pal_n * pal_entry}")
    if info["bf_off"] != want_off:
        issues.append(f"bfOffBits={info['bf_off']} 与 {off_desc} = {want_off} 不符")
    else:
        lines.append(f"  bfOffBits 与 {off_desc} = {want_off} 相符")
    return issues, lines


def check_file(path: str, data: bytes) -> bool:
    """打印单个文件的核验报告, 返回是否不吻合。"""
    issues, lines = verify_bmp(data)
    print(f"文件: {path} ({len(data)} 字节)")
    if lines:
        for ln in lines:
            print(ln)
    if issues:
        for it in issues:
            print(f"  [不吻合] {it}")
        print("结论: 不吻合")
        return True
    print("结论: 吻合")
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="bmp-row-verify.py",
        description="按公式核验 BMP 每行字节数(含 4 字节对齐)与图像数据区总长")
    ap.add_argument("files", nargs="*", metavar="BMP文件", help="要核验的 BMP 文件")
    ap.add_argument("--selftest", action="store_true", help="构造示例文件运行内置自测")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.files:
        ap.print_usage(sys.stderr)
        print("bmp-row-verify.py: 错误: 未提供文件, 或使用 --selftest 查看示例",
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
        if check_file(path, data) and rc == 0:
            rc = 1
    return rc


# ---------------- 内置自测: 临时目录构造示例文件 ----------------

def make_bmp(w, h_signed, bpp, *, comp=0, clr_used=None,
             off_bits=None, bf_size=None, payload=None) -> bytes:
    """构造 BMP: 默认各字段自洽; 可注入错误参数构造问题样本。"""
    rows = abs(h_signed)
    row = ((w * bpp + 31) // 32) * 4
    data = payload if payload is not None else bytes(row * rows)
    pal_n = clr_used if clr_used is not None else (0 if bpp > 8 else 2 ** bpp)
    masks = 12 if comp == 3 else 0
    dib = struct.pack("<IiiHHIIiiII", 40, w, h_signed, 1, bpp, comp,
                      len(data), 0, 0, clr_used or 0, 0)
    off = 14 + len(dib) + masks + pal_n * 4
    if off_bits is not None:
        off = off_bits
    total = (off + len(data)) if bf_size is None else bf_size
    fhdr = b"BM" + struct.pack("<IHHI", total, 0, 0, off)
    return fhdr + dib + bytes(masks) + bytes(pal_n * 4) + data


def _write(tmp, name, blob):
    p = os.path.join(tmp, name)
    with open(p, "wb") as f:
        f.write(blob)
    return p


def selftest() -> int:
    tmp = tempfile.mkdtemp(prefix="bmp-row-verify-selftest-")
    checks = []
    try:
        good = [
            ("3x2-24bpp.bmp", make_bmp(3, 2, 24)),            # 行 9 字节 → 补 3
            ("5x1-24bpp.bmp", make_bmp(5, 1, 24)),            # 行 15 字节 → 补 1
            ("8x8-1bpp-palette.bmp", make_bmp(8, 8, 1)),      # 调色板 2 项
            ("2x2-16bpp-bitfields.bmp", make_bmp(2, 2, 16, comp=3)),
            ("topdown-4x3-32bpp.bmp", make_bmp(4, -3, 32)),   # 负高, 自上而下
            ("8x2-8bpp-2colors.bmp", make_bmp(8, 2, 8, clr_used=2)),
        ]
        paths = []
        for name, blob in good:
            paths.append(_write(tmp, name, blob))
        print("=== 自测 1: 合法 BMP (期望全部吻合, 退出码 0) ===")
        checks.append(main(paths) == 0)
        for name, blob in good:
            issues, _ = verify_bmp(blob)
            checks.append(issues == [])

        bad1 = make_bmp(3, 2, 24, payload=bytes(20))       # 数据区少 4 字节
        bad2 = make_bmp(8, 8, 1, off_bits=54)              # bfOffBits 漏算调色板
        bad3 = make_bmp(4, 2, 8, clr_used=16, bf_size=999)  # bfSize 乱填
        q1 = _write(tmp, "bad-short-data.bmp", bad1)
        q2 = _write(tmp, "bad-offbits.bmp", bad2)
        q3 = _write(tmp, "bad-bfsize.bmp", bad3)
        print("=== 自测 2: 数据区少 4 字节 (期望报告不吻合, 退出码 1) ===")
        checks.append(main([q1]) == 1)
        i1, _ = verify_bmp(bad1)
        checks.append(any("数据区实际" in s for s in i1))
        print("=== 自测 3: bfOffBits 漏算调色板 (期望报告不吻合, 退出码 1) ===")
        checks.append(main([q2]) == 1)
        i2, _ = verify_bmp(bad2)
        checks.append(any("bfOffBits" in s for s in i2))
        print("=== 自测 4: bfSize 乱填 (期望报告不吻合, 退出码 1) ===")
        checks.append(main([q3]) == 1)
        i3, _ = verify_bmp(bad3)
        checks.append(any("bfSize" in s for s in i3))
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
