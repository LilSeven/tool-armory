#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""证书有效期检查（cert-expiry）。

用途：
    读取本地证书文件（PEM，DER 自动回退），或通过 TLS 连接远端主机抓取其
    证书，输出主体/签发者、notBefore / notAfter、剩余天数与状态
    （尚未生效 / 有效 / 即将到期 / 已过期）。
    仅使用标准库 ssl + socket，只读证书信息，不修改任何系统设置。

用法：
    python cert-expiry.py server.pem                检查本地证书文件
    python cert-expiry.py --host example.com        连接远端 443 端口检查证书
    python cert-expiry.py --host host --port 8443   指定端口
    python cert-expiry.py --host host --insecure    不校验证书链（自签名/内网排查）
    python cert-expiry.py --demo                    用内置演示证书自测（安全，无网络）
    python cert-expiry.py <来源> --json              以 JSON 输出

示例命令：
    python cert-expiry.py --demo
    python cert-expiry.py --host example.com --warn-days 30

说明：本地解析使用 Python ssl 模块内部接口 ssl._ssl._test_decode_cert。
退出码：0 = 成功获取证书并输出（含已过期证书）；2 = 读取/连接/解析失败。
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import sys
import tempfile
import time
from datetime import datetime, timezone

# 内置演示证书：openssl 自签名，CN=demo.local，有效期 2026-11-01 ~ 2036-10-29。
DEMO_CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIDPzCCAiegAwIBAgIUVRQBVKm2JstPHNTtWGfFbT6TZkAwDQYJKoZIhvcNAQEL
BQAwLzETMBEGA1UEAwwKZGVtby5sb2NhbDEYMBYGA1UECgwPVG9vbEFybW9yeSBE
ZW1vMB4XDTI2MTEwMTE2NDY0MVoXDTM2MTAyOTE2NDY0MVowLzETMBEGA1UEAwwK
ZGVtby5sb2NhbDEYMBYGA1UECgwPVG9vbEFybW9yeSBEZW1vMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAomWDye39TkmAbX6YB2swGiSke8dmZ75S72c+
yY6pU/UmdlthVBfjW+k7TFcbzXeALF/Apswu+NiHwLihXKRkgeo+9kBGTwMXbMyr
Obni/p5/vEF3l8N0s96wpUKE3a5KV5sAwkL6nLubOvS8KAX8unGRXSaHAHmE7k96
lLMto9n9RoWC4W25A3NCR3azUs4ZEc3GcL4fG55SwW/67XBW3E8HaQ3SVdyp/zaO
3D2qbMzX/ZAkAqwmmbyUv/ZlHzPJPoRvxOun2DKGg0Kkf3ZklrSqneYc8H8hp7fS
B2rC8DiKyM4Kp0BCjufT5XoLqsbAUL8IjOcIjoRiuvCSP9EpzQIDAQABo1MwUTAd
BgNVHQ4EFgQUYKWfQ8ROtLVd66x9zvVpIAeT/5IwHwYDVR0jBBgwFoAUYKWfQ8RO
tLVd66x9zvVpIAeT/5IwDwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOC
AQEAhADUmm9pI8PiZobV9IPpvrUsZSPfA1Bthbt5d8qGGtifZadV6i7Yd1xytzvJ
/iAWvqacMqxq/jn4aFOdZMpSVu3ez5kOzvFpO05lNLGhdhFaewefJ71DHay0wHg8
nvew0EvYjhS+3Ev1Qh8rE1hG44dLmxLrlLL0Q3ieU++wb4/HwMCF71ni5/RKtcp4
rkqGeLsVt8+FG14J/PgTL4So0jU2NLAKhLypnBvUzJEJt6ESwbP0ilo/FhYPkqao
OxaGZLV0pZj1fwk4J6ejNH2iFPXzLdWvpD/eufoM0EnBhU6KYnWMUVrHJvwm/fxe
fOpRJ19jHbU8hg9+7AdPh3PJLA==
-----END CERTIFICATE-----
"""


def _setup_stdio() -> None:
    """让中文输出在 Windows 各类管道下不因编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _decode_cert_file(path: str) -> dict:
    test_decode = getattr(getattr(ssl, "_ssl", None), "_test_decode_cert", None)
    if test_decode is None:
        raise RuntimeError("当前 Python 的 ssl 模块不提供 _test_decode_cert，无法解析本地证书")
    return test_decode(path)


def _decode_cert_der(der: bytes) -> dict:
    pem = ssl.DER_cert_to_PEM_cert(der)
    fd, tmp_path = tempfile.mkstemp(suffix=".pem", prefix="cert-expiry-")
    try:
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            fh.write(pem)
        return _decode_cert_file(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def load_local_cert(path: str) -> dict:
    try:
        return _decode_cert_file(path)
    except Exception:
        with open(path, "rb") as fh:
            data = fh.read()
        if not data:
            raise ValueError(f"证书文件为空: {path}")
        return _decode_cert_der(data)


def fetch_remote_cert(host: str, port: int, timeout: float, insecure: bool) -> dict:
    if insecure:
        context = ssl._create_unverified_context()
    else:
        context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    if not der:
        raise ValueError("服务器未返回证书")
    return _decode_cert_der(der)


def _dn(rdn) -> str:
    if not rdn:
        return "-"
    return "".join(f"/{key}={value}" for group in rdn for key, value in group) or "-"


def _cert_epoch(text: str) -> float:
    try:
        return float(ssl.cert_time_to_seconds(text))
    except (KeyError, ValueError) as exc:
        raise ValueError(f"无法解析证书时间 {text!r}: {exc}")


def build_report(info: dict, source: str, warn_days: int, now: float) -> dict:
    not_before = _cert_epoch(info["notBefore"])
    not_after = _cert_epoch(info["notAfter"])
    remaining = not_after - now
    days = remaining / 86400.0
    if now < not_before:
        status = "尚未生效"
    elif remaining <= 0:
        status = "已过期"
    elif days <= warn_days:
        status = f"即将到期（剩余不足 {warn_days} 天）"
    else:
        status = "有效"
    return {
        "source": source,
        "subject": _dn(info.get("subject")),
        "issuer": _dn(info.get("issuer")),
        "serial": info.get("serialNumber", "-"),
        "not_before": info.get("notBefore"),
        "not_after": info.get("notAfter"),
        "not_before_epoch": not_before,
        "not_after_epoch": not_after,
        "remaining_seconds": remaining,
        "remaining_days": round(days, 2),
        "status": status,
    }


def print_report(rep: dict) -> None:
    nb_local = datetime.fromtimestamp(rep["not_before_epoch"]).astimezone()
    na_local = datetime.fromtimestamp(rep["not_after_epoch"]).astimezone()
    nb_utc = datetime.fromtimestamp(rep["not_before_epoch"], tz=timezone.utc)
    na_utc = datetime.fromtimestamp(rep["not_after_epoch"], tz=timezone.utc)
    print("== 证书有效期检查 ==")
    print(f"证书来源: {rep['source']}")
    print(f"主体:     {rep['subject']}")
    print(f"签发者:   {rep['issuer']}")
    print(f"序列号:   {rep['serial']}")
    print(f"生效自:   {nb_utc:%Y-%m-%d %H:%M:%S} UTC（本地 {nb_local.strftime('%Y-%m-%d %H:%M:%S %z')}）")
    print(f"到期于:   {na_utc:%Y-%m-%d %H:%M:%S} UTC（本地 {na_local.strftime('%Y-%m-%d %H:%M:%S %z')}）")
    days = rep["remaining_days"]
    if days >= 0:
        print(f"剩余有效期: {days:.2f} 天（约 {days / 365.0:.2f} 年）")
    else:
        print(f"已超期: {-days:.2f} 天")
    print(f"状态:     {rep['status']}")


def emit(rep: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print_report(rep)


def main(argv=None) -> int:
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="cert-expiry",
        description="用 ssl 模块读取本地证书或连接远端主机，输出有效期与剩余天数。",
    )
    parser.add_argument("target", nargs="?", help="本地证书文件路径（PEM/DER）")
    parser.add_argument("--host", help="远端主机名（与位置参数二选一）")
    parser.add_argument("--port", type=int, default=443, help="远端端口（默认 443）")
    parser.add_argument("--timeout", type=float, default=10.0, help="连接超时秒数（默认 10）")
    parser.add_argument("--insecure", action="store_true", help="跳过证书链校验（自签名场景）")
    parser.add_argument("--warn-days", type=int, default=30, help="剩余不足该天数时提示“即将到期”（默认 30）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--demo", action="store_true", help="使用内置演示证书自测（安全）")
    args = parser.parse_args(argv)

    if args.demo:
        fd, tmp_path = tempfile.mkstemp(suffix=".pem", prefix="cert-expiry-demo-")
        try:
            with os.fdopen(fd, "w", encoding="ascii") as fh:
                fh.write(DEMO_CERT_PEM)
            info = load_local_cert(tmp_path)
        except Exception as exc:
            print(f"错误: {exc}", file=sys.stderr)
            return 2
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        emit(build_report(info, "内置演示证书（demo.local，自签名）", args.warn_days, time.time()), args.json)
        return 0

    if bool(args.target) == bool(args.host):
        parser.error("请提供且仅提供一个来源：本地证书文件（位置参数）或 --host 主机名")
        return 2

    try:
        if args.host:
            info = fetch_remote_cert(args.host, args.port, args.timeout, args.insecure)
            source = f"远端 {args.host}:{args.port}"
        else:
            info = load_local_cert(args.target)
            source = f"本地文件 {args.target}"
        rep = build_report(info, source, args.warn_days, time.time())
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    emit(rep, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
