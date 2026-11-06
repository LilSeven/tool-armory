#!/usr/bin/env python3
"""prop2env.py -- 把 Java .properties 文件转成 dotenv 风格的 KEY=VALUE 格式。

处理点：等号/冒号分隔符、点号键名转下划线（可选）、大写化键名（可选）、
行尾反斜杠续行、注释行（# 与 !）跳过、值两侧引号去除、\t \n 等转义还原。

用法:
    python prop2env.py app.properties -o .env
    python prop2env.py app.properties --upper --dots
    python prop2env.py app.properties --export

参数:
    INPUT            输入 .properties 文件；"-" 读 stdin
    -o, --output     输出文件，缺省 stdout
    --upper          键名转大写（dotenv 常用）
    --dots           键名中的点号转为下划线（如 db.host -> DB_HOST）
    --export         每行前加 "export "，便于 shell source
    --keep-quote     保留值两侧的引号（默认剥掉）
    -e, --encoding   文件编码，默认 utf-8

示例:
    python prop2env.py config.properties --upper --dots -o .env
    python prop2env.py config.properties --export | source /dev/stdin
"""
import argparse
import sys


ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "f": "\f", "\\": "\\", " ": " "}


def unescape(text):
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt in ESCAPES:
                out.append(ESCAPES[nxt])
                i += 2
                continue
            if nxt == "u" and i + 5 < len(text):
                try:
                    out.append(chr(int(text[i + 2:i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    pass
        out.append(ch)
        i += 1
    return "".join(out)


def strip_quotes(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def parse_lines(raw_lines):
    """处理续行，返回逻辑行列表（保留原始顺序）。"""
    logical = []
    buf = ""
    continued = False
    for line in raw_lines:
        if continued:
            buf += line.lstrip()
            continued = False
        else:
            buf = line
        # 行尾奇数个反斜杠 => 续行
        n_back = 0
        j = len(buf) - 1
        while j >= 0 and buf[j] == "\\":
            n_back += 1
            j -= 1
        if n_back % 2 == 1:
            buf = buf[:-1]  # 去掉续行反斜杠，待下一行合并
            continued = True
            continue
        logical.append(buf)
        buf = ""
    if continued and buf:
        logical.append(buf)
    return logical


def transform_key(key, upper=False, dots=False):
    key = key.strip()
    if dots:
        key = key.replace(".", "_")
    if upper:
        key = key.upper()
    return key


def main():
    ap = argparse.ArgumentParser(
        description="把 Java .properties 转 dotenv 风格 KEY=VALUE")
    ap.add_argument("input", help="输入 .properties 文件，或 '-' 表示 stdin")
    ap.add_argument("-o", "--output", help="输出文件，缺省 stdout")
    ap.add_argument("--upper", action="store_true", help="键名转大写")
    ap.add_argument("--dots", action="store_true",
                    help="键名中的点号转下划线")
    ap.add_argument("--export", action="store_true",
                    help='每行加 "export " 前缀')
    ap.add_argument("--keep-quote", action="store_true", help="保留值引号")
    ap.add_argument("-e", "--encoding", default="utf-8")
    args = ap.parse_args()

    if args.input == "-":
        text = sys.stdin.buffer.read().decode(args.encoding)
    else:
        try:
            with open(args.input, "r", encoding=args.encoding) as f:
                text = f.read()
        except OSError as exc:
            raise SystemExit(f"错误: 无法读取 {args.input}: {exc}")

    pairs = []
    seen = set()
    n_comment = 0
    n_blank = 0
    for line in parse_lines(text.splitlines()):
        stripped = line.strip()
        if not stripped:
            n_blank += 1
            continue
        if stripped[0] in "#!":
            n_comment += 1
            continue
        # 找到第一个未转义的分隔符 = 或 :
        cut = None
        i = 0
        while i < len(stripped):
            ch = stripped[i]
            if ch == "\\":
                i += 2
                continue
            if ch in ("=", ":"):
                cut = i
                break
            i += 1
        if cut is None:
            key, value = stripped, ""
        else:
            key = stripped[:cut]
            value = stripped[cut + 1:].lstrip()
        key_out = transform_key(key, args.upper, args.dots)
        if not key_out:
            continue
        value = unescape(value)
        if not args.keep_quote:
            value = strip_quotes(value)
        if key_out in seen:
            continue  # 后出现的 properties 规则覆盖前面的；这里取首个避免重复
        seen.add(key_out)
        pairs.append((key_out, value))

    out_lines = ["# 由 prop2env.py 生成"]
    for k, v in pairs:
        # 真实换行会破坏 KEY=VALUE 单行格式，转义回 \n / \r（反斜杠保持原样）
        v = v.replace("\n", "\\n").replace("\r", "\\r")
        prefix = "export " if args.export else ""
        out_lines.append(f"{prefix}{k}={v}")
    out_text = "\n".join(out_lines) + "\n"

    if args.output:
        with open(args.output, "w", encoding=args.encoding, newline="") as f:
            f.write(out_text)
        print(f"已写入 {args.output}（{len(pairs)} 个键，"
              f"跳过 {n_comment} 行注释 / {n_blank} 行空行）", file=sys.stderr)
    else:
        sys.stdout.write(out_text)


if __name__ == "__main__":
    main()
