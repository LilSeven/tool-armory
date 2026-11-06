#!/usr/bin/env python3
"""字幕 SRT 与 WebVTT 互转：在 SubRip(.srt) 与 WebVTT(.vtt) 两种字幕格式之间转换。

用法:
    python srt-convert.py input.srt -o output.vtt
    python srt-convert.py input.vtt -o output.srt

说明:
    - 依据输入内容自动判定格式（WEBVTT 头 / 序号行+逗号时间轴），
      也可用 --from srt|vtt 强制指定。
    - SRT->VTT: 加 "WEBVTT" 头，时间轴逗号改为点。
    - VTT->SRT: 去掉 WEBVTT 头，跳过 NOTE/STYLE/REGION 块，
      序号缺失时按顺序重排，时间轴点改为逗号。
    - 时间轴接受 h:mm:ss 与 mm:ss 两种写法，毫秒统一补齐 3 位。

示例:
    python srt-convert.py movie.srt -o movie.vtt
    python srt-convert.py movie.vtt -o movie.srt
"""

import argparse
import re
import sys

TIME_SRT = re.compile(
    r"^\s*(?:(\d+):)?(\d{1,2}):(\d{1,2})[,.](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{1,2})[,.](\d{1,3})\s*$",
    re.M,
)


def _ts(h, m, s, ms):
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def _norm_ms(ms_str):
    return int(ms_str.ljust(3, "0")[:3])


def detect_format(text):
    head = text.lstrip("\ufeff\u200b").lstrip()
    if head.upper().startswith("WEBVTT"):
        return "vtt"
    if TIME_SRT.search(text):
        return "srt"
    return None


def parse_cues(text, is_vtt):
    """通用解析：返回 [[index_or_None, start, end, [lines...]], ...]"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        # VTT 块头：WEBVTT / NOTE / STYLE / REGION 整块跳过
        if is_vtt and re.match(r"^(WEBVTT|NOTE|STYLE|REGION)", line, re.I):
            while i < n and lines[i].strip():
                i += 1
            continue
        idx = None
        if "-->" not in line:
            nxt = lines[i + 1] if i + 1 < n else ""
            if TIME_SRT.match(nxt):
                ident = line.strip()
                if ident.isdigit():
                    idx = int(ident)
                i += 1
                line = lines[i]
            else:
                i += 1
                continue
        m = TIME_SRT.match(line)
        if not m:
            i += 1
            continue
        s1 = _ts(int(m.group(1) or 0), int(m.group(2)), int(m.group(3)), _norm_ms(m.group(4)))
        s2 = _ts(int(m.group(5) or 0), int(m.group(6)), int(m.group(7)), _norm_ms(m.group(8)))
        i += 1
        body = []
        while i < n and lines[i].strip():
            body.append(lines[i])
            i += 1
        cues.append([idx, s1, s2, body])
    return cues


def to_srt(cues):
    out = []
    for num, (_, s1, s2, body) in enumerate(cues, 1):
        out.append(str(num))
        out.append("%s --> %s" % (s1.replace(".", ","), s2.replace(".", ",")))
        out.extend(body)
        out.append("")
    return "\n".join(out) + "\n"


def to_vtt(cues):
    out = ["WEBVTT", ""]
    for _, s1, s2, body in cues:
        out.append("%s --> %s" % (s1.replace(",", "."), s2.replace(",", ".")))
        out.extend(body)
        out.append("")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="SRT 与 WebVTT 字幕互转")
    ap.add_argument("input", help="输入字幕文件 (.srt 或 .vtt)")
    ap.add_argument("-o", "--output", help="输出文件（缺省打印到 stdout）")
    ap.add_argument("--from", dest="fmt", choices=["srt", "vtt"], help="强制指定输入格式")
    args = ap.parse_args(argv)

    with open(args.input, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()

    fmt = args.fmt or detect_format(text)
    if fmt is None:
        print("cannot detect subtitle format; use --from srt|vtt", file=sys.stderr)
        return 1

    cues = parse_cues(text, fmt == "vtt")
    if not cues:
        print("no cues found in input", file=sys.stderr)
        return 1

    result = to_srt(cues) if fmt == "vtt" else to_vtt(cues)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(result)
        print("written: %s (%d cues, %s -> %s)" % (
            args.output, len(cues), fmt, "srt" if fmt == "vtt" else "vtt"))
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
