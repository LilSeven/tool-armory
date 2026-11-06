#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""字符串转义互转：在 Python repr、JSON、shell 单引号等风格之间安全互转。

支持风格:
  py-repr   Python 字面量（repr / ast.literal_eval）
  json      JSON 字符串（json.dumps / json.loads）
  shell     POSIX shell 单引号安全引用（'it''s' 转义）
  url       百分号编码（urllib.parse.quote / unquote）
  unicode   \uXXXX 十六进制转义（unicode_escape）

用法（示例均按 POSIX shell / Git Bash 引号语义书写）:
  python str-escape.py encode --style json -- "he said \"hi\" 中文"
  python str-escape.py decode --style py-repr -- "'a\tb\u4e2d'"
  # py-repr 的 decode 需要收到带引号的字面量：bash 外层用双引号保住内层单引号，
  # 且双引号内 \t \u4e2d 由 Python 原样接收（bash 不解释它们）。
  # PowerShell/cmd 下请把外层引号换成各自能传字面单引号的写法。
  python str-escape.py encode --style shell -- "it's a test"
  echo "text%20here" | python str-escape.py decode --style url

说明:
  - 不带文本参数时从 stdin 读取原文（decode 时按原样读取，不做 shell 去引号）。
  - encode = 把原文转成对应风格的安全表示；decode = 从该表示还原原文。
  - 解析失败（如 py-repr 语法错误）报错并退出码 2。
"""

import argparse
import ast
import json
import sys
import urllib.parse


def do_encode(text, style):
    if style == "py-repr":
        return repr(text)
    if style == "json":
        return json.dumps(text, ensure_ascii=False)
    if style == "shell":
        return "'" + text.replace("'", "'\"'\"'") + "'"
    if style == "url":
        return urllib.parse.quote(text, safe="")
    if style == "unicode":
        return text.encode("unicode_escape").decode("ascii")
    raise ValueError("未知风格 %r" % style)


def do_decode(text, style):
    if style == "py-repr":
        v = ast.literal_eval(text)
        if not isinstance(v, str):
            raise ValueError("py-repr 解析结果不是字符串: %r" % (v,))
        return v
    if style == "json":
        v = json.loads(text)
        if not isinstance(v, str):
            raise ValueError("JSON 解析结果不是字符串: %r" % (v,))
        return v
    if style == "shell":
        s = text.strip()
        if not (s.startswith("'") and s.endswith("'") and len(s) >= 2):
            raise ValueError("shell 单引号格式不正确")
        return s[1:-1].replace("'\"'\"'", "'")
    if style == "url":
        return urllib.parse.unquote(text)
    if style == "unicode":
        return text.encode("ascii", "backslashreplace").decode("unicode_escape")
    raise ValueError("未知风格 %r" % style)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="字符串转义风格互转")
    ap.add_argument("action", choices=["encode", "decode"])
    ap.add_argument("--style", default="json",
                    choices=["py-repr", "json", "shell", "url", "unicode"])
    ap.add_argument("text", nargs="?", help="原文（缺省从 stdin 读）")

    # argparse 对出现在可选参数之后的 `--` 处理不可靠，手动预处理
    argv = sys.argv[1:]
    text_after_dd = None
    if "--" in argv:
        i = argv.index("--")
        tail = argv[i + 1:]
        text_after_dd = " ".join(tail)  # shell 已按空格切分，多段拼接
        argv = argv[:i]
    args = ap.parse_args(argv)
    if text_after_dd is not None and args.text is None:
        args.text = text_after_dd

    if args.text is None:
        if sys.stdin.isatty():
            print("错误: 请提供文本参数或通过 stdin 输入", file=sys.stderr)
            sys.exit(2)
        data = sys.stdin.buffer.read()
        text = data.decode("utf-8-sig", "replace")
        text = text.rstrip("\r\n")
    else:
        text = args.text

    try:
        result = do_encode(text, args.style) if args.action == "encode" else do_decode(text, args.style)
    except (ValueError, SyntaxError, UnicodeDecodeError) as e:
        print("转换失败: %s" % e, file=sys.stderr)
        sys.exit(2)
    sys.stdout.write(result + "\n")


if __name__ == "__main__":
    main()
