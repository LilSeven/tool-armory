#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kinsoku-fix —— 避头尾自动调整：修复折行文本中的禁则问题，输出修订文本。

用途：
    对已按固定宽度折行（或被硬换行切断）的文本自动修复两类禁则：
      * 行首句读（。，、？！…」）等）：
          --mode hang（默认）标点悬挂——上移到上一行行末，上一行可能超出原宽度；
          --mode pull        上拉——把上一行最后一个字拉到本行行首，标点不再顶行；
      * 行尾开括号/开引号（「（“ 等下移）——移到下一行行首。
    修复不跨空行进行（空行是段落边界），无法修复时给出警告并在 stderr 汇总。
    输出统一为 UTF-8 编码、LF 换行；修复结果可用 kinsoku-lint 复查：
        python kinsoku-fix.py wrapped.txt | python kinsoku-lint.py -
    注意：章节标题行请用空行与正文隔开，以免标点被移到标题上。

示例命令：
    python kinsoku-fix.py wrapped.txt                    # 悬挂模式，输出到屏幕
    python kinsoku-fix.py wrapped.txt -o fixed.txt       # 写入文件
    python kinsoku-fix.py wrapped.txt --mode pull        # 上行末字下拉模式
    cat wrapped.txt | python kinsoku-fix.py -            # 从 stdin 读取
"""

import argparse
import sys
import unicodedata

HEAD_FORBIDDEN = set("。，、；：？！…‥⋯·～ー" "」』）】》〉〕｝" "”’" ",.:;!?)]}%")
TAIL_FORBIDDEN = set("“‘「『（【《〈〔｛［" "([{" "￥＄¥$")


def _setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")
        except Exception:
            pass


def _decode_auto(data):
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return data.decode("utf-32")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_text(path, encoding=None):
    if path in ("-", None):
        data = sys.stdin.buffer.read()
    else:
        with open(path, "rb") as fh:
            data = fh.read()
    if encoding:
        return data.decode(encoding, errors="replace")
    return _decode_auto(data)


def write_text(text, out_path):
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def char_label(ch):
    code = "U+%04X" % ord(ch)
    name = unicodedata.name(ch, "")
    if name:
        return '"%s" (%s %s)' % (ch, code, name)
    return '"%s" (%s)' % (ch, code)


def count_problems(text):
    n = 0
    for line in text.splitlines():
        body = line.strip()
        if not body:
            continue
        if body[0] in HEAD_FORBIDDEN:
            n += 1
        if body[-1] in TAIL_FORBIDDEN:
            n += 1
    return n


def fix_lines(lines, mode="hang"):
    """修复禁则。返回 (修订后的行列表, 统计, 警告列表)。"""
    seq = [[i + 1, t] for i, t in enumerate(lines)]
    was_blank = [not t.strip() for _, t in seq]
    warned = set()
    warns = []
    stats = {"hang": 0, "pull": 0, "tail_down": 0}

    guard = 0
    changed = True
    while changed and guard < 10000:
        changed = False
        guard += 1
        for idx in range(len(seq)):
            text = seq[idx][1]
            if not text.strip():
                continue
            # 行尾禁则：开括号/开引号下移到下一行行首
            while text and text[-1] in TAIL_FORBIDDEN:
                nxt = idx + 1
                if nxt < len(seq) and seq[nxt][1].strip():
                    ch = text[-1]
                    text = text[:-1]
                    seq[nxt][1] = ch + seq[nxt][1]
                    stats["tail_down"] += 1
                    changed = True
                else:
                    if idx not in warned:
                        warned.add(idx)
                        warns.append("第 %d 行：行尾禁则字符 %s 无法下移"
                                     "（本行是最后一行，或下一行为空行）"
                                     % (seq[idx][0], char_label(text[-1])))
                    break
            # 行首禁则：句读上移（hang）或把上一行末字下拉（pull）
            while text and text[0] in HEAD_FORBIDDEN:
                prev = idx - 1
                if prev >= 0 and seq[prev][1].strip():
                    if mode == "pull":
                        pulled = seq[prev][1][-1]
                        seq[prev][1] = seq[prev][1][:-1]
                        text = pulled + text
                        stats["pull"] += 1
                    else:
                        seq[prev][1] = seq[prev][1] + text[0]
                        text = text[1:]
                        stats["hang"] += 1
                    changed = True
                else:
                    if idx not in warned:
                        warned.add(idx)
                        warns.append("第 %d 行：行首禁则字符 %s 无法上移"
                                     "（本行是首行，或上一行为空行）"
                                     % (seq[idx][0], char_label(text[0])))
                    break
            seq[idx][1] = text

    result = []
    for i, (_, text) in enumerate(seq):
        if text == "" and not was_blank[i]:
            continue  # 整行上移后变空的行删除，原空行保留
        result.append(text)
    return result, stats, warns


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="kinsoku-fix",
        description="避头尾自动调整：行首句读上移（悬挂/上拉），行尾开括号下移，输出修订文本。",
    )
    parser.add_argument("input", nargs="?", default="-",
                        help="输入文本；缺省或 '-' 表示 stdin")
    parser.add_argument("-o", "--output",
                        help="输出文件（UTF-8/LF）；缺省输出到 stdout")
    parser.add_argument("--mode", choices=("hang", "pull"), default="hang",
                        help="行首句读处理策略：hang=悬挂上移（默认），pull=上一行末字下拉")
    parser.add_argument("--encoding",
                        help="指定输入编码；缺省自动识别 UTF-8/GB18030/Big5")
    args = parser.parse_args(argv)

    try:
        text = read_text(args.input, args.encoding)
    except OSError as exc:
        print("kinsoku-fix: 无法读取输入：%s" % exc, file=sys.stderr)
        return 2

    result, stats, warns = fix_lines(text.splitlines(), mode=args.mode)

    parts = []
    if stats["hang"]:
        parts.append("行首标点上移 %d 处" % stats["hang"])
    if stats["pull"]:
        parts.append("上一行末字下拉 %d 处" % stats["pull"])
    if stats["tail_down"]:
        parts.append("行尾开括号下移 %d 处" % stats["tail_down"])
    print("kinsoku-fix: " + ("；".join(parts) if parts else "无需调整"),
          file=sys.stderr)
    for w in warns:
        print("kinsoku-fix: 警告：" + w, file=sys.stderr)
    remaining = count_problems("\n".join(result))
    if remaining:
        print("kinsoku-fix: 复查：仍有 %d 处禁则未能自动修复（见上方警告）" % remaining,
              file=sys.stderr)
    else:
        print("kinsoku-fix: 复查：输出无禁则问题", file=sys.stderr)

    out_text = "\n".join(result)
    if out_text:
        out_text += "\n"
    try:
        write_text(out_text, args.output)
    except OSError as exc:
        print("kinsoku-fix: 无法写出结果：%s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
