#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""uuid-validate.py —— UUID 批量格式校验与版本分类统计（单文件，纯 Python 标准库）。

接受命令行参数 / 文本文件 / stdin 中的 UUID 列表（每行一个，或空白/逗号/分号分隔），
逐条校验格式合法性（支持标准连字符、32 位无连字符、{花括号}、urn:uuid: 前缀），
按版本分类统计，并标出非法项及具体原因。

用法：
    python -I uuid-validate.py [UUID ...] [-f 列表文件] [--summary-only] [--strict] [--json]

示例命令：
    python -I "K:/WorkAreaZcode/tool-armory/tools/uuid-validate.py" 018f3a2b-7c1d-7e4f-9a01-2b3c4d5e6f70 oops
    python -I "K:/WorkAreaZcode/tool-armory/tools/uuid7-gen.py" -n 3 | python -I "K:/WorkAreaZcode/tool-armory/tools/uuid-validate.py"

示例输出：
    共 3 条：合法 2 条，非法 1 条
    版本分布（合法项）：
      v7 : 2 条
    非法项：
      [✗] 第 3 行  oops  原因：长度不符：……

退出码：默认 0；--strict 时存在非法项则返回 1。
"""

import argparse
import json
import re
import sys
from collections import Counter

_HEX = set("0123456789abcdefABCDEF")


def normalize(text):
    """去掉 urn:uuid: 前缀、花括号与首尾空白。"""
    t = text.strip()
    if t[:9].lower() == "urn:uuid:":
        t = t[9:]
    if len(t) >= 2 and t[0] == "{" and t[-1] == "}":
        t = t[1:-1].strip()
    return t


def to_canonical(text):
    """32 位无连字符或 8-4-4-4-12 形态 -> 小写标准形；否则返回 None。"""
    if len(text) == 32 and all(c in _HEX for c in text):
        h = text.lower()
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
    if (len(text) == 36 and text[8] == "-" and text[13] == "-"
            and text[18] == "-" and text[23] == "-"
            and all(c in _HEX for c in (text[:8] + text[9:13] + text[14:18]
                                        + text[19:23] + text[24:]))):
        return text.lower()
    return None


def describe_error(text):
    """给出校验失败的具体原因。"""
    if not text:
        return "空输入"
    if len(text) not in (32, 36):
        return f"长度不符：应为 36（标准形）或 32（无连字符），实际 {len(text)}"
    if len(text) == 32:
        bad = sorted({c for c in text if c not in _HEX})
        return f"含非十六进制字符：{'、'.join(repr(c) for c in bad[:8])}"
    if not (text[8] == "-" and text[13] == "-" and text[18] == "-" and text[23] == "-"):
        return "连字符位置错误：应为 8-4-4-4-12 分段"
    groups = (text[:8], text[9:13], text[14:18], text[19:23], text[24:])
    for idx, part in enumerate(groups, 1):
        bad = sorted({c for c in part if c not in _HEX})
        if bad:
            return f"第 {idx} 段含非十六进制字符：{'、'.join(repr(c) for c in bad[:8])}"
    return "格式无法识别"


def check_token(raw):
    """校验单个 token。返回 (是否合法, 规范形, 版本号或 None, 原因或 None)。"""
    text = normalize(raw)
    if not text:
        return False, None, None, "空输入"
    canon = to_canonical(text)
    if canon is None:
        return False, None, None, describe_error(text)
    value = int(canon.replace("-", ""), 16)
    return True, canon, (value >> 76) & 0xF, None


def collect_tokens(args):
    """收集 (行号, 原文) 列表；来源优先级：--file > 位置参数 > stdin。"""
    tokens = []
    if args.file:
        with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
            for line_no, line in enumerate(fh, 1):
                for tok in re.split(r"[\s,;]+", line.strip()):
                    if tok:
                        tokens.append((line_no, tok))
    if args.uuids:
        tokens.extend((i, u) for i, u in enumerate(args.uuids, 1))
    if not tokens and args.file is None:
        try:
            if not sys.stdin.isatty():
                for line_no, line in enumerate(sys.stdin, 1):
                    for tok in re.split(r"[\s,;]+", line.strip()):
                        if tok:
                            tokens.append((line_no, tok))
        except (AttributeError, OSError):
            pass
    return tokens


def _selftest():
    v7 = "018f3a2b-7c1d-7e4f-9a01-2b3c4d5e6f70"
    v1 = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    v4_braced = "{334a0d0f-6c1e-4c3d-9a1b-2f3e4d5c6b7a}"
    v4_nohy = "334a0d0f6c1e4c3d9a1b2f3e4d5c6b7a"
    cases = [
        (v7, True, 7),
        (v1, True, 1),
        (v4_braced, True, 4),
        (v4_nohy, True, 4),
        ("not-a-uuid", False, None),
        ("12345678-1234-1234-1234-123456789abc0", False, None),  # 长度 37
        ("g2345678-1234-1234-1234-123456789abc", False, None),   # 非法字符 g
        ("12345678123412341234123456789ab", False, None),        # 31 位
    ]
    for raw, want_ok, want_ver in cases:
        ok, canon, ver, reason = check_token(raw)
        assert ok == want_ok, (raw, ok, reason)
        if want_ok:
            assert ver == want_ver and canon, (raw, ver, canon)
        else:
            assert reason, raw
    ok, canon, ver, _ = check_token(v4_braced)
    assert ok and canon.replace("-", "") == v4_nohy and ver == 4, (canon, ver)
    print("selftest ok: 合法形态（标准/花括号/无连字符）与非法形态（长度/字符）判定全部正确")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog="uuid-validate.py",
        description="批量校验 UUID 格式合法性，按版本分类统计并标出非法项",
    )
    parser.add_argument("uuids", nargs="*",
                        help="要校验的 UUID（可多个；不带参数且未指定 --file 时从 stdin 读取）")
    parser.add_argument("-f", "--file", help="从文本文件读取 UUID 列表")
    parser.add_argument("--summary-only", action="store_true",
                        help="只输出统计摘要与非法项，不逐条列出合法项")
    parser.add_argument("--strict", action="store_true", help="存在非法项时退出码为 1")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出统计结果")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测并退出")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()

    tokens = collect_tokens(args)
    results = []
    for line_no, raw in tokens:
        ok, canon, version, reason = check_token(raw)
        results.append({"line": line_no, "input": raw, "ok": ok,
                        "uuid": canon, "version": version, "reason": reason})
    valid = [r for r in results if r["ok"]]
    invalid = [r for r in results if not r["ok"]]
    versions = dict(sorted(Counter(r["version"] for r in valid).items()))

    if args.json:
        print(json.dumps({
            "total": len(results),
            "valid": len(valid),
            "invalid": len(invalid),
            "versions": {f"v{v}": n for v, n in versions.items()},
            "invalid_items": [{"line": r["line"], "input": r["input"],
                               "reason": r["reason"]} for r in invalid],
        }, ensure_ascii=False, indent=2))
        return 1 if args.strict and invalid else 0

    print(f"共 {len(results)} 条：合法 {len(valid)} 条，非法 {len(invalid)} 条")
    if valid:
        print("\n版本分布（合法项）：")
        for v, n in versions.items():
            print(f"  v{v} : {n} 条")
        if not args.summary_only:
            print("\n合法项：")
            for r in valid:
                print(f"  [✓] 第 {r['line']} 行  v{r['version']}  {r['uuid']}")
    if invalid:
        print("\n非法项：")
        width = max(len(r["input"]) for r in invalid)
        for r in invalid:
            print(f"  [✗] 第 {r['line']} 行  {r['input']:<{width}}  原因：{r['reason']}")
    elif results:
        print("\n无非法项 ✔")
    return 1 if args.strict and invalid else 0


if __name__ == "__main__":
    sys.exit(main())
