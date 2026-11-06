#!/usr/bin/env python3
"""命名组代码生成器 — 从正则的命名捕获组自动生成 Python 样板代码。

生成内容：dataclass 定义（--dataclass，默认）或 m.groupdict() 解包 dict 样板，
并附上编译好的正则与 match 处理函数骨架，可直接粘贴使用。

用法：
  python -I regex-groupgen.py '(?P<year>\\d{4})-(?P<month>\\d{2})-(?P<day>\\d{2})'
  python -I regex-groupgen.py --dict '(?P<host>[\\w.]+):(?P<port>\\d+)'
  python -I regex-groupgen.py --pattern-file pat.txt
退出码：0 成功；1 无命名组；2 正则编译失败。
"""
import argparse
import re
import sys

DATACLASS_TEMPLATE = '''\
import dataclasses
import re

PATTERN = re.compile(r"""{pattern}""")


@dataclasses.dataclass(frozen=True)
class {cls}:
    """由 regex-groupgen.py 自动生成。"""
{fields}

    @classmethod
    def from_match(cls, m: "re.Match[str]") -> "{cls} | None":
        if m is None:
            return None
        return cls(
{ctor}
        )

    @classmethod
    def parse(cls, text: str) -> "{cls} | None":
        return cls.from_match(PATTERN.search(text))
'''

DICT_TEMPLATE = '''\
import re

PATTERN = re.compile(r"""{pattern}""")


def extract(text: str) -> dict | None:
    """从 text 中提取命名组，返回 dict；无匹配返回 None。"""
    m = PATTERN.search(text)
    if m is None:
        return None
    d = m.groupdict()
{cast_body}
    return d
'''

_TYPE_HINTS = {
    r"\\d+": "int",
    r"\d+": "int",
}


def guess_field_line(name: str) -> str:
    return f"    {name}: str"


def main(argv=None):
    # 生成代码含中文注释/文档串，重定向到文件时强制 UTF-8，
    # 否则 Windows 默认 GBK 写出、Python 3 按 UTF-8 解析会 SyntaxError
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser(description="从命名捕获组生成 dataclass/dict 样板代码")
    ap.add_argument("pattern", nargs="?", help="含命名捕获组的正则")
    ap.add_argument("--pattern-file", help="从文件读取正则")
    ap.add_argument("--dict", dest="as_dict", action="store_true",
                    help="生成 dict 解包样板而不是 dataclass")
    ap.add_argument("--class-name", default="Parsed", help="dataclass 类名（默认 Parsed）")
    args = ap.parse_args(argv)

    pattern = args.pattern
    if args.pattern_file:
        with open(args.pattern_file, "r", encoding="utf-8") as f:
            pattern = f.read().strip()
    if not pattern:
        ap.print_usage(sys.stderr)
        return 2

    try:
        rx = re.compile(pattern)
    except re.error as exc:
        print(f"错误：正则编译失败: {exc}", file=sys.stderr)
        return 2

    names = list(rx.groupindex.keys())
    if not names:
        print("错误：正则中没有命名捕获组（如 (?P<name>...)）", file=sys.stderr)
        return 1

    if args.as_dict:
        cast_lines = []
        for name in names:
            cast_lines.append(f"    {name} = d[{name!r}]")
            cast_lines.append(f"    # TODO: 按需转换类型，如 d[{name!r}] = int({name})")
        code = DICT_TEMPLATE.format(pattern=pattern, cast_body="\n".join(cast_lines))
    else:
        fields = "\n".join(guess_field_line(n) for n in names)
        ctor = "\n".join(f"            {n}=m.group({n!r})," for n in names)
        code = DATACLASS_TEMPLATE.format(
            pattern=pattern, cls=args.class_name, fields=fields, ctor=ctor
        )

    print(code)

    # 自检：编译生成的代码是否合法
    try:
        compile(code, "<generated>", "exec")
    except SyntaxError as exc:
        print(f"错误：生成的代码无法编译: {exc}", file=sys.stderr)
        return 1
    print(f"# 生成 {len(names)} 个字段: {', '.join(names)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
