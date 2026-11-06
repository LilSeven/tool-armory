"""按内容重命名 (content-title-rename)

用途：读取文本 / HTML / Markdown 文件的标题行（Markdown 一级标题、HTML <title> 标签、
或首个非空文本行）作为新文件名，保留原扩展名。默认只预演，加 --apply 才真正重命名。

用法:
    python content-title-rename.py FILE [FILE ...] [--apply] [--max-len N]

示例:
    python content-title-rename.py notes/2024-05-01.md --apply
    python content-title-rename.py page.html readme.txt --max-len 60

规则:
    1. Markdown: 首个 "# 标题" 行
    2. HTML:     首个 <title>...</title> 或 <h1>...</h1>
    3. 其他文本: 首个非空行
    标题会去掉文件名非法字符 \\ / : * ? " < > | 并截断到 --max-len。
"""

import argparse
import html.parser
import re
import sys
from pathlib import Path

ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]')


class _TitleParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self.h1 = None
        self._in = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if self.title is None and tag in ("title", "h1") and self._in is None:
            self._in = tag
            self._buf = []

    def handle_endtag(self, tag):
        if self._in == tag:
            text = "".join(self._buf).strip()
            if tag == "title":
                self.title = text or None
            elif self.h1 is None:
                self.h1 = text or None
            self._in = None

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)


def extract_title(text: str) -> str | None:
    """从文本内容中提取标题，返回去掉首尾空白后的字符串或 None。"""
    if re.search(r"<\s*html|<!DOCTYPE", text, re.I):
        p = _TitleParser()
        try:
            p.feed(text)
        except Exception:
            pass
        if p.title or p.h1:
            return p.title or p.h1
    for line in text.splitlines():
        m = re.match(r"\s*#\s+(.+?)\s*#*\s*$", line)
        if m:  # Markdown 一级标题
            return m.group(1)
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return None


def sanitize(title: str, max_len: int) -> str | None:
    t = ILLEGAL.sub(" ", title).strip().strip(".")
    while "  " in t:
        t = t.replace("  ", " ")
    if not t:
        return None
    return t[:max_len]


def plan_rename(path: Path, max_len: int) -> tuple[Path, Path] | tuple[None, None]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"[跳过] {path}: 无法读取 ({e})", file=sys.stderr)
        return None, None
    title = extract_title(text)
    if not title:
        print(f"[跳过] {path}: 未找到标题", file=sys.stderr)
        return None, None
    clean = sanitize(title, max_len)
    if not clean or clean == path.stem:
        return None, None
    return path, path.with_name(clean + path.suffix)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="按文件内容中的标题重命名文件（默认预演）")
    ap.add_argument("files", nargs="+", help="目标文件")
    ap.add_argument("--apply", action="store_true", help="实际执行重命名（默认只预演）")
    ap.add_argument("--max-len", type=int, default=80, help="新文件名主干最大长度（默认 80）")
    ns = ap.parse_args(argv)

    ok = 0
    for f in ns.files:
        p = Path(f)
        if not p.is_file():
            print(f"[跳过] {p}: 不是文件", file=sys.stderr)
            continue
        old, new = plan_rename(p, ns.max_len)
        if old is None:
            continue
        if old == new:
            print(f"[无变化] {old.name}")
            continue
        if new.exists() and new != old:
            print(f"[冲突] {old.name} -> {new.name}: 目标已存在，跳过", file=sys.stderr)
            continue
        if ns.apply:
            old.rename(new)
            print(f"[已改名] {old.name} -> {new.name}")
        else:
            print(f"[预演] {old.name} -> {new.name}")
        ok += 1
    print(f"共处理 {ok} 个文件" + ("" if ns.apply else "（预演模式，加 --apply 生效）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
