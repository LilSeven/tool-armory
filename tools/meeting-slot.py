#!/usr/bin/env python3
"""共同空闲段搜索（meeting-slot）

用途：
    读取一份 JSON 文件（多个人的忙碌时间区间），在给定的工作时段内求出
    所有人忙碌区间并集的补集，即"共同空闲时段"，并可按最短时长过滤，
    用于快速安排多人会议。

输入 JSON 格式（UTF-8 文件，区间为 [起, 止) 半开区间，不支持跨零点）：
    {
      "date": "2026-11-05",
      "work_start": "09:00",
      "work_end": "18:00",
      "duration_min": 30,
      "people": {
        "张三": [["09:30", "10:30"], ["12:00", "13:00"]],
        "李四": [["11:00", "11:45"], ["15:30", "16:30"]]
      }
    }
    其中 date / work_start / work_end / duration_min 均可省略
    （默认分别为未指定 / 09:00 / 18:00 / 30 分钟），也可用同名命令行参数覆盖。

示例命令：
    python meeting-slot.py busy.json
    python meeting-slot.py busy.json --duration 45 --work-start 09:30 --work-end 17:30
    cat busy.json | python meeting-slot.py -
"""

import argparse
import json
import sys

DAY_MIN = 24 * 60


def _setup_streams():
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def to_min(text, field="时间"):
    """"HH:MM" -> 分钟数，允许 00:00-24:00（24:00 仅表示当天结束）。"""
    t = str(text).strip()
    parts = t.split(":")
    if len(parts) != 2:
        raise ValueError("%s %r 格式应为 HH:MM" % (field, t))
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError("%s %r 不是有效时刻" % (field, t))
    if not (0 <= h <= 24 and 0 <= m <= 59) or (h == 24 and m != 0):
        raise ValueError("%s %r 超出 00:00-24:00 范围" % (field, t))
    return h * 60 + m


def fmt(minutes):
    return "%02d:%02d" % (minutes // 60, minutes % 60)


def merge(intervals):
    """合并重叠/相邻区间，返回排好序的 (start, end) 列表。"""
    out = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def complement(busy, ws, we):
    """[ws, we) 减去 busy（已合并、已裁剪到窗口内）得到空闲段。"""
    free = []
    cur = ws
    for s, e in busy:
        if s > cur:
            free.append((cur, s))
        cur = max(cur, e)
    if cur < we:
        free.append((cur, we))
    return free


def main(argv=None):
    _setup_streams()
    parser = argparse.ArgumentParser(
        description="读取多人忙碌区间 JSON，在工作时段内搜索共同空闲时段",
        epilog='示例: python meeting-slot.py busy.json --duration 45（"-" 表示从 stdin 读 JSON）',
    )
    parser.add_argument("input", help="忙碌区间 JSON 文件路径；传 - 从 stdin 读取")
    parser.add_argument("--date", help="覆盖 JSON 里的 date（仅用于展示）")
    parser.add_argument("--work-start", help="覆盖工作开始时刻 HH:MM")
    parser.add_argument("--work-end", help="覆盖工作结束时刻 HH:MM")
    parser.add_argument("--duration", type=int, help="覆盖最短空闲时长（分钟）")
    args = parser.parse_args(argv)

    try:
        if args.input == "-":
            raw = sys.stdin.read()
        else:
            with open(args.input, "r", encoding="utf-8") as fh:
                raw = fh.read()
        data = json.loads(raw)
    except OSError as exc:
        print("错误: 无法读取输入文件: %s" % exc, file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print("错误: JSON 解析失败: %s" % exc, file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("错误: JSON 顶层必须是对象", file=sys.stderr)
        return 2

    date_str = args.date or str(data.get("date", "未指定"))
    try:
        ws = to_min(args.work_start if args.work_start else data.get("work_start", "09:00"), "work_start")
        we = to_min(args.work_end if args.work_end else data.get("work_end", "18:00"), "work_end")
    except ValueError as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2
    if ws >= we:
        print("错误: work_start 必须早于 work_end", file=sys.stderr)
        return 2

    duration = args.duration
    if duration is None:
        try:
            duration = int(data.get("duration_min", 30))
        except (TypeError, ValueError):
            print("错误: duration_min 必须是整数", file=sys.stderr)
            return 2
    if duration < 0:
        print("错误: 最短空闲时长不能为负", file=sys.stderr)
        return 2

    people = data.get("people")
    if not isinstance(people, dict) or not people:
        print("错误: 缺少 people（应为非空对象：姓名 -> 忙碌区间列表）", file=sys.stderr)
        return 2

    busy_all = []
    per_person = {}
    for name, intervals in people.items():
        kept = []
        if not isinstance(intervals, list):
            print("警告: 跳过 %s（忙碌区间不是列表）" % name, file=sys.stderr)
            per_person[name] = []
            continue
        for iv in intervals:
            try:
                if not (isinstance(iv, (list, tuple)) and len(iv) == 2):
                    raise ValueError("区间须为 [起, 止] 两个时刻")
                s = to_min(iv[0], "%s 的区间起点" % name)
                e = to_min(iv[1], "%s 的区间终点" % name)
            except ValueError as exc:
                print("警告: 跳过 %s 的无效区间 %r: %s" % (name, iv, exc), file=sys.stderr)
                continue
            s, e = max(s, ws), min(e, we)
            if s >= e:
                continue  # 不落在工作时段内
            kept.append((s, e))
        per_person[name] = kept
        busy_all.extend(kept)

    merged = merge(busy_all)
    free = complement(merged, ws, we)
    good = [(s, e) for s, e in free if e - s >= duration]
    short = [(s, e) for s, e in free if e - s < duration]

    print("日期: %s" % date_str)
    print("工作时段: %s-%s（%d 分钟）；最短共同空闲: %d 分钟" % (fmt(ws), fmt(we), we - ws, duration))
    print("参与人（%d 人）: %s" % (len(per_person), "、".join(per_person)))
    if merged:
        print("共同忙碌（合并后）: " + "、".join("%s-%s" % (fmt(s), fmt(e)) for s, e in merged))
    else:
        print("共同忙碌（合并后）: 无")
    print()

    if good:
        print("共同空闲时段（>= %d 分钟）共 %d 段:" % (duration, len(good)))
        for i, (s, e) in enumerate(good, 1):
            print("  %d. %s-%s  （%d 分钟）" % (i, fmt(s), fmt(e), e - s))
        print("合计 %d 分钟。" % sum(e - s for s, e in good))
    else:
        print("工作时段内没有 >= %d 分钟的共同空闲时段。" % duration)
    if short:
        print("另有 %d 段短于 %d 分钟的零星空闲未列入: %s" % (
            len(short), duration,
            "、".join("%s-%s(%d分)" % (fmt(s), fmt(e), e - s) for s, e in short)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
