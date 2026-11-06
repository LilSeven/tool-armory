# -*- coding: utf-8 -*-
"""自定义映射转换：加载用户 CSV 映射表做单字/词级替换转换，词优先于字。

CSV 格式两列：第一列原文，第二列替换结果。既支持单字（发,髮）
也支持多字词条（发展,發展）。替换时按最长词条优先（词优先于字），
适合人工维护的自定义词库；可直接使用 s2t-map-export 导出的 CSV
再增删改。方向可用 -d t2s 反转。

示例命令：
    python s2t-custom-map.py input.txt -m mymap.csv
    python s2t-custom-map.py -m mymap.csv -d t2s -o out.txt < in.txt
    type in.txt | python s2t-custom-map.py -m mymap.csv
"""
import argparse
import csv
import sys

HEADER_KEYS = {"简体", "繁体", "from", "to", "源", "目标", "src", "dst",
               "原文", "译文", "简", "繁"}


def read_bytes(path):
    if path == "-":
        return sys.stdin.buffer.read()
    with open(path, "rb") as fh:
        return fh.read()


def decode_smart(data):
    """依次尝试 utf-8-sig / gb18030，最后带替换符兜底。"""
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def load_map(path, direction="s2t"):
    """读 CSV，返回 (mapping, warnings)。冲突时后行覆盖前行并告警。"""
    mapping = {}
    warnings = []
    text = decode_smart(read_bytes(path))
    reader = csv.reader(text.splitlines())
    for lineno, row in enumerate(reader, 1):
        if not row or not any(cell.strip() for cell in row):
            continue
        key = row[0].strip()
        val = row[1].strip() if len(row) > 1 else ""
        if not key or not val:
            warnings.append("第%d行：缺第二列，跳过 %r" % (lineno, row))
            continue
        if key in HEADER_KEYS and val in HEADER_KEYS:
            continue  # 表头
        if key.startswith("#"):
            continue  # 注释行
        # 键值相同（如 皇后,皇后）是合法的“钉死”词条，
        # 用于顶住更短的字符级规则，不得跳过。
        if key in mapping and mapping[key] != val:
            warnings.append("第%d行：键 %r 映射冲突，%r 覆盖 %r"
                            % (lineno, key, val, mapping[key]))
        mapping[key] = val
    if direction == "t2s":
        rev = {}
        for k, v in mapping.items():
            if v in rev and rev[v] != k:
                warnings.append("反转冲突：值 %r 对应多个键，保留 %r"
                                % (v, rev[v]))
                continue
            rev[v] = k
        mapping = rev
    return mapping, warnings


def convert(text, mapping, stats=None, used=None):
    """最长匹配优先的扫描替换：词（多字键）优先于字（单字键）。"""
    if stats is None:
        stats = {}
    lengths = sorted({len(k) for k in mapping}, reverse=True)
    if not lengths:
        return text
    maxlen = lengths[0]
    out = []
    i, n = 0, len(text)
    while i < n:
        hit = None
        for ln in lengths:
            if ln > n - i:
                continue
            seg = text[i:i + ln]
            if seg in mapping:
                hit = (seg, mapping[seg], ln)
                break
        if hit:
            src, dst, ln = hit
            out.append(dst)
            if ln > 1:
                stats["词"] = stats.get("词", 0) + 1
            else:
                stats["字"] = stats.get("字", 0) + 1
            if used is not None:
                used[src] = used.get(src, 0) + 1
            i += ln
        else:
            out.append(text[i])
            stats["未映射"] = stats.get("未映射", 0) + 1
            i += 1
    return "".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="按用户 CSV 映射表做词优先于字的替换转换")
    parser.add_argument("inputs", nargs="*", default=["-"],
                        help="输入文本文件，缺省或 - 读 stdin")
    parser.add_argument("-m", "--map", required=True,
                        help="CSV 映射表路径（两列：原文,替换）")
    parser.add_argument("-d", "--direction", choices=["s2t", "t2s"],
                        default="s2t", help="转换方向，t2s 反转映射表")
    parser.add_argument("-o", "--output", default="-",
                        help="输出文件，缺省 stdout")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="列出实际用到的映射及次数")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace",
                               newline="")

    try:
        mapping, warnings = load_map(args.map, args.direction)
    except OSError as exc:
        print("错误：无法读取映射表 %s：%s" % (args.map, exc),
              file=sys.stderr)
        return 2
    for w in warnings:
        print("警告：" + w, file=sys.stderr)
    if not mapping:
        print("错误：映射表为空：%s" % args.map, file=sys.stderr)
        return 2

    stats = {}
    used = {} if args.verbose else None
    pieces = []
    for path in args.inputs:
        text = decode_smart(read_bytes(path))
        pieces.append(convert(text, mapping, stats, used))
    result = "".join(pieces)

    if args.output == "-":
        sys.stdout.write(result)
    else:
        with open(args.output, "w", encoding="utf-8", newline="") as fh:
            fh.write(result)

    print("统计：词条替换 %d 次，单字替换 %d 次，未映射字符 %d 个"
          % (stats.get("词", 0), stats.get("字", 0),
             stats.get("未映射", 0)), file=sys.stderr)
    if used:
        for k in sorted(used, key=lambda x: (-len(x), x)):
            print("  用到：%s -> %s ×%d" % (k, mapping[k], used[k]),
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
