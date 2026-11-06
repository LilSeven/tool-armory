#!/usr/bin/env python3
"""JPEG EOI 检查 —— 验证 JPEG 是否以 EOI 结尾、扫描数据是否连续、其后有无多余字节。

检查内容:
  1. 文件以 SOI(FF D8) 开始, 以 EOI(FF D9) 结束;
  2. 结构化遍历 SOI 与 EOI 之间的标记段链, 验证扫描数据连续:
     每个带长度段的长度合法且不越界、段间无杂散字节、SOS(FF DA) 之后的
     熵编码数据按 FF00 填充与 RSTn 重启标记规则正确推进并终止于真实标记;
  3. 统计 EOI 之后是否有多余字节(常被用来夹带 zip/exe 等数据)并猜测其类型。

示例命令:
  python jpeg-eoi-check.py photo.jpg
  python jpeg-eoi-check.py a.jpg b.jpg
  python jpeg-eoi-check.py --selftest        # 在临时目录构造示例文件自测

退出码: 0=全部通过  1=发现问题(非 JPEG/结构不连续/缺 EOI/尾随数据)  2=用法或 IO 错误
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import zipfile

STANDALONE_MARKERS = {0x01, 0xC8} | set(range(0xD0, 0xD8))  # TEM/JPG/RST0~7 无长度字段


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


def walk_jpeg(data: bytes) -> dict:
    """结构化遍历 JPEG 标记段链, 返回统计结果。

    返回 dict: size / is_jpeg / eoi_offset / trailing / segments / problems
    eoi_offset 为 EOI(FF D9) 起始偏移; trailing 为 EOI 之后的多余字节数。
    """
    res = {"size": len(data), "is_jpeg": False, "eoi_offset": None,
           "trailing": None, "segments": 0, "problems": []}
    n = res["size"]
    problems = res["problems"]
    if n < 4 or data[:2] != b"\xff\xd8":
        problems.append("缺少 SOI(FF D8) 起始标记, 不是 JPEG 数据")
        return res
    res["is_jpeg"] = True
    pos = 2
    while True:
        if pos >= n:
            problems.append("遍历到文件末尾仍未遇到 EOI(FF D9), 扫描数据中断")
            break
        if data[pos] != 0xFF:
            problems.append(
                f"偏移 0x{pos:X}: 标记段之间出现杂散字节 0x{data[pos]:02X}, 段链不连续")
            break
        while pos < n and data[pos] == 0xFF:
            pos += 1
        if pos >= n:
            problems.append("文件在标记填充字节处截断, 未见 EOI")
            break
        marker = data[pos]
        pos += 1
        if marker == 0xD9:  # EOI
            res["eoi_offset"] = pos - 2
            break
        if marker in STANDALONE_MARKERS:
            continue
        if marker == 0xD8:  # 不应重复出现的 SOI
            problems.append(f"偏移 0x{pos - 2:X}: 出现多余的 SOI(FF D8), 段链不连续")
            continue
        if pos + 2 > n:
            problems.append(f"标记 FF {marker:02X} 的段长度字段被截断")
            break
        seglen = (data[pos] << 8) | data[pos + 1]
        if seglen < 2:
            problems.append(f"标记 FF {marker:02X} 段长度 {seglen} 非法(应 >= 2)")
            break
        if pos + seglen > n:
            problems.append(
                f"标记 FF {marker:02X} 声明段长 {seglen} 字节, 超出文件边界(数据被截断)")
            break
        pos += seglen
        res["segments"] += 1
        if marker == 0xDA:  # SOS: 其后为熵编码扫描数据, 自身无长度字段
            while pos < n - 1:
                if data[pos] != 0xFF:
                    pos += 1
                    continue
                nxt = data[pos + 1]
                if nxt == 0x00 or 0xD0 <= nxt <= 0xD7:
                    pos += 2  # FF00 填充 / 重启标记 RSTn, 不结束扫描
                else:
                    break  # 扫描结束, pos 指向下一个真实标记(通常是 EOI)
            if pos == n - 2 and data[pos:pos + 2] == b"\xff\xd9":
                res["eoi_offset"] = pos
                break
            if pos >= n - 1:
                problems.append("熵编码扫描数据直到文件末尾也没有 EOI(FF D9)")
                break
    if res["eoi_offset"] is not None:
        res["trailing"] = n - (res["eoi_offset"] + 2)
    return res


def report(path: str, data: bytes) -> bool:
    """打印单个文件的检查报告, 返回是否存在问题。"""
    r = walk_jpeg(data)
    print(f"文件: {path} ({r['size']} 字节)")
    if not r["is_jpeg"]:
        for p in r["problems"]:
            print(f"  [问题] {p}")
        print("结论: 发现问题")
        return True
    bad = False
    print("  SOI(FF D8): 偏移 0   [OK]")
    if r["problems"]:
        bad = True
        print("  标记段链(SOI→EOI): 不连续   [问题]")
        for p in r["problems"]:
            print(f"    - {p}")
    else:
        print(f"  标记段链(SOI→EOI): 连续, 共解析 {r['segments']} 个带长度的段   [OK]")
    if r["eoi_offset"] is None:
        bad = True
        print("  EOI(FF D9): 未找到   [问题]")
    else:
        tail = r["trailing"] or 0
        if tail == 0:
            print(f"  EOI(FF D9): 偏移 0x{r['eoi_offset']:X}, 恰好在文件末尾   [OK]")
            print("  EOI 后多余字节: 无   [OK]")
        else:
            bad = True
            tail_data = data[r["eoi_offset"] + 2:]
            print(f"  EOI(FF D9): 偏移 0x{r['eoi_offset']:X}, "
                  f"之后还有 {tail} 字节多余数据   [问题]")
            print(f"  多余数据猜测: {guess_tail(tail_data)}   开头: {tail_data[:8].hex(' ')}")
    print(f"结论: {'发现问题' if bad else '通过'}")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="jpeg-eoi-check.py",
        description="验证 JPEG 以 EOI 结尾、扫描数据连续, 并报告 EOI 后多余字节")
    ap.add_argument("files", nargs="*", metavar="JPG文件", help="要检查的 JPEG 文件")
    ap.add_argument("--selftest", action="store_true", help="构造示例文件运行内置自测")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.files:
        ap.print_usage(sys.stderr)
        print("jpeg-eoi-check.py: 错误: 未提供文件, 或使用 --selftest 查看示例",
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

def _seg(marker: int, payload: bytes = b"") -> bytes:
    return bytes([0xFF, marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def make_clean_jpeg() -> bytes:
    scan = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55])  # 假想的熵编码数据
    return (b"\xff\xd8"
            + _seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
            + _seg(0xDB, b"\x00" * 65)
            + _seg(0xC0, b"\x00" * 15)
            + _seg(0xDA, b"\x00\x01\x01\x00\x00\x3F\x00")
            + scan
            + b"\xff\xd9")


def make_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("payload.txt", "appended payload")
    return buf.getvalue()


def make_truncated_jpeg() -> bytes:
    # 段声明长度 67 字节, 实际只保留 40 字节
    return b"\xff\xd8" + _seg(0xDB, b"\x00" * 65)[:40]


def selftest() -> int:
    tmp = tempfile.mkdtemp(prefix="jpeg-eoi-check-selftest-")
    checks = []
    try:
        zip_bytes = make_zip_bytes()
        clean_p = os.path.join(tmp, "clean.jpg")
        dirty_p = os.path.join(tmp, "trailing.jpg")
        cut_p = os.path.join(tmp, "truncated.jpg")
        with open(clean_p, "wb") as f:
            f.write(make_clean_jpeg())
        with open(dirty_p, "wb") as f:
            f.write(make_clean_jpeg() + zip_bytes)
        with open(cut_p, "wb") as f:
            f.write(make_truncated_jpeg())

        print("=== 自测 1: 干净 JPEG (期望通过, 退出码 0) ===")
        checks.append(main([clean_p]) == 0)
        print("=== 自测 2: EOI 后夹带 ZIP (期望发现问题, 退出码 1) ===")
        checks.append(main([dirty_p]) == 1)
        print("=== 自测 3: 段长越界截断 (期望发现问题, 退出码 1) ===")
        checks.append(main([cut_p]) == 1)

        r_clean = walk_jpeg(open(clean_p, "rb").read())
        r_dirty = walk_jpeg(open(dirty_p, "rb").read())
        r_cut = walk_jpeg(open(cut_p, "rb").read())
        checks.append(r_clean["is_jpeg"] and r_clean["eoi_offset"] is not None
                      and r_clean["trailing"] == 0 and not r_clean["problems"])
        checks.append(r_dirty["eoi_offset"] is not None and r_dirty["problems"] == []
                      and r_dirty["trailing"] == len(zip_bytes))
        checks.append(r_cut["eoi_offset"] is None and len(r_cut["problems"]) == 1)
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
