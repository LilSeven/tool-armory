#!/usr/bin/env python3
"""img-sort-by-date —— 输出按 yyyy/yyyy-mm 目录归置照片的 mv 命令清单（默认不执行）。

按 EXIF 拍摄时间（无则可用 --mtime 回退到文件修改时间）为每张照片计算
目标目录 yyyy/yyyy-mm（默认在照片所在目录就地归置，或用 --dest 指定别的
目标根目录）。dry-run 模式向 stdout 打印可直接粘贴到 Git Bash 等 POSIX
shell 执行的命令清单：先一条 mkdir -p，再每张照片一条
    mv '源文件' '目标/yyyy/yyyy-mm/'
加 -x/--exec 时改用 shutil.move 实际完成移动。只用 Python 标准库。

用法:
    python img-sort-by-date.py <文件或目录>... [-r] [--dest 目录] [--mtime] [-x]

示例命令:
    python img-sort-by-date.py D:/photos                   # 预览 mv 清单
    python img-sort-by-date.py D:/photos -x                # 实际归置
    python img-sort-by-date.py D:/photos --dest D:/sorted  # 归置到别的目录树

说明:
    * 跳过说明与汇总打印到 stderr，stdout 只有命令清单，可直接
      `python img-sort-by-date.py 照片目录 | bash` 执行。
    * 递归扫描时自动跳过名字形如 2024 / 2024-01 的目录（本工具的输出
      目录），里面的文件按"已归置"计，避免重跑时套娃。
"""

import argparse
import datetime
import os
import re
import shlex
import shutil
import struct
import sys

DATE_DIR_RE = re.compile(r"^\d{4}(-\d{2})?$")

# ---------------------------------------------------------------------------
# 极简 EXIF 解析（仅标准库，覆盖本工具用到的标签）
# ---------------------------------------------------------------------------

_TIFF_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1,
               7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}


def _tiff_value(typ, num, raw, endian):
    """按 TIFF 字段类型解码原始字节。"""
    if typ == 2:  # ASCII
        return raw.split(b"\x00", 1)[0].decode("ascii", "replace").strip()
    try:
        if typ in (1, 6, 7):
            return raw
        if typ == 3:
            return list(struct.unpack(endian + "%dH" % num, raw))
        if typ == 8:
            return list(struct.unpack(endian + "%dh" % num, raw))
        if typ == 4:
            return list(struct.unpack(endian + "%dI" % num, raw))
        if typ == 9:
            return list(struct.unpack(endian + "%di" % num, raw))
        if typ == 5:
            vals = struct.unpack(endian + "%dI" % (2 * num), raw)
            return [vals[i] / vals[i + 1] if vals[i + 1] else None
                    for i in range(0, len(vals), 2)]
        if typ == 10:
            vals = struct.unpack(endian + "%di" % (2 * num), raw)
            return [vals[i] / vals[i + 1] if vals[i + 1] else None
                    for i in range(0, len(vals), 2)]
    except struct.error:
        return None
    return raw


def _tiff_parse(blob):
    """解析 TIFF 结构（JPEG 的 Exif APP1 内容，或 TIFF 文件本体）。"""
    if len(blob) < 8:
        return {}
    endian = {b"II": "<", b"MM": ">"}.get(blob[:2])
    if endian is None:
        return {}

    def unpack(fmt, off):
        return struct.unpack_from(endian + fmt, blob, off)

    try:
        ifd0 = unpack("I", 4)[0]
    except struct.error:
        return {}

    tags = {}
    visited = set()

    def read_ifd(off):
        if off in visited or off < 8 or off + 2 > len(blob):
            return
        visited.add(off)
        try:
            count = unpack("H", off)[0]
        except struct.error:
            return
        for _ in range(count):
            p = off + 2 + 12 * _
            if p + 12 > len(blob):
                return
            tag, typ, num = unpack("HHI", p)
            size = _TIFF_SIZES.get(typ, 1) * num
            if size <= 4:
                raw = blob[p + 8:p + 8 + size]
            else:
                try:
                    voff = unpack("I", p + 8)[0]
                except struct.error:
                    return
                if voff >= len(blob):
                    tags[tag] = None
                    continue
                raw = blob[voff:voff + size]
            tags[tag] = _tiff_value(typ, num, raw, endian)
        try:
            nxt = unpack("I", off + 2 + 12 * count)[0]
        except struct.error:
            return
        if nxt:
            read_ifd(nxt)

    read_ifd(ifd0)
    sub = tags.get(0x8769)  # ExifIFDPointer
    if isinstance(sub, list) and sub and isinstance(sub[0], int):
        read_ifd(sub[0])
    return tags


def jpeg_exif(data):
    """从 JPEG 字节流中提取 EXIF 标签字典；没有返回 {}。"""
    if data[:2] != b"\xff\xd8":
        return {}
    n = len(data)
    i = 2
    while i + 4 <= n:
        if data[i] != 0xFF:
            return {}
        marker = data[i + 1]
        if marker == 0xFF:  # 连续填充字节
            i += 1
            continue
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker in (0xD9, 0xDA):  # EOI/SOS 之后不会再有 EXIF
            break
        seg_len = struct.unpack_from(">H", data, i + 2)[0]
        if seg_len < 2:
            return {}
        if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\x00\x00":
            return _tiff_parse(data[i + 10:i + 2 + seg_len])
        i += 2 + seg_len
    return {}


def read_exif(path, limit=4 * 1024 * 1024):
    """读取文件的 EXIF（JPEG APP1 或 TIFF 本体），无则返回 {}。"""
    try:
        with open(path, "rb") as f:
            head = f.read(limit)
    except OSError:
        return {}
    if head[:2] == b"\xff\xd8":
        return jpeg_exif(head)
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return _tiff_parse(head)
    return {}


def exif_datetime(tags):
    """拍摄时间：DateTimeOriginal > DateTimeDigitized > DateTime。"""
    for tag in (0x9003, 0x9004, 0x0132):
        val = tags.get(tag)
        if isinstance(val, str) and val.strip():
            for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.datetime.strptime(val.strip(), fmt)
                except ValueError:
                    pass
    return None


def is_supported_image(path):
    """按文件头签名判断是否为本工具支持的图片容器。"""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
    except OSError:
        return False
    return (head[:2] == b"\xff\xd8"
            or head[:4] in (b"II*\x00", b"MM\x00*")
            or head[:8] == b"\x89PNG\r\n\x1a\n"
            or head[:6] in (b"GIF87a", b"GIF89a")
            or head[:2] == b"BM")


def _yield_date_tree(dd):
    """把日期目录（2024 / 2024-01）里的文件按"已归置"逐个产出。"""
    try:
        names = sorted(os.listdir(dd))
    except OSError:
        return
    for name in names:
        fp2 = os.path.join(dd, name)
        if os.path.isdir(fp2) and DATE_DIR_RE.match(name):
            yield from _yield_date_tree(fp2)
        elif os.path.isfile(fp2):
            yield fp2


def iter_files(paths, recursive=False):
    """收集 (文件路径, 是否已归置)。

    递归时剪掉形如 2024 / 2024-01 的目录（本工具的输出目录），其中的
    文件以 already_sorted=True 产出；普通文件产出 already_sorted=False。
    """
    for p in paths:
        if os.path.isfile(p):
            yield p, False
        elif os.path.isdir(p):
            if recursive:
                for root, dirs, files in os.walk(p):
                    dirs.sort()
                    for name in sorted(files):
                        yield os.path.join(root, name), False
                    for d in dirs[:]:
                        if DATE_DIR_RE.match(d):
                            dirs.remove(d)
                            for fp2 in _yield_date_tree(os.path.join(root, d)):
                                yield fp2, True
            else:
                try:
                    names = sorted(os.listdir(p))
                except OSError as exc:
                    print("[警告] 无法列出目录 %s: %s" % (p, exc), file=sys.stderr)
                    continue
                for name in names:
                    fp = os.path.join(p, name)
                    if os.path.isfile(fp):
                        yield fp, False
        else:
            print("[警告] 路径不存在: %s" % p, file=sys.stderr)


def _same_dir(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _safe_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _safe_stdio()
    parser = argparse.ArgumentParser(
        prog="img-sort-by-date",
        description="输出按 yyyy/yyyy-mm 目录归置照片的 mv 命令清单（默认不执行）。",
    )
    parser.add_argument("paths", nargs="+", help="图片文件或目录")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="递归扫描子目录")
    parser.add_argument("--dest", default=None,
                        help="目标根目录（默认在照片所在目录就地归置）")
    parser.add_argument("--mtime", action="store_true",
                        help="无 EXIF 拍摄时间时回退用文件修改时间")
    parser.add_argument("-x", "--exec", dest="do_exec", action="store_true",
                        help="实际执行移动（默认仅打印清单）")
    args = parser.parse_args(argv)

    def shell_quote(s):
        return shlex.quote(s.replace("\\", "/"))

    plan = []
    no_date = not_img = inplace = 0
    for fp, already_sorted in iter_files(args.paths, args.recursive):
        if not is_supported_image(fp):
            not_img += 1
            continue
        if already_sorted:
            inplace += 1
            continue
        dt = exif_datetime(read_exif(fp))
        if dt is None and args.mtime:
            try:
                dt = datetime.datetime.fromtimestamp(os.stat(fp).st_mtime)
            except OSError:
                dt = None
        if dt is None:
            no_date += 1
            print(f"[跳过] {fp}（无拍摄时间）", file=sys.stderr)
            continue
        dest_root = args.dest if args.dest else os.path.dirname(fp)
        dest_dir = os.path.join(dest_root, f"{dt:%Y}", f"{dt:%Y-%m}")
        if _same_dir(os.path.dirname(fp), dest_dir):
            inplace += 1
            continue
        plan.append((os.path.abspath(fp), os.path.abspath(dest_dir)))

    plan.sort()
    moved = collided = 0
    if args.do_exec:
        for src, dest_dir in plan:
            target = os.path.join(dest_dir, os.path.basename(src))
            if os.path.exists(target):
                collided += 1
                print(f"[跳过] 目标已存在同名文件: {target}", file=sys.stderr)
                continue
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(src, dest_dir)
            print(f"[归类] mv {shell_quote(src)} {shell_quote(dest_dir + '/')}")
            moved += 1
    else:
        dirs = sorted({d for _, d in plan})
        if dirs:
            print("mkdir -p " + " ".join(shell_quote(d) for d in dirs))
        for src, dest_dir in plan:
            print(f"mv {shell_quote(src)} {shell_quote(dest_dir + '/')}")

    mode = "执行" if args.do_exec else "预览（dry-run）"
    n = moved if args.do_exec else len(plan)
    extra = f"，目标冲突 {collided}" if collided else ""
    print(f"-- {mode}: {n} 条 mv 待执行/已执行，已就地 {inplace} 个，"
          f"无拍摄时间 {no_date} 个，非图片 {not_img} 个{extra}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
