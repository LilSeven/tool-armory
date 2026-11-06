#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""icc-profile-info —— 解析 ICC 颜色配置文件头

用途:
    读取 ICC/ICM 色彩特性文件的 128 字节文件头, 输出版本、设备类别、色彩空间、
    连接空间(PCS)、设备厂商/型号、目标渲染意图、光源白点、创建时间与 MD5 指纹等。
    输入为 JPEG 时, 自动提取 APP2 段 (ICC_PROFILE) 中内嵌的 ICC 再解析。
    仅依赖 Python 标准库。

示例命令:
    python icc-profile-info.py sRGB.icc
    python icc-profile-info.py photo.jpg

退出码: 0 成功; 1 无法识别或解析失败; 2 命令行参数错误。
"""

import argparse
import struct
import sys
from pathlib import Path

MAGIC = b"acsp"
MIN_LEN = 132                     # 128 字节头 + tag 表项数(4 字节)
APP2_SIG = b"ICC_PROFILE\x00"

DEVICE_CLASS = {
    b"scnr": "input (scanner / camera)",
    b"mntr": "display",
    b"prtr": "output (printer)",
    b"link": "device link",
    b"spac": "color space conversion",
    b"abst": "abstract",
    b"nmcl": "named color",
}
COLOR_SPACE = {
    b"XYZ ": "CIE XYZ", b"Lab ": "CIELAB", b"Luv ": "CIELUV",
    b"YCbr": "YCbCr", b"Yxy ": "CIE Yxy", b"RGB ": "RGB",
    b"GRAY": "gray", b"HSV ": "HSV", b"HLS ": "HLS",
    b"CMYK": "CMYK", b"CMY ": "CMY",
}
PLATFORMS = {
    b"APPL": "Apple Computer, Inc.",
    b"MSFT": "Microsoft Corporation",
    b"SGI ": "Silicon Graphics",
    b"SUNW": "Sun Microsystems",
}
MANUFACTURERS = {
    b"APPL": "Apple Computer, Inc.",
    b"MSFT": "Microsoft Corporation",
    b"ADBE": "Adobe Systems Inc.",
    b"AGFA": "Agfa-Gevaert N.V.",
    b"KODA": "Eastman Kodak Co.",
    b"LINO": "Linotype-Hell AG",
    b"HDM ": "Heidelberger Druckmaschinen AG",
    b"lcms": "LittleCMS",
    b"argl": "Argyll CMS",
}
RENDER_INTENTS = {
    0: "Perceptual",
    1: "Media-relative colorimetric",
    2: "Saturation",
    3: "ICC-absolute colorimetric",
}


class ToolError(Exception):
    """可预期的解析错误: 输出干净信息, 退出码 1。"""


def sig(raw):
    """把 4 字节签名变成可读形式。"""
    if not any(raw):
        return "(none)"
    if all(0x20 <= c <= 0x7E for c in raw):
        return raw.decode("ascii")
    return "0x" + raw.hex()


def sig_with(raw, table):
    base = sig(raw)
    known = table.get(raw)
    return "{} ({})".format(base, known) if known else base


def space_str(raw):
    if raw in COLOR_SPACE:
        return COLOR_SPACE[raw]
    if len(raw) == 4 and raw[1:] == b"CLR":
        return raw[0:1].decode("latin-1") + "-channel"
    return sig(raw)


def icc_from_jpeg(data):
    """在 JPEG 标记流中寻找 APP2 ICC_PROFILE 段并拼合; 找不到返回 None。"""
    n = len(data)
    pos = 2
    chunks = {}
    total = 0
    while pos + 4 <= n:
        if data[pos] != 0xFF:
            break
        while pos < n and data[pos] == 0xFF:
            pos += 1
        if pos >= n:
            break
        marker = data[pos]
        pos += 1
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker in (0xD9, 0xDA):
            break
        if pos + 2 > n:
            break
        seglen = struct.unpack_from(">H", data, pos)[0]
        if seglen < 2:
            break
        payload = data[pos + 2:min(pos + seglen, n)]
        pos += seglen
        if marker == 0xE2 and payload[:12] == APP2_SIG and len(payload) >= 14:
            seq, cnt = payload[12], payload[13]
            if 1 <= seq <= cnt <= 255:
                chunks[seq] = payload[14:]
                total = max(total, cnt)
    if total and all(i in chunks for i in range(1, total + 1)):
        return b"".join(chunks[i] for i in range(1, total + 1))
    return None


def parse_header(buf):
    """解析 128 字节 ICC 头, 返回 (键, 值) 行列表。"""
    if len(buf) < MIN_LEN:
        raise ToolError("data too short to hold an ICC header ({} bytes, need >= {})".format(len(buf), MIN_LEN))
    if buf[36:40] != MAGIC:
        raise ToolError("missing 'acsp' magic at offset 36 (found {!r}); not an ICC profile".format(bytes(buf[36:40])))

    size = struct.unpack_from(">I", buf, 0)[0]
    ver_raw = struct.unpack_from(">I", buf, 8)[0]
    version = "{}.{}.{}".format(buf[8], buf[9] >> 4, buf[9] & 0x0F)
    y, mo, d, h, mi, s = struct.unpack_from(">6H", buf, 24)
    flags = struct.unpack_from(">I", buf, 44)[0]
    attrs = struct.unpack_from(">Q", buf, 56)[0]
    intent = struct.unpack_from(">I", buf, 64)[0]
    ix, iy, iz = (v / 65536.0 for v in struct.unpack_from(">3i", buf, 68))
    pid_raw = struct.unpack_from(">16s", buf, 84)[0]

    flag_bits = [
        "embedded" if flags & 1 else "not embedded",
        "independent use" if not flags & 2 else "restricted use",
    ]
    attr_bits = [
        "transparency" if attrs & 1 else "reflective",
        "matte" if attrs & 2 else "glossy",
        "negative" if attrs & 4 else "positive",
        "b&w" if attrs & 8 else "color",
    ]
    return [
        ("profile size", "header={}, data={} bytes".format(size, len(buf))),
        ("CMM type", sig_with(buf[4:8], MANUFACTURERS)),
        ("version", "{} (0x{:08X})".format(version, ver_raw)),
        ("device class", sig_with(buf[12:16], DEVICE_CLASS)),
        ("color space", space_str(buf[16:20])),
        ("PCS", space_str(buf[20:24])),
        ("created", "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(y, mo, d, h, mi, s)),
        ("platform", sig_with(buf[40:44], PLATFORMS)),
        ("flags", ", ".join(flag_bits)),
        ("manufacturer", sig_with(buf[48:52], MANUFACTURERS)),
        ("model", sig(buf[52:56])),
        ("attributes", ", ".join(attr_bits)),
        ("render intent", "{} ({})".format(intent, RENDER_INTENTS.get(intent, "unknown"))),
        ("illuminant", "X={:.4f}  Y={:.4f}  Z={:.4f}".format(ix, iy, iz)),
        ("creator", sig_with(buf[80:84], MANUFACTURERS)),
        ("profile ID", pid_raw.hex() if any(pid_raw) else "(none)"),
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="icc-profile-info",
        description="Parse the header of an ICC/ICM color profile (also embedded in JPEG APP2).",
    )
    ap.add_argument("file", help="an .icc/.icm profile file, or a JPEG with an embedded ICC profile")
    args = ap.parse_args(argv)

    path = Path(args.file)
    try:
        data = path.read_bytes()
    except OSError as exc:
        print("error: cannot read {}: {}".format(path, exc), file=sys.stderr)
        return 1

    source = "standalone ICC profile"
    buf = data
    if data[:2] == b"\xff\xd8":
        buf = icc_from_jpeg(data)
        if buf is None:
            print("error: no APP2 (ICC_PROFILE) segment found in this JPEG", file=sys.stderr)
            return 1
        source = "embedded in JPEG APP2 (ICC_PROFILE)"

    try:
        rows = parse_header(buf)
    except ToolError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 1

    rows.insert(0, ("source", "{}  ({})".format(source, path)))
    width = max(len(k) for k, _ in rows)
    for key, val in rows:
        print("{:<{w}} : {}".format(key, val, w=width))
    return 0


if __name__ == "__main__":
    sys.exit(main())
