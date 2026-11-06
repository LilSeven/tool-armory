#!/usr/bin/env python3
"""PATH 目录体检 (path-audit) —— 检查 PATH 中不存在的目录、重复项与超长项，给出清理建议。

用途:
    把 PATH（或 --path 指定的值）按 os.pathsep 拆分后逐项体检并给出清理建议:
      * missing    目录不存在或不是目录 —— 建议从 PATH 移除；
      * duplicate  与更早的条目重复（Windows 下忽略大小写）—— 建议去重；
      * empty      空条目等价于“当前目录”，有安全风险 —— 建议删除；
      * long       条目长度超过 --threshold（默认 200 字符）—— 提示人工核对。
    汇总给出可节省的字符数与“清理后的 PATH”（保留首次出现且存在的条目）。

示例命令:
    python path-audit.py                      # 体检当前 PATH
    python path-audit.py --json               # JSON 输出
    python path-audit.py --path "C:/Windows;C:/Windows;C:/no/such/dir;;" --threshold 20

只依赖 Python 标准库；只读检查，不修改任何环境变量。
"""

import argparse
import json
import os
import sys


def _force_utf8_stdout():
    """管道/重定向场景下尽量以 UTF-8 输出，避免 Windows 默认码页导致乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (stream.encoding or "").lower().replace("-", "")
            if enc and enc != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def audit(entries, threshold):
    """逐条体检 PATH 条目，返回带状态记录的列表。"""
    records = []
    first_seen = {}
    for idx, raw in enumerate(entries):
        entry = raw.strip()
        rec = {"index": idx, "entry": entry, "length": len(entry)}
        if not entry:
            rec["status"] = "empty"
            rec["note"] = "空条目相当于把当前目录加入搜索路径，有安全风险，建议删除"
        else:
            key = entry.lower() if os.name == "nt" else entry
            if key in first_seen:
                rec["status"] = "duplicate"
                rec["note"] = "与第 %d 项重复，保留一处即可" % first_seen[key]
            elif not os.path.isdir(entry):
                rec["status"] = "missing"
                rec["note"] = "目录不存在或不是目录，建议从 PATH 移除"
            elif len(entry) > threshold:
                rec["status"] = "long"
                rec["note"] = "长度 %d 超过阈值 %d，请核对是否确有必要" % (len(entry), threshold)
            else:
                rec["status"] = "ok"
                rec["note"] = ""
            first_seen.setdefault(key, idx)
        records.append(rec)
    return records


def cleaned_path(records):
    """生成清理后的 PATH：去掉 missing/empty/duplicate，保留 ok/long。"""
    return os.pathsep.join(r["entry"] for r in records if r["status"] in ("ok", "long"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="path-audit",
        description="PATH 目录体检：找出不存在的目录、重复项与超长项并给出清理建议",
    )
    parser.add_argument("--path", default=os.environ.get("PATH", ""),
                        help="要体检的 PATH 值（默认读取当前环境变量 PATH）")
    parser.add_argument("--threshold", type=int, default=200,
                        help="超长条目的长度阈值（默认 200 字符）")
    parser.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)
    _force_utf8_stdout()

    records = audit(args.path.split(os.pathsep), args.threshold)
    cleaned = cleaned_path(records)
    counts = {}
    for r in records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    saved = len(args.path) - len(cleaned)

    if args.as_json:
        print(json.dumps({"total": len(records), "counts": counts, "chars_saved": saved,
                          "cleaned_path": cleaned, "entries": records},
                         ensure_ascii=False, indent=2))
        return 0

    print("PATH 共 %d 项，长度 %d 字符" % (len(records), len(args.path)))
    print("统计    : " + ", ".join("%s=%d" % (k, v) for k, v in sorted(counts.items())))
    mark = {"missing": "[不存在]", "duplicate": "[重复]  ", "empty": "[空条目]",
            "long": "[超长]  ", "ok": "[正常]  "}
    for r in records:
        note = "  -- %s" % r["note"] if r["note"] else ""
        print("  %2d %s %s (%d 字符)%s"
              % (r["index"], mark.get(r["status"], "[?]"), r["entry"] or "<空>", r["length"], note))
    print("")
    if saved > 0:
        print("清理建议: 移除异常项后 PATH 可缩短 %d 字符，清理后为:" % saved)
        print("  %s" % cleaned)
    else:
        print("清理建议: 未发现可清理项，PATH 状态良好")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
