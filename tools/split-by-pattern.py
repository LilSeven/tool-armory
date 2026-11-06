#!/usr/bin/env python3
"""按标记拆分文本 (split-by-pattern)

按正则或固定标记行（如 ---、===）把长文本切分为多个文件，
用标记行内容（清理后的）命名输出文件。

用法:
  python split-by-pattern.py notes.txt -o outdir                # 默认按 ^---$ 拆分
  python split-by-pattern.py notes.txt -o outdir -p "^===\\s*(.+)$"
  python split-by-pattern.py notes.txt -o outdir --literal "###"  # 固定字符串标记
  python split-by-pattern.py notes.txt -o outdir --pad 3        # 文件名补序号

匹配到标记的整行作为“标记行”：
  - 若标记行包含捕获组，用第一个捕获组作为文件名来源；
  - 否则用整行内容（去除两侧空白与标点）作为文件名来源。
标记行本身默认写入它开启的那个分片（--drop-marker 可丢弃）。

示例命令:
  python split-by-pattern.py chapters.txt -o ./parts -p "^=== (.+)$"
"""

import argparse
import os
import re
import sys


def sanitize_filename(name, maxlen=60):
    name = re.sub(r'\s+', "_", name.strip())
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = name.strip("._-#=")
    return name[:maxlen] or "part"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="按正则或固定标记行把长文本切分为多个文件，用标记内容命名")
    ap.add_argument("input", help="输入文本文件")
    ap.add_argument("-o", "--outdir", default=".",
                    help="输出目录（默认当前目录）")
    ap.add_argument("-p", "--pattern", default=r"^-{3,}\s*$",
                    help="标记行的正则（默认 '^-{3,}\\\\s*$' 即 --- 或 ----）")
    ap.add_argument("--literal", default=None,
                    help="把该固定字符串当作整行匹配的标记（覆盖 -p）")
    ap.add_argument("--pad", type=int, default=0,
                    help="文件名前补序号位数（0=不补）")
    ap.add_argument("--drop-marker", action="store_true",
                    help="输出分片中不包含标记行本身")
    ap.add_argument("--ext", default=".txt", help="输出扩展名（默认 .txt）")
    args = ap.parse_args(argv)

    if args.literal is not None:
        pat = re.compile(
            r"^\s*" + re.escape(args.literal) + r"\s*$")
    else:
        try:
            pat = re.compile(args.pattern)
        except re.error as e:
            print("错误: 正则无效: %s" % e, file=sys.stderr)
            return 2

    if not os.path.isfile(args.input):
        print("错误: 输入文件不存在: %s" % args.input, file=sys.stderr)
        return 2

    with open(args.input, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines(keepends=True)

    os.makedirs(args.outdir, exist_ok=True)

    chunks = []  # (name_source, [lines])
    cur_name, cur_lines = None, []
    for line in lines:
        m = pat.match(line.rstrip("\r\n"))
        if m:
            if cur_name is not None or cur_lines:
                chunks.append((cur_name, cur_lines))
            g = m.group(1) if m.groups() else m.group(0)
            cur_name = g
            cur_lines = [] if args.drop_marker else [line]
        else:
            cur_lines.append(line)
    if cur_name is not None or cur_lines:
        chunks.append((cur_name, cur_lines))

    chunks = [(n, ls) for n, ls in chunks if any(s.strip() for s in ls) or n]
    if not chunks:
        print("未匹配到任何标记行，未产生输出。", file=sys.stderr)
        return 1

    used = set()
    n_written = 0
    for i, (name, ls) in enumerate(chunks, 1):
        base = sanitize_filename(name if name else "part%03d" % i)
        if args.pad:
            base = "%0*d_%s" % (args.pad, i, base)
        else:
            base = "%03d_%s" % (i, base)
        fname = base + args.ext
        k = 2
        while fname in used:
            fname = "%s_%d%s" % (base, k, args.ext)
            k += 1
        used.add(fname)
        with open(os.path.join(args.outdir, fname), "w",
                  encoding="utf-8", newline="") as f:
            f.writelines(ls)
        n_written += 1
        print("%s  <-  %s" % (fname,
                              (name or "(开头)").strip()[:40]))

    print("共输出 %d 个文件到 %s" % (n_written, args.outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
