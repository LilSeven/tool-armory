#!/usr/bin/env python3
r"""daily-change-log — 每日变更清单: 对比上次运行保存的状态, 输出新增/修改/删除的文件。

无需守护进程: 每次运行扫描目录生成快照 (JSON 状态文件), 与上次快照对比,
输出 ADDED / CHANGED / REMOVED 清单, 然后保存新快照供下次对比。
适合放进计划任务/cron 每天跑一次。

用法:
    python daily-change-log.py <dir> [--state PATH] [--hash] [--no-update] [--json]

选项:
    --state PATH   状态文件位置 (默认 <dir>/.daily-change-log.state.json,
                   扫描时自动跳过该文件)
    --hash         额外记录内容 SHA-256; 大小/mtime 不变但内容变化也能查出 (较慢)
    --no-update    只对比输出, 不更新状态文件 (peek, 不影响下次结果)
    --json         以 JSON 输出结果

说明: 判定“修改”默认依据文件大小与 mtime_ns; 首次运行只建立基线, 不输出变更。

示例:
    python daily-change-log.py K:/WorkAreaZcode/projects
    python daily-change-log.py D:/docs --hash --json
    python daily-change-log.py . --state D:/state/docs.json --no-update

退出码: 0 成功; 1 状态文件损坏/不可读; 2 参数错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat as stat_mod
import sys
import time
from datetime import datetime

DEFAULT_STATE_NAME = ".daily-change-log.state.json"


def fix_streams() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="backslashreplace")
        except Exception:
            pass


def human_size(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or unit == "PB":
            return f"{n:.0f} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def iso_local(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return "out-of-range"


def norm_key(rel: str) -> str:
    """Windows 大小写不敏感, 统一为小写 + 正斜杠作为键。"""
    return rel.replace("\\", "/").lower()


def sha256_file(path: str):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def scan_root(root: str, state_abs: str, use_hash: bool):
    """返回 {key: {"p": 显示路径, "s": 大小, "m": mtime_ns, "h": sha256}}"""
    files = {}
    skip = {os.path.normcase(state_abs), os.path.normcase(state_abs + ".tmp")}
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            full = os.path.join(dirpath, name)
            try:
                if os.path.normcase(os.path.abspath(full)) in skip:
                    continue
                st = os.stat(full)
            except OSError:
                continue
            if not stat_mod.S_ISREG(st.st_mode):
                continue
            rel = os.path.relpath(full, root).replace("\\", "/")
            entry = {"p": rel, "s": st.st_size, "m": st.st_mtime_ns}
            if use_hash:
                entry["h"] = sha256_file(full)
            files[norm_key(rel)] = entry
    return files


def load_state(path: str):
    """返回 (state 或 None, 错误信息或 None)。文件不存在 -> (None, None)。"""
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return None, f"cannot read state file {path}: {e}"
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return None, f"state file {path} is not a valid snapshot"
    return data, None


def save_state(path: str, root: str, files: dict, use_hash: bool) -> None:
    payload = {
        "version": 1,
        "generated_at": time.time(),
        "root": os.path.abspath(root),
        "hash": bool(use_hash),
        "files": files,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)


def diff(old: dict, new: dict, compare_hash: bool):
    added = sorted(k for k in new if k not in old)
    removed = sorted(k for k in old if k not in new)
    changed = []
    for k in sorted(new.keys() & old.keys()):
        a, b = old[k], new[k]
        if a["s"] != b["s"] or a["m"] != b["m"]:
            changed.append(k)
        elif (compare_hash and a.get("h") is not None and b.get("h") is not None
              and a["h"] != b["h"]):
            changed.append(k)
    return added, changed, removed


def print_report(root, old_state, added, changed, removed, new_files) -> None:
    print(f"daily-change-log: {os.path.abspath(root)}")
    if old_state.get("generated_at") is not None:
        print(f"last snapshot: {iso_local(old_state['generated_at'])} "
              f"({len(old_state['files'])} files)")
    for k in added:
        e = new_files[k]
        print(f"ADDED    + {e['p']} ({human_size(e['s'])})")
    for k in changed:
        e = new_files[k]
        old_s = old_state["files"][k]["s"]
        print(f"CHANGED  ~ {e['p']} ({human_size(old_s)} -> {human_size(e['s'])})")
    for k in removed:
        e = old_state["files"][k]
        print(f"REMOVED  - {e['p']} (was {human_size(e['s'])})")
    print(f"summary: +{len(added)} ~{len(changed)} -{len(removed)} | "
          f"current {len(new_files)} files")
    if not (added or changed or removed):
        print("no changes since last run.")


def json_report(root, old_state, added, changed, removed, new_files) -> None:
    payload = {
        "root": os.path.abspath(root),
        "last_snapshot": old_state.get("generated_at"),
        "added": [{"path": new_files[k]["p"], "size": new_files[k]["s"]} for k in added],
        "changed": [{"path": new_files[k]["p"],
                     "old_size": old_state["files"][k]["s"],
                     "new_size": new_files[k]["s"]} for k in changed],
        "removed": [{"path": old_state["files"][k]["p"],
                     "size": old_state["files"][k]["s"]} for k in removed],
        "counts": {"added": len(added), "changed": len(changed),
                   "removed": len(removed)},
        "current_files": len(new_files),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="daily-change-log",
        description="对比上次运行保存的状态, 输出新增/修改/删除的文件清单 (无需守护进程)。",
    )
    ap.add_argument("dir", help="要监控的目录")
    ap.add_argument("--state", metavar="PATH", default=None,
                    help=f"状态文件位置 (默认 <dir>/{DEFAULT_STATE_NAME})")
    ap.add_argument("--hash", dest="use_hash", action="store_true",
                    help="同时记录内容 SHA-256")
    ap.add_argument("--no-update", dest="update", action="store_false",
                    help="只对比, 不更新状态文件")
    ap.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 输出")
    return ap


def main(argv=None) -> int:
    fix_streams()
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.dir):
        print(f"error: not a directory: {args.dir}", file=sys.stderr)
        return 2

    state_path = args.state or os.path.join(args.dir, DEFAULT_STATE_NAME)
    state_abs = os.path.abspath(state_path)

    old_state, err = load_state(state_path)
    if err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    new_files = scan_root(args.dir, state_abs, args.use_hash)

    # 首次运行: 只建立基线
    if old_state is None:
        if not args.update:
            print("error: --no-update needs an existing state file; "
                  "run once without it first.", file=sys.stderr)
            return 2
        if args.as_json:
            print(json.dumps({"root": os.path.abspath(args.dir), "baseline": True,
                              "files": len(new_files), "state": state_abs},
                             ensure_ascii=False))
        else:
            print(f"baseline created: {len(new_files)} files -> {state_abs}")
            print("next run will report ADDED / CHANGED / REMOVED against this snapshot.")
        save_state(state_path, args.dir, new_files, args.use_hash)
        return 0

    compare_hash = bool(args.use_hash and old_state.get("hash"))
    added, changed, removed = diff(old_state["files"], new_files, compare_hash)

    if args.as_json:
        json_report(args.dir, old_state, added, changed, removed, new_files)
    else:
        print_report(args.dir, old_state, added, changed, removed, new_files)

    if args.update:
        save_state(state_path, args.dir, new_files, args.use_hash)
    return 0


if __name__ == "__main__":
    sys.exit(main())
