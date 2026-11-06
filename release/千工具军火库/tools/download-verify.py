#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""download-verify.py -- 核验下载文件的实际哈希是否与官方公布的期望值一致。

用途:
    对刚下载的文件计算实际摘要, 与官方发布的期望摘要比对, 打印
    MATCH(一致)或 MISMATCH(不一致 -> 文件损坏或被调包)。期望值
    有三种给法, 三选一:
        --sha256 <hex>           直接给 sha256 期望值;
        --expect <[algo:]hex>    期望值, 算法由 --algo 或 "algo:hex"
                                 前缀/摘要长度推断;
        --from <CHECKSUMS>       从 sha256sum 风格校验文件按文件名
                                 (不含目录)匹配期望值, 兼容
                                 "sha256:hex" 前缀、'*' 二进制标记
                                 与 # / ; 注释行。
    退出码: 0=一致, 1=不一致, 2=用法或读取错误。

用法:
    python -I download-verify.py <文件> --sha256 <期望hex>
    python -I download-verify.py <文件> --expect d41d8cd98f00b204e9800998ecf8427e --algo md5
    python -I download-verify.py <文件> --from SHA256SUMS

示例:
    $ python -I download-verify.py ubuntu-24.04.iso --from SHA256SUMS
    file:      ubuntu-24.04.iso
    size:      6037594112 bytes
    algorithm: sha256
    actual:    a1b2c3d4...
    expected:  a1b2c3d4...
    MATCH: actual digest matches the expected value.
"""

import argparse
import hashlib
import os
import re
import sys

CHUNK = 1 << 20
LENGTH_TO_ALGO = {32: "md5", 40: "sha1", 64: "sha256", 128: "sha512"}
SUPPORTED = ("md5", "sha1", "sha256", "sha512", "blake2b")


class VerifyError(Exception):
    """Raised for user-facing verification setup errors (exit code 2)."""


def hash_file(path, algo):
    """Return (hexdigest, size) of a file, streamed in chunks."""
    h = hashlib.new(algo)
    size = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def normalize_expected(value, algo):
    """Return (algo, lowercase_hex) for a user-supplied expected digest."""
    v = value.strip().lower()
    if ":" in v:
        prefix, rest = v.split(":", 1)
        if prefix in SUPPORTED:
            algo, v = prefix, rest
        else:
            raise VerifyError("unsupported algorithm prefix: %r" % prefix)
    if not re.fullmatch(r"[0-9a-f]+", v):
        raise VerifyError("expected digest is not hexadecimal: %r" % value)
    if algo is None:
        algo = LENGTH_TO_ALGO.get(len(v))
        if algo is None:
            raise VerifyError("cannot infer algorithm from %d hex chars; use --algo" % len(v))
    else:
        if algo not in SUPPORTED:
            raise VerifyError("unsupported algorithm: %s" % algo)
        need = hashlib.new(algo).digest_size * 2
        if len(v) != need:
            raise VerifyError("digest length %d does not fit %s (need %d hex chars)"
                              % (len(v), algo, need))
    return algo, v


def _basename(name):
    return name.replace("\\", "/").split("/")[-1].lower()


def expected_from_checksum_file(cfile, target):
    """Look up (algo, hex) for `target` inside a sha256sum-style file."""
    if not os.path.isfile(cfile):
        raise VerifyError("checksum file not found: %s" % cfile)
    target_name = _basename(target)
    entries = []
    with open(cfile, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            parts = line.split(None, 1)
            token = parts[0].lower()
            algo = None
            if ":" in token:
                prefix, rest = token.split(":", 1)
                if prefix in SUPPORTED:
                    algo, token = prefix, rest
            if not re.fullmatch(r"[0-9a-f]+", token):
                print("WARN: %s line %d: %r is not a hex digest, skipped"
                      % (cfile, lineno, parts[0]), file=sys.stderr)
                continue
            inferred = algo if algo is not None else LENGTH_TO_ALGO.get(len(token))
            if inferred is None:
                print("WARN: %s line %d: cannot infer algorithm from %d hex chars, skipped"
                      % (cfile, lineno, len(token)), file=sys.stderr)
                continue
            if len(token) != hashlib.new(inferred).digest_size * 2:
                print("WARN: %s line %d: digest length does not fit %s, skipped"
                      % (cfile, lineno, inferred), file=sys.stderr)
                continue
            name = _basename(parts[1].strip().lstrip("*")) if len(parts) > 1 else None
            entries.append((inferred, token, name))
    if not entries:
        raise VerifyError("no usable entries in %s" % cfile)
    named = [e for e in entries if e[2] == target_name]
    if len(named) == 1:
        return named[0][0], named[0][1]
    if len(named) > 1:
        raise VerifyError("multiple entries for %r in %s" % (target_name, cfile))
    unnamed = [e for e in entries if e[2] is None]
    if len(unnamed) == 1 and len(entries) == 1:
        return unnamed[0][0], unnamed[0][1]
    raise VerifyError("no entry for %r in %s (%d entries, none matches)"
                      % (target_name, cfile, len(entries)))


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="download-verify.py",
        description="Verify a downloaded file's actual hash against the officially published digest.")
    parser.add_argument("file", help="the downloaded file to verify")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--sha256", metavar="HEX",
                     help="expected sha256 digest (hex)")
    src.add_argument("--expect", metavar="[ALGO:]HEX",
                     help="expected digest; algorithm from --algo, an ALGO: prefix, or the length")
    src.add_argument("--from", dest="from_file", metavar="CHECKSUMS",
                     help="sha256sum-style checksum file to look up the expected digest from")
    parser.add_argument("--algo", default=None,
                        help="hash algorithm for --expect (default: inferred from digest length)")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.file):
        print("ERROR: not a file: %s" % args.file, file=sys.stderr)
        return 2

    try:
        if args.sha256 is not None:
            algo, expected = normalize_expected(args.sha256, "sha256")
        elif args.expect is not None:
            algo, expected = normalize_expected(args.expect, args.algo)
        else:
            algo, expected = expected_from_checksum_file(args.from_file, args.file)
    except VerifyError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    try:
        actual, size = hash_file(args.file, algo)
    except OSError as exc:
        print("ERROR: cannot hash %s: %s" % (args.file, exc), file=sys.stderr)
        return 2

    print("file:      %s" % args.file)
    print("size:      %d bytes" % size)
    print("algorithm: %s" % algo)
    print("actual:    %s" % actual)
    print("expected:  %s" % expected)
    if actual == expected:
        print("MATCH: actual digest matches the expected value.")
        return 0
    print("MISMATCH: actual digest differs from the expected value - "
          "the file may be corrupted or tampered with.")
    return 1


if __name__ == "__main__":
    _utf8_stdio()
    sys.exit(main())
