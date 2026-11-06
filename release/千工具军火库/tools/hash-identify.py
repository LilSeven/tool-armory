#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hash-identify.py —— 未知哈希算法类型识别（启发式，仅 Python 标准库）。

用途:
    依据哈希串的 $ 前缀格式（如 $1$/$2b$/$5$/$6$/$argon2id$/phpass 等）、
    长度与字符集（十六进制/Base64/纯数字），给出可能算法的候选列表，
    例如 32 位十六进制 → MD5/NTLM/MD4，$6$ → SHA-512 crypt。
    $ 前缀格式可确定算法；仅凭长度只能给候选，属启发式判断。

示例命令:
    python hash-identify.py 5f4dcc3b5aa765d61d8327deb882cf99     # 32 hex -> MD5 等
    python hash-identify.py '$2b$12$ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0'
    python hash-identify.py "..." --json                         # JSON 输出
    echo 'HASH串' | python hash-identify.py                      # stdin，可多行批量
    python hash-identify.py --selftest                           # 运行内置自测
"""

import argparse
import base64
import json
import re
import sys

# ($ 前缀正则, 算法名) —— 命中即基本确定算法
CRYPT_PREFIXES = [
    (r"^\$apr1\$", "Apache $apr1$（MD5 crypt 变体）"),
    (r"^\$1\$", "MD5 crypt（Unix $1$）"),
    (r"^\$2[abxy]\$", "bcrypt"),
    (r"^\$5\$", "SHA-256 crypt（Unix $5$）"),
    (r"^\$6\$", "SHA-512 crypt（Unix $6$）"),
    (r"^\$7\$", "scrypt crypt（Debian $7$）"),
    (r"^\$argon2id\$", "Argon2id"),
    (r"^\$argon2i\$", "Argon2i"),
    (r"^\$argon2d\$", "Argon2d"),
    (r"^\$pbkdf2(?:-sha256|-sha512|-sha1|-md5)?\$", "PBKDF2 crypt"),
    (r"^\$S\$", "Drupal 7+（SHA-512 phpass）"),
    (r"^\$P\$", "phpass portable（WordPress，MD5）"),
    (r"^\$H\$", "phpass portable（phpBB，MD5）"),
]

# 不带 $ 的命名前缀（如 Django）
NAMED_PREFIXES = [
    (r"^pbkdf2_sha256\$", "Django PBKDF2-SHA256"),
    (r"^pbkdf2_sha1\$", "Django PBKDF2-SHA1"),
    (r"^bcrypt_sha256\$", "Django bcrypt_sha256"),
    (r"^md5\$", "Django unsalted MD5"),
    (r"^sha1\$", "Django unsalted SHA-1"),
    (r"^sha256\$", "Django/generic salted SHA-256"),
]

# 十六进制长度 -> 候选算法
HEX_LENGTHS = {
    4: ["CRC-16（16 位校验和）"],
    8: ["CRC-32", "Adler-32"],
    32: ["MD5", "NTLM", "MD4", "RIPEMD-128", "MD2"],
    40: ["SHA-1", "RIPEMD-160", "MySQL5（双 SHA-1）"],
    48: ["Tiger/192", "HAVAL-192"],
    56: ["SHA-224", "SHA-512/224"],
    64: ["SHA-256", "SHA3-256", "Keccak-256（以太坊）", "BLAKE2s-256", "SM3"],
    80: ["RIPEMD-320", "BLAKE2b-320"],
    96: ["SHA-384", "SHA3-384", "BLAKE2b-384"],
    128: ["SHA-512", "SHA3-512", "Whirlpool", "BLAKE2b-512"],
}

# Base64 解码后字节长度 -> 候选算法
B64_BYTE_LENGTHS = {
    16: ["MD5", "NTLM", "MD4", "RIPEMD-128"],
    20: ["SHA-1", "RIPEMD-160"],
    28: ["SHA-224", "SHA-512/224"],
    32: ["SHA-256", "SHA3-256", "BLAKE2s-256"],
    48: ["SHA-384", "SHA3-384"],
    64: ["SHA-512", "SHA3-512", "Whirlpool", "BLAKE2b-512"],
}

MATCH_KINDS = {
    "crypt-prefix": "$ 前缀格式（确定性高）",
    "named-prefix": "命名前缀格式（确定性高）",
    "charset-decimal": "纯数字字符集（候选）",
    "hex-length": "长度 + 十六进制字符集（候选）",
    "base64-length": "Base64 解码后字节长度（候选）",
    "other": "未能识别",
}


def _force_utf8_stdio():
    """让输出在非 UTF-8 控制台上也不因中文而报编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _is_hex(s):
    return re.fullmatch(r"[0-9a-fA-F]+", s) is not None


def _is_dec(s):
    return re.fullmatch(r"[0-9]+", s) is not None


def _is_b64(s):
    return re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", s) is not None


def identify(text):
    """返回 {"input", "length", "charset", "match", "candidates": [{"name","why"}]}。"""
    s = text.strip()
    info = {"input": s, "length": len(s)}

    for pattern, name in CRYPT_PREFIXES:
        if re.match(pattern, s):
            info["match"] = "crypt-prefix"
            info["charset"] = "crypt 格式串"
            info["candidates"] = [{"name": name, "why": "以该算法标准的 $ 前缀开头"}]
            return info

    for pattern, name in NAMED_PREFIXES:
        if re.match(pattern, s):
            info["match"] = "named-prefix"
            info["charset"] = "命名前缀格式串"
            info["candidates"] = [{"name": name, "why": "以该框架的标准前缀开头"}]
            return info

    if s and _is_dec(s):
        cands = []
        if len(s) <= 10:
            cands.append({"name": "CRC-32 / Adler-32",
                          "why": "纯数字且 ≤10 位，常见于校验和的十进制表示"})
        cands.append({"name": "自定义数值哈希/序号", "why": "纯数字串，无标准算法特征"})
        info["match"] = "charset-decimal"
        info["charset"] = "纯数字"
        info["candidates"] = cands
        return info

    if s and _is_hex(s):
        n = len(s)
        size_note = "{} 字节".format(n // 2) if n % 2 == 0 else "奇数长度（异常）"
        names = list(HEX_LENGTHS.get(n, []))
        if n == 32 and s == s.upper():
            names.insert(1, "LM（全大写）")
        info["match"] = "hex-length"
        info["charset"] = "十六进制-" + ("全大写" if s == s.upper() else "小写/混合")
        info["candidates"] = ([{"name": nm, "why": size_note} for nm in names] or
                              [{"name": "（无常见对应）",
                                "why": "{} 个十六进制字符不匹配常见摘要长度".format(n)}])
        return info

    if s and len(s) % 4 == 0 and len(s) >= 4 and _is_b64(s):
        raw = None
        try:
            raw = base64.b64decode(s, validate=True)
        except Exception:
            raw = None
        if raw is not None:
            nb = len(raw)
            names = B64_BYTE_LENGTHS.get(nb)
            info["match"] = "base64-length"
            info["charset"] = "Base64"
            info["candidates"] = ([{"name": nm, "why": "Base64 解码后 {} 字节".format(nb)}
                                   for nm in names] or
                                  [{"name": "（无常见对应）",
                                    "why": "Base64 解码后 {} 字节，非常见摘要长度".format(nb)}])
            return info

    info["match"] = "other"
    info["charset"] = "混合/其他字符集"
    info["candidates"] = [{"name": "（无候选）",
                           "why": "不含 $ 前缀，长度与字符集均无标准特征"}]
    return info


def render(info):
    shown = info["input"]
    if len(shown) > 64:
        shown = shown[:61] + "..."
    lines = [
        "输入: {} ({} 字符, 字符集: {})".format(shown, info["length"], info["charset"]),
        "判定方式: " + MATCH_KINDS[info["match"]],
        "候选算法:",
    ]
    for i, cand in enumerate(info["candidates"], 1):
        lines.append("  {}. {}  [{}]".format(i, cand["name"], cand["why"]))
    if info["match"] in ("hex-length", "base64-length", "charset-decimal"):
        lines.append("提示: 候选按长度/字符集推断，非确定结论；请结合来源系统与大小写进一步排除。")
    return "\n".join(lines)


def selftest():
    ok = True

    def check(cond, label):
        nonlocal ok
        ok = ok and bool(cond)
        print("[{}] {}".format("PASS" if cond else "FAIL", label))

    def names(result):
        return [c["name"] for c in result["candidates"]]

    r = identify("5f4dcc3b5aa765d61d8327deb882cf99")
    check(r["match"] == "hex-length" and "MD5" in names(r) and "SHA-256" not in names(r),
          "32 位十六进制 -> MD5 候选，且不含 SHA-256")

    r = identify("A9993E364706816ABA3E25717850C26C9CD0D89D")
    check("SHA-1" in names(r), "40 位十六进制（大写）-> SHA-1 候选")

    r = identify("$6$saltstring$"
                 "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/+"
                 "0123456789012345678901")
    check(r["match"] == "crypt-prefix" and names(r)[0].startswith("SHA-512 crypt"),
          "$6$ 前缀 -> SHA-512 crypt")

    r = identify("$2b$12$" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz" + "0")
    check(names(r)[0] == "bcrypt", "$2b$ 前缀 -> bcrypt")

    r = identify("$P$8ZtYc6VWbWtP0Q5jJ0m3u6Xv1S9o7O0")
    check("phpass" in names(r)[0], "$P$ 前缀 -> phpass/WordPress")

    r = identify("pbkdf2_sha256$260000$c2FsdA$aGFzaA")
    check("Django PBKDF2-SHA256" in names(r), "pbkdf2_sha256$ 前缀 -> Django PBKDF2-SHA256")

    r = identify("AAAAAAAAAAAAAAAAAAAAAA==")
    check(r["match"] == "base64-length" and "MD5" in names(r),
          "Base64 解码 16 字节 -> MD5 候选")

    r = identify("1234567890")
    check(any("CRC-32" in n for n in names(r)), "纯数字 10 位 -> CRC-32 十进制候选")

    r = identify("!!!")
    check(r["match"] == "other", "无法识别串 -> other")

    print("自测结果: {}".format("全部通过" if ok else "存在失败"))
    return 0 if ok else 1


def main(argv=None):
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="hash-identify.py",
        description="依据长度、字符集、$ 前缀格式判断未知哈希的可能算法类型（启发式）")
    parser.add_argument("hash", nargs="?", help="待识别的哈希串（缺省读 stdin，每行一个）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测并退出")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.hash is not None:
        inputs = [args.hash]
    elif not sys.stdin.isatty():
        inputs = sys.stdin.read().splitlines()
    else:
        parser.error("请提供哈希串或用管道送入 stdin")

    inputs = [x for x in inputs if x.strip()]
    if not inputs:
        parser.error("没有可识别的输入")

    results = [identify(x) for x in inputs]
    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0],
                         ensure_ascii=False, indent=2))
    else:
        for i, result in enumerate(results):
            if i:
                print("-" * 60)
            print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
