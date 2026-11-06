#!/usr/bin/env python3
r"""千工具军火库 GUI — 依照网页版 index.html 的视觉设计实现的桌面端。

布局: 渐变 Hero 头图 → 工具栏（搜索 + 分类胶囊）→ 卡片瀑布流（虚拟渲染）→ 右侧详情/运行台。
配色与网页一致: 底 #f5f6f8, 卡片 #ffffff, 主蓝 #3b5bdb, 墨色 #1c2433。
数据: 启动时扫描 tools\*.py 解析 docstring 首行, catalog.json（slug → {name, category, summary}）
提供中文名与中文分类；运行模式: 军火库.exe --run-tool <tool.py> ...（打包态隐藏入口）。
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

APP_DIR = Path(getattr(sys, "_MEIPASS2", Path(__file__).parent)).resolve()
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
_env_tools = os.environ.get("ARMORY_TOOLS_DIR")
if _env_tools:
    TOOLS_DIR = Path(_env_tools)
elif (APP_DIR / "tools").is_dir() or getattr(sys, "frozen", False):
    TOOLS_DIR = APP_DIR / "tools"
else:
    TOOLS_DIR = APP_DIR.parent / "tools"
CATALOG_PATH = APP_DIR / "catalog.json"

DEFAULT_CATEGORY = "其他"
RUN_TIMEOUT = 120
DOC_RE = re.compile(r'^r?"""(.*)$', re.M)

# ---- 网页配色 ----
BG = "#f5f6f8"
CARD = "#ffffff"
INK = "#1c2433"
MUTED = "#6b7280"
ACCENT = "#3b5bdb"
ACCENT_DARK = "#3350c4"
ACCENT_SOFT = "#eef1fd"
LINE = "#e6e8ee"
SLUG_BG = "#f3f5ff"
DESC = "#4b5563"
HERO_FROM = (0x1E, 0x2A, 0x52)
HERO_MID = (0x3B, 0x5B, 0xDB)
HERO_TO = (0x5F, 0x7A, 0xE8)
SELECT_BG = "#f8f9ff"
CONSOLE_BG = "#fbfcfe"
FONT = "Microsoft YaHei UI"
MONO = "Consolas"

CARD_W, CARD_H, GAP, PAD = 352, 122, 14, 10


def _lerp(c1: tuple, c2: tuple, t: float) -> str:
    return "#%02x%02x%02x" % tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))


def parse_tool(path: Path) -> dict:
    """从工具文件 docstring 首行提取中文说明（兼容三种首行格式）。"""
    slug = path.stem
    desc = name = ""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
        m = DOC_RE.search(head)
        if m:
            line1 = m.group(1).strip()
            desc = line1
            cleaned = re.sub(rf"^\s*{re.escape(slug)}(\.py)?\s*", "", line1)
            cleaned = re.sub(r"^\s*[（(][^（）()]*[）)]\s*", "", cleaned)
            cleaned = re.sub(r"^\s*-{2,}\s*", "", cleaned)
            segs = [s.strip() for s in re.split(r"\s*——\s*|\s*—\s*|\s+--\s+|\s+-\s+", cleaned) if s.strip(" .。")]
            for seg in segs:
                cand = re.split(r"[，,（(：:]", seg)[0].strip(" .。")
                if cand and not cand.startswith("."):
                    name = cand
                    break
    except OSError:
        pass
    return {"slug": slug, "desc": desc, "name": name}


def load_tools() -> dict[str, dict]:
    """扫描 tools 目录, 合并 catalog.json 元数据。"""
    catalog: dict = {}
    if CATALOG_PATH.exists():
        try:
            catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            catalog = {}
    tools: dict[str, dict] = {}
    if TOOLS_DIR.is_dir():
        for py in sorted(TOOLS_DIR.glob("*.py")):
            if not py.is_file():
                continue
            info = parse_tool(py)
            meta = catalog.get(info["slug"], {})
            tools[info["slug"]] = {
                "slug": info["slug"],
                "name": meta.get("name") or info["name"] or info["slug"],
                "summary": meta.get("summary") or info["desc"],
                "category": meta.get("category") or DEFAULT_CATEGORY,
                "path": str(py),
            }
    return tools


class ArmoryApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("千工具军火库")
        self.root.geometry("1280x800")
        self.root.configure(bg=BG)
        self.tools = load_tools()
        self.catalog = sorted(self.tools.values(), key=lambda t: (t["category"], t["name"]))
        self.visible: list[dict] = list(self.catalog)
        self.selected: str | None = None
        self.active_cat = "全部"
        self.keyword = ""
        self._rendered: dict[int, tk.Frame] = {}
        self._render_rows: tuple[int, int] = (-1, -1)
        self.proc: subprocess.Popen | None = None
        self.out_queue: queue.Queue = queue.Queue()
        self._build_hero()
        self._build_toolbar()
        self._build_main()
        self._layout_chips()
        self._apply_filter()
        self.root.after(80, self._drain_output)
        self.root.bind("<Configure>", self._on_resize)

    # ---------- Hero ----------
    def _build_hero(self) -> None:
        self.hero = tk.Canvas(self.root, height=118, highlightthickness=0, bg="#1e2a52")
        self.hero.pack(fill="x")
        self._paint_hero()
        self.hero.create_text(24, 34, anchor="w", text="千工具军火库",
                              fill="#ffffff", font=(FONT, 21, "bold"))
        n = len(self.tools)
        cats = len({t["category"] for t in self.tools.values()})
        self.hero.create_text(24, 66, anchor="w",
                              text=f"911 个纯标准库命令行工具 · {cats} 个类目 · 复验官逐个实测 100% 通过",
                              fill="#dbe4ff", font=(FONT, 10))
        self.hero.create_text(24, 90, anchor="w",
                              text="数据来源: tools\\ 目录 + catalog.json · 双击卡片或在右侧运行台执行",
                              fill="#aab8f0", font=(FONT, 9))

    def _paint_hero(self) -> None:
        self.hero.delete("grad")
        w = max(self.hero.winfo_width(), 1280)
        bands = 96
        for i in range(bands):
            t = i / (bands - 1)
            color = _lerp(HERO_FROM, HERO_MID, min(1.0, t * 1.6)) if t < 0.625 else _lerp(HERO_MID, HERO_TO, (t - 0.625) / 0.375)
            x0 = round(w * i / bands)
            x1 = round(w * (i + 1) / bands) + 1
            self.hero.create_rectangle(x0, 0, x1, 118, fill=color, outline="", tags=("grad",))
        self.hero.tag_lower("grad")

    # ---------- Toolbar ----------
    def _build_toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        bar.pack(fill="x", padx=16, pady=(10, 0))
        inner = tk.Frame(bar, bg=CARD)
        inner.pack(fill="x", padx=14, pady=10)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._on_search())
        self.search_entry = tk.Entry(inner, textvariable=self.search_var, font=(FONT, 11),
                                     bg="#fafbfc", fg=INK, insertbackground=ACCENT,
                                     relief="flat", highlightthickness=1,
                                     highlightbackground=LINE, highlightcolor=ACCENT)
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self._set_placeholder("🔍  搜索名称、slug 或说明…")
        self.search_entry.bind("<FocusIn>", lambda _e: self._clear_placeholder())
        self.search_entry.bind("<FocusOut>", lambda _e: self._restore_placeholder())
        self.count_var = tk.StringVar()
        tk.Label(inner, textvariable=self.count_var, bg=CARD, fg=MUTED, font=(FONT, 10)).pack(side="left", padx=(12, 0))
        self.chips_frame = tk.Frame(bar, bg=CARD)
        self.chips_frame.pack(fill="x", padx=14, pady=(0, 10))
        self.chip_labels: list[tk.Label] = []

    def _set_placeholder(self, text: str) -> None:
        self.search_entry.insert(0, text)
        self.search_entry.configure(fg="#9aa2b1")
        self._placeholder = True

    def _clear_placeholder(self) -> None:
        if getattr(self, "_placeholder", False):
            self.search_entry.delete(0, "end")
            self.search_entry.configure(fg=INK)
            self._placeholder = False

    def _restore_placeholder(self) -> None:
        if not self.search_var.get():
            self._set_placeholder("🔍  搜索名称、slug 或说明…")

    def _on_search(self) -> None:
        if not hasattr(self, "count_var"):
            return
        text = self.search_var.get()
        if text == "🔍  搜索名称、slug 或说明…":
            return
        self.keyword = text.strip().lower()
        self._apply_filter()

    def _layout_chips(self) -> None:
        for c in self.chip_labels:
            c.destroy()
        self.chip_labels = []
        counts: dict[str, int] = {}
        for t in self.tools.values():
            counts[t["category"]] = counts.get(t["category"], 0) + 1
        cats = ["全部"] + sorted(counts, key=lambda c: (-counts[c], c))
        cols = 8
        for i, cat in enumerate(cats):
            n = len(self.tools) if cat == "全部" else counts[cat]
            lab = tk.Label(self.chips_frame, text=f"{cat} {n}", font=(FONT, 9),
                           padx=11, pady=3, cursor="hand2")
            lab.grid(row=i // cols, column=i % cols, sticky="w", padx=(0, 6), pady=2)
            lab.bind("<Button-1>", lambda _e, c=cat: self._on_chip(c))
            self.chip_labels.append(lab)
        self._style_chips()

    def _style_chips(self) -> None:
        for lab in self.chip_labels:
            text = lab.cget("text")
            active = text.split(" ")[0] == self.active_cat or (self.active_cat == "全部" and text.startswith("全部"))
            if active:
                lab.configure(bg=ACCENT, fg="#ffffff", highlightthickness=0)
            else:
                lab.configure(bg=CARD, fg=INK, highlightthickness=1, highlightbackground=LINE)

    def _on_chip(self, cat: str) -> None:
        self.active_cat = cat
        self._style_chips()
        self._apply_filter()

    # ---------- 主区 ----------
    def _build_main(self) -> None:
        pane = ttk.Panedwindow(self.root, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=16, pady=(12, 14))

        # 左: 卡片瀑布流
        grid_wrap = tk.Frame(pane, bg=BG)
        self.canvas = tk.Canvas(grid_wrap, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(grid_wrap, orient="vertical", command=self._on_scrollbar)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._relayout())
        self.root.bind_all("<MouseWheel>", self._on_wheel)
        pane.add(grid_wrap, weight=3)

        # 右: 详情 / 运行台
        detail = tk.Frame(pane, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        pane.add(detail, weight=2)
        head = tk.Frame(detail, bg=CARD)
        head.pack(fill="x", padx=16, pady=(14, 4))
        self.d_name = tk.Label(head, text="未选择工具", bg=CARD, fg=INK, font=(FONT, 14, "bold"), anchor="w")
        self.d_name.pack(side="left")
        self.d_cat = tk.Label(head, text="", bg=ACCENT_SOFT, fg=MUTED, font=(FONT, 9), padx=8, pady=2)
        self.d_cat.pack(side="right")
        self.d_slug = tk.Label(detail, text="", bg=SLUG_BG, fg=ACCENT, font=(MONO, 9), padx=8, pady=2)
        self.d_slug.pack(anchor="w", padx=16)
        self.d_desc = tk.Label(detail, text="在左侧点击任意工具卡片，查看说明并在此运行。",
                               bg=CARD, fg=DESC, font=(FONT, 10), wraplength=380, justify="left", anchor="w")
        self.d_desc.pack(fill="x", padx=16, pady=(8, 4))
        self.d_usage = tk.Text(detail, height=9, wrap="word", relief="flat", bg="#fafbfc",
                               fg=INK, font=(MONO, 9), highlightthickness=1, highlightbackground=LINE,
                               state="disabled")
        self.d_usage.pack(fill="both", expand=True, padx=16, pady=(6, 6))
        runbar = tk.Frame(detail, bg=CARD)
        runbar.pack(fill="x", padx=16)
        tk.Label(runbar, text="参数", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.args_var = tk.StringVar()
        tk.Entry(runbar, textvariable=self.args_var, font=(MONO, 10), relief="flat",
                 highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT,
                 bg="#fafbfc", fg=INK, insertbackground=INK).pack(side="left", fill="x", expand=True, padx=8, ipady=3)
        self.run_btn = tk.Button(runbar, text="运行", command=self._run_tool, font=(FONT, 10, "bold"),
                                 bg=ACCENT, fg="#ffffff", activebackground=ACCENT_DARK, activeforeground="#ffffff",
                                 relief="flat", bd=0, padx=16, pady=3, cursor="hand2")
        self.run_btn.pack(side="left")
        self.stop_btn = tk.Button(runbar, text="停止", command=self._stop_tool, font=(FONT, 10),
                                  bg=CARD, fg=MUTED, activebackground="#f0f1f4", relief="flat",
                                  bd=1, highlightbackground=LINE, padx=12, pady=3,
                                  cursor="hand2", state="disabled")
        self.stop_btn.pack(side="left", padx=(6, 0))
        self.output = tk.Text(detail, height=9, wrap="none", relief="flat", bg=CONSOLE_BG,
                              fg=INK, font=(MONO, 9), highlightthickness=1, highlightbackground=LINE,
                              insertbackground=INK)
        osb = ttk.Scrollbar(detail, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=osb.set)
        self.output.pack(side="bottom", fill="both", expand=True, padx=16, pady=(8, 14))
        osb.pack(side="bottom", fill="x", padx=16, pady=(0, 14))
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(detail, textvariable=self.status_var, bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side="bottom", anchor="w", padx=16, pady=(0, 4))

    # ---------- 过滤与卡片网格（虚拟渲染） ----------
    def _apply_filter(self) -> None:
        cat = self.active_cat
        kw = self.keyword
        rows = []
        for t in self.catalog:
            if cat != "全部" and t["category"] != cat:
                continue
            if kw and kw not in (t["name"] + t["slug"] + t["summary"]).lower():
                continue
            rows.append(t)
        self.visible = rows
        self.count_var.set(f"共 {len(self.tools)} 个 · 显示 {len(rows)} 个")
        self._clear_cards()
        self._relayout(reset_scroll=True)

    def _cols(self) -> int:
        w = self.canvas.winfo_width() or 1280
        return max(1, (w - PAD * 2 + GAP) // (CARD_W + GAP))

    def _relayout(self, reset_scroll: bool = False) -> None:
        cols = self._cols()
        if cols != getattr(self, "_cols_cached", cols):
            self._clear_cards()
        rows = (len(self.visible) + cols - 1) // cols
        self._cols_cached = cols
        self.canvas.configure(scrollregion=(0, 0, 0, rows * (CARD_H + GAP) + PAD))
        if reset_scroll:
            self.canvas.yview_moveto(0)
        self._sync_render()

    def _on_resize(self, e) -> None:
        if e.widget is not self.root:
            return  # 子控件几何变化（建卡/滚动）也会冒泡到 toplevel，忽略之
        if e.width != getattr(self, "_last_root_w", None):
            self._last_root_w = e.width
            if self.hero.winfo_width() > 1:
                self._paint_hero()
            if hasattr(self, "_cols_cached") and self._cols() != self._cols_cached:
                self._relayout()

    def _on_scrollbar(self, *args) -> None:
        """滚动条 command 协议: moveto <frac> / scroll <n> units|pages。"""
        if not args:
            return
        if args[0] == "moveto":
            self.canvas.yview_moveto(float(args[1]))
        elif args[0] == "scroll":
            self.canvas.yview_scroll(int(args[1]), args[2])
        self._sync_render()

    def _on_wheel(self, e) -> None:
        # 只接管卡片流区域: 沿父链判断指针下的控件是否属于 Canvas
        # （卡片 Frame 覆盖在 Canvas 上，滚轮事件先落到它们身上）
        p = getattr(e, "widget", None)
        while p is not None and p is not self.root:
            if p is self.canvas:
                self.canvas.yview_scroll(-1 * (e.delta // 120), "units")
                self._sync_render()
                return
            p = getattr(p, "master", None)
        # 详情面板的 Text 等控件保持各自的原生滚动

    def _visible_range(self) -> tuple[int, int]:
        cols = self._cols_cached
        try:
            first, last = self.canvas.yview()
        except tk.TclError:
            first, last = 0.0, 1.0
        total = len(self.visible)
        rows = (total + cols - 1) // cols
        lo_row = max(0, int(first * rows) - 1)
        hi_row = min(rows - 1, int(last * rows) + 1)
        lo = lo_row * cols
        hi = min(total - 1, (hi_row + 1) * cols - 1)
        return lo, max(lo, hi)

    def _sync_render(self) -> None:
        if not self.visible:
            self._clear_cards()
            return
        lo, hi = self._visible_range()
        if (lo, hi) == self._render_rows:
            return
        self._render_rows = (lo, hi)
        cols = self._cols_cached
        for idx in list(self._rendered):
            if not (lo <= idx <= hi):
                self._rendered.pop(idx).destroy()
        for idx in range(lo, hi + 1):
            if idx in self._rendered or idx >= len(self.visible):
                continue
            t = self.visible[idx]
            r, c = divmod(idx, cols)
            x = PAD + c * (CARD_W + GAP)
            y = PAD + r * (CARD_H + GAP)
            frame = self._make_card(t)
            self.canvas.create_window(x, y, window=frame, anchor="nw", width=CARD_W, height=CARD_H)
            self._rendered[idx] = frame

    def _clear_cards(self) -> None:
        for f in self._rendered.values():
            f.destroy()
        self._rendered.clear()
        self._render_rows = (-1, -1)

    def _make_card(self, t: dict) -> tk.Frame:
        sel = self.selected == t["slug"]
        frame = tk.Frame(self.canvas, bg=SELECT_BG if sel else CARD,
                         highlightthickness=2 if sel else 1,
                         highlightbackground=ACCENT if sel else LINE,
                         highlightcolor=ACCENT)
        top = tk.Frame(frame, bg=frame.cget("bg"))
        top.pack(fill="x", padx=14, pady=(10, 0))
        name_lab = tk.Label(top, text=t["name"][:18], bg=top.cget("bg"), fg=INK,
                            font=(FONT, 11, "bold"), anchor="w")
        name_lab.pack(side="left")
        tk.Label(top, text=t["category"][:6], bg=ACCENT_SOFT, fg=MUTED,
                 font=(FONT, 8), padx=6, pady=1).pack(side="right")
        tk.Label(frame, text=t["slug"], bg=SLUG_BG, fg=ACCENT, font=(MONO, 8),
                 padx=6, pady=1).pack(anchor="w", padx=14, pady=(5, 0))
        tk.Label(frame, text=t["summary"][:52], bg=frame.cget("bg"), fg=DESC,
                 font=(FONT, 9), wraplength=CARD_W - 30, justify="left", anchor="nw").pack(fill="x", padx=14, pady=(4, 8))
        for w in (frame, top, name_lab):
            w.bind("<Button-1>", lambda _e, s=t["slug"]: self._select(s))
        return frame

    def _select(self, slug: str) -> None:
        self.selected = slug
        old = self._render_rows
        self._render_rows = (-1, -1)
        self._sync_render()
        self._render_rows = old
        self._sync_render()
        t = self.tools.get(slug)
        if not t:
            return
        self.d_name.configure(text=t["name"])
        self.d_cat.configure(text=t["category"])
        self.d_slug.configure(text=t["slug"])
        self.d_desc.configure(text=t["summary"])
        try:
            head = Path(t["path"]).read_text(encoding="utf-8", errors="replace")[:3600]
        except OSError:
            head = "(无法读取文件)"
        self.d_usage.configure(state="normal")
        self.d_usage.delete("1.0", "end")
        self.d_usage.insert("1.0", head)
        self.d_usage.configure(state="disabled")

    # ---------- 运行 ----------
    def _run_tool(self) -> None:
        if not self.selected:
            self.status_var.set("请先点击选择一个工具卡片")
            return
        if self.proc and self.proc.poll() is None:
            self.status_var.set("已有工具在运行，请先停止")
            return
        t = self.tools[self.selected]
        args = self.args_var.get().split()
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--run-tool", t["path"], *args]
        else:
            cmd = [sys.executable, t["path"], *args]
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        self.output.delete("1.0", "end")
        self._append_out(f"$ {t['slug']} {' '.join(args)}\n")
        self.status_var.set("运行中…")
        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        started = time.time()
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                         errors="replace", env=env, cwd=str(TOOLS_DIR.parent))
        except OSError as exc:
            self._append_out(f"[启动失败] {exc}\n")
            self._finish_run(0.0, -1)
            return
        threading.Thread(target=self._pump, args=(self.proc, started), daemon=True).start()

    def _pump(self, proc: subprocess.Popen, started: float) -> None:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                self.out_queue.put(line)
            code = proc.wait(timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            self.out_queue.put(f"\n[超时 {RUN_TIMEOUT}s, 已终止]\n")
            code = -9
        self.out_queue.put(f"\n__DONE__{code}__{time.time() - started:.1f}")

    def _drain_output(self) -> None:
        try:
            while True:
                item = self.out_queue.get_nowait()
                if item.strip().startswith("__DONE__"):
                    _tag, code, secs = item.strip().strip("_").split("__")
                    self._finish_run(float(secs), int(code))
                else:
                    self._append_out(item)
        except queue.Empty:
            pass
        self.root.after(80, self._drain_output)

    def _append_out(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")

    def _finish_run(self, secs: float, code: int) -> None:
        self.run_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_var.set(f"结束 (用时 {secs:.1f}s, 退出码 {code})")

    def _stop_tool(self) -> None:
        if self.proc and self.proc.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True)
            else:
                self.proc.kill()
            self.status_var.set("已停止")


def run_tool_child(tool_path: str, argv: list[str]) -> int:
    """打包模式隐藏入口: 在本进程内执行单个工具脚本 (--run-tool)。"""
    sys.argv = [os.path.basename(tool_path), *argv]
    import runpy
    try:
        runpy.run_path(tool_path, run_name="__main__")
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--run-tool":
        sys.exit(run_tool_child(sys.argv[2], sys.argv[3:]))
    root = tk.Tk()
    ArmoryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
