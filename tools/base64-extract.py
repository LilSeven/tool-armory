#!/usr/bin/env python3
"""base64-extract.py — 从文本/HTML/日志中抽取疑似 Base64 片段并尝试解码保存(单文件, 仅标准库)。

用途:
    按行流式扫描输入(文件或 stdin), 找出所有疑似 Base64 的连续片段
    (默认: 长度 >=16 的 [A-Za-z0-9+/_-] 串, 允许尾部 1-2 个 '='),
    逐一严格解码(validate=True; 先标准字母表, 含 -/_ 时再试 URL-safe,
    允许自动补齐缺失的 padding), 把解码成功的字节保存到 --out-dir,
    并输出带偏移与分类(TEXT/BINARY)的报告。注意: 纯英文长单词或随机串
    也可能碰巧可解码, 属于误报; 可用 --min-len 提高门槛, 用 --text-only
    只保存解码结果为可读文本的片段。

示例:
    python base64-extract.py page.html --out-dir found
    python base64-extract.py server.log --min-len 24 --text-only
    python base64-extract.py capture.txt --list-only          # 只看报告不落盘
    type server.log | python base64-extract.py - --out-dir found
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import os
import re
import sys

TOKEN_CLASS = r"[A-Za-z0-9+/_-]"


def build_pattern(min_len):
    """独立成段的候选串: 左右两侧不再是 base64 字符('=' 除外, 以便命中 query 参数值)。"""
    return re.compile(
        r"(?<!%s)%s{%d,}={0,2}(?!%s)"
        % (TOKEN_CLASS, TOKEN_CLASS, min_len, TOKEN_CLASS))


def try_decode(token):
    """严格尝试解码。成功返回 (kind, data), 失败返回 None。kind 为 std 或 url。"""
    core = token.rstrip("=")
    rem = len(core) % 4
    if rem == 1:          # 长度 mod 4 == 1 的串不可能是合法 base64
        return None
    padded = core + "=" * ((4 - rem) % 4)
    variants = [("std", padded, None)]
    if "-" in core or "_" in core:
        variants.append(("url", padded, b"-_"))
    for kind, text, altchars in variants:
        try:
            if altchars:
                data = base64.b64decode(text, altchars=altchars, validate=True)
            else:
                data = base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError):
            continue
        if data:
            return kind, data
    return None


def classify(data):
    """TEXT: 合法 UTF-8 且 95% 以上字符可打印; 否则 BINARY。"""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return "BINARY"
    if not text:
        return "TEXT"
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\t\r\n")
    return "TEXT" if printable >= 0.95 * len(text) else "BINARY"


def preview(data, limit=48):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data[:12].hex() + ("..." if len(data) > 12 else "")
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def scan_lines(fh, min_len):
    """按行流式扫描二进制行, 产出 (绝对字节偏移, token)。latin-1 视图保证偏移=字节偏移。"""
    pattern = build_pattern(min_len)
    off = 0
    for raw in fh:
        line = raw.decode("latin-1")
        for m in pattern.finditer(line):
            yield off + m.start(), m.group(0)
        off += len(raw)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    parser = argparse.ArgumentParser(
        prog="base64-extract",
        description="扫描文本/HTML/日志中的疑似 Base64 片段, 尝试解码并保存。")
    parser.add_argument("infile", nargs="?", default="-",
                        help="输入文件; '-' 或省略表示 stdin")
    parser.add_argument("--out-dir", default="base64_found",
                        help="解码结果保存目录(默认 ./base64_found)")
    parser.add_argument("--min-len", type=int, default=16,
                        help="片段最小长度(默认 16)")
    parser.add_argument("--text-only", action="store_true",
                        help="只保存解码结果为可读文本(TEXT)的片段")
    parser.add_argument("--list-only", action="store_true",
                        help="只打印报告, 不写任何文件")
    parser.add_argument("--report", default=None,
                        help="把报告同时写入指定文件")
    args = parser.parse_args(argv)

    if args.min_len < 4:
        parser.error("--min-len 至少为 4")

    try:
        if args.infile == "-":
            fh = sys.stdin.buffer
            in_close = False
        else:
            fh = open(args.infile, "rb")
            in_close = True
    except OSError as exc:
        print("base64-extract: cannot open input: %s" % exc, file=sys.stderr)
        return 1

    if not args.list_only:
        try:
            os.makedirs(args.out_dir, exist_ok=True)
        except OSError as exc:
            print("base64-extract: cannot create output dir: %s" % exc, file=sys.stderr)
            return 1

    report_lines = []
    matched = 0
    saved = 0
    stats = {"TEXT": 0, "BINARY": 0}
    seen = {}
    seq = 0
    try:
        for off, token in scan_lines(fh, args.min_len):
            matched += 1
            if token in seen:
                continue
            seen[token] = off
            got = try_decode(token)
            if not got:
                continue
            kind, data = got
            cls = classify(data)
            stats[cls] += 1
            seq += 1
            digest = hashlib.md5(token.encode("ascii")).hexdigest()[:8]
            fname = "frag_%03d_%s.bin" % (seq, digest)
            fpath = ""
            if not args.list_only and (not args.text_only or cls == "TEXT"):
                try:
                    with open(os.path.join(args.out_dir, fname), "wb") as fo:
                        fo.write(data)
                except OSError as exc:
                    print("base64-extract: save failed: %s" % exc, file=sys.stderr)
                    return 1
                saved += 1
                fpath = os.path.join(args.out_dir, fname)
            entry = "[%03d] off=%d len=%d kind=%s cls=%s bytes=%d" % (
                seq, off, len(token), kind, cls, len(data))
            if fpath:
                entry += " file=%s" % fpath
            elif not args.list_only:
                entry += " file=(skipped)"
            entry += " preview=%r" % preview(data)
            report_lines.append(entry)
    finally:
        if in_close:
            fh.close()

    summary = ("summary: %d token(s) matched, %d decoded (%d TEXT / %d BINARY), "
               "%d saved%s" % (matched, seq, stats["TEXT"], stats["BINARY"],
                               0 if args.list_only else saved,
                               "" if not args.list_only else " (--list-only)"))
    report_lines.append(summary)
    if matched and not seq:
        report_lines.append("note: candidates matched but none strictly decoded; "
                            "try adjusting --min-len")
    output = "\n".join(report_lines) + "\n"
    sys.stdout.write(output)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
