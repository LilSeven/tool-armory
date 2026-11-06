#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件指纹清单生成器（hash-manifest）。

用途:
    为目录内所有文件计算 SHA-256，生成 JSON 或 CSV 清单文件，作为
    后续完整性校验的基准；配合 --verify 可将目录当前状态与基准清单
    比对，报告缺失 / 已变更 / 新增的文件。清单内路径相对根目录并用
    / 分隔，保证跨平台一致。

用法:
    python hash-manifest.py <目录> [-f json|csv] [-o 输出文件]
    python hash-manifest.py <目录> --verify 基准清单文件

示例:
    python hash-manifest.py ./dist -o manifest.json
    python hash-manifest.py ./dist -f csv -o manifest.csv
    python hash-manifest.py ./dist --verify manifest.json

清单格式:
    JSON: {"root":..., "algorithm":"sha256", "files":[{"path","size","sha256"}...]}
    CSV : 表头 path,size,sha256（UTF-8 带 BOM）

退出码:
    0 = 生成成功；或 --verify 校验无差异
    1 = --verify 发现差异（缺失/变更/新增）
    2 = 目录或清单不存在、格式错误等
"""

import argparse
import csv
import hashlib
import io
import json
import os
import sys
from datetime import datetime

CHUNK = 1 << 20  # 1 MiB 分块读取


def human(nbytes):
    """字节数转人类可读字符串。"""
    size = float(nbytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return "%d B" % int(size)
            return "%.1f %s" % (size, unit)
        size /= 1024.0


def force_utf8_stdio():
    """让中文输出在管道/重定向（如 Git Bash）下不乱码、不报错。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def sha256_file(path):
    """分块计算文件 SHA-256，返回十六进制摘要。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def generate_records(root):
    """遍历目录并哈希所有文件，返回 (记录列表, 错误列表)。"""
    records = []
    errors = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            try:
                size = os.path.getsize(full)
                digest = sha256_file(full)
            except OSError as exc:
                errors.append({"path": rel, "error": str(exc)})
                continue
            records.append({"path": rel, "size": size, "sha256": digest})
    records.sort(key=lambda rec: rec["path"])
    return records, errors


def load_manifest(path):
    """读取基准清单（JSON 或 CSV），返回 {相对路径: (大小, sha256)}。"""
    with open(path, "rb") as fh:
        text = fh.read().decode("utf-8-sig")
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    base = {}
    if isinstance(data, dict) and isinstance(data.get("files"), list):
        for rec in data["files"]:
            base[rec["path"]] = (int(rec["size"]), str(rec["sha256"]).lower())
        return base
    if data is not None:
        raise ValueError("JSON 清单缺少 files 字段")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "path" not in reader.fieldnames:
        raise ValueError("清单格式无法识别（既不是 JSON 也不是 path,size,sha256 的 CSV）")
    for row in reader:
        base[row["path"]] = (int(row["size"]), row["sha256"].lower())
    return base


def write_manifest(args, records, errors):
    """把清单写入 -o 指定的文件，或无 -o 时打印到 stdout（纯数据）。"""
    total_size = sum(rec["size"] for rec in records)
    if args.output:
        if args.format == "json":
            payload = {
                "tool": "hash-manifest",
                "root": os.path.abspath(args.root),
                "algorithm": "sha256",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "file_count": len(records),
                "total_bytes": total_size,
                "files": records,
                "errors": errors,
            }
            with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        else:
            with open(args.output, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["path", "size", "sha256"])
                for rec in records:
                    writer.writerow([rec["path"], rec["size"], rec["sha256"]])
        print("已生成清单: %s（%d 个文件，合计 %s，SHA-256）"
              % (os.path.abspath(args.output), len(records), human(total_size)))
    else:
        if args.format == "json":
            payload = {
                "tool": "hash-manifest",
                "root": os.path.abspath(args.root),
                "algorithm": "sha256",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "file_count": len(records),
                "total_bytes": total_size,
                "files": records,
                "errors": errors,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            writer = csv.writer(sys.stdout)
            writer.writerow(["path", "size", "sha256"])
            for rec in records:
                writer.writerow([rec["path"], rec["size"], rec["sha256"]])
    if errors:
        print("警告: %d 个文件未能读取:" % len(errors), file=sys.stderr)
        for err in errors:
            print("  %s: %s" % (err["path"], err["error"]), file=sys.stderr)


def verify(root, manifest_path):
    """把目录当前状态与基准清单比对，返回退出码。"""
    if not os.path.isdir(root):
        print("错误: 目录不存在: %s" % root, file=sys.stderr)
        return 2
    try:
        base = load_manifest(manifest_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("错误: 无法读取清单 %s: %s" % (manifest_path, exc), file=sys.stderr)
        return 2
    current_records, errors = generate_records(root)
    current = {rec["path"]: (rec["size"], rec["sha256"]) for rec in current_records}
    missing = sorted(set(base) - set(current))
    added = sorted(set(current) - set(base))
    changed = sorted(p for p in set(base) & set(current) if base[p][1] != current[p][1])
    same = len(set(base) & set(current)) - len(changed)

    print("校验基准 : %s（记录 %d 个文件）" % (manifest_path, len(base)))
    print("目标目录 : %s" % os.path.abspath(root))
    print("结果     : %d 个一致，%d 个已变更，%d 个缺失，%d 个新增"
          % (same, len(changed), len(missing), len(added)))
    for p in changed:
        print("  [变更] %s" % p)
    for p in missing:
        print("  [缺失] %s" % p)
    for p in added:
        print("  [新增] %s" % p)
    if errors:
        print("警告: %d 个文件无法读取:" % len(errors), file=sys.stderr)
        for err in errors:
            print("  %s: %s" % (err["path"], err["error"]), file=sys.stderr)
    return 0 if not (changed or missing or added) else 1


def build_parser():
    parser = argparse.ArgumentParser(
        prog="hash-manifest.py",
        description="为目录生成含 SHA-256 的清单文件（JSON/CSV），作为后续校验基准；支持 --verify 比对。",
    )
    parser.add_argument("root", nargs="?", default=".", help="目标目录（默认当前目录）")
    parser.add_argument("-f", "--format", choices=("json", "csv"), default="json",
                        help="清单格式（默认 json）")
    parser.add_argument("-o", "--output", metavar="FILE",
                        help="清单输出文件；省略则打印到 stdout")
    parser.add_argument("--verify", metavar="MANIFEST",
                        help="校验模式：用基准清单与目录当前状态比对")
    return parser


def main(argv=None):
    force_utf8_stdio()
    args = build_parser().parse_args(argv)

    if args.verify:
        return verify(args.root, args.verify)

    if not os.path.isdir(args.root):
        print("错误: 目录不存在: %s" % args.root, file=sys.stderr)
        return 2
    records, errors = generate_records(args.root)
    write_manifest(args, records, errors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
