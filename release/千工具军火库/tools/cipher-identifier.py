#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编码类型侦探 (cipher-identifier)。

分析未知字符串，判断它可能是 hex / base64 / base32 / 哈希值 / UUID / JWT /
URL 编码 / Unix 时间戳 / 纯数字串 / 普通文本，并为每类候选给出下一步处理建议。
仅用 Python 标准库；适合 CTF、日志排查中的编码类型快速识别。

用法 (Windows Git Bash):
  python -I cipher-identifier.py "dGVzdA=="                                # 分析 base64 串
  python -I cipher-identifier.py "550e8400-e29b-41d4-a716-446655440000"    # 分析 UUID
  python -I cipher-identifier.py "21232f297a57a5a743894a0e4a801fc3"        # 分析 32 位十六进制
  echo "dGVzdA==" | python -I cipher-identifier.py -                       # 从 stdin 读取
  python -I cipher-identifier.py --json "94287082"                         # 输出 JSON

退出码: 0 = 分析完成; 2 = 未提供输入。
"""

import argparse
import base64
import binascii
import json
import re
import sys
import urllib.parse
import uuid

HASH_HEX_LEN = {
    32: "MD5 / NTLM / MD4",
    40: "SHA-1",
    56: "SHA-224",
    64: "SHA-256",
    96: "SHA-384",
    128: "SHA-512",
}

UUID_VERSIONS = {
    1: "时间型 v1 (含 MAC/时间戳)",
    2: "DCE 安全型 v2",
    3: "MD5 名字空间 v3",
    4: "随机型 v4",
    5: "SHA-1 名字空间 v5",
    6: "时间排序型 v6",
    7: "时间排序型 v7",
}

MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "PNG 图片"),
    (b"\xff\xd8\xff", "JPEG 图片"),
    (b"GIF8", "GIF 图片"),
    (b"PK\x03\x04", "ZIP 压缩包"),
    (b"Rar!", "RAR 压缩包"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip 压缩包"),
    (b"\x1f\x8b", "GZIP 压缩流"),
    (b"BZh", "BZIP2 压缩流"),
    (b"%PDF", "PDF 文档"),
    (b"Salted__", "OpenSSL 加密数据"),
    (b"\x7fELF", "Linux ELF 可执行文件"),
    (b"MZ", "Windows PE 可执行文件"),
)

UUID_RE = re.compile(
    r"\{?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}?"
)


def looks_like_text(raw):
    """判断解码出的字节是否像人类可读文本。

    UTF-8 可解码时看可打印比例即可；退化到 latin-1 时额外要求 >=90% 为 ASCII，
    防止随机二进制碰巧落在 latin-1 扩展区 (如 \\xdf\\xf6 等) 而被误判为文本。
    """
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


def preview(text, limit=100):
    text = re.sub(r"\s+", " ", text.strip())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def b64url_decode(seg):
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def try_b64(s):
    """尝试 base64 / base64url 严格解码，成功返回 (名称, bytes)，否则 None。"""
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
        return name, raw
    return None


def detect_magic(raw):
    for prefix, name in MAGIC:
        if raw.startswith(prefix):
            return name
    return None


def analyze(s):
    """返回候选列表，每项 {rank, type, desc, suggest}。"""
    findings = []

    def add(rank, ftype, desc, suggest):
        findings.append({"rank": rank, "type": ftype, "desc": desc, "suggest": suggest})

    compact = re.sub(r"\s+", "", s)
    digit_only = bool(re.fullmatch(r"\d+", compact)) and len(compact) <= 18

    # --- JWT (三段式 base64url) ---
    parts = s.split(".")
    if len(parts) == 3 and parts[0] and parts[1] and all(
        re.fullmatch(r"[A-Za-z0-9_-]*", p) for p in parts
    ):
        try:
            header = json.loads(b64url_decode(parts[0]).decode("utf-8"))
            payload = json.loads(b64url_decode(parts[1]).decode("utf-8"))
            if isinstance(header, dict):
                add(1, "JWT", "三段式 JWT (base64url)，header=%s"
                    % preview(json.dumps(header, ensure_ascii=False)),
                    "校验签名需要密钥；payload=%s"
                    % preview(json.dumps(payload, ensure_ascii=False)))
        except Exception:
            pass

    # --- UUID ---
    if UUID_RE.fullmatch(s):
        try:
            u = uuid.UUID(s.strip("{}"))
            ver = "，%s" % UUID_VERSIONS[u.version] if u.version else ""
            add(2, "UUID", "合法 UUID%s" % ver,
                "标识符本身无需解码；v4 为随机生成、不可反解，通常作为资源 ID")
        except ValueError:
            pass

    # --- 哈希形状 (纯十六进制且长度命中常见摘要长度) ---
    if re.fullmatch(r"[0-9a-fA-F]+", compact) and len(compact) in HASH_HEX_LEN:
        add(3, "哈希形状", "%d 位十六进制，长度匹配 %s"
            % (len(compact), HASH_HEX_LEN[len(compact)]),
            "若是口令哈希，仅可在授权测试范围内用 hashcat/john 处理；"
            "也可能只是普通 hex 数据 (见 hex 候选)")

    # --- hex ---
    if re.fullmatch(r"[0-9a-fA-F]+", compact) and len(compact) >= 2 and len(compact) % 2 == 0:
        raw = bytes.fromhex(compact)
        ok, text = looks_like_text(raw)
        if ok:
            add(4, "hex", "合法十六进制串 (%d 位 -> %d 字节)，解出文本: %s"
                % (len(compact), len(raw), preview(text)),
                "下一步: 用 chain-decoder.py 继续解链，或 bytes.fromhex(s).decode()")
        elif not digit_only:
            magic = detect_magic(raw)
            add(4, "hex", "合法十六进制串 (%d 位 -> %d 字节)，解码为二进制%s"
                % (len(compact), len(raw), ("，文件头像 " + magic) if magic else ""),
                "下一步: 判断是密钥/二进制数据，还是需换其他解读方式")

    # --- base64 / base64url ---
    hit = try_b64(compact)
    if hit:
        kind, raw = hit
        ok, text = looks_like_text(raw)
        if ok:
            add(5, kind, "合法 %s，解出文本: %s" % (kind, preview(text)),
                "下一步: 用 chain-decoder.py 检查是否还有嵌套编码")
        elif kind == "base64" and not digit_only:
            magic = detect_magic(raw)
            add(5, kind, "合法 %s，解出 %d 字节二进制%s"
                % (kind, len(raw), ("，文件头像 " + magic) if magic else ""),
                "解码后是二进制: 可能是文件内容/加密数据；若输入同时是合法 hex，优先按 hex 处理")

    # --- base32 ---
    if len(compact) >= 8 and len(compact) % 8 == 0 and re.fullmatch(r"[A-Za-z2-7]+=*", compact):
        try:
            raw = base64.b32decode(compact, casefold=True)
        except (binascii.Error, ValueError):
            raw = None
        if raw is not None:
            ok, text = looks_like_text(raw)
            if ok:
                add(6, "base32", "合法 Base32，解出文本: %s" % preview(text),
                    "Base32 常见于 TOTP 密钥/邮件编码；用 chain-decoder.py 继续解链")
            elif not digit_only:
                add(6, "base32", "合法 Base32，解出 %d 字节二进制" % len(raw),
                    "可能是二进制数据，也可能是 TOTP 密钥本体 (如 totp-gen.py 的输入)")

    # --- URL 编码 ---
    pct = re.findall(r"%[0-9A-Fa-f]{2}", s)
    if pct:
        dec = urllib.parse.unquote(s)
        if dec != s:
            add(7, "URL 编码", "含 %d 个 %%XX 转义，解码: %s" % (len(pct), preview(dec)),
                "下一步: urllib.parse.unquote(s) 还原；注意 + 不会被 unquote 转成空格")

    # --- 纯数字串 ---
    if re.fullmatch(r"\d+", compact):
        v = int(compact)
        hints = []
        if len(compact) == 11 and compact.startswith("1"):
            hints.append("11 位且 1 开头，疑似中国大陆手机号")
        if 1_000_000_000 <= v <= 4_100_000_000:
            hints.append("处于 Unix 秒级时间戳常见区间")
        if 1_700_000_000_000 <= v <= 4_100_000_000_000:
            hints.append("处于 Unix 毫秒级时间戳常见区间")
        add(8, "数字串", "纯数字 (%d 位)%s"
            % (len(compact), ("；" + "；".join(hints)) if hints else ""),
            "下一步: 按业务含义判断 (ID/验证码/时间戳/手机号)；时间戳可用 date -d @N 查看")

    # --- 兜底 ---
    if not findings:
        printable = all(ch.isprintable() or ch in "\t\n\r" for ch in s)
        if printable:
            add(9, "普通文本", "未发现 hex/base64/UUID/数字等已知形态",
                "下一步: 确认字符串来源；或用 chain-decoder.py 兜底再扫一遍")
        else:
            add(9, "二进制输入", "输入包含不可打印字符，可能是原始二进制",
                "下一步: 先用 base64/hexdump 转成可打印形式再分析")
    return findings


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="编码类型侦探: 识别字符串可能的编码/类型并给出下一步建议")
    ap.add_argument("target", nargs="?", help="待分析字符串; '-' 表示从 stdin 读取")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = ap.parse_args(argv)

    if args.target == "-":
        s = sys.stdin.read()
    elif args.target:
        s = args.target
    else:
        ap.error("请提供待分析字符串，或用 '-' 从 stdin 读取")
    s = s.strip()
    if not s:
        print("输入为空，无事可做。", file=sys.stderr)
        return 2

    findings = analyze(s)
    if args.json:
        print(json.dumps({"input_chars": len(s), "findings": findings},
                         ensure_ascii=False, indent=2))
        return 0

    nonascii = " (含非 ASCII 字符)" if any(ord(c) > 126 for c in s) else ""
    print("== 编码类型侦探 ==")
    print("输入: %d 字符%s" % (len(s), nonascii))
    for i, f in enumerate(findings, 1):
        print("候选 %d [%s] %s" % (i, f["type"], f["desc"]))
        print("        建议: %s" % f["suggest"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
