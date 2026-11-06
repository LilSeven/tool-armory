#!/usr/bin/env python3
"""批量打包：把一组文件或目录打包为 zip 或 tar.gz 归档。

- 目录输入会递归打包，目录内文件使用该目录内的相对路径（含目录名本身）；
- 支持 glob 排除模式（--exclude），对归档内相对路径及其中任一层名称匹配，
  可多次指定；
- 归档格式按输出扩展名自动判断（.zip -> zip；.tar.gz/.tgz -> tar.gz），也可用
  --format 强制指定。

用法示例：
  python batch-zip.py out.zip mydir extra_file.txt
  python batch-zip.py out.tar.gz mydir --exclude "*.log" --exclude "*/tmp/*"
  python batch-zip.py out.zip mydir --format zip

退出码：0 表示打包成功。
"""
import argparse
import fnmatch
import os
import sys
import tarfile
import zipfile


def detect_format(out_path, forced):
    if forced != "auto":
        return forced
    lower = out_path.lower()
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith((".tar.gz", ".tgz")):
        return "targz"
    print("无法从扩展名判断格式（%s），请用 --format 指定。" % out_path, file=sys.stderr)
    sys.exit(2)


def is_excluded(arcname, patterns):
    """arcname 使用 / 分隔；模式可匹配完整相对路径或其中任意一层。"""
    norm = arcname.replace(os.sep, "/")
    for pat in patterns:
        if fnmatch.fnmatch(norm, pat):
            return True
        if any(fnmatch.fnmatch(part, pat) for part in norm.split("/")):
            return True
    return False


def collect(inputs, excludes):
    """产出 (磁盘路径, 归档内路径) 对；归档内路径以 / 分隔。"""
    for p in inputs:
        if os.path.isfile(p):
            if not is_excluded(os.path.basename(p), excludes):
                yield p, os.path.basename(p).replace(os.sep, "/")
        elif os.path.isdir(p):
            top = os.path.basename(os.path.normpath(p)) or p
            for root, _dirs, files in os.walk(p):
                for name in sorted(files):
                    fp = os.path.join(root, name)
                    arc = (top + "/" + os.path.relpath(fp, p).replace(os.sep, "/"))
                    if not is_excluded(arc, excludes):
                        yield fp, arc
        else:
            print("警告：路径不存在，跳过：%s" % p, file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="把文件/目录打包为 zip 或 tar.gz")
    ap.add_argument("output", help="输出归档路径（.zip / .tar.gz / .tgz）")
    ap.add_argument("inputs", nargs="+", metavar="PATH", help="要打包的文件或目录")
    ap.add_argument("-e", "--exclude", action="append", default=[],
                    metavar="GLOB", help="排除模式，可多次指定")
    ap.add_argument("-f", "--format", choices=["auto", "zip", "targz"], default="auto",
                    help="归档格式（默认按扩展名自动判断）")
    args = ap.parse_args(argv)

    fmt = detect_format(args.output, args.format)
    items = list(collect(args.inputs, args.exclude))
    if not items:
        print("没有可打包的文件（可能全部被排除）。", file=sys.stderr)
        return 1

    if fmt == "zip":
        with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp, arc in items:
                zf.write(fp, arc)
    else:
        with tarfile.open(args.output, "w:gz") as tf:
            for fp, arc in items:
                tf.add(fp, arcname=arc, recursive=False)

    size = os.path.getsize(args.output)
    print("已打包 %d 个文件到 %s（%s，%.1f KB）" % (len(items), args.output, fmt, size / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
