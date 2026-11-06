#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""老板键伪装 —— 一键清屏假装在跑漫长的编译与测试日志。

清空屏幕后循环打印以假乱真的 configure/compile/link/test 流水日志，
进度条一路爬升，偶尔蹦出 warning；按任意键或 Ctrl+C 随时收场。

用法:
    python fake-compile.py                       # 一直跑，直到按键或 Ctrl+C
    python fake-compile.py --duration 300 --project my-app
    python fake-compile.py --no-clear --duration 2 --speed 6

选项:
    --project NAME   假装在构建的项目名（默认随机挑选）
    --duration SEC   最长运行秒数；缺省一直运行
    --speed FLOAT    日志速度倍率，>1 表示更快（默认 1.0）
    --no-clear       启动时不清屏（便于重定向调试）

示例命令:
    python -I fake-compile.py --duration 2 --no-clear --speed 6

退出码: 0 正常结束或按键/中断收场；2 参数错误。
"""
import argparse
import os
import random
import sys
import time

MODULES = ["core", "net", "ui", "db", "utils", "auth", "render", "io", "sched", "codec"]
SRCS = ["main", "util", "config", "socket", "parser", "worker",
        "cache", "shader", "model", "fixture"]
SUITES = ["core", "net.http", "db.pool", "util.str", "auth.session", "render.pipeline"]
CASES = ["basic", "timeout", "retry", "edge_case", "load", "cleanup", "roundtrip", "fallback"]
PROJECTS = ["quantum-leap", "hyperion", "night-build", "skyforge", "teapot-9000"]
COMPILER_PATHS = ["C:/mingw64/bin/g++.exe", "/usr/bin/c++", "/usr/bin/clang++"]
WARNINGS = [
    "unused variable 'tmp' [-Wunused-variable]",
    "implicit conversion loses integer precision [-Wconversion]",
    "comparison of integers of different signs [-Wsign-compare]",
    "deprecated declaration [-Wdeprecated-declarations]",
    "'struct Config' has no member named 'size_'",
]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="fake-compile", description="老板键伪装：假装在跑漫长的编译与测试")
    parser.add_argument("--project", help="假装构建的项目名（默认随机）")
    parser.add_argument("--duration", type=float, default=None,
                        help="最长运行秒数，缺省一直运行")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="日志速度倍率，>1 更快（默认 1.0）")
    parser.add_argument("--no-clear", action="store_true", help="启动时不清屏")
    args = parser.parse_args(argv)
    if args.duration is not None and args.duration < 0:
        parser.error("--duration 不能为负数")
    if args.speed <= 0:
        parser.error("--speed 必须大于 0")
    return args


def enable_ansi() -> None:
    """在 Windows 控制台尽量启用 ANSI 转义序列（其他平台无操作）。"""
    if os.name == "nt":
        os.system("")  # 触发 Windows 10+ 的 VT 处理
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass


def reconfigure_stdio() -> None:
    """尽量把标准流切到 UTF-8，避免中文在管道里触发编码异常。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def key_pressed() -> bool:
    """终端按下了任意键则返回 True（仅 stdin 为 tty 时生效）。"""
    if not sys.stdin.isatty():
        return False
    if os.name == "nt":
        try:
            import msvcrt
            return bool(msvcrt.kbhit())
        except Exception:
            return False
    try:
        import select
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if ready:
            sys.stdin.read(1)
            return True
    except Exception:
        return False
    return False


class FakeBuild:
    """按阶段随机生成一条条“可信”的构建日志。"""

    def __init__(self, rng: random.Random, project: str) -> None:
        self.rng = rng
        self.project = project
        self.percent = 0

    def _src(self) -> str:
        return f"src/{self.rng.choice(MODULES)}/{self.rng.choice(SRCS)}.cpp"

    def line_configure(self) -> str:
        rng = self.rng
        return rng.choice([
            f"-- The CXX compiler identification is GNU "
            f"{rng.randint(8, 13)}.{rng.randint(0, 5)}.{rng.randint(0, 9)}",
            "-- Detecting CXX compiler ABI info - done",
            f"-- Check for working CXX compiler: {rng.choice(COMPILER_PATHS)} - skipped",
            f"-- Found PythonInterp: 3.{rng.randint(8, 12)}.{rng.randint(0, 9)}",
            "-- Looking for pthread_create - found",
            f"-- Configuring done ({rng.uniform(0.4, 9.9):.1f} s)",
            "-- Generating done",
        ])

    def line_compile(self) -> str:
        rng = self.rng
        self.percent = min(100, self.percent + rng.randint(0, 4))
        roll = rng.random()
        if roll < 0.10:
            warn = rng.choice(WARNINGS)
            return (f"{self._src()}:{rng.randint(1, 400)}:{rng.randint(1, 90)}: "
                    f"warning: {warn}")
        if roll < 0.18:
            cc = rng.choice(("gcc", "g++", "clang++", "cc"))
            return f"{cc} -O2 -std=c++17 -Wall -c {self._src()} -o build/{rng.choice(SRCS)}.o"
        return (f"[{self.percent:3d}%] Building CXX object "
                f"CMakeFiles/{self.project}.dir/{self._src()}.o")

    def line_test(self) -> str:
        rng = self.rng
        roll = rng.random()
        if roll < 0.08:
            return "[----------] Global test environment set-up"
        if roll < 0.14:
            return f"[  PASSED  ] {rng.randint(4, 60)} tests."
        suite = rng.choice(SUITES)
        case = rng.choice(CASES)
        return f"[       OK ] {suite}.{case} ({rng.randint(1, 240)} ms)"


def build_lines(rng: random.Random, project: str):
    """无限生成日志行：configure -> compile -> link -> test -> 小结，循环往复。"""
    build = FakeBuild(rng, project)
    n = rng.randint(1000, 2000)
    while True:
        yield f"==== Build #{n} of {project} ===="
        for _ in range(rng.randint(4, 8)):
            yield build.line_configure()
        build.percent = 0
        for _ in range(rng.randint(25, 60)):
            yield build.line_compile()
        yield f"[100%] Linking CXX executable bin/{project}"
        yield f"Built target {project}"
        for _ in range(rng.randint(8, 24)):
            yield build.line_test()
        yield f"[  PASSED  ] {rng.randint(20, 120)} tests, 0 failures"
        n += 1


def main(argv=None) -> int:
    args = parse_args(argv)
    enable_ansi()
    reconfigure_stdio()
    rng = random.Random()
    project = args.project or rng.choice(PROJECTS)
    out = sys.stdout
    if not args.no_clear:
        out.write("\x1b[2J\x1b[H")
    deadline = time.monotonic() + args.duration if args.duration is not None else None
    start = time.monotonic()
    interrupted = False
    try:
        for line in build_lines(rng, project):
            out.write(line + "\n")
            out.flush()
            if key_pressed():
                interrupted = True
                break
            if deadline is not None and time.monotonic() >= deadline:
                break
            time.sleep(rng.uniform(0.04, 0.5) / args.speed)
    except KeyboardInterrupt:
        interrupted = True
    elapsed = time.monotonic() - start
    if interrupted:
        # 老板来了：立刻安静收场，不留多余输出
        try:
            out.write("\n")
            out.flush()
        except OSError:
            pass
    else:
        out.write(f"\nBUILD SUCCESSFUL  total time: {elapsed:.1f} s\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
