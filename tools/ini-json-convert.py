#!/usr/bin/env python3
"""INI 与 JSON 互转 —— 用 configparser 在 INI 配置文件与 JSON 之间双向转换，保留节结构。

用法:
    python ini-json-convert.py config.ini  -o config.json    # INI -> JSON
    python ini-json-convert.py config.json -o config.ini     # JSON -> INI
    python ini-json-convert.py config.ini --to json          # 显式指定方向

示例命令:
    python ini-json-convert.py settings.ini -o settings.json
    python ini-json-convert.py settings.json -o settings.ini

规则:
    - 转换方向按输出文件扩展名推断，可用 --to ini|json 显式指定。
    - 保留节（section）结构；configparser 关闭插值并保留键的大小写。
    - INI 的 [DEFAULT] 节在 JSON 中以 "DEFAULT" 键表示。
    - JSON -> INI 时非字符串值转为字符串（true/false 保留小写，null 转空串）。
    - 不支持嵌套对象/数组作为键值（INI 只有扁平的键值对），遇到会报错。
"""
import argparse
import json
import os
import sys
from configparser import ConfigParser, MissingSectionHeaderError, DuplicateOptionError


def ini_to_obj(path):
    cfg = ConfigParser(interpolation=None, strict=True)
    cfg.optionxform = str  # 保留键大小写
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            cfg.read_file(f)
    except (OSError, MissingSectionHeaderError, DuplicateOptionError,
            ConfigParser.Error) as e:
        print(f"错误: 解析 INI 失败: {e}", file=sys.stderr)
        return None
    data = {}
    defaults = cfg.defaults()
    if defaults:
        data["DEFAULT"] = dict(defaults)
    for section in cfg.sections():
        items = dict(cfg.items(section))
        # configparser 的 items() 会把 [DEFAULT] 的键合并进每个节；
        # 与默认值相同的条目不并入该节（语义不变），只有真正的节内覆盖才保留。
        for k in list(defaults):
            if items.get(k) == defaults.get(k):
                items.pop(k, None)
        data[section] = items
    return data


def obj_to_ini(data, path):
    if not isinstance(data, dict) or not all(
        isinstance(v, dict) for v in data.values()
    ):
        print("错误: JSON 顶层必须是 {节名: {键: 值}} 的两层结构", file=sys.stderr)
        return False
    cfg = ConfigParser(interpolation=None)
    cfg.optionxform = str
    for section, items in data.items():
        if section == "DEFAULT":
            sec = cfg.defaults()
        else:
            if not cfg.has_section(section):
                cfg.add_section(section)
            sec = cfg[section]
        for key, value in items.items():
            if isinstance(value, (dict, list)):
                print(f"错误: 节 {section} 键 {key} 的值是嵌套结构，INI 无法表示",
                      file=sys.stderr)
                return False
            sec[key] = _scalar_to_str(value)
    try:
        with open(path, "w", encoding="utf-8") as f:
            cfg.write(f)
    except OSError as e:
        print(f"错误: 写入 INI 失败: {e}", file=sys.stderr)
        return False
    return True


def _scalar_to_str(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return ""
    return str(value)


def main(argv=None):
    ap = argparse.ArgumentParser(description="INI 与 JSON 双向转换（保留节结构）")
    ap.add_argument("input", help="输入文件（.ini 或 .json）")
    ap.add_argument("-o", "--output", required=True, help="输出文件路径")
    ap.add_argument("--to", choices=("ini", "json"), help="显式指定转换方向（默认按输出扩展名）")
    args = ap.parse_args(argv)

    direction = args.to or ("ini" if args.output.lower().endswith(".ini") else "json")

    if direction == "json":
        data = ini_to_obj(args.input)
        if data is None:
            return 2
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
    else:
        try:
            with open(args.input, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"错误: 读取/解析 JSON 失败: {e}", file=sys.stderr)
            return 2
        if not obj_to_ini(data, args.output):
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
