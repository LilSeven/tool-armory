#!/usr/bin/env python3
"""批量校验和生成：为一批文件/目录生成 sha256sum 风格的校验清单（可选 md5/sha1）。

输出格式与 GNU coreutils 的 sha256sum/md5sum 兼容（文本模式）：
  <十六进制摘要>  <文件路径>
（摘要后跟两个空格，随后是路径），可用 `sha256sum -c` 或本目录的 verify-manifest.py 验证。

用法示例：
  python checksum-manifest.py -o manifest.sha256 file1.txt dir/
  python checksum-manifest.py --algorithm md5 -o manifest.md5 dir/
  python checksum-manifest.py dir/            # 不指定 -o 时打印到标准输出

退出码：0 表示全部生成成功。
"""
import argparse
import hashlib
import os
import sys

ALGORITHMS = ("sha256", "md5", "sha1")
CHUNK = 1 << 20


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for name in sorted(files):
                    yield os.path.join(root, name)
        else:
            print("警告：路径不存在，跳过：%s" % p, file=sys.stderr)


def digest_file(path, algo):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成 sha256sum 风格校验清单")
    ap.add_argument("paths", nargs="+", metavar="PATH", help="要计算的文件或目录")
    ap.add_argument("-a", "--algorithm", choices=ALGORITHMS, default="sha256",
                    help="哈希算法（默认 sha256）")
    ap.add_argument("-o", "--output", help="清单输出文件（默认打印到标准输出）")
    args = ap.parse_args(argv)

    lines = []
    for fp in iter_files(args.paths):
        try:
            lines.append("%s  %s" % (digest_file(fp, args.algorithm), fp))
        except OSError as e:
            print("跳过无法读取的文件：%s（%s）" % (fp, e), file=sys.stderr)

    if not lines:
        print("没有可处理的文件。", file=sys.stderr)
        return 1

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        print("已写入 %d 条记录到 %s" % (len(lines), args.output))
    else:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
