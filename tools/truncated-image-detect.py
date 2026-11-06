#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""截断图片检测（truncated-image-detect）。

用途：
    比对图片头里"声明"的数据量与实际字节数，检测 PNG / GIF / BMP 是否被
    截断（下载/传输中断、保存不完整等）。只读文件，不修改任何文件。

判定方式：
    PNG  逐块走块链：每块声明 len + 4 字节 CRC，若声明的字节数越过文件
         末尾、或数据在块边界结束却没有 IEND 结束块，判为截断。
    GIF  按块结构走（逻辑屏幕/全局色表/扩展块/图像块/子块链）：数据区读
         完仍未遇到结束符 0x3B，或某个子块声明的长度越过文件末尾，判为
         截断。
    BMP  文件头 bfSize（偏移 2，4 字节小端）声明的总字节数与实际大小比对：
         实际 < 声明 -> 截断；实际 > 声明 -> OK（尾部多余数据）；
         声明为 0 -> 无法判断（UNKNOWN）。

示例命令：
    python truncated-image-detect.py a.png b.gif c.bmp
    python truncated-image-detect.py --dir D:/downloads
    python truncated-image-detect.py --dir D:/downloads --json
    python truncated-image-detect.py --dir D:/downloads --strict

说明：
    --dir 只检查扩展名为 .png/.gif/.bmp 的文件；直接指定的文件一律按
    文件头魔数嗅探，非目标格式列为 UNKNOWN（跳过）。

退出码：0 检查完成（是否截断看输出/JSON）；1 仅当 --strict 且发现截断；
        2 参数错误或目录不存在。
"""
import argparse
import json
import os
import struct
import sys

PNG_SIG = b"\x89PNG\r\n\x1a\n"
DIR_EXTS = {".png", ".gif", ".bmp"}
VERDICT_LABEL = {"ok": "OK", "truncated": "TRUNCATED", "unknown": "UNKNOWN"}


def _check_png(path):
    size = os.path.getsize(path)
    with open(path, "rb") as fp:
        if fp.read(8) != PNG_SIG:
            return "unknown", "PNG 签名不符"
        while True:
            hdr = fp.read(8)
            if len(hdr) == 0:
                return "truncated", "数据在块边界处结束，缺少 IEND 结束块"
            if len(hdr) < 8:
                return "truncated", "文件在块头处截断（仅剩 %d 字节）" % len(hdr)
            (declared,) = struct.unpack(">I", hdr[:4])
            ctype = hdr[4:8].decode("latin1")
            end = fp.tell() + declared + 4  # 块数据 + CRC
            if end > size:
                return "truncated", (
                    "块 %s 声明数据 %d 字节（含 CRC 共 %d 字节），但文件仅剩 %d 字节"
                    % (ctype, declared, declared + 4, size - fp.tell()))
            fp.seek(end)
            if ctype == "IEND":
                extra = size - fp.tell()
                if extra > 0:
                    return "ok", "块链完整，IEND 在文件末尾（其后另有 %d 字节多余数据）" % extra
                return "ok", "块链完整，IEND 位于文件末尾"


def _check_gif(path):
    size = os.path.getsize(path)
    with open(path, "rb") as fp:
        head = fp.read(13)
        if len(head) < 13 or head[:6] not in (b"GIF87a", b"GIF89a"):
            return "unknown", "GIF 头不符"
        pos = 13
        if head[10] & 0x80:  # 全局色表
            pos += 3 * (2 ** ((head[10] & 0x07) + 1))
        fp.seek(pos)
        while True:
            b = fp.read(1)
            if not b:
                return "truncated", "数据区读完仍未遇到块结束符 0x3B"
            c = b[0]
            if c == 0x3B:
                extra = size - fp.tell()
                if extra > 0:
                    return "ok", "块结构完整，结束符 0x3B 后另有 %d 字节多余数据" % extra
                return "ok", "块结构完整，结束符 0x3B 位于文件末尾"
            if c == 0x21:  # 扩展块
                if not fp.read(1):
                    return "truncated", "扩展块标签处截断"
                while True:
                    n = fp.read(1)
                    if not n:
                        return "truncated", "扩展块子块长度处截断"
                    if n[0] == 0:
                        break
                    if fp.tell() + n[0] > size:
                        return "truncated", "扩展块子块声明 %d 字节，越过文件末尾" % n[0]
                    fp.seek(n[0], 1)
            elif c == 0x2C:  # 图像描述块
                d = fp.read(9)
                if len(d) < 9:
                    return "truncated", "图像描述块处截断"
                if d[8] & 0x80:  # 局部色表
                    fp.seek(3 * (2 ** ((d[8] & 0x07) + 1)), 1)
                if not fp.read(1):
                    return "truncated", "LZW 最小编码长度处截断"
                while True:
                    n = fp.read(1)
                    if not n:
                        return "truncated", "图像数据子块长度处截断"
                    if n[0] == 0:
                        break
                    if fp.tell() + n[0] > size:
                        return "truncated", "图像数据子块声明 %d 字节，越过文件末尾" % n[0]
                    fp.seek(n[0], 1)
            else:
                return "truncated", "在 0x%02X 处遇到意外块（数据中断或损坏）" % c


def _check_bmp(path):
    size = os.path.getsize(path)
    with open(path, "rb") as fp:
        head = fp.read(6)
        if len(head) < 6 or head[:2] != b"BM":
            return "unknown", "BMP 头不符"
        (declared,) = struct.unpack("<I", head[2:6])
    if declared == 0:
        return "unknown", "头未声明文件大小（bfSize=0），无法比对字节数"
    if size < declared:
        return "truncated", "头声明 %d 字节，实际 %d 字节（缺 %d 字节）" % (
            declared, size, declared - size)
    if size > declared:
        return "ok", "实际 %d 字节，比头声明多 %d 字节（尾部多余数据）" % (
            size, size - declared)
    return "ok", "实际 %d 字节与头声明完全一致" % size


def check_file(path):
    """返回 (格式, 判定, 说明)。格式: PNG/GIF/BMP/None；判定: ok/truncated/unknown。"""
    try:
        with open(path, "rb") as fp:
            magic = fp.read(8)
        if magic[:8] == PNG_SIG:
            v, d = _check_png(path)
            return "PNG", v, d
        if magic[:4] == b"GIF8":
            v, d = _check_gif(path)
            return "GIF", v, d
        if magic[:2] == b"BM":
            v, d = _check_bmp(path)
            return "BMP", v, d
        return None, "unknown", "非 PNG/GIF/BMP（跳过）"
    except OSError as exc:
        return None, "unknown", "无法读取：%s" % exc


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="比对头声明数据量与实际字节数，检测 PNG/GIF/BMP 是否被截断")
    ap.add_argument("files", nargs="*", help="图片文件（按头魔数嗅探格式）")
    ap.add_argument("--dir", help="目录：检查其中 .png/.gif/.bmp（递归）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--strict", action="store_true",
                    help="发现截断文件时退出码置 1（默认总是 0）")
    args = ap.parse_args(argv)

    paths = list(args.files)
    if args.dir:
        if not os.path.isdir(args.dir):
            print("错误：目录不存在：%s" % args.dir, file=sys.stderr)
            return 2
        for dirpath, dirnames, filenames in os.walk(args.dir):
            dirnames.sort()
            for name in sorted(filenames):
                if os.path.splitext(name)[1].lower() in DIR_EXTS:
                    paths.append(os.path.join(dirpath, name))
    if not paths:
        ap.error("未指定任何文件或目录")

    results = []
    seen = set()
    for p in paths:
        key = os.path.abspath(p)
        if key in seen:
            continue
        seen.add(key)
        fmt, verdict, detail = check_file(p)
        results.append({"file": p, "format": fmt,
                        "verdict": verdict, "detail": detail})

    n_ok = sum(1 for r in results if r["verdict"] == "ok")
    n_bad = sum(1 for r in results if r["verdict"] == "truncated")
    n_unk = sum(1 for r in results if r["verdict"] == "unknown")

    if args.json:
        print(json.dumps({"results": results,
                          "counts": {"ok": n_ok, "truncated": n_bad,
                                     "unknown": n_unk}},
                         ensure_ascii=False, indent=2))
    else:
        for r in results:
            print("%-9s %-4s %s — %s"
                  % (VERDICT_LABEL[r["verdict"]], r["format"] or "-",
                     r["file"], r["detail"]))
        print("汇总：共 %d 项 —— OK %d，TRUNCATED %d，UNKNOWN/跳过 %d"
              % (len(results), n_ok, n_bad, n_unk))

    if args.strict and n_bad:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
