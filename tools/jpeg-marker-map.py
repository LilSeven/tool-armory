#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jpeg-marker-map —— 按顺序列出 JPEG 全部标记段的偏移与长度。

用途:
    从 SOI 开始顺序扫描 JPEG 文件的标记段 (marker segment), 逐一输出
    每个标记 (SOI/APPn/COM/DQT/SOFn/DHT/DRI/SOS/EOI/RSTn/TEM) 的
    文件偏移与占用字节数。SOS 段的 size 包含其后的熵编码数据
    (自动跳过 0xFF00 填充与 RSTn 重启标记), 直到下一个真实标记。

用法:
    python -I jpeg-marker-map.py <file.jpg> [--json]

示例:
    python -I jpeg-marker-map.py photo.jpg
    python -I jpeg-marker-map.py photo.jpg --json

退出码: 0=成功; 1=不是 JPEG 或结构损坏/截断; 2=命令行参数错误。
仅使用 Python 标准库。
"""

import argparse
import json
import sys

NAMES = {
    0xC0: "SOF0", 0xC1: "SOF1", 0xC2: "SOF2", 0xC3: "SOF3",
    0xC4: "DHT", 0xC5: "SOF5", 0xC6: "SOF6", 0xC7: "SOF7",
    0xC8: "JPG", 0xC9: "SOF9", 0xCA: "SOF10", 0xCB: "SOF11",
    0xCC: "DAC", 0xCD: "SOF13", 0xCE: "SOF14", 0xCF: "SOF15",
    0xDB: "DQT", 0xDC: "DNL", 0xDD: "DRI", 0xDE: "DHP", 0xDF: "EXP",
    0xFE: "COM",
}


def marker_name(m):
    if m == 0x01:
        return "TEM"
    if 0xD0 <= m <= 0xD7:
        return "RST%d" % (m - 0xD0)
    if 0xE0 <= m <= 0xEF:
        return "APP%d" % (m - 0xE0)
    return NAMES.get(m, "0x%02X" % m)


class JpegError(Exception):
    """JPEG 结构错误。"""


def scan(data):
    """顺序扫描标记段, 返回 (segments, found_eoi)。

    每个 segment 是 dict: marker/code/offset/size/note。
    offset 指向标记码前的 0xFF; size 为该段占用的总字节数
    (标记 2 字节 + 长度字段 + 载荷; SOS 额外包含熵编码数据)。
    """
    n = len(data)
    if n < 2 or data[0] != 0xFF or data[1] != 0xD8:
        raise JpegError("not a JPEG file (missing SOI FF D8)")
    segs = [{"marker": "SOI", "code": 0xD8, "offset": 0, "size": 2,
             "note": "start of image"}]
    pos = 2
    found_eoi = False
    while pos < n:
        start = pos
        while pos < n and data[pos] == 0xFF:      # 跳过填充字节
            pos += 1
        if pos >= n:
            segs.append({"marker": "??", "code": -1, "offset": start,
                         "size": n - start,
                         "note": "trailing fill bytes, truncated (no EOI)"})
            break
        if data[pos] == 0x00:
            raise JpegError("stray 0x00 after fill bytes at offset %d" % start)
        m = data[pos]
        moff = pos - 1                             # 标记码前最近的 0xFF
        if data[moff] != 0xFF:
            raise JpegError("desync: expected 0xFF at offset %d before marker "
                            "0x%02X" % (moff, m))
        pos += 1
        if m == 0xD9:                              # EOI
            segs.append({"marker": "EOI", "code": m, "offset": moff,
                         "size": 2, "note": "end of image"})
            found_eoi = True
            break
        if m == 0x01:                              # TEM, 无长度字段
            segs.append({"marker": "TEM", "code": m, "offset": moff,
                         "size": 2, "note": ""})
            continue
        if 0xD0 <= m <= 0xD7:                      # RSTn, 无长度字段
            segs.append({"marker": "RST%d" % (m - 0xD0), "code": m,
                         "offset": moff, "size": 2, "note": ""})
            continue
        if pos + 2 > n:
            raise JpegError("file truncated before length field of marker "
                            "0x%02X at offset %d" % (m, moff))
        seglen = (data[pos] << 8) | data[pos + 1]
        if seglen < 2:
            raise JpegError("invalid segment length %d for marker 0x%02X at "
                            "offset %d" % (seglen, m, moff))
        total = 2 + seglen                         # 标记 2 字节 + 长度段
        if moff + total > n:
            raise JpegError("segment 0x%02X at offset %d exceeds file size "
                            "(truncated)" % (m, moff))
        if m == 0xDA:                              # SOS: 段头 + 熵编码数据
            p = moff + total
            while p < n:
                if data[p] != 0xFF:
                    p += 1
                    continue
                if p + 1 < n and data[p + 1] == 0x00:   # 0xFF00 填充
                    p += 2
                    continue
                if p + 1 < n and 0xD0 <= data[p + 1] <= 0xD7:  # RSTn
                    p += 2
                    continue
                break
            segs.append({"marker": "SOS", "code": m, "offset": moff,
                         "size": p - moff,
                         "note": "scan header + entropy-coded data (%d bytes)"
                                 % (p - (moff + total))})
            pos = p
        else:
            segs.append({"marker": marker_name(m), "code": m, "offset": moff,
                         "size": total, "note": ""})
            pos = moff + total
    return segs, found_eoi


def human_report(path, size, segs, found_eoi):
    lines = [
        "file: %s" % path,
        "size: %d bytes" % size,
        "markers: %d" % len(segs),
        "",
        "  #  offset         size  marker  note",
    ]
    for i, s in enumerate(segs):
        lines.append("%3d  %-5d (0x%-4X) %5d  %-6s  %s"
                     % (i, s["offset"], s["offset"], s["size"], s["marker"],
                        s["note"]))
    lines.append("")
    eoi_off = None
    if found_eoi:
        eoi_off = segs[-1]["offset"]
        lines.append("EOI found: yes (offset %d)" % eoi_off)
    else:
        lines.append("EOI found: no (file truncated?)")
    if eoi_off is not None and eoi_off + 2 < size:
        lines.append("trailing bytes after EOI: %d" % (size - (eoi_off + 2)))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="jpeg-marker-map",
        description="按顺序列出 JPEG 全部标记段 (SOI/APPn/DQT/SOF/SOS/EOI 等) 的偏移与长度。")
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
        segs, found_eoi = scan(data)
    except JpegError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    if args.json:
        out = {"file": args.file, "size": len(data),
               "eoi_found": found_eoi, "segments": segs}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(human_report(args.file, len(data), segs, found_eoi))
    return 0


if __name__ == "__main__":
    sys.exit(main())
