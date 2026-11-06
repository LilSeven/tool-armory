#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NTP 时钟对时：向 NTP 服务器发送 SNTP 请求，测算本地时钟偏差，
可选地把偏差校正到 Windows 系统时钟（需管理员权限，慎用）。

原理（SNTP, RFC 4330 四时间戳法）:
    t0=本地发出时刻  t1=服务器收到时刻  t2=服务器发出时刻  t3=本地收到时刻
    偏差 offset = ((t1 - t0) + (t2 - t3)) / 2     （正数 = 本地钟比服务器慢）
    往返 delay  = (t3 - t0) - (t2 - t1)

用法:
    python ntp-offset.py                          # 查 ntp.aliyun.com，显示偏差
    python ntp-offset.py --server pool.ntp.org --timeout 5
    python ntp-offset.py --demo                   # 离线自测：解析伪造的应答
    python ntp-offset.py --apply                  # 校正 Windows 系统时钟（会先确认）
    python ntp-offset.py --apply --yes            # 跳过确认直接校正
"""

import argparse
import datetime as dt
import socket
import struct
import sys
import time

NTP_EPOCH_DELTA = 2208988800      # 1900-01-01 到 1970-01-01 的秒数


def _force_utf8():
    """让中文在管道/重定向（Windows 默认 GBK）下也不乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def build_request():
    """48 字节 SNTP 客户端请求：LI=0, VN=3, Mode=3(client)。"""
    return bytes([0x1B]) + bytes(47)


def unix_to_ntp(ts):
    """Unix 时间戳 -> (NTP 秒, 32 位小数部分)。"""
    sec = int(ts) + NTP_EPOCH_DELTA
    frac = int((ts - int(ts)) * (1 << 32))
    return sec, frac


def ntp_to_unix(sec, frac):
    return (sec - NTP_EPOCH_DELTA) + frac / float(1 << 32)


def parse_response(data, t0, t3):
    """解析服务器应答，返回 (offset, delay, t1, t2)。"""
    if len(data) < 48:
        raise ValueError("应答长度 %d 字节，不足 48" % len(data))
    mode = data[0] & 0x07
    stratum = data[1]
    if mode not in (4, 5):
        raise ValueError("应答模式异常 mode=%d（应为 4=server 或 5=broadcast）" % mode)
    if stratum == 0:
        raise ValueError("服务器 stratum=0（Kiss-of-Death），拒绝服务")
    t1 = ntp_to_unix(*struct.unpack("!II", data[32:40]))
    t2 = ntp_to_unix(*struct.unpack("!II", data[40:48]))
    offset = ((t1 - t0) + (t2 - t3)) / 2.0
    delay = (t3 - t0) - (t2 - t1)
    return offset, delay, t1, t2


def query(server, timeout, port=123):
    """发一次 SNTP 请求，返回 (offset, delay, t1, t2, t0, t3)。"""
    addr = (socket.gethostbyname(server), port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        t0 = time.time()
        sock.sendto(build_request(), addr)
        data, _ = sock.recvfrom(1024)
        t3 = time.time()
    finally:
        sock.close()
    offset, delay, t1, t2 = parse_response(data, t0, t3)
    return offset, delay, t1, t2, t0, t3


def report(offset, delay, t2, t3):
    print("  时钟偏差    : %+.6f s  （正数 = 本地比服务器慢）" % offset)
    print("  往返延迟    : %.6f s" % delay)
    srv = dt.datetime.fromtimestamp(t2, dt.timezone.utc)
    print("  服务器时刻  : %s UTC" % srv.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
    print("  本地时刻    : %s" %
          dt.datetime.fromtimestamp(t3).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
    corrected = t3 + offset
    print("  校正后本地  : %s" %
          dt.datetime.fromtimestamp(corrected).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])


def run_demo():
    """构造已知偏差的应答验证解析/计算，全离线。"""
    true_offset = 123.456           # 服务器比本地快 123.456 秒
    oneway = 0.05                   # 单程网络延迟
    t0 = time.time()
    t1 = t0 + oneway + true_offset  # 服务器收到（服务器时标）
    t2 = t1                         # 服务器立即回应
    t3 = t0 + 2 * oneway            # 本地收到
    pkt = bytearray(48)
    pkt[0] = 0x24                   # LI=0, VN=4, Mode=4(server)
    pkt[1] = 2                      # stratum=2
    struct.pack_into("!II", pkt, 32, *unix_to_ntp(t1))
    struct.pack_into("!II", pkt, 40, *unix_to_ntp(t2))
    offset, delay, _, _ = parse_response(bytes(pkt), t0, t3)
    print("[demo] 构造应答：服务器比本地快 %.3f s，单程延迟 %.3f s" %
          (true_offset, oneway))
    print("[demo] 解析得  ：偏差 %+.6f s，往返 %.6f s" % (offset, delay))
    err_off = abs(offset - true_offset)
    err_dly = abs(delay - 2 * oneway)
    print("[demo] 误差    ：偏差 %.2e s，往返 %.2e s" % (err_off, err_dly))
    if err_off > 1e-3 or err_dly > 1e-3:
        print("[demo] 自测失败！")
        return 1
    print("[demo] 自测通过。")
    return 0


def apply_windows(offset):
    """把 offset 校正到 Windows 系统时钟（写 UTC，需管理员权限）。"""
    import ctypes

    class SYSTEMTIME(ctypes.Structure):
        _fields_ = [("wYear", ctypes.c_ushort), ("wMonth", ctypes.c_ushort),
                    ("wDayOfWeek", ctypes.c_ushort), ("wDay", ctypes.c_ushort),
                    ("wHour", ctypes.c_ushort), ("wMinute", ctypes.c_ushort),
                    ("wSecond", ctypes.c_ushort),
                    ("wMilliseconds", ctypes.c_ushort)]

    corrected = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=offset)
    st = SYSTEMTIME(corrected.year, corrected.month,
                    (corrected.weekday() + 1) % 7,   # Windows: 周日=0（实际被忽略）
                    corrected.day, corrected.hour, corrected.minute,
                    corrected.second, corrected.microsecond // 1000)
    if not ctypes.windll.kernel32.SetSystemTime(ctypes.byref(st)):
        code = ctypes.windll.kernel32.GetLastError()
        print("校正失败（错误码 %d）：通常需要以管理员身份运行。" % code)
        return 1
    print("已把 Windows 系统时钟校正 %+.6f 秒。" % offset)
    return 0


def main(argv=None):
    _force_utf8()
    p = argparse.ArgumentParser(
        description="SNTP 对时：测算本地时钟偏差，可选校正 Windows 系统时钟")
    p.add_argument("--server", default="ntp.aliyun.com",
                   help="NTP 服务器，默认 ntp.aliyun.com")
    p.add_argument("--port", type=int, default=123)
    p.add_argument("--timeout", type=float, default=5.0,
                   help="超时秒数，默认 5")
    p.add_argument("--demo", action="store_true",
                   help="离线自测：解析伪造的服务器应答")
    p.add_argument("--apply", action="store_true",
                   help="把偏差校正到 Windows 系统时钟（需管理员）")
    p.add_argument("--yes", action="store_true", help="--apply 时跳过确认")
    args = p.parse_args(argv)

    if args.demo:
        return run_demo()

    try:
        offset, delay, t1, t2, t0, t3 = query(args.server, args.timeout,
                                              args.port)
    except socket.gaierror as exc:
        print("无法解析服务器地址 %s：%s" % (args.server, exc), file=sys.stderr)
        return 2
    except (socket.timeout, OSError) as exc:
        print("查询 %s 失败：%s" % (args.server, exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print("服务器应答异常：%s" % exc, file=sys.stderr)
        return 2

    report(offset, delay, t2, t3)

    if args.apply:
        if not sys.platform.startswith("win"):
            print("当前仅实现 Windows 的系统时钟校正。", file=sys.stderr)
            return 1
        if not args.yes:
            try:
                ans = input("将修改系统时钟（需管理员权限），确认？[y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = ""
            if ans not in ("y", "yes"):
                print("已取消。")
                return 0
        return apply_windows(offset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
