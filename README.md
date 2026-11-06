# 千工具军火库 · Tool Armory

911 个**单文件、纯 Python 标准库**的命令行小工具，配一个按工具总目录网页设计的 **Tkinter 桌面 GUI**（附打包好的免安装 exe）。

![类目统计](https://img.shields.io/badge/工具-911-blue) ![类目](https://img.shields.io/badge/中文类目-14-blueviolet) ![依赖](https://img.shields.io/badge/依赖-纯标准库-success)

## ✨ 特点

- **零依赖**：每个工具只用 Python 标准库，`python 工具.py` 即跑，无需 pip install
- **全覆盖验证**：911 个工具全部经 8 位独立复验官用 `python -I` 逐个实测通过，另有 `python -m compileall` 全量编译门禁
- **中文优先**：每个工具的 docstring 首行含中文名与说明；GUI/总目录按 14 个中文类目组织
- **免安装 GUI**：`军火库.exe`（PyInstaller 单文件）双击即用，目标机无需 Python

## 📊 类目分布

| 类目 | 数量 | 类目 | 数量 |
|---|---:|---|---:|
| 文本处理 | 117 | 日期与日历 | 86 |
| 文件与目录 | 117 | 数据转换 | 73 |
| 图片与媒体 | 107 | 编码与哈希 | 72 |
| 开发助手 | 92 | 中文本地化 | 52 |
| 趣味生成 | 91 | 密码与安全 | 43 |
| 财务人民币 | 22 | 网络与系统 | 20 |
| 效率办公 | 16 | 其他 | 3 |

## 🚀 使用方式

### 1. 桌面 GUI（最省事）

```
release/千工具军火库/军火库.exe   # 双击运行（tools/ 与 catalog.json 需在同一目录，仓库已备好）
```

渐变头图 + 分类胶囊 + 卡片瀑布流（虚拟渲染，911 张不卡顿）+ 右侧详情/参数/运行控制台。

### 2. 网页总目录

打开 [`index.html`](index.html)：可搜索、按类目筛选，每张卡片带用法示例。

### 3. 命令行直接用

```bash
python tools/age-calc.py 1990-05-20          # 精确年龄计算
python tools/backup-codes-gen.py --count 5   # 2FA 恢复码生成
python tools/csv2mdtable.py data.csv         # CSV 转 Markdown 表格
python tools/<slug>.py --help                # 每个工具都有 docstring 用法
```

工具索引见 `catalog.json`（slug → 中文名/类目/说明）。

## 📁 目录结构

```
tool-armory/
├── tools/            # 911 个工具（每工具一个 .py）
├── app/              # GUI 源码（armory_gui.py）+ 打包产物
│   └── hidden-imports.txt   # PyInstaller hidden-import 清单（LF 行尾！）
├── release/千工具军火库/    # 交付目录：军火库.exe + tools/ + catalog.json
├── catalog.json      # 分类数据（slug → {name, category, summary}）
├── index.html        # 网页版总目录（可搜索）
└── RESUME-LEDGER.md  # 项目档案（构建/修复记录）
```

## 🔨 从源码构建 exe

```bash
pip install pyinstaller tzdata
cd app
# hidden-imports.txt 必须是 LF 行尾（CRLF 会让 PyInstaller 静默跳过！）
python - <<'EOF'
mods = [l.strip() for l in open("hidden-imports.txt") if l.strip()]
import sys
args = " ".join(f"--hidden-import {m}" for m in mods + ["tzdata"])
print(args)
EOF
python -m PyInstaller --onefile --noconsole --name 军火库 \
  $(cat 上面输出的参数) armory_gui.py
```

> **坑位提示**：GUI 通过 `runpy` 在进程内执行工具，工具的 import 对 PyInstaller 静态分析不可见，
> 所以 60 个标准库模块必须显式 `--hidden-import`；Windows 文本模式写出的清单是 CRLF，
> 会让 PyInstaller 静默跳过它们——保持 LF。

## 🧪 质量说明

- 每个工具由实现者自测（`python -I` 实际运行）+ 独立复验官二次实测，双重验证
- 详见 [RESUME-LEDGER.md](RESUME-LEDGER.md) 的构建与修复记录（含四代 GUI bug 的根因分析）
- **未覆盖**：边界条件与恶意输入的系统性测试——工具是"实测能跑"，不是"加固过"

## 📄 License

MIT
