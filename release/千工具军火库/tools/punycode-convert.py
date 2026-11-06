#!/usr/bin/env python3
"""Punycode 域名转换 —— 中文等国际化域名（IDN）与 xn-- Punycode 互转。

使用 Python 内置 idna 编解码（RFC 3490/3492）。输入既可以是单个域名，
也可以是每行一个域名的文件；自动识别每个域名的方向：
  - 含 xn-- 标签 → 解码回 Unicode 域名；
  - 含非 ASCII 字符 → 编码为 Punycode（xn-- 形式）；
  - 纯 ASCII 且无 xn-- → 原样输出。
也可用 --to encode/--to decode 强制指定方向。

用法：
  python punycode-convert.py "北京大学.cn"
  python punycode-convert.py "xn--5jsv45l.cn"
  python punycode-convert.py -i domains.txt -o converted.txt
  cat domains.txt | python punycode-convert.py --to encode

示例命令：
  python punycode-convert.py --text "www.清华大学.edu.cn"
  python punycode-convert.py --text "xn--xhqy76av1jzya.cn" --show-both

选项：
  -i, --input PATH    每行一个域名的输入文件；缺省读 stdin
  -o, --output PATH   输出文件；缺省写 stdout
  --text STR          直接处理该字符串（空格或逗号分隔多个域名）
  --to MODE           encode/decode/auto（默认 auto 自动识别）
  --show-both         每行同时输出 "unicode<TAB>punycode"
  --errors MODE       strict=出错即停；skip=跳过坏行到 stderr（默认 strict）
"""

import argparse
import sys


def _convert_label(label: str, mode: str):
    """转换单个 DNS 标签。mode: auto/encode/decode。返回转换后的标签。"""
    has_xn = label.lower().startswith("xn--")
    non_ascii = any(ord(c) > 127 for c in label)
    # 已是 Unicode 的标签在 decode 方向下原样保留
    if has_xn and mode != "encode":
        return label.encode("ascii").decode("idna")
    if non_ascii and mode != "decode":
        return label.encode("idna").decode("ascii")
    return label  # 纯 ASCII 且非 xn--（或方向相反时），原样


def convert_domain(domain: str, mode: str = "auto") -> str:
    domain = domain.strip().rstrip(".")
    if not domain:
        return domain
    # 按点分标签逐个转换，再拼回
    labels = domain.split(".")
    return ".".join(_convert_label(lb, mode) for lb in labels)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="punycode-convert",
        description="中文域名与 Punycode(xn--) 互转（内置 idna 编解码）")
    p.add_argument("domains", nargs="*", help="要转换的域名")
    p.add_argument("-i", "--input", help="每行一个域名的输入文件")
    p.add_argument("-o", "--output", help="输出文件，缺省写 stdout")
    p.add_argument("--text", help="直接处理该字符串")
    p.add_argument("--to", default="auto", choices=["auto", "encode", "decode"])
    p.add_argument("--show-both", action="store_true",
                   help="输出 'unicode<TAB>punycode' 两列")
    p.add_argument("--errors", default="strict", choices=["strict", "skip"])
    a = p.parse_args(argv)

    # 收集所有待处理域名
    items = list(a.domains)
    if a.text:
        items += [s for s in a.text.replace(",", " ").split() if s]
    if a.input:
        with open(a.input, "r", encoding="utf-8") as f:
            items += [line.strip() for line in f if line.strip() and not line.startswith("#")]
    if not a.input and not a.text and not items and not sys.stdin.isatty():
        items += [line.strip() for line in sys.stdin.buffer.read().decode("utf-8").splitlines()
                  if line.strip() and not line.startswith("#")]

    out_lines = []
    rc = 0
    for dom in items:
        try:
            unicode_form = convert_domain(dom, "decode")
            puny_form = convert_domain(dom, "encode")
        except Exception as e:
            if a.errors == "skip":
                print(f"skip: {dom!r}: {e}", file=sys.stderr)
                continue
            print(f"error: {dom!r}: {e}", file=sys.stderr)
            return 1
        if a.show_both:
            out_lines.append(f"{unicode_form}\t{puny_form}")
        else:
            # auto 模式输出与输入方向相对的形式：unicode 输入给 punycode，反之亦然
            out_lines.append(puny_form if any(ord(c) > 127 for c in dom)
                             else (unicode_form if dom.lower().startswith("xn--") else puny_form))
    # 去重保序
    seen = set()
    lines = [l for l in out_lines if not (l in seen or seen.add(l))]

    payload = "".join(l + "\n" for l in lines)
    if a.output:
        with open(a.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
    else:
        sys.stdout.buffer.write(payload.encode("utf-8"))
        sys.stdout.buffer.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main())
