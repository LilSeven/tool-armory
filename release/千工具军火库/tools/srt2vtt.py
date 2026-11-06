#!/usr/bin/env python3
"""srt2vtt.py -- 在 SRT 与 WebVTT 字幕格式之间转换，并校正时间戳格式。

SRT:  "1\\n00:00:01,000 --> 00:00:04,000\\n文本\\n"
VTT:  "WEBVTT\\n\\n1\\n00:00:01.000 --> 00:00:04.000\\n文本\\n"

转换规则：
  SRT -> VTT: 加 WEBVTT 头；毫秒分隔逗号换点号；序号保留；兼容 SRT 位移
              坐标（" X1:.. X2:.."）剔除。
  VTT -> SRT: 去 WEBVTT 头、NOTE 块与 STYLE 块；点号换逗号；缺毫秒补 ",000"；
              保留 cue 标签（如 <i>）。

用法:
    python srt2vtt.py sub.srt -o sub.vtt
    python srt2vtt.py sub.vtt -o sub.srt
    python srt2vtt.py sub.srt --check        # 只检查时间戳格式并报告
    cat sub.srt | python srt2vtt.py -

参数:
    INPUT           输入文件（按扩展名 .vtt/.srt 判断方向，也可用 --to 指定）；
                    "-" 读 stdin
    -o, --output    输出文件，缺省 stdout
    --to vtt|srt    强制目标格式，缺省按输入扩展名自动判断
    --check         不转换，只校验时间戳并逐条报告问题
    -e, --encoding  文件编码，默认 utf-8（SRT 常见 gbk 可用 -e gbk）

示例:
    python srt2vtt.py movie.srt -o movie.vtt
    python srt2vtt.py movie.vtt -o movie.srt --check
"""
import argparse
import re
import sys

TS_SRT = re.compile(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
                    r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{1,3})")
TS_VTT = re.compile(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\.(\d{1,3})\s*-->\s*"
                    r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\.(\d{1,3})")


def looks_vtt(text):
    return text.lstrip("﻿ \t\r\n").upper().startswith("WEBVTT")


def fmt_ts(h, m, s, ms, target):
    ms = (int(ms) % 1000) if int(ms) >= 1000 else int(ms)
    if target == "vtt":
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}.{int(ms):03d}"
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(ms):03d}"


def _srt_ms(frac):
    """SRT 毫秒为定宽字段，',5' 表示 005ms。"""
    return int(frac) if int(frac) < 1000 else int(frac) % 1000


def _vtt_ms(frac):
    """VTT 小数秒右补零，'.5' 表示 500ms。"""
    return int((frac + "000")[:3])


def parse_blocks(text):
    """按空行切块。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b for b in re.split(r"\n\s*\n", text) if b.strip()]
    return blocks


def srt_to_vtt(text):
    """SRT -> VTT，按时间线行做两遍扫描，兼容 cue 之间缺空行的文件。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    tl_idx = [i for i, ln in enumerate(lines) if TS_SRT.search(ln)]
    out = ["WEBVTT", ""]
    for k, ti in enumerate(tl_idx):
        m = TS_SRT.search(lines[ti])
        g = m.groups()
        # 文本行：本条时间线之后到下一条时间线之前
        end = tl_idx[k + 1] if k + 1 < len(tl_idx) else len(lines)
        region = [ln.strip() for ln in lines[ti + 1:end] if ln.strip()]
        # 时间线行尾可能挂着文本（缺空行的 SRT）；剔除 X1:/X2: 位移坐标后作为文本
        tail = re.sub(r"\s+X1:\S+.*$", "", lines[ti][m.end():],
                      flags=re.IGNORECASE).strip()
        if tail:
            region.insert(0, tail)
        ident = None
        if region and region[-1].isdigit():
            ident = region.pop()  # 下一条 cue 的序号
        if k == 0 and ti > 0 and lines[ti - 1].strip().isdigit():
            ident = lines[ti - 1].strip()  # 首条 cue 的序号
        if ident:
            out.append(ident)
        out.append(f"{fmt_ts(*g[0:4], 'vtt')} --> {fmt_ts(*g[4:8], 'vtt')}")
        out.extend(region)
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def _to_ms(h, m, s, ms):
    return ((int(h or 0) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def vtt_to_srt(text):
    out = []
    n = 0
    for block in parse_blocks(text):
        lines = [ln for ln in block.split("\n")]
        lines[0] = re.sub(r"^\ufeff", "", lines[0]).strip()
        tl_pos = None
        for i, ln in enumerate(lines):
            if "-->" in ln:
                tl_pos = i
                break
        if tl_pos is None:
            continue  # WEBVTT 头 / NOTE / STYLE 块跳过
        tl = lines[tl_pos]
        m = TS_VTT.search(tl)
        if not m:
            continue
        g = m.groups()
        ts = (f"{fmt_ts(g[0] or 0, g[1], g[2], _vtt_ms(g[3]), 'srt')} --> "
              f"{fmt_ts(g[4] or 0, g[5], g[6], _vtt_ms(g[7]), 'srt')}")
        n += 1
        out.append(str(n))
        out.append(ts)
        out.extend(lines[tl_pos + 1:])
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def check(text):
    problems = 0
    n_cues = 0
    for ln in text.replace("\r\n", "\n").split("\n"):
        if "-->" not in ln:
            continue
        n_cues += 1
        if not (TS_SRT.search(ln) or TS_VTT.search(ln)):
            problems += 1
            print(f"时间戳格式异常: {ln.strip()}", file=sys.stderr)
    print(f"检查完成: {n_cues} 条字幕时间行，{problems} 条异常",
          file=sys.stderr)
    return 0 if problems == 0 else 1


def main():
    ap = argparse.ArgumentParser(
        description="SRT 与 WebVTT 字幕格式互转并校正时间戳")
    ap.add_argument("input", help="输入字幕文件，或 '-' 表示 stdin")
    ap.add_argument("-o", "--output", help="输出文件，缺省 stdout")
    ap.add_argument("--to", choices=("vtt", "srt"),
                    help="目标格式，缺省按输入扩展名判断")
    ap.add_argument("--check", action="store_true",
                    help="只校验时间戳格式，不转换")
    ap.add_argument("-e", "--encoding", default="utf-8")
    args = ap.parse_args()

    if args.input == "-":
        data = sys.stdin.buffer.read()
    else:
        try:
            with open(args.input, "rb") as f:
                data = f.read()
        except OSError as exc:
            raise SystemExit(f"错误: 无法读取 {args.input}: {exc}")
    text = data.decode(args.encoding)

    if args.check:
        sys.exit(check(text))

    target = args.to
    if not target:
        if args.input != "-" and args.input.lower().endswith(".vtt"):
            target = "srt"
        else:
            target = "vtt" if not looks_vtt(text) else "srt"

    if target == "vtt":
        out_text = srt_to_vtt(text)
    else:
        out_text = vtt_to_srt(text)

    if args.output:
        with open(args.output, "w", encoding=args.encoding, newline="") as f:
            f.write(out_text)
        print(f"已写入 {args.output}（目标格式 {target}）", file=sys.stderr)
    else:
        sys.stdout.write(out_text)


if __name__ == "__main__":
    main()
