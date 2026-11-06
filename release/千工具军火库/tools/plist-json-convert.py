#!/usr/bin/env python3
"""plist 与 JSON 互转：用标准库 plistlib 在 macOS plist（XML / 二进制）与 JSON 之间双向转换。

用法:
    python plist-json-convert.py input.plist -o output.json     # plist -> JSON
    python plist-json-convert.py input.json  -o output.plist    # JSON -> plist (XML)
    python plist-json-convert.py input.plist --bin -o out.plist # 输出二进制 plist

说明:
    - 输入格式按扩展名与内容自动判定（plist 以 <?xml / bplist 开头）。
    - plist 的 date/data 类型转换: date -> ISO 字符串, data -> base64 字符串；
      反向转换时，形如 ISO 时间戳的字符串会尝试还原为 date，
      键名以 ":base64" 结尾的字符串还原为 data（可选，用于往返）。
    - JSON -> plist 时 keys 必须为字符串（json 本身保证）。

示例:
    python plist-json-convert.py Info.plist -o Info.json
    python plist-json-convert.py config.json -o config.plist
"""

import argparse
import base64
import binascii
import json
import plistlib
import re
import sys
from datetime import datetime, timezone

_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
)


def _looks_like_plist(raw):
    head = raw.lstrip()
    return head.startswith(b"<?xml") or head.startswith(b"bplist")


def plist_to_obj(value):
    """plist 值 -> JSON 可序列化对象"""
    if isinstance(value, dict):
        return {str(k): plist_to_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plist_to_obj(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    return value


def obj_to_plist(value):
    """JSON 对象 -> plistlib 可写对象（尽力还原 date/data）"""
    if isinstance(value, dict):
        return {k: obj_to_plist(v) for k, v in value.items()}
    if isinstance(value, list):
        return [obj_to_plist(v) for v in value]
    if isinstance(value, str):
        if _ISO_RE.match(value):
            try:
                iso = value.replace(" ", "T")
                if iso.endswith("Z"):
                    iso = iso[:-1] + "+00:00"
                dt = datetime.fromisoformat(iso)
                if dt.tzinfo is not None:
                    # plistlib 要求 naive datetime（按 UTC 解释），二进制格式尤其严格
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            except ValueError:
                pass
        if value.endswith(":base64"):
            try:
                return base64.b64decode(value[:-7], validate=True)
            except (binascii.Error, ValueError):
                pass
        return value
    return value


def main(argv=None):
    ap = argparse.ArgumentParser(description="plist (XML/二进制) 与 JSON 双向转换")
    ap.add_argument("input", help="输入文件 (.plist / .json)")
    ap.add_argument("-o", "--output", help="输出文件（缺省打印到 stdout）")
    ap.add_argument("--bin", action="store_true", help="JSON->plist 时输出二进制 plist")
    ap.add_argument("--indent", type=int, default=2, help="JSON 缩进（默认 2）")
    args = ap.parse_args(argv)

    with open(args.input, "rb") as f:
        raw = f.read()

    if _looks_like_plist(raw):
        data = plistlib.loads(raw)
        obj = plist_to_obj(data)
        out_text = json.dumps(obj, ensure_ascii=False, indent=args.indent) + "\n"
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(out_text)
            print("written: %s (plist -> json)" % args.output)
        else:
            sys.stdout.write(out_text)
    else:
        obj = json.loads(raw.decode("utf-8-sig"))
        data = obj_to_plist(obj)
        fmt = plistlib.FMT_BINARY if args.bin else plistlib.FMT_XML
        payload = plistlib.dumps(data, fmt=fmt)
        if args.output:
            with open(args.output, "wb") as f:
                f.write(payload)
            print("written: %s (json -> %s plist)" %
                  (args.output, "binary" if args.bin else "xml"))
        else:
            sys.stdout.buffer.write(payload)
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
