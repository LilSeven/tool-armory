#!/usr/bin/env python3
"""YAML 子集转 JSON (yaml-subset2json) —— 自实现的 YAML 子集解析器，
把受支持的 YAML 文档转换为 JSON 输出。

支持的子集：
  - 缩进式映射:  key: value / key:            （嵌套块）
  - 缩进式序列:  - item / - key: value        （序列内嵌映射）
  - 标量:        整数、浮点、true/false、null/~、带引号字符串、裸字符串
  - 行内写法:    {a: 1, b: [1, 2]}  与  [1, 2, "x"]
  - 注释:        # 开头（整行与行尾，引号内的 # 不算）
不支持：块标量 | >、锚点/别名、多文档、标签、复杂键。

用法:
    python yaml-subset2json.py 输入.yaml [输出.json]
示例:
    python yaml-subset2json.py config.yaml config.json
"""

import json
import re
import sys


class YamlError(ValueError):
    pass


# ---------- 行内（flow）解析 ----------

class FlowParser:
    """解析单行行内写法: {..} [..] 与标量。"""

    def __init__(self, text):
        self.s = text
        self.i = 0

    def parse(self):
        val = self._value()
        self._skip_ws()
        if self.i < len(self.s):
            raise YamlError(f"行内解析有残留: {self.s[self.i:]!r}")
        return val

    def _skip_ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t":
            self.i += 1

    def _value(self):
        self._skip_ws()
        if self.i >= len(self.s):
            raise YamlError("行内值意外结束")
        c = self.s[self.i]
        if c == "{":
            return self._flow_map()
        if c == "[":
            return self._flow_seq()
        return self._scalar()

    def _flow_map(self):
        self.i += 1  # {
        obj = {}
        self._skip_ws()
        if self._peek() == "}":
            self.i += 1
            return obj
        while True:
            self._skip_ws()
            key = self._flow_key()
            self._skip_ws()
            if self._peek() != ":":
                raise YamlError("行内映射缺少 ':'")
            self.i += 1
            obj[key] = self._value()
            self._skip_ws()
            c = self._peek()
            if c == ",":
                self.i += 1
                continue
            if c == "}":
                self.i += 1
                return obj
            raise YamlError(f"行内映射期望 , 或 }}，得到 {c!r}")

    def _flow_seq(self):
        self.i += 1  # [
        seq = []
        self._skip_ws()
        if self._peek() == "]":
            self.i += 1
            return seq
        while True:
            seq.append(self._value())
            self._skip_ws()
            c = self._peek()
            if c == ",":
                self.i += 1
                continue
            if c == "]":
                self.i += 1
                return seq
            raise YamlError(f"行内序列期望 , 或 ]，得到 {c!r}")

    def _peek(self):
        if self.i >= len(self.s):
            raise YamlError("行内写法意外结束（括号未闭合）")
        return self.s[self.i]

    def _flow_key(self):
        c = self._peek()
        if c in "\"'":
            return self._quoted()
        m = re.match(r"[^:\],}\s]+", self.s[self.i:])
        if not m:
            raise YamlError(f"无法解析行内键于 {self.s[self.i:]!r}")
        self.i += m.end()
        return m.group(0)

    def _quoted(self):
        quote = self.s[self.i]
        self.i += 1
        out = []
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "\\" and quote == '"':
                self.i += 1
                esc = self.s[self.i] if self.i < len(self.s) else ""
                out.append({"n": "\n", "t": "\t", '"': '"',
                            "\\": "\\", "/": "/"}.get(esc, esc))
                self.i += 1
                continue
            if c == quote:
                self.i += 1
                return "".join(out)
            out.append(c)
            self.i += 1
        raise YamlError("字符串引号未闭合")

    def _scalar(self):
        c = self._peek()
        if c in "\"'":
            return self._quoted()
        m = re.match(r"[^\],}]+", self.s[self.i:])
        raw = m.group(0).strip()
        self.i += m.end()
        return coerce_scalar(raw)


def coerce_scalar(raw):
    """把裸标量文本转为 int/float/bool/None/字符串。"""
    if raw == "":
        return ""
    if re.fullmatch(r"[+-]?\d+", raw):
        return int(raw)
    if re.fullmatch(r"[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?", raw) \
            and any(ch in raw for ch in ".eE"):
        return float(raw)
    low = raw.strip().lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", "none"):
        return None
    return raw


def strip_comment(line):
    """去掉注释：不在引号内的 # 之后内容。"""
    out, quote = [], None
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            out.append(c)
            if quote == '"' and c == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
            out.append(c)
        elif c == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        else:
            out.append(c)
        i += 1
    return "".join(out).rstrip()


# ---------- 块结构解析 ----------

def parse_block(lines, indent=0):
    """解析从首行开始的顶层块，返回 (值, 已消费行数)。缩进取首行文本缩进。"""
    # 跳过空行
    idx = 0
    while idx < len(lines) and lines[idx][2] == "":
        idx += 1
    if idx >= len(lines):
        return None, idx
    ln, first_indent, itext = lines[idx]

    if itext.startswith("- ") or itext == "-":
        return parse_seq(lines, idx, first_indent)
    return parse_map(lines, idx, first_indent)


def split_key(text):
    """把 'key: value' 拆成 (key, value_or_None)。返回 None 表示不是映射行。"""
    quote = None
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == ":" and (i + 1 == len(text) or text[i + 1] in " \t"):
            key = text[:i].strip()
            rest = text[i + 1:].strip()
            return (unquote_key(key), rest if rest else None)
        i += 1
    return None


def unquote_key(key):
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
        return key[1:-1]
    return key


def parse_map(lines, idx, indent):
    obj = {}
    while idx < len(lines):
        ln, ind, text = lines[idx]
        if text == "":
            idx += 1
            continue
        if ind < indent:
            break
        if ind > indent:
            raise YamlError(f"第 {ln} 行: 意外的多余缩进")
        kv = split_key(text)
        if kv is None:
            raise YamlError(f"第 {ln} 行: 期望映射行，得到 {text!r}")
        key, rest = kv
        idx += 1
        if rest is not None:
            obj[key] = FlowParser(rest).parse()
        else:
            # 值在后续行：子块（映射或序列，序列可与键同缩进）
            nxt = next_nonempty(lines, idx)
            if nxt is None:
                obj[key] = None
            else:
                _nln, nind, ntext = lines[nxt]
                if nind > indent:
                    val, used = parse_block_at(lines, idx, nind)
                    obj[key] = val
                    idx = used
                elif nind == indent and (ntext.startswith("- ") or ntext == "-"):
                    val, used = parse_seq(lines, idx, indent)
                    obj[key] = val
                    idx = used
                else:
                    obj[key] = None
    return obj, idx


def next_nonempty(lines, idx):
    """返回 idx 之后第一个非空行的下标，没有则 None。"""
    while idx < len(lines):
        if lines[idx][2] != "":
            return idx
        idx += 1
    return None


def parse_seq(lines, idx, indent):
    seq = []
    while idx < len(lines):
        ln, ind, text = lines[idx]
        if text == "":
            idx += 1
            continue
        if ind < indent:
            break
        if ind > indent:
            raise YamlError(f"第 {ln} 行: 意外的多余缩进")
        if not (text.startswith("- ") or text == "-"):
            break
        item = text[1:].strip() if text != "-" else ""
        idx += 1
        if item == "":
            # 值在下一行缩进块中
            child_indent = next_indent(lines, idx, indent)
            if child_indent is None:
                seq.append(None)
            else:
                val, used = parse_block_at(lines, idx, child_indent)
                seq.append(val)
                idx = used
        elif split_key(item) is not None:
            # 序列项是映射的首行: - key: value，键列 = indent + 2
            key_col = indent + 2
            key, rest = split_key(item)
            inner = {}
            if rest is not None:
                inner[key] = FlowParser(rest).parse()
            else:
                ci = next_indent(lines, idx, key_col - 1)
                if ci is None:
                    inner[key] = None
                else:
                    val, used = parse_block_at(lines, idx, ci)
                    inner[key] = val
                    idx = used
            # 同一项的后续键（缩进 == key_col 的映射行）
            while idx < len(lines):
                _nl, ni, ntext = lines[idx]
                if ntext == "":
                    idx += 1
                    continue
                if ni != key_col:
                    break
                kv = split_key(ntext)
                if kv is None:
                    break
                k2, r2 = kv
                idx += 1
                if r2 is not None:
                    inner[k2] = FlowParser(r2).parse()
                else:
                    ci = next_indent(lines, idx, key_col)
                    if ci is None:
                        inner[k2] = None
                    else:
                        val, used = parse_block_at(lines, idx, ci)
                        inner[k2] = val
                        idx = used
            seq.append(inner)
        else:
            seq.append(FlowParser(item).parse())
    return seq, idx


def next_indent(lines, idx, parent_indent):
    """找到 idx 之后第一个非空行的缩进；仅当缩进 > parent 时返回它。"""
    while idx < len(lines):
        _ln, ind, text = lines[idx]
        if text == "":
            idx += 1
            continue
        if ind > parent_indent:
            return ind
        return None
    return None


def parse_block_at(lines, idx, indent):
    """在 idx 处以给定缩进解析一个块。"""
    text = lines[idx][2]
    if text.startswith("- ") or text == "-":
        return parse_seq(lines, idx, indent)
    return parse_map(lines, idx, indent)


def parse_yaml(text):
    """解析 YAML 子集文本为 Python 对象。"""
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = []
    for n, raw in enumerate(raw_lines, 1):
        clean = strip_comment(raw.rstrip())
        if clean.strip() == "":
            lines.append((n, 0, ""))
        else:
            stripped = clean.lstrip(" ")
            if clean != clean.expandtabs(4).lstrip(" "):
                pass
            indent = len(clean) - len(stripped)
            lines.append((n, indent, stripped))
    # 去掉首尾空行
    while lines and lines[0][2] == "":
        lines.pop(0)
    while lines and lines[-1][2] == "":
        lines.pop()
    if not lines:
        return None
    if lines[0][2].startswith("---"):
        lines.pop(0)
        while lines and lines[0][2] == "":
            lines.pop(0)
    if not lines:
        return None
    val, used = parse_block(lines)
    if used < len(lines):
        raise YamlError(f"第 {lines[used][0]} 行附近: 无法解析 {lines[used][2]!r}")
    return val


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__.strip())
        return 2
    with open(argv[1], "r", encoding="utf-8-sig") as f:
        text = f.read()
    try:
        data = parse_yaml(text)
    except YamlError as exc:
        print(f"YAML 解析错误: {exc}", file=sys.stderr)
        return 1
    out = json.dumps(data, ensure_ascii=False, indent=2)
    if len(argv) == 3:
        with open(argv[2], "w", encoding="utf-8") as f:
            f.write(out + "\n")
        print(f"已写入 {argv[2]}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
