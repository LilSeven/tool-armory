#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JPEG SOF 扫描 —— 遍历 JPEG 段(segment), 定位 SOF0–SOF15 帧头标记。

从 SOI(0xFFD8) 开始逐段遍历: 跳过 SOS 之后的熵编码数据, 正确处理
FF00 字节填充与 RSTn 重启标记, 找到文件中所有 SOF 帧头(注意 DHT=0xC4、
JPG=0xC8、DAC=0xCC 不属于 SOF)。对每个 SOF 输出: 精度、宽、高、分量数,
以及每个分量的编号、水平/垂直采样因子和量化表选择器。

用法:
    python jpeg-sof-scan.py <文件.jpg> [--json]

示例:
    python jpeg-sof-scan.py sample.jpg
    python jpeg-sof-scan.py sample.jpg --json

退出码: 0 = 完成遍历(未找到 SOF 时给出警告); 1 = 不是 JPEG 或结构损坏。
仅使用 Python 标准库, 需 Python 3.7+。
"""

import argparse
import json
import struct
import sys

SOI = b"\xFF\xD8"


class JpegError(Exception):
    pass


SOF_NAMES = {
    0xC0: ("SOF0", "基线 DCT, Huffman 编码"),
    0xC1: ("SOF1", "扩展顺序 DCT, Huffman 编码"),
    0xC2: ("SOF2", "累进 DCT, Huffman 编码"),
    0xC3: ("SOF3", "无损, Huffman 编码"),
    0xC5: ("SOF5", "差分顺序 DCT, Huffman 编码"),
    0xC6: ("SOF6", "差分累进 DCT, Huffman 编码"),
    0xC7: ("SOF7", "差分无损, Huffman 编码"),
    0xC9: ("SOF9", "顺序 DCT, 算术编码"),
    0xCA: ("SOF10", "累进 DCT, 算术编码"),
    0xCB: ("SOF11", "无损, 算术编码"),
    0xCD: ("SOF13", "差分顺序 DCT, 算术编码"),
    0xCE: ("SOF14", "差分累进 DCT, 算术编码"),
    0xCF: ("SOF15", "差分无损, 算术编码"),
}
SOF_MARKERS = set(SOF_NAMES)

MARKER_NAMES = {
    0x01: "TEM", 0xC4: "DHT", 0xC8: "JPG", 0xCC: "DAC",
    0xD8: "SOI", 0xD9: "EOI", 0xDA: "SOS", 0xDB: "DQT", 0xDC: "DNL",
    0xDD: "DRI", 0xDE: "DHP", 0xDF: "EXP", 0xFE: "COM",
}
for _i in range(8):
    MARKER_NAMES[0xD0 + _i] = "RST%d" % _i
for _i in range(16):
    MARKER_NAMES[0xE0 + _i] = "APP%d" % _i
for _i in range(14):
    MARKER_NAMES[0xF0 + _i] = "JPG%d" % _i

MARKER_NOTES = {
    0xC4: "Huffman 表", 0xCC: "算术条件表", 0xDB: "量化表",
    0xDD: "重启间隔定义", 0xDA: "扫描头, 之后是熵编码数据",
    0xE0: "通常为 JFIF", 0xE1: "通常为 EXIF/XMP", 0xFE: "注释",
}


def setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def die(msg):
    sys.stderr.write("jpeg-sof-scan: 错误: %s\n" % msg)
    raise SystemExit(1)


def skip_entropy(data, i):
    """从 SOS 头结束处跳过熵编码数据, 返回下一个真实标记(0xFF 前缀)的位置。

    熵编码数据中的 0xFF 必定后随 0x00(字节填充)或 RSTn(重启标记),
    其他 0xFF xx 组合即为下一段的标记。
    """
    n = len(data)
    while i < n - 1:
        if data[i] == 0xFF:
            nxt = data[i + 1]
            if nxt == 0x00 or 0xD0 <= nxt <= 0xD7:
                i += 2
            elif nxt == 0xFF:
                i += 1
            else:
                return i
        else:
            i += 1
    return n


def parse_sof(marker, payload, off):
    short, desc = SOF_NAMES[marker]
    if len(payload) < 6:
        raise JpegError("偏移 0x%X: %s 载荷仅 %d 字节, 至少需要 6 字节"
                        % (off, short, len(payload)))
    precision = payload[0]
    height, width = struct.unpack(">HH", payload[1:5])  # Y 在前, X 在后
    ncomp = payload[5]
    expect = 6 + 3 * ncomp
    if len(payload) != expect:
        raise JpegError("偏移 0x%X: %s 载荷 %d 字节与分量数 %d 不符(应为 %d 字节)"
                        % (off, short, len(payload), ncomp, expect))
    comps = []
    for k in range(ncomp):
        cid = payload[6 + 3 * k]
        hv = payload[7 + 3 * k]
        tq = payload[8 + 3 * k]
        comps.append({"id": cid, "h_sampling": hv >> 4, "v_sampling": hv & 0x0F,
                      "quant_table": tq})
    return {"marker": marker, "name": short, "desc": desc, "offset": off,
            "precision": precision, "width": width, "height": height,
            "components": comps}


def walk(data):
    segs, sofs, warnings = [], [], []
    n = len(data)
    pos = 2
    saw_eoi = False
    while pos < n:
        start = pos
        if data[pos] != 0xFF:
            raise JpegError("偏移 0x%X: 此处应为标记前缀 0xFF, 实际为 0x%02X"
                            % (pos, data[pos]))
        while pos < n and data[pos] == 0xFF:  # 允许连续 0xFF 填充字节
            pos += 1
        if pos >= n:
            raise JpegError("文件在标记前缀 0xFF 之后截断")
        marker = data[pos]
        pos += 1
        if marker in (0x00, 0xFF):
            raise JpegError("偏移 0x%X: 非法标记 0xFF 0x%02X(熵编码数据疑似混入段区)"
                            % (start, marker))
        if marker in SOF_MARKERS:
            name = SOF_NAMES[marker][0]
        else:
            name = MARKER_NAMES.get(marker, "0x%02X" % marker)
        if marker == 0xD9:  # EOI: 无长度, 文件结束
            segs.append({"offset": start, "marker": marker, "name": name,
                         "length": None, "note": "图像结束"})
            saw_eoi = True
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:  # TEM/RSTn: 无长度
            segs.append({"offset": start, "marker": marker, "name": name,
                         "length": None, "note": "无长度独立标记"})
            continue
        if pos + 2 > n:
            raise JpegError("偏移 0x%X: %s 的段长度字段被截断" % (start, name))
        (seglen,) = struct.unpack(">H", data[pos:pos + 2])
        if seglen < 2:
            raise JpegError("偏移 0x%X: %s 段长度为 %d, 非法(必须 >= 2)"
                            % (start, name, seglen))
        end = pos + seglen
        if end > n:
            raise JpegError("偏移 0x%X: %s 段长度 %d 超出文件大小" % (start, name, seglen))
        payload = data[pos + 2:end]
        segs.append({"offset": start, "marker": marker, "name": name,
                     "length": seglen, "note": MARKER_NOTES.get(marker, "")})
        if marker in SOF_MARKERS:
            sofs.append(parse_sof(marker, payload, start))
        pos = end
        if marker == 0xDA:  # SOS: 跳过熵编码数据再继续找标记
            nxt = skip_entropy(data, end)
            segs[-1]["note"] += "; 熵编码数据 0x%X-0x%X 已跳过" % (end, max(end, nxt - 1))
            pos = nxt
    if not saw_eoi:
        warnings.append("遍历到文件末尾也没有遇到 EOI(0xFFD9) — 文件可能被截断")
    if not sofs:
        warnings.append("未找到任何 SOF 帧头标记 — 文件可能不是完整的 JPEG")
    return segs, sofs, warnings


def render_text(path, size, segs, sofs, warnings):
    lines = []
    lines.append("文件: %s (%d 字节) — SOI(0xFFD8) 校验 OK" % (path, size))
    lines.append("")
    lines.append("段遍历 (偏移为标记 0xFF 前缀所在位置):")
    lines.append("  偏移    标记   段长   说明")
    for s in segs:
        ln = "-" if s["length"] is None else str(s["length"])
        lines.append("  0x%04X  %-6s %-5s %s" % (s["offset"], s["name"], ln, s["note"]))
    lines.append("")
    if sofs:
        lines.append("找到 %d 个 SOF 帧头:" % len(sofs))
        for f in sofs:
            lines.append("")
            lines.append("[%s] %s  @0x%04X" % (f["name"], f["desc"], f["offset"]))
            lines.append("  精度 precision    : %d 位/样本" % f["precision"])
            lines.append("  高度 height       : %d 像素" % f["height"])
            lines.append("  宽度 width        : %d 像素" % f["width"])
            lines.append("  分量数 components : %d" % len(f["components"]))
            lines.append("  分量   采样(H×V)  量化表")
            for c in f["components"]:
                lines.append("   %3d     %d×%d       %d"
                             % (c["id"], c["h_sampling"], c["v_sampling"], c["quant_table"]))
    else:
        lines.append("未找到 SOF 帧头。")
    lines.append("")
    if warnings:
        lines.append("警告 (%d 条):" % len(warnings))
        for w in warnings:
            lines.append("  - " + w)
    else:
        lines.append("警告: 无")
    return "\n".join(lines) + "\n"


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="遍历 JPEG 段定位 SOF0–SOF15, 输出宽高、精度、分量数与采样因子")
    ap.add_argument("file", help="JPEG 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = ap.parse_args(argv)
    try:
        with open(args.file, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        die("无法读取文件: %s" % exc)
    if data[:2] != SOI:
        die("缺少 SOI 标记(前 2 字节为 %s), 不是 JPEG 文件" % data[:2].hex(" "))
    try:
        segs, sofs, warnings = walk(data)
    except JpegError as exc:
        die(str(exc))
    if args.json:
        out = {"file": args.file, "file_size": len(data),
               "segments": segs, "sofs": sofs, "warnings": warnings}
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(render_text(args.file, len(data), segs, sofs, warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
