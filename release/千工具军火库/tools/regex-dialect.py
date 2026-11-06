#!/usr/bin/env python3
"""正则方言转换器 — 在 PCRE/JavaScript/Go(RE2) 与 Python re 之间改写常见语法差异。

处理的差异包括：
  * 命名捕获组：  (?P<name>...)  <->  (?<name>...)   (PCRE/JS/.NET 风格)
  * 命名反向引用：(?P=name)      <->  \\k<name>       (PCRE/JS 风格)
  * POSIX 字符类：[[:alpha:]] [[:digit:]] ...       (Python 不支持，翻译为 \d\w 等)
  * 非捕获组 (?:...)、前后瞻 (?=...) (?!...) (<=) 等多数方言通用；
    Go(RE2) 不支持前后瞻与反向引用，转换时给出警告注释。

用法：
  python -I regex-dialect.py --to python   '<(?<tag>[[:alpha:]]+)>\\k<tag>'
  python -I regex-dialect.py --to js       '(?P<year>\\d{4})-(?P<month>\\d{2})'
  python -I regex-dialect.py --to go       '(?P<word>\\w+)\\s+(?P<num>\\d+)'
  python -I regex-dialect.py --to pcre     '[[:alpha:]]+@(?P<host>[\\w.]+)'
  python -I regex-dialect.py --to python --stdin < pattern.txt

退出码：0 成功；1 参数/正则解析错误。
"""
import argparse
import sys

# POSIX 字符类 -> 各方言通用等价写法（跨方言都能用的字符范围）
POSIX_MAP = {
    "alpha": "a-zA-Z",
    "digit": "0-9",
    "alnum": "a-zA-Z0-9",
    "upper": "A-Z",
    "lower": "a-z",
    "space": r"\s",
    "blank": r" \t",
    "punct": r"""!"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~""",
    "xdigit": "0-9a-fA-F",
    "word": r"\w",
    "cntrl": r"\x00-\x1f",
    "print": r"\x20-\x7e",
    "graph": r"\x21-\x7e",
}


def _warn(go_mode: bool, notes: list, msg: str) -> None:
    notes.append(msg)


def convert(pattern: str, target: str):
    """把 pattern 转写为目标方言，返回 (新pattern, 警告列表)。"""
    notes = []
    out = []
    i = 0
    n = len(pattern)
    in_class = False  # 方括号内不做组语法替换

    while i < n:
        ch = pattern[i]

        if ch == "\\" and i + 1 < n:
            # 命名反向引用 \k<name> 须先于普通转义处理
            if pattern.startswith("\\k<", i):
                end = pattern.find(">", i)
                if end != -1:
                    name = pattern[i + 3 : end]
                    if target == "python":
                        out.append(f"(?P={name})")
                    else:
                        out.append(f"\\k<{name}>")
                    i = end + 1
                    continue
            out.append(pattern[i : i + 2])
            i += 2
            continue

        if ch == "[" and not in_class:
            # 尝试识别 POSIX 类 [:name:]（可能连续多个，如 [[:alpha:][:digit:]]）
            j = i
            cls = "["
            i += 1
            pos_begin = len(out)
            cls = "["
            found_posix = False
            while i < n and i - j < 512:
                if pattern.startswith("[:", i):
                    end = pattern.find(":]", i + 2)
                    if end != -1:
                        name = pattern[i + 2 : end]
                        if name in POSIX_MAP:
                            cls += POSIX_MAP[name]
                            found_posix = True
                            i = end + 2
                            continue
                        else:
                            notes.append(f"未知 POSIX 类 [[:{name}:]]，原样保留")
                if pattern[i] == "]":
                    cls += "]"
                    i += 1
                    break
                cls += pattern[i]
                i += 1
            out.append(cls)
            continue

        if ch == "(" and not in_class:
            rest = pattern[i:]
            if rest.startswith("(?P<"):
                end = pattern.find(">", i)
                if end != -1:
                    name = pattern[i + 4 : end]
                    if target in ("js", "pcre", "dotnet"):
                        out.append(f"(?<{name}>")
                    else:  # python
                        out.append(f"(?P<{name}>")
                    i = end + 1
                    continue
            if rest.startswith("(?<") and not rest.startswith("(?<=") and not rest.startswith("(?<!"):
                end = pattern.find(">", i)
                if end != -1:
                    name = pattern[i + 3 : end]
                    if target == "python":
                        out.append(f"(?P<{name}>")
                    else:
                        out.append(f"(?<{name}>")
                    i = end + 1
                    continue
            # 命名反向引用 (?P=name)
            if rest.startswith("(?P="):
                end = pattern.find(")", i)
                if end != -1:
                    name = pattern[i + 4 : end]
                    if target in ("js",):
                        out.append(f"\\k<{name}>")
                        i = end + 1
                        continue
                    if target in ("pcre", "dotnet"):
                        out.append(f"\\k<{name}>")
                        i = end + 1
                        continue
                    # python
                    out.append(f"(?P={name})")
                    i = end + 1
                    continue
            if rest.startswith("\\k<") or rest.startswith("k<"):
                pass
            out.append(ch)
            i += 1
            continue

        if pattern.startswith("\\k<", i) and not in_class:
            end = pattern.find(">", i)
            if end != -1:
                name = pattern[i + 3 : end]
                if target == "python":
                    out.append(f"(?P={name})")
                else:
                    out.append(f"\\k<{name}>")
                i = end + 1
                continue

        out.append(ch)
        if ch == "]":
            in_class = False
        elif ch == "[":
            in_class = True
        i += 1

    result = "".join(out)

    # Go(RE2) 特有限制提示
    if target == "go":
        for tok, desc in (
            ("(?=", "前瞻断言"),
            ("(?!", "负前瞻断言"),
            ("(?<=", "后顾断言"),
            ("(?<!", "负后顾断言"),
        ):
            if tok in result:
                notes.append(f"Go RE2 不支持{desc} {tok}...)，需人工改写")
        if "(?P=" in result or "\\k<" in result:
            notes.append("Go RE2 不支持反向引用，需人工改写")
    if target == "js" and "(?<" in result.replace("(?<=<", ""):
        pass  # ES2018+ 已支持后顾，现代 JS 可用
    return result, notes


def main(argv=None):
    ap = argparse.ArgumentParser(description="PCRE/JS/Go <-> Python re 正则方言转换器")
    ap.add_argument("pattern", nargs="?", help="要转换的正则；省略时从 stdin 读取")
    ap.add_argument("--to", required=True, choices=("python", "js", "pcre", "go", "dotnet"),
                    help="目标方言")
    ap.add_argument("--stdin", action="store_true", help="从 stdin 读入正则")
    args = ap.parse_args(argv)

    pattern = args.pattern
    if args.stdin or pattern is None:
        pattern = sys.stdin.read().rstrip("\n")
    if not pattern:
        print("错误：空正则", file=sys.stderr)
        return 1

    new, notes = convert(pattern, args.to)
    print(new)
    for note in notes:
        print(f"# 警告: {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
