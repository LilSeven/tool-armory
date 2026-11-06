#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TTL 剩余时间换算（ttl-remaining）。

用途：
    给定缓存 TTL 时长与三种时间参考之一——绝对过期时刻（--expire）、写入
    时刻（--stored）、已存在时长（--age），计算缓存条目的剩余有效时间，
    按 TTL 折算已流逝/剩余百分比，并给出人性化提示
    （缓存新鲜 / 即将过期 / 已过期 / 时钟异常）。

用法：
    python ttl-remaining.py --ttl 3600 --age 1200
    python ttl-remaining.py --ttl 3600 --expire 2026-11-02T12:00:00Z
    python ttl-remaining.py --ttl 3600 --stored 2026-11-02T10:00:00
    python ttl-remaining.py --ttl 3600 --age 1200 --now 1761900000
    python ttl-remaining.py --demo            # 内置示例参数自测（安全）

说明：
    --ttl/--age 接受秒数；--expire/--stored/--now 接受 epoch 秒或 ISO8601
    字符串（可带 Z 或时区偏移；不带时区按本地时间理解）。

退出码：0 = 计算成功（含已过期）；2 = 参数不合法。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime


def _setup_stdio() -> None:
    """让中文输出在 Windows 各类管道下不因编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


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


def parse_time_value(text: str) -> float:
    """epoch 秒 或 ISO8601（Z/时区偏移可；无时区按本地时间）。"""
    raw = text.strip()
    try:
        return float(raw)
    except ValueError:
        pass
    if raw.upper().endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"无法解析时间: {text!r}（应为 epoch 秒或 ISO8601）")
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.timestamp()


def local_str(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


def main(argv=None) -> int:
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="ttl-remaining",
        description="根据过期时刻与缓存 TTL 计算剩余有效时间并给出人性化提示。",
    )
    parser.add_argument("--ttl", type=float, default=None, help="缓存 TTL 时长（秒，正数）")
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--expire", type=parse_time_value, help="绝对过期时刻（epoch 秒或 ISO8601）")
    src.add_argument("--stored", type=parse_time_value, help="条目写入时刻（epoch 秒或 ISO8601）")
    src.add_argument("--age", type=float, help="条目已存在的时长（秒）")
    parser.add_argument("--now", type=parse_time_value, help="参考“当前时刻”（默认系统时间）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--demo", action="store_true", help="内置示例参数（--ttl 3600，写入于 20 分钟前）；忽略其他输入")
    args = parser.parse_args(argv)

    if args.demo:
        args.ttl, args.stored, args.expire, args.age = 3600.0, time.time() - 1200.0, None, None
    else:
        if args.ttl is None:
            parser.error("缺少 --ttl（或使用 --demo）")
        if args.expire is None and args.stored is None and args.age is None:
            parser.error("需要 --expire / --stored / --age 之一（或使用 --demo）")

    if args.ttl is not None and args.ttl <= 0:
        parser.error("--ttl 必须为正数")
    if args.age is not None and args.age < 0:
        parser.error("--age 不能为负数")

    now = args.now if args.now is not None else time.time()

    if args.expire is not None:
        expire_at = args.expire
        origin = f"指定过期时刻 {args.expire:.0f}"
    elif args.stored is not None:
        expire_at = args.stored + args.ttl
        origin = f"写入时刻 {args.stored:.0f} + TTL"
    else:
        expire_at = now + (args.ttl - args.age)
        origin = f"已存在 {args.age:.0f} 秒"

    remaining = expire_at - now
    elapsed = args.ttl - remaining
    pct_left = max(0.0, remaining) / args.ttl * 100.0

    if remaining <= 0:
        hint = f"已过期 {humanize(-remaining)}，建议清理或回源刷新"
    elif elapsed < 0:
        hint = "剩余时间超过 TTL，请核对 expire/stored/age 与系统时钟"
    elif remaining < max(60.0, args.ttl * 0.1):
        hint = "即将过期（剩余不足 TTL 的 10% 或 60 秒），建议提前刷新"
    else:
        hint = "缓存新鲜"

    result = {
        "ttl_seconds": args.ttl,
        "time_origin": origin,
        "now_epoch": now,
        "expire_at_epoch": expire_at,
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "pct_left": round(pct_left, 1),
        "hint": hint,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("== TTL 剩余时间换算 ==")
    print(f"TTL 设定:       {humanize(args.ttl)}（{args.ttl:.0f} 秒）")
    print(f"时间参考:       {origin}")
    print(f"参考当前时刻:   {now:.0f}（本地 {local_str(now)}）")
    print(f"已流逝:         {humanize(elapsed)}（{elapsed:.0f} 秒，{100 - pct_left:.1f}%）")
    print(f"剩余有效时间:   {humanize(remaining)}（{remaining:.0f} 秒，{pct_left:.1f}%）")
    print(f"预计过期时刻:   {expire_at:.0f}（本地 {local_str(expire_at)}）")
    print(f"提示: {hint}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
