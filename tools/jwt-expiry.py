#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JWT 过期时间解析（jwt-expiry）。

用途：
    解码 JWT（JSON Web Token）载荷中的 iat / nbf / exp 时间戳，输出签发时刻、
    生效时刻、过期时刻（UTC 与本地时间），并相对当前时刻计算剩余有效期，
    给出「尚未生效 / 有效 / 即将过期 / 已过期」状态判断。
    仅做 Base64URL 解码与本地展示，不校验签名、不发起网络请求。

用法：
    python jwt-expiry.py <token>                     解析 JWT 字符串（“-”表示从 stdin 读）
    python jwt-expiry.py --file token.txt            从文件读取第一个非空行作为 token
    python jwt-expiry.py --demo                      用内置示例 token 自测（安全）
    python jwt-expiry.py <token> --now 1761900000    指定“当前时刻”（epoch 秒或 ISO8601）
    python jwt-expiry.py <token> --json              以 JSON 输出全部字段

示例命令：
    python jwt-expiry.py --demo
    python jwt-expiry.py eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE5MDAwMDAwMDB9.x --now 1700000000

退出码：0 = 解析成功（含已过期的情况）；2 = 输入不是合法 JWT 或读取失败。
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from datetime import datetime, timezone


def _setup_stdio() -> None:
    """让中文输出在 Windows 各类管道下不因编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def b64url_decode(segment: str) -> bytes:
    segment = segment.strip()
    segment += "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment.encode("ascii"))
    except Exception as exc:
        raise ValueError(f"不是合法的 Base64URL 段: {segment[:24]!r}… ({exc})")


def parse_token(token: str):
    parts = token.strip().split(".")
    if not 2 <= len(parts) <= 5:
        raise ValueError(f"JWT 应为 2~5 段、以“.”分隔，实际为 {len(parts)} 段")
    for idx, part in enumerate(parts, 1):
        if not part:
            raise ValueError(f"第 {idx} 段为空")
    try:
        header = json.loads(b64url_decode(parts[0]).decode("utf-8"))
        payload = json.loads(b64url_decode(parts[1]).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JWT 头/载荷不是合法 JSON: {exc}")
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise ValueError("JWT 头/载荷应为 JSON 对象")
    return header, payload, parts


def get_ts(payload: dict, key: str):
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} 不应是布尔值")
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            raise ValueError(f"{key} 不是数字时间戳: {value!r}")
    if not isinstance(value, (int, float)):
        raise ValueError(f"{key} 不是数字时间戳: {value!r}")
    return float(value)


def humanize(seconds: float) -> str:
    """把秒数转成“1天2小时3分4秒”式中文时长。"""
    seconds = float(seconds)
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    if seconds < 1:
        return f"{sign}{seconds:.3f}秒"
    total = int(round(seconds))
    chunks = []
    for size, name in ((86400, "天"), (3600, "小时"), (60, "分"), (1, "秒")):
        if total >= size:
            count, total = divmod(total, size)
            chunks.append(f"{count}{name}")
    return sign + ("".join(chunks) or "0秒")


def fmt_epoch(epoch: float) -> str:
    utc = datetime.fromtimestamp(epoch, tz=timezone.utc)
    local = datetime.fromtimestamp(epoch).astimezone()
    return (f"{utc:%Y-%m-%d %H:%M:%S} UTC"
            f"（本地 {local:%Y-%m-%d %H:%M:%S} {local:%z}）")


def resolve_now(value) -> float:
    if value is None:
        return time.time()
    try:
        return float(value)
    except ValueError:
        pass
    text = value.strip()
    if text.upper().endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"--now 只接受 epoch 秒或 ISO8601 时间: {value!r}")
    if dt.tzinfo is None:
        dt = dt.astimezone()  # 不带时区时按本地时区理解
    return dt.timestamp()


def build_demo_token() -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": "demo-user",
        "iat": now - 3600,
        "nbf": now - 3600,
        "exp": now + 86400,
    }

    def b64url(obj) -> str:
        raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return ".".join((b64url(header), b64url(payload), "ZGVtby1zaWduYXR1cmU"))


def load_token(args) -> str:
    if args.demo:
        return build_demo_token()
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    break
            else:
                raise ValueError(f"文件 {args.file} 中没有非空行")
    elif args.token == "-":
        line = sys.stdin.read().strip()
    elif args.token:
        line = args.token.strip()
    else:
        raise ValueError("请提供一个 JWT（位置参数）、--file 或 --demo")
    if line.lower().startswith("bearer "):
        line = line[7:].strip()
    if not line:
        raise ValueError("JWT 内容为空")
    return line


def main(argv=None) -> int:
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="jwt-expiry",
        description="解码 JWT 载荷中的 iat/exp/nbf，输出签发与过期时刻及剩余有效期（不校验签名）。",
    )
    parser.add_argument("token", nargs="?", help="JWT 字符串；传“-”从 stdin 读取")
    parser.add_argument("--file", help="从文件读取第一个非空行作为 JWT")
    parser.add_argument("--now", help="指定“当前时刻”：epoch 秒或 ISO8601（默认系统时间）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--demo", action="store_true", help="使用内置示例 token（安全自测）")
    args = parser.parse_args(argv)

    try:
        token = load_token(args)
        header, payload, parts = parse_token(token)
        now = resolve_now(args.now)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"错误: 读取失败: {exc}", file=sys.stderr)
        return 2

    iat = get_ts(payload, "iat")
    nbf = get_ts(payload, "nbf")
    exp = get_ts(payload, "exp")
    remaining = None if exp is None else exp - now

    if nbf is not None and now < nbf:
        status = "尚未生效（nbf 在未来）"
    elif exp is None:
        status = "载荷未包含 exp，无法判断过期"
    elif remaining <= 0:
        status = "已过期"
    elif remaining < 300:
        status = "即将过期（不足 5 分钟）"
    else:
        status = "有效"

    if args.json:
        print(json.dumps({
            "header": header,
            "signature_present": len(parts) >= 3,
            "now_epoch": now,
            "iat_epoch": iat,
            "nbf_epoch": nbf,
            "exp_epoch": exp,
            "remaining_seconds": remaining,
            "status": status,
        }, ensure_ascii=False, indent=2))
        return 0

    print("== JWT 过期时间解析 ==")
    sig_note = "（签名未校验）" if len(parts) >= 3 else "（无签名字段）"
    print(f"算法/类型:  {header.get('alg', '-')} / {header.get('typ', '-')}{sig_note}")
    if iat is not None:
        print(f"签发时刻 iat: {iat:.0f} → {fmt_epoch(iat)}")
    else:
        print("签发时刻 iat: 载荷未包含")
    if nbf is not None:
        print(f"生效时刻 nbf: {nbf:.0f} → {fmt_epoch(nbf)}")
    else:
        print("生效时刻 nbf: 载荷未包含（默认签发即可用）")
    if exp is not None:
        print(f"过期时刻 exp: {exp:.0f} → {fmt_epoch(exp)}")
        if remaining > 0:
            print(f"剩余有效期:   {humanize(remaining)}（{remaining:.0f} 秒）")
        else:
            print(f"已超期:       {humanize(-remaining)}（{-remaining:.0f} 秒前到期）")
    else:
        print("过期时刻 exp: 载荷未包含")
    print(f"参考当前时刻: {fmt_epoch(now)}")
    print(f"状态: {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
