#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时长人性化格式化（duration-format）。

用途：
    把秒数转换成「1天2小时3分4秒」这类可读形式，支持精度档位（从最大非零
    单位起保留多少个单位，跳过中间为 0 的单位）、中英文单位名与小数秒。

用法：
    python duration-format.py 93784                # 1天2小时3分4秒
    python duration-format.py 93784 -p 2           # 1天2小时
    python duration-format.py 3661.5 --decimals 1  # 1小时1分1.5秒
    python duration-format.py -3661                # 负数 → -1小时1分1秒
    python duration-format.py 1234567 -p 2 --lang en   # 14d 6h
    python duration-format.py --demo               # 内置示例自测（安全）

参数：
    -p/--precision  精度档位：保留的非零单位个数（1~4，默认 4）
    --decimals      秒的小数位数（0~6，默认 0 即取整到秒）
    --lang          zh（默认，天/小时/分/秒）或 en（d/h/m/s）
    --sep           单位间连接符（默认：zh 为空串，en 为空格）

退出码：0 = 成功；2 = 参数不合法。
"""

from __future__ import annotations

import argparse
import sys

UNIT_NAMES = {
    "zh": ("天", "小时", "分", "秒"),
    "en": ("d", "h", "m", "s"),
}
UNIT_SIZES = (86400, 3600, 60, 1)


def _setup_stdio() -> None:
    """让中文输出在 Windows 各类管道下不因编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def format_duration(seconds, precision=4, decimals=0, lang="zh", sep=None) -> str:
    if not 1 <= precision <= 4:
        raise ValueError("precision 必须在 1~4 之间")
    if not 0 <= decimals <= 6:
        raise ValueError("decimals 必须在 0~6 之间")
    names = UNIT_NAMES.get(lang)
    if names is None:
        raise ValueError(f"不支持的语言: {lang!r}（可选 zh/en）")

    value = float(seconds)
    sign = "-" if value < 0 else ""
    value = abs(value)
    if decimals > 0:
        whole, frac = int(value), value - int(value)
    else:
        whole, frac = int(round(value)), 0.0

    days, whole = divmod(whole, 86400)
    hours, whole = divmod(whole, 3600)
    minutes, secs = divmod(whole, 60)
    vals = (days, hours, minutes, secs + frac)

    if all(v == 0 for v in vals):
        return f"0{names[3]}"

    parts = []
    kept = 0
    for idx, val in enumerate(vals):
        if val == 0:
            continue
        if kept >= precision:
            break
        kept += 1
        if idx == 3 and decimals > 0:
            text = f"{val:.{decimals}f}".rstrip("0").rstrip(".")
        else:
            text = str(int(val))
        parts.append(f"{text}{names[idx]}")
    joiner = sep if sep is not None else ("" if lang == "zh" else " ")
    return sign + joiner.join(parts)


def main(argv=None) -> int:
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="duration-format",
        description="把秒数转换为「1天2小时3分4秒」等可读形式，支持精度档位。",
    )
    parser.add_argument("seconds", nargs="?", type=float, help="时长（秒），可为小数或负数")
    parser.add_argument("-p", "--precision", type=int, default=4,
                        help="精度档位：保留的非零单位个数（1~4，默认 4）")
    parser.add_argument("--decimals", type=int, default=0,
                        help="秒的小数位数（0~6，默认 0 即取整到秒）")
    parser.add_argument("--lang", choices=("zh", "en"), default="zh", help="单位语言（默认 zh）")
    parser.add_argument("--sep", help="单位之间的连接符（默认：zh 空串，en 空格）")
    parser.add_argument("--demo", action="store_true", help="内置示例自测（安全）")
    args = parser.parse_args(argv)

    try:
        if args.demo:
            samples = [
                (93784.0, 4, 0, "zh", None),
                (93784.0, 2, 0, "zh", None),
                (3600.0, 4, 0, "zh", None),
                (45.0, 4, 0, "zh", None),
                (3661.5, 4, 1, "zh", None),
                (-3661.0, 4, 0, "zh", None),
                (1234567.0, 2, 0, "en", None),
                (0.0, 4, 0, "zh", None),
            ]
            for sec, prec, dec, lang, sep in samples:
                text = format_duration(sec, prec, dec, lang, sep)
                print(f"{sec!r:>10} 秒  p={prec} dec={dec} lang={lang}  →  {text}")
            return 0
        if args.seconds is None:
            parser.error("请提供秒数（位置参数）或使用 --demo")
        text = format_duration(args.seconds, args.precision, args.decimals, args.lang, args.sep)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
