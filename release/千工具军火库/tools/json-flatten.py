#!/usr/bin/env python3
"""JSON 展平还原器：嵌套 JSON 与点路径扁平键值对互相转换，便于填表或 diff。

展平:  {"a": {"b": [1, 2]}}  ->  {"a.b.0": 1, "a.b.1": 2}
还原:  {"a.b.0": 1, "a.b.1": 2}  ->  {"a": {"b": [1, 2]}}
数组索引还原时若键名不连续，按数值排序后重排。

用法:
    python json-flatten.py flatten input.json            # 展平，输出 JSON 对象
    python json-flatten.py unflatten flat.json           # 还原为嵌套 JSON
    python json-flatten.py flatten input.json -o out.json
    cat nested.json | python json-flatten.py flatten -

示例命令:
    python json-flatten.py flatten config.json
    python json-flatten.py unflatten flat.json --sep "__"
"""
import argparse
import json
import sys


def flatten(obj, prefix="", sep="."):
    """把嵌套 dict/list 展平为点路径键值对。"""
    flat = {}
    if isinstance(obj, dict):
        items = obj.items()
    elif isinstance(obj, list):
        items = [(str(i), v) for i, v in enumerate(obj)]
    else:
        return {prefix: obj} if prefix else {}
    if not items and prefix:
        flat[prefix] = {} if isinstance(obj, dict) else []
        return flat
    for k, v in items:
        key = f"{prefix}{sep}{k}" if prefix else str(k)
        if isinstance(v, (dict, list)):
            flat.update(flatten(v, key, sep))
        else:
            flat[key] = v
    return flat


def unflatten(flat, sep="."):
    """把点路径扁平键值对还原为嵌套 dict/list。"""
    root = {}
    for key in sorted(flat, key=lambda k: (k.split(sep)[0], len(k.split(sep)), k)):
        parts = key.split(sep)
        cur = root
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            # 判断下一层是数组还是对象
            nxt_is_index = (not last and parts[i + 1].isdigit())
            if part.isdigit():
                idx = int(part)
                while isinstance(cur, list) and len(cur) <= idx:
                    cur.append({} if not nxt_is_index or last else [])
                while isinstance(cur, dict) and idx not in cur:
                    cur[idx] = [] if nxt_is_index and not last else (None if last else {})
                target = cur[idx] if isinstance(cur, (list, dict)) else None
                if last:
                    cur[idx] = flat[key]
                else:
                    if not isinstance(target, (dict, list)):
                        cur[idx] = [] if nxt_is_index else {}
                    cur = cur[idx]
            else:
                if last:
                    cur[part] = flat[key]
                else:
                    if not isinstance(cur.get(part), (dict, list)):
                        cur[part] = [] if nxt_is_index else {}
                    cur = cur[part]
    return root


def main(argv=None):
    ap = argparse.ArgumentParser(description="嵌套 JSON 与点路径扁平键值对互相转换")
    ap.add_argument("mode", choices=["flatten", "unflatten"], help="flatten=展平, unflatten=还原")
    ap.add_argument("input", help="JSON 文件路径，'-' 表示 stdin")
    ap.add_argument("-o", "--output", help="输出文件路径，缺省 stdout")
    ap.add_argument("--sep", default=".", help="路径分隔符 (默认 '.')")
    ap.add_argument("--indent", type=int, default=2, help="输出缩进 (默认 2)")
    args = ap.parse_args(argv)

    src = sys.stdin if args.input == "-" else open(args.input, encoding="utf-8")
    try:
        data = json.load(src)
    except json.JSONDecodeError as e:
        print(f"json-flatten: 输入 JSON 解析失败: {e}", file=sys.stderr)
        return 1
    finally:
        if args.input != "-":
            src.close()

    try:
        result = flatten(data, sep=args.sep) if args.mode == "flatten" else unflatten(data, sep=args.sep)
    except Exception as e:  # 还原时结构冲突等
        print(f"json-flatten: 转换失败: {e}", file=sys.stderr)
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
