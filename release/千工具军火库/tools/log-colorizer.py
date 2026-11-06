#!/usr/bin/env python3
r"""日志着色器 (log-colorizer): 按级别和自定义正则给日志行加 ANSI 颜色后输出。

用途:
    读取日志文件或标准输入, 按内置级别规则给整行着色
    (FATAL/PANIC=加粗红, ERROR/CRITICAL=红, WARN/WARNING=黄, INFO/NOTICE=绿,
    DEBUG=青, TRACE=暗青), 并支持两类自定义规则:
      -r 正则=颜色   整行规则: 行命中正则时整行用该颜色 (可多次, 优先于内置级别规则)
      -H 正则=颜色   片段规则: 行内命中的文字用该颜色高亮 (可多次, 可与整行色叠加)
    输出接终端时自动着色; 重定向到管道/文件时自动关闭, 需要时用 --force-color 强制。

示例命令:
    python -I log-colorizer.py --force-color app.log
    python -I log-colorizer.py -r "Timeout=bold_red" -H "10\\.0\\.0\\.9=cyan" app.log
    tail -n 200 server.log | python -I log-colorizer.py
    python -I log-colorizer.py --no-color app.log
    python -I log-colorizer.py --list-colors

退出码: 0 成功; 2 参数错误或文件读取失败。
"""

import argparse
import re
import sys

RESET = "\x1b[0m"

BASE_COLORS = {
    "black": 30, "red": 31, "green": 32, "yellow": 33,
    "blue": 34, "magenta": 35, "cyan": 36, "white": 37,
    "bright_black": 90, "bright_red": 91, "bright_green": 92,
    "bright_yellow": 93, "bright_blue": 94, "bright_magenta": 95,
    "bright_cyan": 96, "bright_white": 97,
}
MODIFIERS = {"bold": "1", "dim": "2", "italic": "3", "ul": "4", "strike": "9"}

_LEVEL_SPEC = [
    (r"\b(?:FATAL|PANIC|EMERG(?:ENCY)?)\b", "bold_red"),
    (r"\b(?:ERROR|CRIT(?:ICAL)?|SEV0)\b", "red"),
    (r"\bWARN(?:ING)?\b", "yellow"),
    (r"\b(?:DEBUG|DBG)\b", "cyan"),
    (r"\b(?:INFO|NOTICE)\b", "green"),
    (r"\bTRACE\b", "dim_cyan"),
]


def resolve_color(name):
    """把颜色名 (如 bold_red / dim_cyan / 1;31 / none) 解析为 ANSI 前缀, 非法时抛 ValueError。"""
    name = name.strip().lower().replace("-", "_")
    if name in ("", "none", "off"):
        return ""
    mods, rest = [], name
    while True:
        head, sep, tail = rest.partition("_")
        if sep and head in MODIFIERS:
            mods.append(MODIFIERS[head])
            rest = tail
        else:
            break
    if re.fullmatch(r"\d{1,2}(?:;\d{1,2})*", rest):
        codes = [rest]
    elif rest in BASE_COLORS:
        codes = [str(BASE_COLORS[rest])]
    else:
        raise ValueError(f"未知颜色 {name!r} (可用 --list-colors 查看名字)")
    return "\x1b[" + ";".join(mods + codes) + "m"


class Rule:
    """一条着色规则: 编译好的正则 + ANSI 前缀。"""

    def __init__(self, pattern, color):
        self.regex = re.compile(pattern)
        self.ansi = resolve_color(color)


LEVEL_RULES = [Rule(pat, color) for pat, color in _LEVEL_SPEC]


def parse_rule(spec):
    """解析 '正则=颜色' 形式的规则字符串为 Rule 对象。"""
    pat, sep, color = spec.rpartition("=")
    if not sep or not pat:
        raise ValueError(f"规则需写成 '正则=颜色' 的形式: {spec!r}")
    return Rule(pat, color)


def render_line(line, line_rules, hl_rules, use_color):
    """渲染单行: 先按整行规则(自定义在前, 内置级别在后)定基色, 再叠加片段高亮。"""
    if not use_color or not line:
        return line
    base = ""
    for rule in line_rules:
        if rule.regex.search(line):
            base = rule.ansi
            break
    if not hl_rules:
        return f"{base}{line}{RESET}" if base else line
    segments = [(line, "")]
    for rule in hl_rules:
        nxt = []
        for text, col in segments:
            if col or not text:
                nxt.append((text, col))
                continue
            pieces, last, matched = [], 0, False
            for mobj in rule.regex.finditer(text):
                if mobj.start() == mobj.end():
                    continue
                matched = True
                if mobj.start() > last:
                    pieces.append((text[last:mobj.start()], ""))
                pieces.append((mobj.group(0), rule.ansi))
                last = mobj.end()
            if not matched:
                nxt.append((text, ""))
            else:
                if last < len(text):
                    pieces.append((text[last:], ""))
                nxt.extend(pieces)
        segments = nxt
    out = []
    for text, col in segments:
        color = col or base
        out.append(f"{color}{text}{RESET}" if color else text)
    return "".join(out)


def stream_setup():
    """让 stdout/stderr 在 Windows 管道/重定向场景下也按 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def iter_lines(paths):
    """逐行产出输入; paths 为空时读标准输入。"""
    if not paths:
        for line in sys.stdin:
            yield line
        return
    for path in paths:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                yield line


def list_colors():
    print("基础颜色:")
    for name, code in BASE_COLORS.items():
        print(f"  {name:<15}\x1b[{code}m████████{RESET}  {name}")
    print("修饰前缀 (可与颜色组合, 如 bold_red / dim_cyan): "
          + ", ".join(f"{k}_" for k in MODIFIERS))
    print("也接受 ANSI 数字串, 如 '1;31'。")
    return 0


def main(argv=None):
    stream_setup()
    parser = argparse.ArgumentParser(
        prog="log-colorizer",
        description="按级别和自定义正则给日志行加 ANSI 颜色后输出。")
    parser.add_argument("files", nargs="*", help="日志文件; 缺省读标准输入")
    parser.add_argument("-r", "--rule", action="append", default=[], metavar="PAT=COLOR",
                        help="整行规则: 行命中正则 PAT 时整行用 COLOR (可重复, 优先于内置级别规则)")
    parser.add_argument("-H", "--highlight", action="append", default=[], metavar="PAT=COLOR",
                        help="片段规则: 行内命中 PAT 的文字用 COLOR 高亮 (可重复)")
    parser.add_argument("--no-color", action="store_true", help="强制输出纯文本")
    parser.add_argument("--force-color", action="store_true", help="输出不是终端时也强制着色")
    parser.add_argument("--list-colors", action="store_true", help="列出可用颜色名后退出")
    args = parser.parse_args(argv)

    if args.list_colors:
        return list_colors()
    try:
        line_rules = [parse_rule(s) for s in args.rule] + LEVEL_RULES
        hl_rules = [parse_rule(s) for s in args.highlight]
    except (ValueError, re.error) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    use_color = (not args.no_color) and (args.force_color or sys.stdout.isatty())
    try:
        for raw in iter_lines(args.files):
            sys.stdout.write(render_line(raw.rstrip("\r\n"), line_rules, hl_rules, use_color) + "\n")
    except OSError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
