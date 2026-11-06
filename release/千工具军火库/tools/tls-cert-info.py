#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TLS 证书查看器（标准库 ssl/socket 实现）。

用途:
    连接目标主机的 TLS 端口完成握手并获取服务器证书，显示协议版本、
    主体、签发者、序列号、有效期（含剩余天数与状态）与 SHA256 指纹；
    可选输出 PEM 或 base64 单行 DER。默认执行标准证书链与主机名校验；
    查看自签名/内网证书时可用 --insecure 跳过校验（仅用于检查）。
    证书字段由内置的最小化 DER 解析器提取，不依赖第三方库。

示例:
    python tls-cert-info.py pypi.org
    python tls-cert-info.py example.com:8443
    python tls-cert-info.py 127.0.0.1 8443 --insecure --server-name localhost
    python tls-cert-info.py example.com --pem --der-b64

退出码: 0 成功；2 连接/握手/验证失败或参数错误。
"""

import argparse
import base64
import hashlib
import re
import socket
import ssl
import sys
from datetime import datetime, timezone

# 常用 X.509 名称属性 OID（未收录的 OID 直接以点分形式显示）
OID_NAMES = {
    "2.5.4.3": "CN",
    "2.5.4.4": "SN",
    "2.5.4.5": "serialNumber",
    "2.5.4.6": "C",
    "2.5.4.7": "L",
    "2.5.4.8": "ST",
    "2.5.4.9": "street",
    "2.5.4.10": "O",
    "2.5.4.11": "OU",
    "2.5.4.17": "postalCode",
    "2.5.4.42": "GN",
    "0.9.2342.19200300.100.1.25": "DC",
    "1.2.840.113549.1.9.1": "emailAddress",
}


def _utf8_stdio():
    """让中文输出在管道/重定向时保持 UTF-8，避免 Windows 本地编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


# ---------- 最小化 DER / X.509 解析 ----------

def _read_tlv(data, off):
    tag = data[off]
    off += 1
    ln = data[off]
    off += 1
    if ln & 0x80:
        n = ln & 0x7F
        if n == 0:
            raise ValueError("不支持的 DER 长度编码")
        ln = int.from_bytes(data[off:off + n], "big")
        off += n
    return tag, data[off:off + ln], off + ln


def _iter_tlvs(body):
    off = 0
    while off < len(body):
        tag, val, off = _read_tlv(body, off)
        yield tag, val


def _decode_oid(raw):
    if not raw:
        return "?"
    parts = [str(raw[0] // 40), str(raw[0] % 40)]
    val = 0
    for c in raw[1:]:
        val = (val << 7) | (c & 0x7F)
        if not c & 0x80:
            parts.append(str(val))
            val = 0
    return ".".join(parts)


def _decode_name(der):
    """Name ::= SEQUENCE OF SET OF SEQUENCE { type OID, value ANY }"""
    parts = []
    for _tag, set_val in _iter_tlvs(der):
        for _tag2, atv_val in _iter_tlvs(set_val):
            attrs = list(_iter_tlvs(atv_val))
            if len(attrs) < 2:
                continue
            oid = _decode_oid(attrs[0][1])
            value = attrs[1][1].decode("utf-8", "replace")
            parts.append("%s=%s" % (OID_NAMES.get(oid, oid), value))
    return ", ".join(parts)


def _decode_time(raw):
    s = raw.decode("ascii", "replace").strip()
    if s.endswith("Z"):
        s = s[:-1]
    s = re.split(r"[+-]", s)[0]
    if "." in s:
        s = s.split(".")[0]
    if len(s) == 10:      # UTCTime YYMMDDHHMM
        yy = int(s[:2])
        year = 2000 + yy if yy < 50 else 1900 + yy
        digits = s[2:] + "00"
    elif len(s) == 12:    # UTCTime YYMMDDHHMMSS
        yy = int(s[:2])
        year = 2000 + yy if yy < 50 else 1900 + yy
        digits = s[2:]
    elif len(s) == 14:    # GeneralizedTime YYYYMMDDHHMMSS
        year = int(s[:4])
        digits = s[4:]
    else:
        raise ValueError("无法解析 ASN.1 时间: %r" % raw)
    return datetime(year, int(digits[0:2]), int(digits[2:4]),
                    int(digits[4:6]), int(digits[6:8]), int(digits[8:10]),
                    tzinfo=timezone.utc)


def parse_cert_info(der):
    """从 DER 证书提取 version/serial/issuer/subject/validity。

    Certificate ::= SEQUENCE { tbsCertificate, sigAlg, sigValue }
    tbsCertificate ::= SEQUENCE { [0] version, serial, sigAlg, issuer,
                                  validity, subject, spki, [3] extensions }
    """
    tag, cert_body, _ = _read_tlv(der, 0)
    if tag != 0x30:
        raise ValueError("不是 DER 编码的 X.509 证书")
    cert_elems = list(_iter_tlvs(cert_body))
    if len(cert_elems) != 3 or cert_elems[0][0] != 0x30:
        raise ValueError("tbsCertificate 结构异常")
    elems = list(_iter_tlvs(cert_elems[0][1]))
    if len(elems) < 6:
        raise ValueError("tbsCertificate 结构异常")
    idx = 0
    version = 1
    if elems[0][0] == 0xA0:          # [0] EXPLICIT version
        inner = _read_tlv(elems[0][1], 0)[1]
        version = (inner[0] if inner else 0) + 1
        idx = 1
    serial = int.from_bytes(elems[idx][1], "big")
    idx += 1                          # serialNumber
    idx += 1                          # 跳过 signature AlgorithmIdentifier
    issuer = _decode_name(elems[idx][1])
    idx += 1
    validity = list(_iter_tlvs(elems[idx][1]))
    idx += 1
    not_before = _decode_time(validity[0][1])
    not_after = _decode_time(validity[1][1])
    subject = _decode_name(elems[idx][1])
    return {"version": version, "serial": serial, "issuer": issuer,
            "subject": subject, "not_before": not_before, "not_after": not_after}


# ---------- 连接与展示 ----------

def fetch_certificate(host, port, timeout, insecure=False, server_hostname=None):
    if insecure:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    else:
        ctx = ssl.create_default_context()
    raw = socket.create_connection((host, port), timeout=timeout)
    try:
        with ctx.wrap_socket(raw, server_hostname=server_hostname) as tls:
            return {
                "der": tls.getpeercert(binary_form=True),
                "protocol": tls.version(),
                "cipher": tls.cipher(),
            }
    finally:
        try:
            raw.close()
        except OSError:
            pass


def main(argv=None):
    _utf8_stdio()
    ap = argparse.ArgumentParser(
        description="获取并显示 TLS 服务器证书信息（纯标准库）")
    ap.add_argument("host", help="主机名，或 host:port")
    ap.add_argument("port", nargs="?", type=int, default=None,
                    help="端口（默认 443）")
    ap.add_argument("--timeout", type=float, default=10.0, metavar="SEC")
    ap.add_argument("--insecure", action="store_true",
                    help="跳过证书链与主机名校验（自签名/内网证书）")
    ap.add_argument("--server-name", default=None, metavar="NAME",
                    help="SNI 与主机名校验使用的名字（默认取 host）")
    ap.add_argument("--pem", action="store_true", help="同时输出 PEM 证书")
    ap.add_argument("--der-b64", action="store_true", help="同时输出 base64 单行 DER")
    args = ap.parse_args(argv)

    host, port = args.host, args.port
    if port is None:
        head, sep, tail = host.rpartition(":")
        if sep and tail.isdigit() and ":" not in head:
            host, port = head, int(tail)
        else:
            port = 443

    try:
        res = fetch_certificate(host, port, args.timeout, args.insecure,
                                args.server_name or host)
    except ssl.SSLCertVerificationError as e:
        print("错误: 证书验证失败: %s" % e, file=sys.stderr)
        print("提示: 若为自签名/内网证书，可加 --insecure 仅查看", file=sys.stderr)
        return 2
    except socket.timeout:
        print("错误: 连接或握手超时（可用 --timeout 调整）", file=sys.stderr)
        return 2
    except (OSError, ssl.SSLError) as e:
        print("错误: %s" % e, file=sys.stderr)
        return 2

    der = res["der"]
    if not der:
        print("错误: 服务器未提供证书", file=sys.stderr)
        return 2
    try:
        info = parse_cert_info(der)
    except (ValueError, IndexError) as e:
        print("错误: 证书解析失败: %s" % e, file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    if now < info["not_before"]:
        status = "尚未生效"
    elif now > info["not_after"]:
        status = "已过期"
    else:
        status = "有效"
    remain = (info["not_after"] - now).total_seconds() / 86400.0
    cipher = res["cipher"] or ("?", "?", 0)
    cipher_name = cipher[0]
    cipher_bits = cipher[2] if len(cipher) > 2 else 0

    print("主机        : %s:%d" % (host, port))
    print("协议/套件   : %s / %s（%s 位）" % (res["protocol"] or "?",
                                             cipher_name, cipher_bits))
    print("证书版本    : v%d" % info["version"])
    print("序列号      : 0x%X" % info["serial"])
    print("主体        : %s" % (info["subject"] or "-"))
    print("签发者      : %s" % (info["issuer"] or "-"))
    print("生效时间    : %s" % info["not_before"].strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("失效时间    : %s" % info["not_after"].strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("状态        : %s（距失效 %.1f 天）" % (status, remain))
    print("SHA256 指纹 : %s" % ":".join("%02X" % b for b in hashlib.sha256(der).digest()))
    if args.der_b64:
        print("base64 DER  : %s" % base64.b64encode(der).decode("ascii"))
    if args.pem:
        print("-" * 64)
        print(ssl.DER_cert_to_PEM_cert(der).strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
