#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""字幕排版清洗 —— 清洗 SRT 字幕：统一标点、去除 HTML 标签残留、压缩空行，时间轴不变。

处理规则
  1. 去标签：删除 <i>、</b>、<font color="#fff"> 等残留 HTML 标签；
  2. 统一标点：仅对「含汉字」的文本行生效，半角 , ! ? : ; 转全角，句点转「。」；
     保护数字之间的 . , :（如 3.5、1,000、3:2 不受影响）；
     连续两个以上半角句点统一为「……」，连续两个以上连字符统一为「——」；
  3. 压缩空行：行首尾空白去除、连续空格压为一个、汉字之间空格删除，
     字幕块之间多余空行压缩为一个空行；
  4. 清洗后正文为空的块（如只剩 <br/>）整块删除，无时间轴的游离块删除并计数；
  5. 序号与时间轴行（含 "-->"）原样保留，不重排序号、不改动时间。

用法
  python subtitle-clean.py input.srt -o clean.srt     # 清洗后写入文件
  python subtitle-clean.py input.srt --inplace        # 原地覆盖
  python subtitle-clean.py input.srt                  # 输出到标准输出
  python subtitle-clean.py - < input.srt              # 从标准输入读
  python subtitle-clean.py input.srt --encoding gb18030 -o out.srt

示例
  printf '1\n00:00:01,000 --> 00:00:02,000\n<i>你好,世界...</i>\n\n' > t.srt
  python subtitle-clean.py t.srt
  # => 1 / 00:00:01,000 --> 00:00:02,000 / 你好，世界……
统计信息写入标准错误，便于重定向。仅用 Python 标准库。
"""

import argparse
import re
import sys

TAG_RE = re.compile(r"</?[A-Za-z][^<>]*/?>")
CJK_RE = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323AF]")
DOTS_RE = re.compile(r"\.{2,}")
DOT_RE = re.compile(r"(?<!\d)\.(?!\d)")
DASH_RE = re.compile(r"-{2,}")
COMMA_RE = re.compile(r"(?<!\d),(?!\d)")
COLON_RE = re.compile(r"(?<!\d):(?!\d)")
SPACE_RE = re.compile(r"[ \t\u00a0\u3000]+")
CJK_GAP_RE = re.compile(r"(?<=[\u4e00-\u9fff]) (?=[\u4e00-\u9fff])")


def _setup_stdio():
    for s in (sys.stdout, sys.stderr, sys.stdin):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def decode_auto(data, encoding=None):
    if encoding:
        return data.decode(encoding)
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def clean_line(line, stats):
    orig = line
    n_tags = len(TAG_RE.findall(line))
    if n_tags:
        stats["tags"] += n_tags
        line = TAG_RE.sub("", line)
    if CJK_RE.search(line):
        line = DOTS_RE.sub("……", line)
        line = DOT_RE.sub("。", line)
        line = DASH_RE.sub("——", line)
        line = COMMA_RE.sub("，", line)
        line = COLON_RE.sub("：", line)
        line = line.replace("!", "！").replace("?", "？").replace(";", "；")
    line = SPACE_RE.sub(" ", line).strip()
    line = CJK_GAP_RE.sub("", line)
    if line != orig:
        stats["lines_changed"] += 1
    return line


def parse_blocks(text):
    blocks, cur = [], []
    for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if ln.strip():
            cur.append(ln.strip())
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


def clean_srt(text, stats):
    blocks = parse_blocks(text)
    stats["blocks_in"] = len(blocks)
    out_blocks = []
    for block in blocks:
        tc = next((i for i, ln in enumerate(block) if "-->" in ln), None)
        if tc is None:
            stats["orphans"] += 1
            continue
        head, tail, body = block[:tc], block[tc], block[tc + 1:]
        cleaned = []
        for raw in body:
            line = clean_line(raw, stats)
            if line:
                cleaned.append(line)
            else:
                stats["dropped_lines"] += 1
        if not cleaned:
            stats["dropped_blocks"] += 1
            continue
        out_blocks.append("\n".join([*head, tail, *cleaned]))
    stats["blocks_out"] = len(out_blocks)
    if not out_blocks:
        return ""
    return "\n\n".join(out_blocks) + "\n"


def main(argv=None):
    _setup_stdio()
    p = argparse.ArgumentParser(description="SRT 字幕排版清洗（统一标点/去 HTML 标签/压缩空行，时间轴不变）")
    p.add_argument("input", help="输入 .srt 文件路径，- 表示标准输入")
    p.add_argument("-o", "--output", help="输出文件路径（缺省打印到标准输出）")
    p.add_argument("--inplace", action="store_true", help="原地覆盖输入文件")
    p.add_argument("--encoding", help="输入编码（缺省自动探测 utf-8/gb18030）")
    args = p.parse_args(argv)

    try:
        if args.input == "-":
            text = sys.stdin.read()
            in_path = None
        else:
            text = decode_auto(read_bytes(args.input), args.encoding)
            in_path = args.input
    except OSError as e:
        print(f"错误: 无法读取输入: {e}", file=sys.stderr)
        return 1
    except (UnicodeDecodeError, LookupError) as e:
        print(f"错误: 解码失败: {e}", file=sys.stderr)
        return 1

    if args.inplace and in_path is None:
        print("错误: --inplace 需要文件输入，不能用于标准输入", file=sys.stderr)
        return 2

    stats = {"tags": 0, "lines_changed": 0, "orphans": 0,
             "dropped_blocks": 0, "dropped_lines": 0, "blocks_in": 0, "blocks_out": 0}
    result = clean_srt(text, stats)

    out_path = args.input if args.inplace else args.output
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(result)
    else:
        sys.stdout.write(result)

    print(f"[subtitle-clean] 块 {stats['blocks_in']}→{stats['blocks_out']}，"
          f"删空块 {stats['dropped_blocks']}，删游离块 {stats['orphans']}，"
          f"去标签 {stats['tags']} 处，改写行 {stats['lines_changed']}，"
          f"删空行 {stats['dropped_lines']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
