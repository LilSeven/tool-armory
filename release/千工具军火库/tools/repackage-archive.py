#!/usr/bin/env python3
"""压缩包转格式：在内存中把 zip 内容重新打包为 tar.gz（或反向），全程不落盘解压。

用法:
  python repackage-archive.py input.zip output.tar.gz
  python repackage-archive.py input.tar.gz output.zip

说明:
  - 根据输入/输出扩展名自动判断转换方向 (zip<->tar.gz / tar.bz2 / tar.xz / tar)
  - 所有成员在内存中解压并重新打包，不向磁盘解压任何文件
  - 输出文件直接写到目标路径

示例命令:
  python repackage-archive.py backup.zip backup.tar.gz
  python repackage-archive.py data.tar.gz data.zip
"""

import argparse
import io
import os
import sys
import tarfile
import zipfile


def detect_kind(path: str) -> str:
    """根据扩展名判断压缩包类型，返回 'zip' / 'tar' / '' """
    lower = path.lower()
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".tar")):
        return "tar"
    return ""


def mode_for_output(path: str) -> str:
    lower = path.lower()
    if lower.endswith((".tar.gz", ".tgz")):
        return "w:gz"
    if lower.endswith((".tar.bz2", ".tbz2")):
        return "w:bz2"
    if lower.endswith(".tar.xz"):
        return "w:xz"
    return "w"  # plain tar


def members_of_zip(data: bytes):
    """从 zip 字节流读取全部成员，返回 [(arcname, bytes, mtime)]"""
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            blob = zf.read(info.filename)
            mtime = info.date_time  # tuple
            out.append((info.filename, blob, mtime))
    return out


def members_of_tar(data: bytes):
    """从 tar(可带压缩) 字节流读取全部成员，返回 [(arcname, bytes, mtime)]"""
    out = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            fh = tf.extractfile(member)
            if fh is None:
                continue
            out.append((member.name, fh.read(), member.mtime))
    return out


def write_zip(members, out_path: str) -> None:
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, blob, mtime in members:
            if isinstance(mtime, int):
                # tar 的 Unix 时间戳 -> zip 需要的 (Y,M,D,h,m,s)
                import datetime

                dt = datetime.datetime.fromtimestamp(max(mtime, 315532800))
                mtime = tuple(dt.timetuple())[:6]
            zi = zipfile.ZipInfo(name, date_time=mtime)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, blob)


def write_tar(members, out_path: str, mode: str) -> None:
    with tarfile.open(out_path, mode) as tf:
        for name, blob, mtime in members:
            info = tarfile.TarInfo(name=name)
            info.size = len(blob)
            import time

            info.mtime = mtime if isinstance(mtime, int) else int(
                time.mktime(mtime + (0, 0, -1))
            )
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(blob))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="在内存中把 zip 重新打包为 tar.gz（或反向），不落盘解压"
    )
    ap.add_argument("src", help="源压缩包路径 (.zip / .tar.gz / .tar ...)")
    ap.add_argument("dst", help="目标压缩包路径 (.zip / .tar.gz / ...)")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.src):
        print(f"错误: 源文件不存在: {args.src}", file=sys.stderr)
        return 2
    src_kind = detect_kind(args.src)
    dst_kind = detect_kind(args.dst)
    if src_kind == "" or dst_kind == "":
        print(
            f"错误: 无法识别的压缩包格式 src={args.src} dst={args.dst} "
            "(支持 .zip 与 .tar/.tar.gz/.tar.bz2/.tar.xz)",
            file=sys.stderr,
        )
        return 2
    if src_kind == dst_kind and os.path.abspath(args.src) == os.path.abspath(args.dst):
        print("错误: 源与目标是同一种格式且同一路径", file=sys.stderr)
        return 2

    with open(args.src, "rb") as fh:
        data = fh.read()

    if src_kind == "zip":
        members = members_of_zip(data)
    else:
        members = members_of_tar(data)

    if dst_kind == "zip":
        write_zip(members, args.dst)
    else:
        write_tar(members, args.dst, mode_for_output(args.dst))

    print(f"OK: {len(members)} 个文件 {args.src} -> {args.dst} (内存转换，未落盘解压)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
