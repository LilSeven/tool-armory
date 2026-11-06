#!/usr/bin/env python3
"""魔数与扩展名核对 —— 批量核对图片扩展名与真实魔数, 报告被改名/伪装的文件。

对目录(默认非递归, -r 递归)或显式给出的文件逐个读取文件头, 依据常见图片
魔数(JPEG/PNG/GIF/BMP/ICO/CUR/WEBP/TIFF/HEIF/AVIF/SVG)与扩展名比对;
同时识别 ZIP/EXE/PDF/7Z/RAR/GZIP 等非图片魔数, 报告伪装文件与魔数无法
识别的可疑文件。

示例命令:
  python img-magic-vs-ext.py ./pics
  python img-magic-vs-ext.py -r ./uploads
  python img-magic-vs-ext.py a.png b.jpg suspicious.ico
  python img-magic-vs-ext.py --selftest      # 在临时目录构造示例自测

退出码: 0=全部一致  1=发现不一致/可疑文件  2=用法或 IO 错误
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

IMAGE_EXT = {
    ".jpg": "jpeg", ".jpeg": "jpeg", ".jfif": "jpeg",
    ".png": "png", ".gif": "gif",
    ".bmp": "bmp", ".dib": "bmp",
    ".ico": "ico", ".cur": "cur", ".webp": "webp",
    ".tif": "tiff", ".tiff": "tiff",
    ".heic": "heif", ".heif": "heif", ".avif": "avif",
    ".svg": "svg",
}

FORMAT_LABEL = {
    "jpeg": "JPEG", "png": "PNG", "gif": "GIF", "bmp": "BMP",
    "ico": "ICO", "cur": "CUR", "webp": "WEBP", "tiff": "TIFF",
    "heif": "HEIF", "avif": "AVIF", "svg": "SVG",
    "zip": "ZIP", "exe": "EXE/DLL", "pdf": "PDF", "7z": "7-Zip",
    "rar": "RAR", "gzip": "GZIP",
}

VERDICT_TAG = {"ok": "[一致]", "伪装": "[伪装]", "未知": "[未知]",
               "过小": "[过小]", "错误": "[错误]", "跳过": "[跳过]"}


def detect_magic(data: bytes):
    """按文件头识别真实格式, 返回内部格式名; 无法识别返回 None。"""
    if len(data) < 6:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:2] == b"BM":
        return "bmp"
    if data[:4] == b"\x00\x00\x01\x00":
        return "ico"
    if data[:4] == b"\x00\x00\x02\x00":
        return "cur"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"heim", b"heis",
                     b"hevc", b"hevx", b"mif1", b"msf1"):
            return "heif"
        if brand in (b"avif", b"avis"):
            return "avif"
        return None
    if data[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return "zip"
    if data[:2] == b"MZ":
        return "exe"
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7z"
    if data[:6] == b"Rar!\x1a\x07":
        return "rar"
    if data[:2] == b"\x1f\x8b":
        return "gzip"
    if b"<svg" in data[:1024].lower():
        return "svg"
    return None


def check_file(path: Path):
    """核对单个文件, 返回 (verdict, detail)。

    verdict: ok / 伪装 / 未知 / 过小 / 错误 / 跳过
    """
    ext = path.suffix.lower()
    if ext not in IMAGE_EXT:
        return "跳过", f"非图片扩展名 '{ext or '(无)'}', 不核对"
    try:
        with open(path, "rb") as f:
            data = f.read(4096)
    except OSError as e:
        return "错误", f"无法读取: {e}"
    if len(data) < 6:
        return "过小", f"文件仅 {len(data)} 字节, 无法判断魔数"
    magic = detect_magic(data)
    expect = IMAGE_EXT[ext]
    if magic is None:
        return "未知", f"扩展名 {ext} 但头部魔数无法识别, 开头 {data[:8].hex(' ')}"
    if magic == expect:
        return "ok", f"扩展名 {ext.lstrip('.')} ↔ 魔数 {FORMAT_LABEL[magic]}, 一致"
    return "伪装", (f"扩展名 {ext.lstrip('.')} 但真实格式为 "
                    f"{FORMAT_LABEL[magic]}, 疑被改名/伪装")


def run_scan(targets, recursive: bool) -> int:
    """执行扫描并打印报告, 返回进程退出码。"""
    counts = {"ok": 0, "伪装": 0, "未知": 0, "过小": 0, "错误": 0, "跳过": 0}
    files = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            try:
                it = p.rglob("*") if recursive else p.iterdir()
                files.extend(str(q) for q in it if q.is_file())
            except OSError as e:
                print(f"[错误] 无法枚举目录 {t}: {e}")
                counts["错误"] += 1
        elif p.is_file():
            files.append(str(p))
        else:
            print(f"[错误] 目标不存在: {t}")
            counts["错误"] += 1
    for fp in sorted(files):
        verdict, detail = check_file(Path(fp))
        counts[verdict] += 1
        print(f"{VERDICT_TAG[verdict]} {fp}  {detail}")
    suspicious = counts["伪装"] + counts["未知"] + counts["过小"]
    print(f"合计: 一致 {counts['ok']} / 伪装 {counts['伪装']} / 未知 {counts['未知']} / "
          f"过小 {counts['过小']} / 读取错误 {counts['错误']} / 跳过 {counts['跳过']}")
    if counts["错误"]:
        print("结论: 存在读取错误")
        return 2
    if suspicious:
        print("结论: 发现被改名/伪装/可疑文件")
        return 1
    print("结论: 全部一致")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="img-magic-vs-ext.py",
        description="批量核对图片扩展名与真实魔数, 报告被改名或伪装的文件")
    ap.add_argument("targets", nargs="*", metavar="目录或文件",
                    help="要核对的目录或图片文件")
    ap.add_argument("-r", "--recursive", action="store_true", help="递归扫描子目录")
    ap.add_argument("--selftest", action="store_true", help="构造示例文件运行内置自测")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.targets:
        ap.print_usage(sys.stderr)
        print("img-magic-vs-ext.py: 错误: 未提供目录或文件, 或使用 --selftest 查看示例",
              file=sys.stderr)
        return 2
    return run_scan(args.targets, args.recursive)


# ---------------- 内置自测: 临时目录构造示例文件 ----------------

def make_png_bytes() -> bytes:
    def chunk(ctype: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + ctype + payload
                + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def make_bmp_bytes() -> bytes:
    row = ((3 * 24 + 31) // 32) * 4  # 12 字节, 含对齐填充
    dib = struct.pack("<IiiHHIIiiII", 40, 3, 2, 1, 24, 0, row * 2, 0, 0, 0, 0)
    fhdr = b"BM" + struct.pack("<IHHI", 14 + 40 + row * 2, 0, 0, 54)
    return fhdr + dib + bytes(row * 2)


def selftest() -> int:
    tmp = tempfile.mkdtemp(prefix="img-magic-vs-ext-selftest-")
    checks = []
    try:
        clean = Path(tmp) / "clean"
        dirty = Path(tmp) / "dirty"
        clean.mkdir()
        dirty.mkdir()
        png = make_png_bytes()
        (clean / "real.png").write_bytes(png)
        (clean / "real.bmp").write_bytes(make_bmp_bytes())
        (clean / "real.gif").write_bytes(b"GIF89a" + b"\x00" * 30)
        (clean / "real.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 40 + b"\xff\xd9")
        (clean / "notes.txt").write_bytes(b"just a text file")
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as z:
            z.writestr("evil.txt", "not an image")
        (dirty / "fake.jpg").write_bytes(png)                   # PNG 改名成 .jpg
        (dirty / "evil.png").write_bytes(zip_buf.getvalue())    # ZIP 伪装成 .png
        (dirty / "readme.bmp").write_bytes(b"hello, this is not an image at all")

        print("=== 自测 1: 干净目录 (期望全部一致, 退出码 0) ===")
        checks.append(run_scan([str(clean)], False) == 0)
        print("=== 自测 2: 伪装目录 (期望报告 3 个问题, 退出码 1) ===")
        checks.append(run_scan([str(dirty)], False) == 1)
        v1, _ = check_file(dirty / "fake.jpg")
        v2, _ = check_file(dirty / "evil.png")
        v3, _ = check_file(dirty / "readme.bmp")
        v4, _ = check_file(clean / "real.png")
        checks.append((v1, v2, v3, v4) == ("伪装", "伪装", "未知", "ok"))
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
