#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""uuid-bulk.py —— UUID 清单批量生成与导出（单文件，纯 Python 标准库）。

批量生成带序号与生成时间戳（UTC，ISO 8601 毫秒）的 UUID 表格；版本可选 v4/v7
（默认 v7，毫秒时间戳有序），导出为 CSV / JSON / TXT 三种格式；-o 指定输出文件
（UTF-8），缺省打印到 stdout。

用法：
    python -I uuid-bulk.py [-n 数量] [--version {4,7}] [-f {csv,json,txt}] [-o 文件] [--upper] [--selftest]

示例命令：
    python -I "K:/WorkAreaZcode/tool-armory/tools/uuid-bulk.py" -n 5 --format csv -o uuids.csv
    python -I "K:/WorkAreaZcode/tool-armory/tools/uuid-bulk.py" -n 3 --format json

示例输出（TXT）：
       no  uuid                                  created_at (UTC)
       --  ------------------------------------  ------------------------
        1  018f3a2b-7c1d-7e4f-9a01-2b3c4d5e6f70  2026-11-02T08:00:00.123Z
"""

import argparse
import csv
import datetime
import io
import json
import secrets
import sys
import threading
import time

_LOCK = threading.Lock()
_STATE = {"ts_ms": -1, "counter": 0}


def _format_uuid(value, upper=False):
    h = f"{value:032x}"
    text = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
    return text.upper() if upper else text


def _gen_v7():
    """UUIDv7：48 位毫秒时间戳 + 12 位单调计数器 + 62 位随机。"""
    now_ms = time.time_ns() // 1_000_000
    with _LOCK:
        if now_ms < _STATE["ts_ms"]:
            now_ms = _STATE["ts_ms"]
        if now_ms == _STATE["ts_ms"]:
            counter = (_STATE["counter"] + 1) & 0x0FFF
            if counter == 0:
                now_ms += 1
                counter = secrets.randbelow(1 << 12)
        else:
            counter = secrets.randbelow(1 << 12)
        _STATE["ts_ms"] = now_ms
        _STATE["counter"] = counter
    return ((now_ms & 0xFFFFFFFFFFFF) << 80) | (0x7 << 76) | (counter << 64) \
        | (0b10 << 62) | secrets.randbits(62)


def _gen_v4():
    """UUIDv4：122 位随机 + 版本 4 + 变体 10。"""
    value = secrets.randbits(128)
    value = (value & ~(0xF << 76)) | (0x4 << 76)
    value = (value & ~(0b11 << 62)) | (0b10 << 62)
    return value


def build_rows(count, version, upper=False):
    """生成 count 行：序号 no、UUID、逐条生成时刻 created_at (UTC)。"""
    gen = _gen_v7 if version == 7 else _gen_v4
    rows = []
    for no in range(1, count + 1):
        uuid_text = _format_uuid(gen(), upper)
        now = datetime.datetime.now(datetime.timezone.utc)
        rows.append({
            "no": no,
            "uuid": uuid_text,
            "created_at": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        })
    return rows


def render_csv(rows):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["no", "uuid", "created_at"])
    for r in rows:
        writer.writerow([r["no"], r["uuid"], r["created_at"]])
    return buf.getvalue()


def render_json(rows):
    return json.dumps(rows, ensure_ascii=False, indent=2)


def render_txt(rows):
    headers = ("no", "uuid", "created_at (UTC)")
    w0 = max(len(headers[0]), max((len(str(r["no"])) for r in rows), default=0))
    w1 = max(len(headers[1]), max((len(r["uuid"]) for r in rows), default=0))
    w2 = max(len(headers[2]), max((len(r["created_at"]) for r in rows), default=0))
    lines = [
        f"{headers[0]:>{w0}}  {headers[1]:<{w1}}  {headers[2]}",
        f"{'-' * w0}  {'-' * w1}  {'-' * w2}",
    ]
    for r in rows:
        lines.append(f"{r['no']:>{w0}}  {r['uuid']:<{w1}}  {r['created_at']}")
    return "\n".join(lines) + "\n"


_RENDERERS = {"csv": render_csv, "json": render_json, "txt": render_txt}


def _selftest():
    for version in (4, 7):
        rows = build_rows(5, version)
        assert [r["no"] for r in rows] == [1, 2, 3, 4, 5], rows
        for r in rows:
            h = r["uuid"].replace("-", "")
            assert len(h) == 32, r
            assert int(h[12], 16) == version, r          # 版本号
            assert h[16] in "89ab", r                    # 变体位 10
            assert r["created_at"].endswith("Z") and "T" in r["created_at"], r
        # CSV 可往返解析
        parsed = list(csv.reader(io.StringIO(render_csv(rows))))
        assert parsed[0] == ["no", "uuid", "created_at"] and len(parsed) == 6, parsed
        # JSON 可往返解析
        obj = json.loads(render_json(rows))
        assert len(obj) == 5 and all(set(o) == {"no", "uuid", "created_at"} for o in obj)
        # TXT：表头 + 分隔线 + 5 行
        assert len(render_txt(rows).splitlines()) == 7
    # v7 连续生成严格单调递增（字典序 = 时间序）
    vals = [_gen_v7() for _ in range(300)]
    assert all(b > a for a, b in zip(vals, vals[1:])), "v7 未单调递增"
    print("selftest ok: v4/v7 行结构与序号正确，CSV/JSON/TXT 均可往返解析，v7 连续生成单调递增")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog="uuid-bulk.py",
        description="批量生成带序号/生成时间戳的 UUID 表格，导出 CSV/JSON/TXT",
    )
    parser.add_argument("-n", "--count", type=int, default=10,
                        help="生成数量（默认 10，须为正整数）")
    parser.add_argument("--version", type=int, choices=(4, 7), default=7,
                        help="UUID 版本（默认 7）")
    parser.add_argument("-f", "--format", choices=("csv", "json", "txt"), default="txt",
                        help="输出格式（默认 txt）")
    parser.add_argument("-o", "--output", help="输出文件路径（UTF-8）；缺省打印到 stdout")
    parser.add_argument("--upper", action="store_true", help="UUID 用大写")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测并退出")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.count < 1:
        parser.error("-n 必须为正整数")

    rows = build_rows(args.count, args.version, args.upper)
    text = _RENDERERS[args.format](rows)
    if args.output:
        newline = "" if args.format == "csv" else None
        with open(args.output, "w", encoding="utf-8", newline=newline) as fh:
            fh.write(text)
        print(f"已写出 {args.count} 条 UUID 到 {args.output}（格式 {args.format}，版本 v{args.version}）")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
