"""Base64 合法性检测 —— 检测字符串是否为合法 Base64, 报告非法字符位置并估算解码后长度。

用途:
    对输入做 Base64 校验: 检查字符集(A-Z a-z 0-9 + / =)、总长是否为 4 的倍数、
    填充符 '=' 是否只出现在末尾且不超过 2 个。非法字符逐个报告 0 基位置、原因
    与上下文摘录; 同时按 4 字符一组估算解码后的字节数。
    默认自动剥离 data:...;base64, 前缀并忽略所有空白(--strict 可关闭空白容忍),
    --urlsafe 额外接受 '-' 与 '_'。校验失败时退出码为 1, 便于脚本判断。

示例命令:
    python base64-validate.py --string "SGVsbG8sIHdvcmxkIQ=="
    python base64-validate.py --string "SGVs?bG8" --max-errors 5
    python base64-validate.py dump.b64
    cat payload.txt | python base64-validate.py --urlsafe

退出码: 0 校验通过; 1 校验不通过; 2 参数错误。

仅依赖 Python 标准库。
"""

import argparse
import pathlib
import re
import string
import sys

STD_ALPHABET = set(string.ascii_letters + string.digits + "+/")
URLSAFE_ALPHABET = STD_ALPHABET | {"-", "_"}
WHITESPACE = " \t\r\n\f\v"
DATA_URI_RE = re.compile(r"\s*data:[^;,]{0,200};base64\s*,", re.IGNORECASE)
BASE64_SCHEME_RE = re.compile(r"\s*base64://", re.IGNORECASE)


def read_text(args):
    if args.string is not None:
        return args.string
    path = args.in_file or args.file
    if path:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    if sys.stdin.isatty():
        raise ValueError("没有输入: 请用 --string、--in/位置参数文件或 stdin 提供内容")
    return sys.stdin.read()


def strip_prefix(text):
    """去掉 data:...;base64, 或 base64:// 前缀, 返回 (剩余文本, 跳过的前缀长度)。"""
    m = DATA_URI_RE.match(text)
    if m:
        return text[m.end():], m.end()
    m = BASE64_SCHEME_RE.match(text)
    if m:
        return text[m.end():], m.end()
    return text, 0


def analyze(text, urlsafe=False, strict=False):
    """校验并返回 (是否合法, 错误列表[(位置, 字符, 原因)], 统计 dict)。"""
    errors = []
    stripped, offset = strip_prefix(text)
    alphabet = URLSAFE_ALPHABET if urlsafe else STD_ALPHABET

    cleaned = []  # [(原始位置, 字符)]
    for i, ch in enumerate(stripped):
        pos = offset + i
        if ch in WHITESPACE:
            if strict:
                errors.append((pos, ch, "空白字符(--strict 模式下视为非法)"))
            continue
        if ch not in alphabet and ch != "=":
            errors.append((pos, ch, "非法字符, 不在 Base64 字符集中"))
        else:
            cleaned.append((pos, ch))

    n = len(cleaned)
    if n == 0 and not errors:
        errors.append((offset, "", "没有有效的 Base64 字符(输入为空)"))

    pad_idx = [k for k, (_pos, ch) in enumerate(cleaned) if ch == "="]
    for k in pad_idx:
        if k < n - 2:
            errors.append((cleaned[k][0], "=", "'=' 只能出现在末尾 1-2 位"))
    if len(pad_idx) > 2:
        errors.append((cleaned[pad_idx[2]][0], "=", "'=' 数量最多 2 个"))

    if n and n % 4 != 0:
        tail_pos = cleaned[-1][0] + 1
        errors.append((tail_pos, "", "有效字符长度 %d 不是 4 的倍数(余 %d)"
                       % (n, n % 4)))

    pad_count = len(pad_idx)
    groups, rem = divmod(n - pad_count, 4)
    if rem == 1:
        estimate = groups * 3
        note = "末尾余 1 个数据字符, 理论上无法构成完整 6 位组, 估算仅按整组计"
    else:
        estimate = groups * 3 + max(0, rem - 1)
        note = ""

    stats = {
        "raw_len": len(text),
        "clean_len": n,
        "pad": pad_count,
        "estimate": estimate,
        "note": note,
    }
    return (not errors), errors, stats


def context_snippet(text, pos, radius=12):
    lo = max(0, pos - radius)
    hi = min(len(text), pos + radius + 1)
    frag = text[lo:hi].replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    caret = " " * (pos - lo) + "^"
    return frag, caret


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="检测字符串是否为合法 Base64, 报告非法字符位置并估算解码长度")
    parser.add_argument("file", nargs="?", help="包含待检文本的文件(省略则读 stdin)")
    parser.add_argument("--in", dest="in_file", help="输入文件路径(优先于位置参数)")
    parser.add_argument("--string", help="直接传入待检字符串")
    parser.add_argument("--urlsafe", action="store_true",
                        help="同时接受 URL 安全字符 '-' 和 '_'")
    parser.add_argument("--strict", action="store_true",
                        help="空白字符也算非法(默认忽略空白)")
    parser.add_argument("--max-errors", type=int, default=10,
                        help="最多报告多少处问题(默认 10, 0=只看结论)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if args.max_errors < 0:
        parser.error("--max-errors 不能为负数")

    try:
        text = read_text(args)
    except Exception as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1

    ok, errors, stats = analyze(text, urlsafe=args.urlsafe, strict=args.strict)
    print("输入长度: %d 字符 | 有效字符(含 '='): %d 个 | 填充符: %d 个"
          % (stats["raw_len"], stats["clean_len"], stats["pad"]))
    if stats["note"]:
        print("估算说明: %s" % stats["note"])
    if ok:
        print("结论: 合法 Base64")
        print("估算解码后长度: %d 字节" % stats["estimate"])
        return 0

    print("结论: 不是合法 Base64")
    print("估算解码后长度(仅参考, 含非法字符时无意义): %d 字节" % stats["estimate"])
    print("共 %d 处问题:" % len(errors))
    show = errors if args.max_errors == 0 else errors[:args.max_errors]
    for pos, ch, reason in show:
        ch_disp = repr(ch) if ch else "<末尾>"
        print("  - 位置 %d 字符 %s: %s" % (pos, ch_disp, reason))
        if ch:
            frag, caret = context_snippet(text, pos)
            print("      %s" % frag)
            print("      %s" % caret)
    if len(show) < len(errors):
        print("  (其余 %d 处省略, 可用 --max-errors 调整)"
              % (len(errors) - len(show)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
