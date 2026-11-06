#!/usr/bin/env python3
"""plist 转 JSON (plist2json) —— 用 plistlib 在 macOS plist (XML/二进制)
与 JSON 之间双向转换。

自动识别输入格式：
  - 输入是合法 JSON -> 输出 plist（默认 XML，可用 --binary 输出二进制）
  - 输入是 plist (XML 或 binaryplist) -> 输出 JSON（UTF-8）

用法:
    python plist2json.py 输入.plist 输出.json          # plist -> JSON
    python plist2json.py 输入.json 输出.plist          # JSON -> plist
    python plist2json.py 输入.json 输出.plist --binary # JSON -> 二进制 plist
示例:
    python plist2json.py Info.plist Info.json
"""

import argparse
import json
import plistlib
import sys


def detect_json(text):
    """粗判输入是否为 JSON（首字符启发 + 尝试解析）。"""
    s = text.lstrip()
    if s.startswith(("{", "[")):
        try:
            json.loads(s)
            return True
        except ValueError:
            pass
    return False


def plist_to_json(src, dst):
    with open(src, "rb") as f:
        data = plistlib.load(f)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")
    print(f"plist -> JSON: {dst}")


def json_to_plist(src, dst, binary=False):
    with open(src, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    fmt = plistlib.FMT_BINARY if binary else plistlib.FMT_XML
    with open(dst, "wb") as f:
        plistlib.dump(data, f, fmt=fmt)
    kind = "二进制 plist" if binary else "XML plist"
    print(f"JSON -> {kind}: {dst}")


def main(argv):
    ap = argparse.ArgumentParser(description="plist 与 JSON 双向转换")
    ap.add_argument("src", help="输入文件 (.plist 或 .json)")
    ap.add_argument("dst", help="输出文件")
    ap.add_argument("--binary", action="store_true",
                    help="JSON 转 plist 时输出二进制格式")
    args = ap.parse_args(argv[1:])

    with open(args.src, "rb") as f:
        head = f.read(8)
    try:
        text = open(args.src, "r", encoding="utf-8-sig", errors="strict").read()
    except (UnicodeDecodeError, OSError):
        text = ""

    if head == b"bplist00":
        plist_to_json(args.src, args.dst)
    elif detect_json(text):
        json_to_plist(args.src, args.dst, binary=args.binary)
    else:
        # 其余按 XML plist 处理
        plist_to_json(args.src, args.dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
