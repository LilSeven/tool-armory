#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jpeg-app-audit —— 识别 JPEG 各 APPn 段的归属及其占用字节。

用途:
    扫描 JPEG 文件的 APPn 标记段 (0xFFE0-0xFFEF), 按段首签名判定归属:
      APP0  "JFIF\\0"           -> JFIF;   "JFXX\\0" -> JFXX
      APP1  "Exif\\0\\0"          -> EXIF;   "http://ns.adobe.com/xap/1.0/\\0" -> XMP
      APP2  "ICC_PROFILE\\0"     -> ICC
      APP13 "Photoshop 3.0\\0"   -> Photoshop IRB
      APP14 "Adobe"             -> Adobe
      其余 APPn                  -> (unrecognized)
    汇总每个 APPn 段的偏移、大小、归属与签名字节, 并统计 APPn 总字节数
    及其占整个文件的比例。

用法:
    python -I jpeg-app-audit.py <file.jpg> [--json]

示例:
    python -I jpeg-app-audit.py photo.jpg
    python -I jpeg-app-audit.py photo.jpg --json

退出码: 0=成功; 1=不是 JPEG 或结构损坏/截断; 2=命令行参数错误。
仅使用 Python 标准库。
"""

import argparse
import json
import sys


class JpegError(Exception):
    """JPEG 结构错误。"""


def identify(no, payload):
    """按 APPn 序号与段首签名判定归属, 返回 (标签, 匹配的签名字节) 或 (None, None)。"""
    if no == 0:
        if payload.startswith(b"JFIF\x00"):
            return "JFIF", b"JFIF\x00"
        if payload.startswith(b"JFXX\x00"):
            return "JFXX", b"JFXX\x00"
    elif no == 1:
        if payload.startswith(b"Exif\x00\x00"):
            return "EXIF", b"Exif\x00\x00"
        if payload.startswith(b"http://ns.adobe.com/xap/1.0/\x00"):
            return "XMP", b"http://ns.adobe.com/xap/1.0/\x00"
    elif no == 2:
        if payload.startswith(b"ICC_PROFILE\x00"):
            return "ICC", b"ICC_PROFILE\x00"
    elif no == 13:
        if payload.startswith(b"Photoshop 3.0\x00"):
            return "Photoshop IRB", b"Photoshop 3.0\x00"
    elif no == 14:
        if payload.startswith(b"Adobe"):
            return "Adobe", b"Adobe"
    return None, None


def sig_preview(payload, limit=24):
    """取段首前 limit 字节, 可打印 ASCII 原样显示, 其余转义为 \\xNN。"""
    out = []
    for b in payload[:limit]:
        if 32 <= b < 127:
            out.append(chr(b))
        else:
            out.append("\\x%02X" % b)
    if len(payload) > limit:
        out.append("...")
    return "".join(out)


def scan(data):
    """扫描到 SOS/EOI 为止, 返回 (apps, stop_note)。

    app 为 dict: marker/offset/size/label/signature/payload_head。
    """
    n = len(data)
    if n < 2 or data[0] != 0xFF or data[1] != 0xD8:
        raise JpegError("not a JPEG file (missing SOI FF D8)")
    apps = []
    pos = 2
    stop_note = None
    while pos < n:
        start = pos
        while pos < n and data[pos] == 0xFF:      # 跳过填充字节
            pos += 1
        if pos >= n:
            stop_note = "truncated after offset %d (no terminating marker)" % start
            break
        if data[pos] == 0x00:
            raise JpegError("stray 0x00 after fill bytes at offset %d" % start)
        m = data[pos]
        moff = pos - 1                             # 标记码前最近的 0xFF
        if data[moff] != 0xFF:
            raise JpegError("desync: expected 0xFF at offset %d before marker "
                            "0x%02X" % (moff, m))
        pos += 1
        if m == 0xD9:
            stop_note = "EOI at offset %d" % moff
            break
        if m == 0xDA:
            stop_note = "SOS at offset %d (compressed image data starts)" % moff
            break
        if m == 0x01 or 0xD0 <= m <= 0xD7:         # TEM / RSTn
            continue
        if pos + 2 > n:
            raise JpegError("file truncated before length field of marker "
                            "0x%02X at offset %d" % (m, moff))
        seglen = (data[pos] << 8) | data[pos + 1]
        if seglen < 2:
            raise JpegError("invalid segment length %d for marker 0x%02X at "
                            "offset %d" % (seglen, m, moff))
        total = 2 + seglen
        if moff + total > n:
            raise JpegError("segment 0x%02X at offset %d exceeds file size "
                            "(truncated)" % (m, moff))
        if 0xE0 <= m <= 0xEF:                      # APPn
            payload = data[moff + 4:moff + 2 + seglen]
            label, sig = identify(m - 0xE0, payload)
            apps.append({
                "marker": "APP%d" % (m - 0xE0),
                "offset": moff,
                "size": total,
                "label": label,
                "signature": None if sig is None else sig_preview(sig),
                "payload_head": sig_preview(payload),
            })
        pos = moff + total
    return apps, stop_note


def human_report(path, size, apps, stop_note):
    app_total = sum(a["size"] for a in apps)
    pct = (app_total * 100.0 / size) if size else 0.0
    lines = [
        "file: %s" % path,
        "file_size: %d bytes" % size,
        "app_segments: %d (total %d bytes, %.1f%% of file)"
        % (len(apps), app_total, pct),
        "",
        "  #  marker  offset          size  identified-as    signature",
    ]
    for i, a in enumerate(apps):
        lines.append("%3d  %-6s  %-5d (0x%-4X) %5d  %-16s  %s"
                     % (i, a["marker"], a["offset"], a["offset"], a["size"],
                        a["label"] or "(unrecognized)",
                        a["signature"] or a["payload_head"]))
    if stop_note:
        lines.append("")
        lines.append("(scan stopped: %s)" % stop_note)
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="jpeg-app-audit",
        description="识别 JPEG 各 APPn 段的归属 (EXIF/XMP/ICC/Adobe/Photoshop IRB/JFIF) 及占用字节。")
    ap.add_argument("file", help="JPEG 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    try:
        with open(args.file, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print("error: cannot read %s: %s" % (args.file, exc), file=sys.stderr)
        return 1
    try:
        apps, stop_note = scan(data)
    except JpegError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    if args.json:
        app_total = sum(a["size"] for a in apps)
        out = {"file": args.file, "size": len(data),
               "app_total_bytes": app_total,
               "app_total_pct": round(app_total * 100.0 / len(data), 1) if data else 0.0,
               "apps": apps, "stop": stop_note}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(human_report(args.file, len(data), apps, stop_note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
