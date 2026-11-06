#!/usr/bin/env python3
"""INI 转 JSON：用 configparser 读取 INI 配置并带类型推断输出为 JSON。

每个 section 变成一个 JSON 对象；顶层 [DEFAULT] 键合并进各 section，
单独以键 "__default__" 输出一份。无 section 的裸键归入 "_root"。

用法:
    python ini2json.py config.ini               # 输出到 stdout
    python ini2json.py config.ini -o out.json   # 输出到文件
    python ini2json.py config.ini --no-infer    # 全部保留字符串

示例命令:
    python ini2json.py app.ini --indent 2
类型推断规则: true/false -> bool; 整数 -> int; 浮点 -> float; 其余字符串原样。
"""
import argparse
import configparser
import json
import sys


def infer(text: str, no_infer=False):
    """把字符串推断为 int/float/bool，失败则原样返回。"""
    if no_infer:
        return text
    s = text.strip()
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return text


def parse(path_or_fp, has_section_arg=False, no_infer=False):
    """解析 INI，返回 (root_dict, default_dict)。"""
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str  # 保留键大小写
    if has_section_arg:
        cp.read_file(path_or_fp)
    else:
        read = cp.read(path_or_fp, encoding="utf-8-sig")
        if not read:
            raise FileNotFoundError(f"无法读取文件: {path_or_fp}")
    raw_defaults = cp.defaults()  # 原始字符串，用于判断键是否来自 DEFAULT
    defaults = {k: infer(v, no_infer) for k, v in raw_defaults.items()}
    result = {}
    if defaults:
        result["__default__"] = dict(defaults)
    for section in cp.sections():
        obj = {}
        for k, v in cp.items(section):
            if k in raw_defaults and raw_defaults[k] == v:
                continue  # 该键继承自 [DEFAULT]，已单独输出
            obj[k] = infer(v, no_infer)
        result[section] = obj
    return result, defaults


def main(argv=None):
    ap = argparse.ArgumentParser(description="INI 配置转 JSON，带类型推断")
    ap.add_argument("input", help="INI 文件路径")
    ap.add_argument("-o", "--output", help="输出 JSON 路径，缺省 stdout")
    ap.add_argument("--no-infer", action="store_true", help="不推断类型")
    ap.add_argument("--indent", type=int, default=2, help="输出缩进 (默认 2)")
    args = ap.parse_args(argv)

    try:
        result, _ = parse(args.input, no_infer=args.no_infer)
    except FileNotFoundError as e:
        print(f"ini2json: {e}", file=sys.stderr)
        return 1
    except configparser.Error as e:
        print(f"ini2json: INI 解析失败: {e}", file=sys.stderr)
        return 1

    out = open(args.output, "w", encoding="utf-8", newline="\n") if args.output else sys.stdout
    try:
        json.dump(result, out, ensure_ascii=False, indent=args.indent)
        out.write("\n")
    finally:
        if args.output:
            out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
