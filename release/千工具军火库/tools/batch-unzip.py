#!/usr/bin/env python3
"""批量解包：把 zip / tar（.gz/.bz2/.xz）归档解压到目标目录。

- zip 条目文件名编码：带 UTF-8 标志的按 UTF-8 处理；未带标志的按
  UTF-8 -> GBK -> cp437 顺序尝试还原（兼容 Windows 中文系统打包的 zip）；
- 安全：拦截路径穿越条目（绝对路径、含 `..`、盘符等），跳过并告警，不写出目标目录之外。

用法示例：
  python batch-unzip.py archive.zip -o outdir
  python batch-unzip.py archive.tar.gz -o outdir

退出码：0 = 全部解出；1 = 存在被拦截或解压失败的条目；2 = 归档无法打开。
"""
import argparse
import os
import sys
import tarfile
import zipfile


def safe_relpath(arcname):
    """把归档内路径规范化为安全相对路径；不安全（穿越/绝对路径）时返回 None。"""
    name = arcname.replace("\\", "/")
    if name.startswith("/") or (len(name) >= 2 and name[1] == ":"):
        return None
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." or ":" in p for p in parts):
        return None
    return os.path.join(*parts)


def decode_zip_name(info):
    """还原 zip 条目文件名：未带 UTF-8 标志时按 UTF-8 -> GBK -> cp437 尝试。"""
    name = info.filename
    if not name or (info.flag_bits & 0x800):
        return name
    try:
        raw = name.encode("cp437")
    except UnicodeError:
        return name
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return name


def extract_zip(zf, dest):
    extracted = skipped = 0
    for info in zf.infolist():
        arc = decode_zip_name(info)
        rel = safe_relpath(arc)
        if rel is None:
            print("已拦截不安全条目：%r" % info.filename, file=sys.stderr)
            skipped += 1
            continue
        target = os.path.join(dest, rel)
        if info.is_dir() or arc.endswith("/"):
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target) or dest, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as out:
            for chunk in iter(lambda: src.read(1 << 20), b""):
                out.write(chunk)
        extracted += 1
    return extracted, skipped


def extract_tar(tf, dest):
    extracted = skipped = 0
    for member in tf.getmembers():
        rel = safe_relpath(member.name)
        if rel is None:
            print("已拦截不安全条目：%r" % member.name, file=sys.stderr)
            skipped += 1
            continue
        if not (member.isreg() or member.isdir()):
            print("已跳过非常规条目（链接/设备等）：%r" % member.name, file=sys.stderr)
            skipped += 1
            continue
        target = os.path.join(dest, rel)
        if member.isdir():
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target) or dest, exist_ok=True)
        with tf.extractfile(member) as src, open(target, "wb") as out:
            for chunk in iter(lambda: src.read(1 << 20), b""):
                out.write(chunk)
        extracted += 1
    return extracted, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description="解压 zip/tar 归档（含安全防护）")
    ap.add_argument("archive", help="归档文件（.zip / .tar / .tar.gz / .tgz 等）")
    ap.add_argument("-o", "--output", default="./extracted",
                    help="目标目录（默认 ./extracted）")
    args = ap.parse_args(argv)

    dest = os.path.abspath(args.output)
    os.makedirs(dest, exist_ok=True)

    try:
        if zipfile.is_zipfile(args.archive):
            with zipfile.ZipFile(args.archive) as zf:
                extracted, skipped = extract_zip(zf, dest)
        elif tarfile.is_tarfile(args.archive):
            with tarfile.open(args.archive, "r:*") as tf:
                extracted, skipped = extract_tar(tf, dest)
        else:
            print("无法识别的归档格式：%s" % args.archive, file=sys.stderr)
            return 2
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as e:
        print("解压失败：%s" % e, file=sys.stderr)
        return 2

    print("解压完成：成功 %d 个条目 -> %s；拦截/跳过 %d 个。" % (extracted, dest, skipped))
    return 0 if skipped == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
