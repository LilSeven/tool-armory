#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘古之白加空格 (pangu-space)。

在中英文、中文与数字之间的紧邻处插入一个半角空格 (中文排版 /
盘古之白 / GitHub 风格)。重复运行结果不变 (幂等)。纯标准库实现。

规则:
  - 仅在 CJK 汉字 (\u3400-\u4dbf, \u4e00-\u9fff, \uf900-\ufaff)
    与 ASCII 字母/数字直接相邻处插入空格;
  - 全角标点与英文之间不插入 (如 「Python」 保持原样);
  - 已有空格分隔的不重复加。

用法:
    python pangu-space.py [文件...] [-i]

示例命令:
    python pangu-space.py note.txt
    echo "使用Python学习编程" | python pangu-space.py -
    python pangu-space.py -i note.txt

退出码: 0 = 成功; 2 = 读文件失败。
"""

import argparse
import re
import sys

_CJK = r"\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF"
_ALNUM = r"A-Za-z0-9"

_RE_CJK_ALNUM = re.compile(rf"([{_CJK}])([{_ALNUM}])")
_RE_ALNUM_CJK = re.compile(rf"([{_ALNUM}])([{_CJK}])")


def add_space(text):
    text = _RE_CJK_ALNUM.sub(r"\1 \2", text)
    text = _RE_ALNUM_CJK.sub(r"\1 \2", text)
    return text


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="中英文/中文与数字之间加半角空格")
    ap.add_argument("paths", nargs="*", default=[],
                    help="输入文件; 省略或 '-' 表示 stdin")
    ap.add_argument("-i", "--in-place", action="store_true",
                    help="就地改写文件")
    args = ap.parse_args(argv)

    paths = args.paths or ["-"]
    if args.in_place and paths == ["-"]:
        print("错误: -i 需要指定文件", file=sys.stderr)
        return 2

    rc = 0
    for p in paths:
        try:
            if p == "-":
                data = sys.stdin.buffer.read()
            else:
                with open(p, "rb") as fh:
                    data = fh.read()
        except OSError as exc:
            print(f"错误: 无法读取 {p}: {exc}", file=sys.stderr)
            rc = 2
            continue
        out = add_space(data.decode("utf-8", errors="replace"))
        if args.in_place:
            try:
                with open(p, "wb") as fh:
                    fh.write(out.encode("utf-8"))
            except OSError as exc:
                print(f"错误: 无法写入 {p}: {exc}", file=sys.stderr)
                rc = 2
        else:
            sys.stdout.write(out + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
