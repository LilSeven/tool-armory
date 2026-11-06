#!/usr/bin/env python3
"""补丁应用器 (diff-patch-apply)

读取 unified diff 补丁文本，按 hunks 应用到目标文件。
支持 --check 干跑校验（不写盘）、--reverse 反向应用（回滚）、stdin 读取补丁。
自动识别目标文件行尾（LF/CRLF）：匹配时忽略行尾 \r 差异，
写回时保持目标文件原有的主导行尾风格（CRLF 文件打完补丁仍是 CRLF）。

用法:
  python diff-patch-apply.py patch.diff                  # 应用补丁（补丁内含文件路径）
  python diff-patch-apply.py patch.diff -o target.txt    # 指定目标文件
  python diff-patch-apply.py patch.diff --check          # 仅校验能否干净应用
  python diff-patch-apply.py patch.diff --reverse        # 反向应用（回滚补丁）
  cat patch.diff | python diff-patch-apply.py - -o f.txt # 从 stdin 读补丁

退出码: 0 成功/校验通过; 1 补丁不匹配或其他错误。
"""

import argparse
import re
import sys

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_unified_diff(text):
    """解析 unified diff 文本，返回 [(old_path, new_path, [hunk, ...]), ...]。

    hunk 为 {'old_start','old_count','new_start','new_count','lines':[(tag,str)],'header':str}
    """
    files = []
    cur_file = None
    cur_hunk = None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            old_path = line[4:].strip()
            new_path = None
            if i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                new_path = lines[i + 1][4:].strip()
                i += 1
            cur_file = {"old": strip_paths(old_path), "new": strip_paths(new_path), "hunks": []}
            files.append(cur_file)
            cur_hunk = None
        elif line.startswith("@@") and cur_file is not None:
            m = HUNK_RE.match(line)
            if not m:
                raise ValueError("无法解析 hunk 头: %r" % line)
            cur_hunk = {
                "old_start": int(m.group(1)),
                "old_count": int(m.group(2)) if m.group(2) is not None else 1,
                "new_start": int(m.group(3)),
                "new_count": int(m.group(4)) if m.group(4) is not None else 1,
                "lines": [],
                "header": line,
            }
            cur_file["hunks"].append(cur_hunk)
        elif cur_hunk is not None:
            if line.startswith("\\"):
                # "\ No newline at end of file" —— 记录但不参与匹配
                cur_hunk["no_eol_newline"] = True
            elif line.startswith("+"):
                cur_hunk["lines"].append(("+", line[1:]))
            elif line.startswith("-"):
                cur_hunk["lines"].append(("-", line[1:]))
            elif line.startswith(" ") or line == "":
                cur_hunk["lines"].append((" ", line[1:] if line else ""))
            else:
                # 无法识别的行，视为上下文容错结束
                pass
        i += 1
    return files


def strip_paths(p):
    if p is None:
        return None
    if p in ("/dev/null",):
        return None
    # 去掉 a/ b/ 前缀和时间戳（tab 分隔）
    p = p.split("\t")[0].strip()
    if p.startswith(("a/", "b/")):
        p = p[2:]
    return p


def apply_hunks(old_lines, hunks, reverse=False, ignore_ws=False):
    """按顺序应用 hunks，返回 (new_lines, applied_info)。上下文不匹配抛 ValueError。"""
    new_lines = []
    pos = 0  # 0-based，已消费的 old_lines 数
    applied = []
    for h in hunks:
        old_start = h["old_start"] - 1 if h["old_start"] > 0 else 0
        if reverse:
            # 反向：+ 行要求匹配删除，- 行作为插入
            target_start = h["new_start"] - 1 if h["new_start"] > 0 else 0
            body = [("+" if t == "-" else "-" if t == "+" else " ", s) for t, s in h["lines"]]
        else:
            target_start = old_start
            body = h["lines"]
        if target_start < pos:
            raise ValueError("hunk 重叠/顺序错误（起始行 %d < 当前行 %d）" % (target_start + 1, pos + 1))
        # 复制 hunk 之前的内容
        new_lines.extend(old_lines[pos:target_start])
        pos = target_start
        consumed = 0
        added = 0
        for tag, s in body:
            if tag == " ":
                if pos + consumed >= len(old_lines) or not line_eq(old_lines[pos + consumed], s, ignore_ws):
                    ctx = old_lines[pos + consumed] if pos + consumed < len(old_lines) else "<EOF>"
                    raise ValueError(
                        "上下文不匹配（第 %d 行）:\n  补丁: |%s|\n  文件: |%s|" % (pos + consumed + 1, s, ctx)
                    )
                new_lines.append(old_lines[pos + consumed])
                consumed += 1
            elif tag == "-":
                if pos + consumed >= len(old_lines) or not line_eq(old_lines[pos + consumed], s, ignore_ws):
                    ctx = old_lines[pos + consumed] if pos + consumed < len(old_lines) else "<EOF>"
                    raise ValueError(
                        "删除行不匹配（第 %d 行）:\n  补丁: |%s|\n  文件: |%s|" % (pos + consumed + 1, s, ctx)
                    )
                consumed += 1
            elif tag == "+":
                new_lines.append(s)
                added += 1
        pos += consumed
        applied.append({"header": h["header"], "deleted": consumed, "added": added})
    new_lines.extend(old_lines[pos:])
    return new_lines, applied


def line_eq(a, b, ignore_ws):
    if ignore_ws:
        def norm(s):
            return s.replace(" ", "").replace("\t", "").replace("\r", "")
        return norm(a) == norm(b)
    return a == b


def detect_eol(text):
    """返回文本的主导行尾：CRLF 行多于孤立的 LF 行时判为 CRLF，否则 LF。"""
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def read_text(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser(description="应用 unified diff 补丁到目标文件")
    ap.add_argument("patch", help="补丁文件路径，'-' 表示 stdin")
    ap.add_argument("-o", "--output", help="目标文件（覆盖补丁内路径；单文件补丁时也可省略）")
    ap.add_argument("--check", action="store_true", help="只校验能否干净应用，不写盘")
    ap.add_argument("--reverse", action="store_true", help="反向应用（回滚）")
    ap.add_argument("--ignore-whitespace", action="store_true", help="匹配时忽略空白差异")
    ap.add_argument("-v", "--verbose", action="store_true", help="输出每个 hunk 的详情")
    args = ap.parse_args()

    try:
        patch_text = read_text(args.patch)
        files = parse_unified_diff(patch_text)
    except Exception as e:
        print("错误: 解析补丁失败: %s" % e, file=sys.stderr)
        return 1
    if not files:
        print("错误: 补丁中没有找到文件头（---/+++）", file=sys.stderr)
        return 1

    rc = 0
    for finfo in files:
        # 目标路径优先级: -o > 补丁 new 路径 > 补丁 old 路径
        target = args.output or finfo["new"] or finfo["old"]
        if not target:
            print("错误: 补丁无目标路径，请用 -o 指定", file=sys.stderr)
            return 1
        # 反向应用时针对的目标文件内容应该是"当前"文件
        try:
            old_text = read_text(target)
        except OSError as e:
            print("错误: 读取目标 %s 失败: %s" % (target, e), file=sys.stderr)
            return 1
        # 目标文件可能是 CRLF 行尾（Windows 常规文本）：split("\n") 会让每行残留 \r，
        # 而补丁侧经 parse_unified_diff 的 splitlines() 已无 \r，逐行比较将永不匹配。
        # 这里统一去掉行尾 \r 再匹配，写盘时按原文件主导行尾（detect_eol）还原。
        old_lines = [ln[:-1] if ln.endswith("\r") else ln for ln in old_text.split("\n")]
        try:
            new_lines, applied = apply_hunks(old_lines, finfo["hunks"], reverse=args.reverse,
                                             ignore_ws=args.ignore_whitespace)
        except ValueError as e:
            print("FAIL %s: %s" % (target, e), file=sys.stderr)
            print("提示: 可先运行 --check 校验；若要撤销已应用的补丁，请使用 --reverse 回滚。",
                  file=sys.stderr)
            rc = 1
            continue
        if args.verbose:
            for a in applied:
                print("  %s  (+%d -%d)" % (a["header"], a["added"], a["deleted"]))
        if args.check:
            print("OK   %s: %d 个 hunk 可干净应用（未写盘）" % (target, len(applied)))
        else:
            write_text(target, detect_eol(old_text).join(new_lines))
            print("APPLIED %s: %d 个 hunk%s" % (target, len(applied), "（反向）" if args.reverse else ""))
    return rc


if __name__ == "__main__":
    sys.exit(main())
