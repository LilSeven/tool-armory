#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PEM 证书指纹提取。

用途:
    从 PEM 文本中提取 CERTIFICATE 块，base64 解码得到 DER 编码，计算
    SHA256 指纹（OpenSSL 风格冒号分隔十六进制），并输出 base64 单行 DER
    形式（等价于 `openssl x509 -outform der | base64 -w0` 的输出）。
    支持一个文件里含多张证书（如证书链），逐张输出。

示例:
    python pem-fingerprint.py cert.pem
    python pem-fingerprint.py chain.pem           # 逐个列出链上每张证书
    python pem-fingerprint.py - < cert.pem        # 从 stdin 读取
    openssl x509 -in cert.pem -noout -fingerprint -sha256   # 结果可对照

退出码: 0 成功；2 未找到证书块或输入非法。
"""

import argparse
import base64
import hashlib
import re
import sys

_PEM_RE = re.compile(
    r"-----BEGIN (?P<label>[A-Z0-9 ]+?)-----(?P<body>.*?)-----END (?P=label)-----",
    re.DOTALL,
)
_B64_RE = re.compile(r"[A-Za-z0-9+/]*={0,2}\Z")


def _utf8_stdio():
    """让中文输出在管道/重定向时保持 UTF-8，避免 Windows 本地编码报错。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def extract_certificate_bodies(text):
    """返回文本中所有 CERTIFICATE 块的 base64 体（已去除空白）。"""
    bodies = []
    for m in _PEM_RE.finditer(text):
        if m.group("label").strip() != "CERTIFICATE":
            continue
        body = "".join(m.group("body").split())
        if body:
            bodies.append(body)
    return bodies


def body_to_der(body):
    if not _B64_RE.match(body):
        raise ValueError("证书体包含非法 base64 字符")
    if len(body) % 4 != 0:
        raise ValueError("证书体 base64 长度不是 4 的倍数")
    try:
        return base64.b64decode(body, validate=True)
    except Exception as e:
        raise ValueError("base64 解码失败: %s" % e)


def fingerprint_hex(der):
    """SHA256 指纹，OpenSSL 风格冒号分隔大写十六进制。"""
    return ":".join("%02X" % b for b in hashlib.sha256(der).digest())


def main(argv=None):
    _utf8_stdio()
    ap = argparse.ArgumentParser(
        description="解码 PEM 证书体并计算 SHA256 指纹与 base64 DER（纯标准库）")
    ap.add_argument("input", nargs="?", default="-", metavar="FILE",
                    help="PEM 文件路径；'-' 或缺省表示 stdin")
    args = ap.parse_args(argv)

    if args.input == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(args.input, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            print("错误: %s" % e, file=sys.stderr)
            return 2

    bodies = extract_certificate_bodies(text)
    if not bodies:
        print("错误: 输入中没有找到 CERTIFICATE 块", file=sys.stderr)
        return 2

    for i, body in enumerate(bodies, 1):
        try:
            der = body_to_der(body)
        except ValueError as e:
            print("错误: 第 %d 个证书块: %s" % (i, e), file=sys.stderr)
            return 2
        print("证书 #%d" % i)
        print("  大小      : %d 字节 (DER)" % len(der))
        print("  SHA256    : %s" % fingerprint_hex(der))
        print("  base64 DER: %s" % base64.b64encode(der).decode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
