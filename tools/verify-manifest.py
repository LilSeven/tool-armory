#!/usr/bin/env python3
"""校验和清单验证：按 sha256sum 风格清单逐条验证文件，结果分三类输出。

  [OK]      文件存在且摘要一致
  [MISSING] 文件不存在
  [FAILED]  文件存在但摘要不一致，或读取失败

清单格式兼容 GNU coreutils：`<十六进制摘要>  <路径>` 或 `<摘要> *<路径>`（二进制模式），
'#' 开头的行与空行被忽略。支持 sha256 / sha1 / md5，算法按摘要长度自动判断。

用法示例：
  python verify-manifest.py manifest.sha256
  python verify-manifest.py --base ./somedir manifest.sha256

退出码：0 = 全部通过；1 = 存在 MISSING 或 FAILED。
"""
import argparse
import hashlib
import os
import sys

# 摘要长度 -> 算法名（sha256sum 风格清单的摘要均为小写十六进制）
LENGTH_TO_ALGO = {32: "md5", 40: "sha1", 64: "sha256"}
CHUNK = 1 << 20


def parse_manifest(path):
    """解析清单，产出 (摘要, 路径) 元组列表。"""
    entries = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            sep = line.find(" ")
            if sep <= 0:
                raise ValueError("第 %d 行格式无法解析：%r" % (lineno, line))
            digest, rest = line[:sep], line[sep + 1:]
            if rest[:1] in (" ", "*"):  # 文本模式两个空格 / 二进制模式星号
                rest = rest[1:]
            if not rest:
                raise ValueError("第 %d 行缺少文件路径：%r" % (lineno, line))
            entries.append((digest.lower(), rest))
    return entries


def digest_file(path, algo):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="验证 sha256sum 风格清单")
    ap.add_argument("manifest", help="清单文件路径")
    ap.add_argument("--base", help="把清单中的相对路径解析到该目录下（默认相对当前目录）")
    args = ap.parse_args(argv)

    try:
        entries = parse_manifest(args.manifest)
    except (OSError, ValueError) as e:
        print("无法读取清单：%s" % e, file=sys.stderr)
        return 1
    if not entries:
        print("清单为空，没有可验证的条目。", file=sys.stderr)
        return 1

    ok = missing = failed = 0
    for digest, rel in entries:
        path = os.path.join(args.base, rel) if args.base else rel
        algo = LENGTH_TO_ALGO.get(len(digest))
        if algo is None:
            print("[FAILED] %s（无法识别的摘要长度 %d）" % (path, len(digest)))
            failed += 1
            continue
        if not os.path.isfile(path):
            print("[MISSING] %s" % path)
            missing += 1
            continue
        try:
            if digest_file(path, algo) == digest:
                print("[OK] %s" % path)
                ok += 1
            else:
                print("[FAILED] %s（摘要不一致）" % path)
                failed += 1
        except OSError as e:
            print("[FAILED] %s（读取失败：%s）" % (path, e))
            failed += 1

    print("\n验证完成：%d 通过，%d 缺失，%d 损坏（共 %d 条）。"
          % (ok, missing, failed, len(entries)))
    return 0 if (missing == 0 and failed == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
