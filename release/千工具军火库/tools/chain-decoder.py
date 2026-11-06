#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多层编码解链 (chain-decoder)。

自动递归解码嵌套编码，支持 base64 / base64url / base32 / hex / URL 编码任意嵌套；
每层解码结果必须"看起来像文本"才会被采纳，直到解出明文或无可识别的编码层。
仅用 Python 标准库。

用法 (Windows Git Bash):
  python -I chain-decoder.py "V2h5IGRpZCB0aGUgY2hpY2tlbiBjcm9zcyB0aGUgcm9hZD8="
  echo "<编码串>" | python -I chain-decoder.py -      # 从 stdin 读取
  python -I chain-decoder.py --max-depth 10 "..."     # 限制最大解链层数 (默认 20)
  python -I chain-decoder.py --only-result "..."      # 只输出最终明文，便于管道接续

退出码: 0 = 完成 (含"已是明文"); 2 = 未提供输入。
"""

import argparse
import base64
import binascii
import re
import sys
import urllib.parse


def looks_like_text(raw):
    """UTF-8 可解码时看可打印比例；退化到 latin-1 时额外要求 >=90% ASCII，
    防止随机二进制碰巧落在 latin-1 扩展区被误判为文本。"""
    if not raw:
        return False, ""
    try:
        text = raw.decode("utf-8")
        strict_utf8 = True
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
        strict_utf8 = False
    if "\x00" in text:
        return False, ""
    good = sum(1 for ch in text if ch.isprintable() or ch in "\t\n\r")
    if good / len(text) < 0.95:
        return False, ""
    if not strict_utf8:
        ascii_ok = sum(1 for ch in text if 0x20 <= ord(ch) <= 0x7E or ch in "\t\n\r")
        if ascii_ok / len(text) < 0.9:
            return False, ""
    return True, text


def try_base64(s):
    """base64 / base64url -> 文本；解码出二进制垃圾则不采纳。"""
    if len(s) < 4:
        return None
    cands = []
    if re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", s):
        cands.append(("base64", s))
    if re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", s):
        cands.append(("base64url", s.replace("-", "+").replace("_", "/")))
    for name, data in cands:
        rem = len(data) % 4
        if rem == 1:
            continue
        data = data + "=" * ((4 - rem) % 4)
        try:
            raw = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            continue
        ok, text = looks_like_text(raw)
        if ok:
            return name, text
    return None


def try_base32(s):
    if len(s) < 8 or len(s) % 8 != 0 or not re.fullmatch(r"[A-Za-z2-7]+=*", s):
        return None
    try:
        raw = base64.b32decode(s, casefold=True)
    except (binascii.Error, ValueError):
        return None
    ok, text = looks_like_text(raw)
    return ("base32", text) if ok else None


def try_hex(s):
    if len(s) < 2 or len(s) % 2 != 0 or not re.fullmatch(r"[0-9a-fA-F]+", s):
        return None
    raw = bytes.fromhex(s)
    ok, text = looks_like_text(raw)
    return ("hex", text) if ok else None


def try_url(s):
    if "%" not in s:
        return None
    dec = urllib.parse.unquote(s)
    if dec == s:
        return None
    if all(ch.isprintable() or ch in "\t\n\r" for ch in dec):
        return "url", dec
    return None


def decode_step(text):
    """按优先级尝试一种解码，返回 (编码名, 解码文本) 或 None。"""
    for fn in (try_base64, try_base32, try_hex, try_url):
        hit = fn(text)
        if hit:
            return hit
    return None


def preview(text, limit=120):
    text = re.sub(r"\s+", " ", text.strip())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="多层编码解链: 自动递归解码 base64/base32/hex/URL 嵌套编码")
    ap.add_argument("target", nargs="?", help="待解码字符串; '-' 表示从 stdin 读取")
    ap.add_argument("--max-depth", type=int, default=20, help="最大解链层数 (默认 20)")
    ap.add_argument("--only-result", action="store_true", help="只输出最终明文")
    args = ap.parse_args(argv)

    if args.target == "-":
        s = sys.stdin.read()
    elif args.target:
        s = args.target
    else:
        ap.error("请提供待解码字符串，或用 '-' 从 stdin 读取")
    if not s.strip():
        print("输入为空，无事可做。", file=sys.stderr)
        return 2

    current = s.strip()
    layers = []
    for _ in range(max(1, args.max_depth)):
        hit = decode_step(current)
        if not hit:
            break
        layers.append(hit)
        current = hit[1]

    if args.only_result:
        print(current)
        return 0

    print("[输入] %d 字符" % len(s.strip()))
    if layers:
        for i, (name, text) in enumerate(layers, 1):
            print("[层 %d] %-9s -> %s" % (i, name, preview(text)))
        print("[明文] %s (共解码 %d 层)" % (preview(current, 200), len(layers)))
    else:
        print("[明文] 未检测到可解编码层，输入已是明文: %s" % preview(current, 200))
    return 0


if __name__ == "__main__":
    sys.exit(main())
