#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hash-watch.py -- 轮询监视指定文件的哈希, 一旦变化立即打印告警。

用途:
    以 --interval 秒为周期反复计算目标文件的 --algo 摘要并与上次
    比较; 一旦摘要变化, 立即打印 ALERT 行、时间戳以及新旧摘要。
    注意: 两次轮询之间发生的多次修改只能观察到最终状态。
    适合监视配置文件、巡检脚本、防篡改抽查等场景。Ctrl+C 随时
    停止(返回 0); 文件一时不可读会打印 WARN 并保持旧基线继续
    监视; 用法错误返回 2。

用法:
    python -I hash-watch.py <文件> [--interval 1.0] [--algo sha256] [--loops 0]

示例:
    $ python -I hash-watch.py C:/WebRoot/index.html --interval 2
    WATCHING C:/WebRoot/index.html algo=sha256 interval=2s
    baseline  e3b0c44298fc...
    [2026-11-02 10:00:30] ALERT #1: file changed!
      old sha256 e3b0c44298fc...
      new sha256 84a51689e3b0...
"""

import argparse
import datetime
import hashlib
import sys
import time

CHUNK = 1 << 20


def digest_of(path, algo):
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="hash-watch.py",
        description="Poll a file's hash and alert (with old/new digests) as soon as it changes.")
    parser.add_argument("file", help="file to watch")
    parser.add_argument("-i", "--interval", type=float, default=1.0,
                        help="seconds between polls (default: 1.0)")
    parser.add_argument("-a", "--algo", default="sha256",
                        help="hash algorithm, e.g. md5/sha1/sha256/sha512 (default: sha256)")
    parser.add_argument("-l", "--loops", type=int, default=0,
                        help="number of polls before exiting; 0 = watch forever (default: 0)")
    args = parser.parse_args(argv)

    if args.interval <= 0:
        parser.error("--interval must be > 0")
    try:
        hashlib.new(args.algo)
    except (ValueError, TypeError):
        parser.error("unknown hash algorithm: %s" % args.algo)
    if args.loops < 0:
        parser.error("--loops must be >= 0")

    last = None
    announced = False
    changes = 0
    done = 0
    try:
        while args.loops == 0 or done < args.loops:
            cur = None
            try:
                cur = digest_of(args.file, args.algo)
            except OSError as exc:
                print("WARN %s: cannot read %s (%s); keeping previous baseline"
                      % (time.strftime("%H:%M:%S"), args.file, exc), flush=True)

            if not announced:
                print("WATCHING %s algo=%s interval=%gs"
                      % (args.file, args.algo, args.interval), flush=True)
                announced = True
            if cur is None:
                pass  # unreadable this round; keep previous baseline
            elif last is None:
                print("baseline  %s" % cur, flush=True)
                last = cur
            elif cur != last:
                changes += 1
                stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print("[%s] ALERT #%d: file changed!" % (stamp, changes), flush=True)
                print("  old %s %s" % (args.algo, last), flush=True)
                print("  new %s %s" % (args.algo, cur), flush=True)
                last = cur
            done += 1
            if args.loops == 0 or done < args.loops:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("stopped by user after %d poll(s), %d change(s)" % (done, changes),
              flush=True)
    else:
        print("done after %d poll(s), %d change(s)" % (done, changes), flush=True)
    return 0


if __name__ == "__main__":
    _utf8_stdio()
    sys.exit(main())
