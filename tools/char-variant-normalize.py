# -*- coding: utf-8 -*-
"""异体字标准化：把異體字/舊字形按 Unicode 标准化到目标字形。

内置一组无争议的异体映射（戸/戶→户、峯→峰、眞→真、羣→群、
畧→略、內→内、祕→秘、溫→温、鑑/鑒→鉴 等），逐字替换到通行
字形；另有 --unify-zhezhu 把 著/着 统一到指定字形（无分词，
纯字形统一，请自行斟酌），--nfkc 追加 Unicode NFKC 规范化
（兼收兼容表意文字），--table 可加载额外 CSV(from,to) 扩充。

示例命令：
    python char-variant-normalize.py input.txt
    python char-variant-normalize.py input.txt --nfkc -o out.txt
    python char-variant-normalize.py input.txt --unify-zhezhu zhu
    python char-variant-normalize.py --list
"""
import argparse
import csv
import sys

# 异体字/旧字形 -> 通行字形（简繁两岸通行的目标字形）
VARIANT_TABLE = [
    ("戸", "户"), ("戶", "户"),      # 旧字形/日字形户
    ("峯", "峰"),                    # 峯->峰
    ("羣", "群"), ("畧", "略"),
    ("眞", "真"), ("兪", "俞"),
    ("塡", "填"), ("唸", "念"),
    ("歎", "叹"), ("遙", "遥"),
    ("內", "内"), ("祕", "秘"),
    ("溫", "温"), ("煙", "烟"),
    ("髙", "高"), ("兎", "兔"),
    ("吳", "吴"), ("竝", "并"),
    ("毘", "毗"), ("恆", "恒"),
    ("鑑", "鉴"), ("鑒", "鉴"),
    ("廻", "回"), ("迴", "回"),
]

ZHEZHU = ("著", "着")  # --unify-zhezhu 的操作对象


def load_extra(path):
    """加载额外 CSV 映射(from,to)，仅接受单字符。"""
    extra = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        for lineno, row in enumerate(csv.reader(fh), 1):
            cells = [c.strip() for c in row]
            if not cells or not cells[0] or cells[0].startswith("#"):
                continue
            if len(cells) < 2 or not cells[1]:
                print("警告：第%d行缺列，跳过 %r" % (lineno, row),
                      file=sys.stderr)
                continue
            src, dst = cells[0], cells[1]
            if len(src) != 1 or len(dst) != 1:
                print("警告：第%d行需单字符，跳过 %r" % (lineno, row),
                      file=sys.stderr)
                continue
            extra.append((src, dst))
    return extra


def normalize(text, table, stats):
    trans = {}
    for src, dst in table:
        trans[ord(src)] = dst
    out = []
    for ch in text:
        if ord(ch) in trans:
            dst = trans[ord(ch)]
            stats[src_key(ch, dst)] = stats.get(src_key(ch, dst), 0) + 1
            out.append(dst)
        else:
            out.append(ch)
    return "".join(out)


def src_key(src, dst):
    return "%s->%s" % (src, dst)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="把异体字/旧字形标准化到目标字形")
    parser.add_argument("inputs", nargs="*", default=["-"],
                        help="输入文本文件，缺省或 - 读 stdin")
    parser.add_argument("-o", "--output", default="-",
                        help="输出文件，缺省 stdout")
    parser.add_argument("--table", default=None,
                        help="额外异体映射 CSV（两列 from,to，单字符）")
    parser.add_argument("--nfkc", action="store_true",
                        help="在异体替换后追加 NFKC 规范化")
    parser.add_argument("--unify-zhezhu", choices=["none", "zhu", "zhe"],
                        default="none",
                        help="著/着 字形统一：zhu=统一到著，zhe=统一到着")
    parser.add_argument("--list", action="store_true",
                        help="列出内置异体表后退出")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace",
                               newline="")

    table = list(VARIANT_TABLE)
    if args.unify_zhezhu != "none":
        target = "著" if args.unify_zhezhu == "zhu" else "着"
        for ch in ZHEZHU:
            if ch != target:
                table.append((ch, target))
        if target == "着":
            print("注意：统一到着 为纯字形统一（著名→着名这类词请人工复核）",
                  file=sys.stderr)
    if args.table:
        try:
            table.extend(load_extra(args.table))
        except OSError as exc:
            print("错误：无法读取扩充表 %s：%s" % (args.table, exc),
                  file=sys.stderr)
            return 2

    if args.list:
        for src, dst in table:
            print("%s U+%04X -> %s U+%04X"
                  % (src, ord(src), dst, ord(dst)))
        return 0

    stats = {}
    pieces = []
    for path in args.inputs:
        if path == "-":
            data = sys.stdin.buffer.read()
        else:
            with open(path, "rb") as fh:
                data = fh.read()
        text = None
        for enc in ("utf-8-sig", "gb18030"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = data.decode("utf-8", errors="replace")
        text = normalize(text, table, stats)
        if args.nfkc:
            import unicodedata
            text = unicodedata.normalize("NFKC", text)
        pieces.append(text)
    result = "".join(pieces)

    if args.output == "-":
        sys.stdout.write(result)
    else:
        with open(args.output, "w", encoding="utf-8", newline="") as fh:
            fh.write(result)

    if stats:
        print("统计：" + "，".join("%s×%d" % (k, v)
                                   for k, v in sorted(stats.items())),
              file=sys.stderr)
    else:
        print("统计：未发现内置异体字", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
