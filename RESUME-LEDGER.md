# 千工具军火库 · 项目档案

> **项目全部完工（2026-11-07）。** 开发线 + GUI/exe 交付线均已完成并实机验证。本档案留作项目记录。

## ✅ 完工总览

### 交付物
| 产物 | 位置 |
|---|---|
| 911 个工具 | `tools\*.py`（单文件、纯标准库、docstring 中文说明） |
| 总目录页 | `index.html`（274KB，分类筛选+搜索，网页版） |
| 桌面 GUI | `release\千工具军火库\军火库.exe`（10.5MB，单文件免安装） |
| 发布目录 | `release\千工具军火库\`（exe + tools 911 + catalog.json） |
| 分类数据 | `catalog.json`（911 工具 → 14 个中文类目，4 个并行编目官产出，0 缺失 0 越界） |
| GUI 源码 | `app\armory_gui.py`（tkinter 纯标准库） |

### GUI 设计（对齐网页版 index.html）
- 渐变 Hero 头图（#1e2a52→#3b5bdb→#5f7ae8）+ 标题/统计
- 工具栏：搜索框（占位符+焦点高亮）+ 计数 + 14 个分类胶囊（激活态主蓝）
- 卡片瀑布流：Canvas 虚拟渲染（只画可视区，911 张不卡顿），卡片=中文名+类目标签+slug 芯片+说明
- 右侧运行台：详情（名称/类目/slug/说明/docstring）+ 参数 + 运行/停止 + 控制台
- 打包态经隐藏入口 `军火库.exe --run-tool <tool.py>` 在进程内执行工具（目标机无需 Python）

### 质量账
- 911/911 经复验官 python -I 实测通过（183 批全覆盖，failed=0）
- python -m compileall 全量编译门禁退出码 0
- exe 实机验证：选中/详情/运行/输出链路全通；tz-info(zoneinfo)、plist2json、crc-tool、backup-codes-gen 抽查全过

### 修复记录（GUI 线四代 bug）
1. **hidden-import 全部失效**：清单文件 CRLF 行尾 → PyInstaller 收到 `secrets\r` 等假模块名静默跳过。修：`tr -d '\r'`。教训：生成给 shell 消费的清单一律 LF
2. **运行完成哨兵漏进控制台**：`__DONE__` 前带换行导致 startswith 失配。修：先 strip 再判
3. **exe 卡顿 + 分类切换显示不准**（2026-11-07 用户实测反馈）：
   - 卡顿根因：`root.bind("<Configure>")` 因 Tk bindtag 机制对所有子控件几何变化都触发 → 每次滚动建卡引发「重绘 96 条渐变带 + 重排网格」级联风暴。修：回调里 `if e.widget is not self.root: return` + 宽度变化才重绘 hero
   - 切换不准根因：`_apply_filter` 里误写 `self._rendered_rows_span`（拼写错误属性），真正的 `_render_rows` 未重置 → 新旧筛选可视区间相同时 `_sync_render` 提前返回，旧分类卡片残留。修：数据集变化一律 `_clear_cards()` 后重渲染；列数变化同样清卡
   - 实机验证：胶囊切换激活态/计数/卡片内容全对、无残留；滚动 10 格无空洞；切回全部滚动位置正确重置
4. **滚动条拖动无效 + 卡片上滚轮无效**（2026-11-07 用户实测反馈）：
   - 拖动根因：把 Scrollbar 的 `command` 回调当成了 `yscrollcommand` 的 `(first, last)` 形状——拖动时 Tk 实际传入 `("moveto", frac)` / `("scroll", n, units)`，`float("moveto")` 抛 ValueError，拖动每次静默失败。修：按 command 协议分派 moveto/scroll
   - 滚轮根因：滚轮只绑在 Canvas 上，但卡片是覆盖其上的独立 Frame——鼠标悬在卡片上时事件到不了 Canvas。修：`bind_all("<MouseWheel>")` + 沿父链判断指针是否在卡片流区域内（详情面板 Text 保持原生滚动，且移除 Canvas 单独绑定避免双重滚动）
   - 实机验证：拖动滑块视图正确跳转（列表头 → 中部中文本地化区）；无头测试确认卡片 Label 上的滚轮事件能滚动、详情 Text 上不干扰

### 项目最终结构
```
tool-armory\
├── tools\            911 个 .py 工具
├── app\              GUI 源码 + 打包工作目录（hidden-imports.txt 为 LF）
├── release\千工具军火库\   军火库.exe + tools\ + catalog.json  ← 交付目录
├── catalog.json      分类数据主副本
├── index.html        网页版总目录
└── RESUME-LEDGER.md  本档案
```

### 未覆盖（如实声明）
- 工具未做边界条件与恶意输入的系统性测试
- GUI 未做高 DPI/多显示器适配测试；主验证环境 125% 缩放

### 历史运行链（留档）
`219dbe8f` → `cb8e683f`（11-02 额度尽）→ `6636a8ca`（11-04 周月上限）→ `80349ae1`（11-05 会话关闭；旧 channel-pool 结构重放哈希失败）→ `ea58fb1f`（确定性重构，3 次暂停恢复无损）✅ 完工
累计消耗：约 7.7 亿 token（GLOBAL BUILD / WEEKEND BUILD 活动池多轮）
