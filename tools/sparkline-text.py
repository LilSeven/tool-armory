#!/usr/bin/env python3
"""迷你趋势线 (sparkline-text) -- 用 ▁▂▃▄▅▆▇█ 把一列数据渲染成一行火花线。

示例命令:
    python sparkline-text.py 3 1 4 1 5 9 2 6
    python sparkline-text.py "1.5, -2, 3.25, 0, 7" --stats
    echo "10 20 15 30 25" | python sparkline-text.py

说明:
    * 数据来自命令行参数; 若没有参数则从 stdin 读取。
    * 分隔符: 空白、逗号、分号均可, 可混用。
    * 所有值相等时输出平坦线 (▄▄▄); 出现 nan/inf 等非有限数时报错, 退出码 2。
    * 单文件, 只依赖 Python 标准库; 输出强制 UTF-8。
"""

from __future__ import annotations

import argparse
import math
import re
import sys

BLOCKS = "▁▂▃▄▅▆▇█"
FLAT_CHAR = "▄"


def force_utf8() -> None:
    """Windows 管道/Git Bash 下 stdout 默认是 ANSI 代码页 (如 gbk), 统一改成 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def render(values: list[float]) -> str:
    """把数值序列映射到 8 级块字符, 最小值 ▁ 最大值 █。"""
    lo, hi = min(values), max(values)
    if hi == lo:
        return FLAT_CHAR * len(values)
    span = hi - lo
    top = len(BLOCKS) - 1
    out = []
    for v in values:
        idx = int((v - lo) / span * top + 0.5)
        out.append(BLOCKS[min(top, idx)])
    return "".join(out)


def parse_numbers(text: str) -> list[float]:
    tokens = [t for t in re.split(r"[\s,;]+", text.strip()) if t]
    if not tokens:
        raise ValueError("没有读到任何数据")
    values = []
    for tok in tokens:
        try:
            v = float(tok)
        except ValueError:
            raise ValueError(f"无法解析为数字: {tok!r}") from None
        if not math.isfinite(v):
            raise ValueError(f"只接受有限数值, 拒绝: {tok!r}")
        values.append(v)
    return values


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(
        prog="sparkline-text.py",
        description="用 ▁▂▃▄▅▆▇█ 把一列数字渲染成一行 Unicode 火花线",
    )
    parser.add_argument("values", nargs="*", help="数字序列 (空白/逗号分隔); 省略时读 stdin")
    parser.add_argument("--stats", action="store_true", help="在火花线下方附加 min/max/n 统计行")
    args = parser.parse_args(argv)

    text = " ".join(args.values).strip()
    if not text:
        text = sys.stdin.read()
    try:
        values = parse_numbers(text)
    except ValueError as exc:
        print(f"sparkline-text: 错误: {exc}", file=sys.stderr)
        return 2

    print(render(values))
    if args.stats:
        print(f"min={min(values):g}  max={max(values):g}  n={len(values)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
