#!/usr/bin/env python3
"""字节分布分析 —— 输出文件字节频率直方与高位字节(>127)占比，辅助人工判断未知编码。

对输入文件统计每个字节值 0-255 的出现次数：
  - 打印总字节数、唯一字节值数；
  - 打印高位字节（>127）占比：纯 ASCII 文件为 0%，GB2312/GBK 中文约 30-50%，
    Big5 约 30-40%，UTF-8 中文约 60-90%，可据此初判编码家族；
  - 打印 256 桶直方图（非 0 桶）及 32 字节区间汇总分布；
  - 给出可疑提示：是否含 BOM、\r\n vs \n、高位字节聚集区间。

用法：
  python byte-frequency-report.py FILE
  python byte-frequency-report.py FILE -o report.txt
  python byte-frequency-report.py FILE --top 20
  cat FILE | python byte-frequency-report.py -

示例命令：
  python byte-frequency-report.py unknown-encoding.txt --top 10

选项：
  -o, --output PATH   报告输出文件；缺省写 stdout
  --top N             额外打印出现频率最高的前 N 个字节（默认 10，0=不打印）
  --hist-chars N      直方图条最大字符宽度（默认 60）
"""

import argparse
import sys


def _bar(count: int, max_count: int, width: int) -> str:
    if max_count <= 0:
        return ""
    return "#" * max(1, round(count * width / max_count))


def analyze(data: bytes, top: int = 10, hist_width: int = 60) -> str:
    total = len(data)
    if total == 0:
        return "空文件：无字节可统计。\n"

    freq = [0] * 256
    for b in data:
        freq[b] += 1

    high = sum(freq[128:])
    high_pct = high * 100.0 / total
    lines = []
    lines.append(f"总字节数: {total}")
    lines.append(f"唯一字节值: {sum(1 for c in freq if c)} / 256")
    lines.append(f"高位字节 (>127): {high} ({high_pct:.2f}%)")
    lines.append(f"低位字节 (<=127): {total - high} ({100 - high_pct:.2f}%)")

    # BOM 检测
    if data.startswith(b"\xef\xbb\xbf"):
        lines.append("BOM: 检测到 UTF-8 BOM (EF BB BF)")
    elif data.startswith(b"\xff\xfe\x00\x00"):
        lines.append("BOM: 检测到 UTF-32LE BOM")
    elif data.startswith(b"\x00\x00\xfe\xff"):
        lines.append("BOM: 检测到 UTF-32BE BOM")
    elif data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        lines.append("BOM: 检测到 UTF-16 BOM (FF FE / FE FF)")
    else:
        lines.append("BOM: 未检测到")

    # 换行风格
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    cr = data.count(b"\r") - crlf
    lines.append(f"换行: CRLF={crlf}  LF={lf}  CR={cr}")

    # 编码初判提示（供人工参考，非结论）
    if high == 0:
        hint = "高位字节为 0：文件很可能是纯 ASCII（UTF-8 兼容）。"
    elif 0 < high_pct < 5:
        hint = "高位字节占比很低：可能是偶发非 ASCII 字符的 UTF-8/Latin-1 文本。"
    elif high_pct < 25:
        hint = "低位字节为主：可能是欧洲单字节编码（Latin-1/CP1252）或掺杂少量非 ASCII。"
    elif high_pct <= 55:
        hint = "高低位字节混居、高位占比中等：典型 GBK/GB2312/Big5 双字节中文特征。"
    else:
        hint = ("高位字节占多数：常见于 UTF-8 多字节中日韩文本；"
                "注意短小的 GBK/Big5 中文样本也可能如此，请结合其它特征人工判断。")
    lines.append(f"初判提示: {hint}")

    # 32 字节区间汇总
    lines.append("")
    lines.append("字节区间分布 (每 32 个字节值为一桶):")
    lines.append(f"{'区间':<14}{'数量':>12}{'占比':>9}  直方")
    max_bucket = max(sum(freq[i:i + 32]) for i in range(0, 256, 32))
    for start in range(0, 256, 32):
        c = sum(freq[start:start + 32])
        if c == 0:
            continue
        rng = f"0x{start:02X}-0x{start + 31:02X}"
        lines.append(f"{rng:<14}{c:>12}{c * 100.0 / total:>8.2f}%  "
                     f"{_bar(c, max_bucket, hist_width)}")

    # 逐字节直方（非零桶）
    lines.append("")
    lines.append("字节值直方 (仅列出出现过的字节值):")
    lines.append(f"{'字节':>8}{'次数':>12}{'占比':>9}  字符  直方")
    max_c = max(freq)
    for v in range(256):
        c = freq[v]
        if c == 0:
            continue
        ch = chr(v) if 32 <= v < 127 else "."
        lines.append(f"0x{v:02X} ({v:>3}){c:>10}{c * 100.0 / total:>8.2f}%  "
                     f"{ch:>5}  {_bar(c, max_c, hist_width)}")

    if top > 0:
        top_bytes = sorted(range(256), key=lambda v: (-freq[v], v))[:top]
        top_bytes = [v for v in top_bytes if freq[v] > 0]
        if top_bytes:
            lines.append("")
            lines.append(f"出现频率最高的前 {len(top_bytes)} 个字节:")
            for v in top_bytes:
                ch = chr(v) if 32 <= v < 127 else "."
                lines.append(f"  0x{v:02X} '{ch}'  {freq[v]:>10} 次 "
                             f"({freq[v] * 100.0 / total:.2f}%)")

    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="byte-frequency-report",
        description="统计文件字节频率分布与高位字节占比，辅助判断未知编码")
    p.add_argument("file", help="输入文件路径，'-' 表示读 stdin")
    p.add_argument("-o", "--output", help="报告输出文件，缺省写 stdout")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--hist-chars", type=int, default=60)
    a = p.parse_args(argv)

    if a.file == "-":
        data = sys.stdin.buffer.read()
    else:
        try:
            with open(a.file, "rb") as f:
                data = f.read()
        except OSError as e:
            print(f"error: 无法读取 {a.file}: {e}", file=sys.stderr)
            return 1

    report = analyze(data, top=a.top, hist_width=a.hist_chars)
    if a.output:
        with open(a.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(report)
    else:
        sys.stdout.buffer.write(report.encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
