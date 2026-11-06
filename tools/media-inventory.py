#!/usr/bin/env python3
r"""媒体文件清单（media-inventory）—— 按类别统计媒体库概况。

递归扫描目录，按扩展名把文件归入 图片/音频/视频/文档/其他 五类，统计
每类的文件数与总大小，生成一份媒体库概况。--detail 可按类别列出文件
明细（按大小从大到小），--top 限制每类列出的条数。

用法:
    python media-inventory.py <目录> [选项]

示例:
    python media-inventory.py D:\media
    python media-inventory.py D:\media --detail --top 10

选项:
    --detail    额外列出每个类别的文件明细
    --top N     --detail 时每类最多列出 N 个，默认 20（0 表示不限）

退出码: 0 正常（包括空目录）；2 参数错误或目录不存在。
"""

import argparse
import os
import sys

CATEGORY_EXTS = {
    "图片": (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif",
             ".tiff", ".heic", ".heif", ".svg", ".ico", ".avif", ".raw"),
    "音频": (".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma",
             ".opus", ".aiff", ".ape", ".mid", ".midi"),
    "视频": (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
             ".m4v", ".mpg", ".mpeg", ".ts", ".3gp", ".rmvb", ".rm"),
    "文档": (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
             ".txt", ".md", ".csv", ".epub", ".rtf", ".odt", ".ods",
             ".odp", ".wps"),
}
EXT_CATEGORY = {ext: cat for cat, exts in CATEGORY_EXTS.items() for ext in exts}
ORDER = ("图片", "音频", "视频", "文档", "其他")


def human_size(num):
    """字节数 → 人类可读大小，如 49B、200.0KB、1.5MB。"""
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return "%dB" % num if unit == "B" else "%.1f%s" % (num, unit)
        num /= 1024.0


def disp_width(text):
    """估算终端显示宽度：CJK 等全角字符按 2 计。"""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in text)


def fmt_row(cells, widths, right_cols):
    parts = []
    for i, (text, width) in enumerate(zip(cells, widths)):
        pad = " " * (width - disp_width(text))
        parts.append((pad + text) if i in right_cols else (text + pad))
    return "  ".join(parts).rstrip()


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="按 音频/视频/图片/文档 分类统计文件数与总大小，"
                    "生成媒体库概况。")
    parser.add_argument("root", help="要扫描的媒体库目录")
    parser.add_argument("--detail", action="store_true",
                        help="额外列出每个类别的文件明细")
    parser.add_argument("--top", type=int, default=20, metavar="N",
                        help="--detail 时每类最多列出 N 个，默认 20，0 不限")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.root):
        parser.error("目录不存在或不是目录: %s" % args.root)

    counts = {cat: 0 for cat in ORDER}
    bytes_total = {cat: 0 for cat in ORDER}
    files = {cat: [] for cat in ORDER}
    for dirpath, dirnames, filenames in os.walk(args.root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            try:
                size = os.lstat(path).st_size
            except OSError:
                continue
            cat = EXT_CATEGORY.get(os.path.splitext(name)[1].lower(), "其他")
            counts[cat] += 1
            bytes_total[cat] += size
            files[cat].append((path, size))

    total_n = sum(counts.values())
    total_b = sum(bytes_total.values())
    print("媒体库概况: %s" % args.root)
    if total_n == 0:
        print("未发现任何文件。")
        return 0

    header = ("类别", "文件数", "总大小")
    body = [(cat, str(counts[cat]), human_size(bytes_total[cat]))
            for cat in ORDER if counts[cat]]
    total_row = ("合计", str(total_n), human_size(total_b))
    widths = [
        max(disp_width(r[i]) for r in [header] + body + [total_row])
        for i in range(3)
    ]
    print(fmt_row(header, widths, right_cols={1, 2}))
    for row in body:
        print(fmt_row(row, widths, right_cols={1, 2}))
    print(fmt_row(total_row, widths, right_cols={1, 2}))

    if args.detail:
        for cat in ORDER:
            items = files[cat]
            if not items:
                continue
            items.sort(key=lambda r: (-r[1], r[0]))
            print("")
            print("== %s：%d 个文件，%s =="
                  % (cat, len(items), human_size(bytes_total[cat])))
            shown = items if args.top <= 0 else items[:args.top]
            for path, size in shown:
                print("%10s  %s" % (human_size(size), path))
            if 0 < args.top < len(items):
                print("... 其余 %d 个未列出" % (len(items) - args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
