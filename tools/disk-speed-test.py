#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""disk-speed-test — 磁盘读写测速。

在指定目录写一个临时文件并读回, 测量顺序写入/读取速度, 快速评估磁盘性能。
写入数据用 os.urandom 生成(不可压缩), 写完强制 fsync 落盘再停止计时;
读回后校验字节数一致, 测速文件用后即删。
注意: 读取发生在刚写入之后, 数据大概率仍在系统缓存中, 读取速度偏乐观,
仅作快速参考; 想测真实冷读请用大于物理内存的 --size。

示例:
    python -I disk-speed-test.py                           # 系统临时目录, 64 MiB
    python -I disk-speed-test.py --dir D:\\tmp --size 256   # 指定目录 256 MiB
    python -I disk-speed-test.py --dir /tmp --size 32 --block 64

选项: --size 单位 MiB(默认 64), --block 单位 KiB(默认 1024)。
退出码: 0 成功; 1 参数/运行错误。
"""

import argparse
import os
import sys
import tempfile
import time

MIB = 1024.0 * 1024.0


def human(num):
    val = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if val < 1024 or unit == "TiB":
            if unit == "B":
                return "%d %s" % (int(val), unit)
            return "%.1f %s" % (val, unit)
        val /= 1024.0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="disk-speed-test",
        description="在指定目录写并读回临时文件, 测量顺序读写速度, 快速评估磁盘性能。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python -I disk-speed-test.py --dir D:\\tmp --size 256")
    parser.add_argument("--dir", default=None,
                        help="测试文件所在目录 (默认: 系统临时目录)")
    parser.add_argument("--size", type=float, default=64.0,
                        help="测试文件大小, 单位 MiB (默认 64)")
    parser.add_argument("--block", type=float, default=1024.0,
                        help="读写块大小, 单位 KiB (默认 1024)")
    args = parser.parse_args(argv)

    if args.size <= 0 or args.block <= 0:
        print("--size/--block must be positive", file=sys.stderr)
        return 1
    directory = args.dir or tempfile.gettempdir()
    if not os.path.isdir(directory):
        print("目录不存在: %s" % directory, file=sys.stderr)
        return 1

    total = int(args.size * MIB)
    block_size = int(args.block * 1024)
    if total < block_size:
        block_size = total  # 保证至少一个完整块
    path = os.path.join(directory, "dstest_%d_%d.tmp" % (os.getpid(), int(time.time())))
    payload = os.urandom(block_size)

    print("dir  : %s" % directory)
    print("file : %s  (%s, block %s)" % (
        os.path.basename(path), human(total), human(block_size)))

    try:
        t0 = time.perf_counter()
        with open(path, "wb") as fh:
            written = 0
            while written < total:
                step = min(block_size, total - written)
                fh.write(payload[:step] if step != block_size else payload)
                written += step
            fh.flush()
            os.fsync(fh.fileno())
        write_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        got = 0
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(block_size)
                if not chunk:
                    break
                got += len(chunk)
        read_time = time.perf_counter() - t0
    except OSError as exc:
        print("test failed: %s" % exc, file=sys.stderr)
        return 1
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    if got != total:
        print("warning: read back %d bytes, expected %d" % (got, total),
              file=sys.stderr)
    w_mibs = total / MIB / write_time if write_time > 0 else float("inf")
    r_mibs = total / MIB / read_time if read_time > 0 else float("inf")
    print("write: %9.1f MiB/s  (%.3f s, %s)" % (w_mibs, write_time, human(total)))
    print("read : %9.1f MiB/s  (%.3f s, %s)  [may benefit from OS cache]" % (
        r_mibs, read_time, human(total)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
