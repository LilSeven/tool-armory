#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作者贡献行数 (blame-loc-stats) —— 解析 git blame 输出, 按作者统计行数贡献分布。

用途:
    解析 `git blame --porcelain / --line-porcelain` 的文本输出,
    按作者汇总其贡献的行数与占比, 以表格 + ASCII 条形图展示。

输入方式(三选一):
    1. 管道:  git blame --line-porcelain src/main.py | python blame-loc-stats.py
    2. 文件:  python blame-loc-stats.py blame.txt
    3. 自动:  python blame-loc-stats.py --run src/main.py   (内部代为执行 git blame)

示例命令:
    git blame --line-porcelain -- src/ | python blame-loc-stats.py --top 10
    python blame-loc-stats.py blame.txt --sort name
    python blame-loc-stats.py --run src/main.py --json
    python blame-loc-stats.py --self-test

退出码:
    0 = 成功; 1 = 无有效输入或 git 执行失败; 2 = 参数错误
"""

import argparse
import json
import re
import subprocess
import sys

SHA_LINE_RE = re.compile(r"^[0-9a-f]{40} \d+ \d+")


def _force_utf8_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _disp_width(s):
    return sum(2 if ord(c) > 0x2E7F else 1 for c in s)


def _pad(s, width):
    return s + " " * max(0, width - _disp_width(s))


def parse_blame(lines):
    """解析 porcelain blame 输出, 返回 {作者: 行数}。

    - "\t" 开头的行是代码内容, 记到当前作者名下(尚无作者头时记 "(未知)");
    - "author <name>" 设置当前作者(--line-porcelain 每行都有, --porcelain 每块一次,
      块内后续记录沿用当前作者);
    - "<40位sha> <原行号> <现行号>" 为记录起始行。
    """
    authors = {}
    current = None
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line.startswith("\t"):
            name = current if current is not None else "(未知)"
            authors[name] = authors.get(name, 0) + 1
        elif line.startswith("author "):
            current = line[len("author "):].strip() or "(无名)"
        elif SHA_LINE_RE.match(line):
            continue
    return authors


def render(authors, top=20, sort_key="lines"):
    """渲染作者贡献表, 返回多行字符串。"""
    if sort_key == "name":
        items = sorted(authors.items(), key=lambda kv: kv[0].lower())
    else:
        items = sorted(authors.items(), key=lambda kv: (-kv[1], kv[0]))
    total = sum(authors.values())
    shown = items if top <= 0 else items[:top]
    name_w = min(max([_disp_width(k) for k, _ in shown] + [8]), 40)
    max_v = max([v for _, v in shown] + [1])
    out = ["{} {} {}  bar".format(_pad("作者", name_w), "lines".rjust(8), "pct".rjust(6)),
           "-" * (name_w + 21)]
    for name, cnt in shown:
        pct = (cnt / total * 100) if total else 0.0
        bar_n = int(round(40 * cnt / max_v)) if cnt else 0
        if cnt > 0 and bar_n == 0:
            bar_n = 1
        out.append("{} {} {}%  {}".format(
            _pad(name, name_w), "{:>8,}".format(cnt), "{:>5.1f}".format(pct), "#" * bar_n))
    out.append("-" * (name_w + 21))
    out.append("合计 {:,} 行 / {} 位作者".format(total, len(authors)))
    return "\n".join(out)


def git_blame_lines(path, cwd=None):
    """执行 git blame --line-porcelain, 返回输出行列表; 失败返回 None。"""
    cmd = ["git", "blame", "--line-porcelain", "--", path]
    try:
        proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("错误: 未找到 git 命令, 无法执行 --run; 可改用管道输入。", file=sys.stderr)
        return None
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", "replace"))
        print("错误: git blame 执行失败(退出码 {})。".format(proc.returncode), file=sys.stderr)
        return None
    return proc.stdout.decode("utf-8", "replace").splitlines()


def run(args, parser):
    if args.run:
        lines = git_blame_lines(args.run, cwd=args.cwd)
        if lines is None:
            return 1
    elif args.files:
        lines = []
        for fp in args.files:
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    lines.extend(f)
            except OSError as e:
                print("错误: 无法读取 {}: {}".format(fp, e), file=sys.stderr)
                return 1
    elif not sys.stdin.isatty():
        lines = sys.stdin.read().splitlines()
    else:
        parser.error("缺少输入: 请提供文件参数、stdin 管道, 或用 --run PATH 代为执行 git blame")

    authors = parse_blame(lines)
    if not authors or sum(authors.values()) == 0:
        print("错误: 输入中未解析到任何 blame 行(期望 git blame --porcelain 输出)。", file=sys.stderr)
        return 1
    if args.json:
        total = sum(authors.values())
        data = [{"author": a, "lines": c, "pct": round(c / total * 100, 1)}
                for a, c in sorted(authors.items(), key=lambda kv: -kv[1])]
        print(json.dumps({"total_lines": total, "authors": data}, ensure_ascii=False, indent=2))
    else:
        print(render(authors, top=args.top, sort_key=args.sort))
    return 0


def self_test():
    """用合成的 porcelain 输出验证解析逻辑(不依赖 git)。"""
    a_sha, b_sha = "a" * 40, "b" * 40
    sample = "\n".join([
        # 块 1: --line-porcelain 风格, Alice 两行
        "{} 1 1 2".format(a_sha),
        "author Alice",
        "author-mail <alice@example.com>",
        "author-time 1700000000",
        "author-tz +0800",
        "committer Alice",
        "committer-mail <alice@example.com>",
        "committer-time 1700000000",
        "committer-tz +0800",
        "summary first commit",
        "filename a.py",
        "\tfirst line",
        "\tsecond line",
        # 块 2: 无 author 头的记录, 应沿用当前作者 Alice(--porcelain 块内语义)
        "{} 2 4 1".format(a_sha),
        "boundary",
        "filename a.py",
        "\tfourth line (沿用上一作者)",
        # 块 3: Bob 一行
        "{} 3 3 1".format(b_sha),
        "author Bob",
        "author-mail <bob@example.com>",
        "author-time 1700000001",
        "author-tz +0800",
        "committer Bob",
        "committer-mail <bob@example.com>",
        "committer-time 1700000001",
        "committer-tz +0800",
        "summary fix bug",
        "filename a.py",
        "\tthird line (fixed by Bob)",
        # 块 4: 内容里伪装的 author 行(有 \t 前缀)不应改变作者
        "{} 5 5 1".format(b_sha),
        "author Bob",
        "summary tricky",
        "filename a.py",
        "\tauthor Alice (这只是代码内容)",
    ])
    authors = parse_blame(sample.splitlines())
    assert authors == {"Alice": 3, "Bob": 2}, authors

    empty = parse_blame([])
    assert empty == {}, empty

    print("[blame-loc-stats 自测] porcelain 解析断言通过:", authors)
    print()
    print(render(authors, top=10))
    print("SELF-TEST OK")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="blame-loc-stats",
        description="作者贡献行数: 解析 git blame 输出, 按作者统计行数贡献分布。",
        epilog="示例: git blame --line-porcelain -- src/ | python blame-loc-stats.py --top 10")
    parser.add_argument("files", nargs="*", help="blame 输出文本文件(缺省读 stdin)")
    parser.add_argument("--run", metavar="PATH", help="对 PATH 代为执行 git blame --line-porcelain")
    parser.add_argument("--cwd", metavar="DIR", help="--run 时 git 的工作目录(默认当前目录)")
    parser.add_argument("--top", type=int, default=20, help="只显示前 N 位作者(默认 20, 0=全部)")
    parser.add_argument("--sort", choices=["lines", "name"], default="lines",
                        help="排序依据(默认按行数降序)")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出统计结果")
    parser.add_argument("--self-test", action="store_true", help="运行内置自测")
    _force_utf8_stdout()
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    return run(args, parser)


if __name__ == "__main__":
    sys.exit(main())
