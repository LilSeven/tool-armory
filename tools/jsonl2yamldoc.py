#!/usr/bin/env python3
"""jsonl2yamldoc —— JSON Lines 与 “--- 分隔的 YAML 多文档流”双向转换(纯标准库)。

默认(正向):      每行一个 JSON 值 → 一个 YAML 文档, 文档之间用 --- 分隔;
--reverse(反向): YAML 多文档流 → 每行一个 JSON 值(JSONL)。

YAML 侧为常用子集: 块映射/块序列、流式 [..] {..}、单双引号与裸标量、
| 与 > 块标量、---/... 文档分隔; 不支持锚点/别名/标签/跨行纯标量/
缩进中的制表符。空 YAML 文档反向时输出为一行 null, 保证文档数不丢。

示例:
    python -I jsonl2yamldoc.py data.jsonl -o data.yaml       # JSONL → YAML 文档流
    python -I jsonl2yamldoc.py data.yaml --reverse -o data.jsonl
    python -I jsonl2yamldoc.py data.jsonl --indent 4 -o data.yaml
    cat data.jsonl | python -I jsonl2yamldoc.py

退出码: 0 成功; 1 输入/格式错误; 2 用法错误(argparse)。
"""

import argparse
import json
import re
import sys

# ---------------- 迷你 YAML 子集解析器(替代 PyYAML) ----------------

_NUM_RE = re.compile(r'[+-]?(?:[0-9][0-9]*\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')


class YamlError(ValueError):
    """本工具不支持的 YAML 语法或 YAML 格式错误。"""


def _is_doc_marker(content):
    return (content == '---' or content == '...'
            or content.startswith('--- ') or content.startswith('... '))


class _YamlParser:
    """支持: 块映射/块序列、流式 [..] {..}、单双引号标量、裸标量类型推断、
    | 与 > 块标量(含 -/+ 抑止符与显式缩进数字)、---/... 多文档流。
    不支持: 锚点/别名/标签、跨行纯标量、复杂键、缩进中的制表符。"""

    def __init__(self, text):
        self.lines = []
        for no, raw in enumerate(text.splitlines(), 1):
            if raw.strip() == '':
                self.lines.append([no, None, ''])
                continue
            body = raw.lstrip(' ')
            indent = len(raw) - len(body)
            if '\t' in raw[:indent]:
                raise YamlError('第 %d 行: 缩进中不能使用制表符' % no)
            self.lines.append([no, indent, body])
        self.i = 0
        self.n = len(self.lines)

    # -- 游标 --
    def _peek(self):
        while self.i < self.n:
            no, ind, c = self.lines[self.i]
            if ind is None or c.startswith('#'):
                self.i += 1
                continue
            return ind, c, no
        return None, None, None

    # -- 多文档 --
    def documents(self):
        docs = []
        root_ind = None
        while True:
            ind, c, no = self._peek()
            if ind is None:
                break
            if _is_doc_marker(c):
                root_ind = ind
                if c.startswith('...'):
                    self.i += 1
                    continue
                tail = c[3:]
                stripped = tail.lstrip(' ')
                if stripped == '' or stripped.startswith('#'):
                    self.i += 1
                    docs.append(self._block())
                else:
                    # “--- xxx”: 当前行改写为节点首行, 由 _block_inline 消费
                    docs.append(self._block_inline(3 + len(tail) - len(stripped)))
            else:
                if root_ind is not None and ind > root_ind:
                    raise YamlError('第 %d 行: 意外的更深缩进'
                                    '(可能是跨行纯标量, 本解析器不支持)' % no)
                if (root_ind is not None and ind == root_ind
                        and (c == '-' or c.startswith('- '))
                        and docs and isinstance(docs[-1], dict)):
                    raise YamlError('第 %d 行: 映射之后出现同缩进的序列项, '
                                    '缺少键名或缺少 --- 文档分隔' % no)
                root_ind = ind
                docs.append(self._block())
        return docs

    # -- 块节点 --
    def _block(self):
        ind, c, no = self._peek()
        if ind is None or _is_doc_marker(c):
            return None
        if c == '-' or c.startswith('- '):
            return self._seq(ind)
        if self._find_key_colon(c) is not None:
            return self._map(ind)
        self.i += 1
        return self._inline_value(c, no)

    def _block_inline(self, off):
        """把当前行第 off 列起的内容当作块节点首行(用于 “- xxx” / “--- xxx”)。"""
        ln = self.lines[self.i]
        rest = ln[2][off:]
        lead = len(rest) - len(rest.lstrip(' \t'))
        ln[2] = rest.lstrip(' \t')
        ln[1] = ln[1] + off + lead
        return self._block()

    def _seq(self, ind):
        items = []
        while True:
            pi, c, no = self._peek()
            if pi is None or pi != ind or _is_doc_marker(c):
                break
            if not (c == '-' or c.startswith('- ')):
                break
            tail = c[1:]
            stripped = tail.lstrip(' ')
            if stripped == '' or stripped.startswith('#'):
                self.i += 1
                ci, cc, _ = self._peek()
                if ci is not None and ci > ind and not _is_doc_marker(cc):
                    items.append(self._block())
                else:
                    items.append(None)
            else:
                items.append(self._block_inline(1 + len(tail) - len(stripped)))
        return items

    def _map(self, ind):
        out = {}
        while True:
            pi, c, no = self._peek()
            if pi is None or pi != ind or _is_doc_marker(c):
                break
            if c == '-' or c.startswith('- '):
                break
            kcol = self._find_key_colon(c)
            if kcol is None:
                raise YamlError('第 %d 行: 期望 "key: value", 实际是 %r' % (no, c))
            key = self._parse_key(c[:kcol], no)
            rest = c[kcol + 1:]
            stripped = rest.lstrip(' \t')
            if stripped == '' or stripped.startswith('#'):
                self.i += 1
                out[key] = self._child_value(ind)
            elif stripped[0] in '|>':
                out[key] = self._block_scalar(stripped, ind, no)
            else:
                self.i += 1
                out[key] = self._inline_value(stripped, no)
        return out

    def _child_value(self, ind):
        ci, cc, _ = self._peek()
        if ci is None or _is_doc_marker(cc):
            return None
        if ci > ind:
            return self._block()
        if ci == ind and (cc == '-' or cc.startswith('- ')):
            return self._seq(ind)
        return None

    # -- 标量 --
    def _inline_value(self, s, no):
        s = s.strip()
        if s == '':
            return None
        first = s[0]
        if first in '[{':
            val, end = self._parse_flow(s, 0, no)
            tail = s[end:].lstrip(' \t')
            if tail and not tail.startswith('#'):
                raise YamlError('第 %d 行: 流式集合后有多余内容 %r' % (no, tail))
            return val
        if first in '"\'':
            val, end = self._read_quoted(s, 0, no)
            tail = s[end:].lstrip(' \t')
            if tail and not tail.startswith('#'):
                raise YamlError('第 %d 行: 引号标量后有多余内容 %r' % (no, tail))
            return val
        if s == '-' or s.startswith('- ') or s == '?' or s.startswith('? '):
            raise YamlError('第 %d 行: 此处不允许出现块集合 %r' % (no, s))
        return self._plain_scalar(self._strip_comment(s))

    def _parse_key(self, s, no):
        s = s.strip()
        if s == '':
            raise YamlError('第 %d 行: 空键' % no)
        if s[0] in '"\'':
            val, end = self._read_quoted(s, 0, no)
            if s[end:].strip() != '':
                raise YamlError('第 %d 行: 引号键之后有多余内容 %r' % (no, s[end:]))
            return val
        return s

    def _block_scalar(self, ind_text, parent_indent, no):
        style = ind_text[0]
        j = 1
        explicit = None
        chomp = 'clip'
        while j < len(ind_text):
            ch = ind_text[j]
            if ch in '0123456789' and explicit is None:
                explicit = int(ch)
            elif ch == '-' and chomp == 'clip':
                chomp = 'strip'
            elif ch == '+' and chomp == 'clip':
                chomp = 'keep'
            else:
                break
            j += 1
        rest = ind_text[j:].strip()
        if rest and not rest.startswith('#'):
            raise YamlError('第 %d 行: 无法识别的块标量指示符 %r' % (no, ind_text))
        self.i += 1  # 跳过键所在行
        block_indent = None if explicit is None else parent_indent + explicit
        raws = []
        while self.i < self.n:
            ln = self.lines[self.i]
            if ln[1] is None:
                raws.append('')
                self.i += 1
                continue
            if block_indent is None:
                if ln[1] <= parent_indent:
                    break
                block_indent = ln[1]
            if ln[1] < block_indent:
                break
            raws.append(' ' * (ln[1] - block_indent) + ln[2])
            self.i += 1
        trail = 0
        while raws and raws[-1] == '':
            raws.pop()
            trail += 1
        if style == '|':
            body = '\n'.join(raws)
        else:
            body = self._fold(raws)
        if chomp == 'strip':
            return body
        if chomp == 'keep':
            return body + '\n' * (1 + trail) if body else '\n' * trail
        return body + '\n' if body else ''

    @staticmethod
    def _fold(raws):
        res = ''
        blanks = 0
        for r in raws:
            if r == '':
                blanks += 1
                continue
            if res == '':
                res = r
            elif blanks == 0:
                res += ' ' + r
            else:
                res += '\n' * blanks + r
            blanks = 0
        return res

    # -- 流式集合 --
    def _parse_flow(self, s, i, no):
        opener = s[i]
        closer = ']' if opener == '[' else '}'
        is_seq = opener == '['
        coll = [] if is_seq else {}
        i += 1
        while True:
            i = self._skip_ws(s, i)
            if i >= len(s):
                raise YamlError('第 %d 行: 流式集合未闭合' % no)
            if s[i] == closer:
                return coll, i + 1
            if is_seq:
                val, i = self._flow_node(s, i, no)
                coll.append(val)
            else:
                key, i = self._flow_key(s, i, no)
                i = self._skip_ws(s, i)
                if i >= len(s) or s[i] != ':':
                    raise YamlError('第 %d 行: 流式映射缺少 ":"' % no)
                i = self._skip_ws(s, i + 1)
                if i < len(s) and s[i] in ',}':
                    coll[key] = None
                else:
                    val, i = self._flow_node(s, i, no)
                    coll[key] = val
            i = self._skip_ws(s, i)
            if i < len(s) and s[i] == ',':
                i += 1
                continue
            if i < len(s) and s[i] == closer:
                return coll, i + 1
            raise YamlError('第 %d 行: 流式集合中缺少 "," 或 %r' % (no, closer))

    def _flow_node(self, s, i, no):
        if s[i] in '[{':
            return self._parse_flow(s, i, no)
        if s[i] in '"\'':
            return self._read_quoted(s, i, no)
        j = i
        n = len(s)
        while j < n:
            ch = s[j]
            if ch in ',]}':
                break
            if ch == ':' and (j + 1 >= n or s[j + 1] in ' \t,]}'):
                break
            j += 1
        text = s[i:j].strip()
        if text == '':
            raise YamlError('第 %d 行: 流式集合中有空元素' % no)
        return self._plain_scalar(text), j

    def _flow_key(self, s, i, no):
        if s[i] in '"\'':
            return self._read_quoted(s, i, no)
        if s[i] in '[{':
            raise YamlError('第 %d 行: 不支持复杂流式键' % no)
        j = i
        n = len(s)
        while j < n:
            ch = s[j]
            if ch in ',]}':
                break
            if ch == ':' and (j + 1 >= n or s[j + 1] in ' \t,]}'):
                break
            j += 1
        text = s[i:j].strip()
        if text == '':
            raise YamlError('第 %d 行: 流式映射中有空键' % no)
        return self._plain_scalar(text), j

    @staticmethod
    def _skip_ws(s, i):
        while i < len(s) and s[i] in ' \t':
            i += 1
        return i

    def _read_quoted(self, s, i, no):
        quote = s[i]
        i += 1
        out = []
        n = len(s)
        if quote == "'":
            while True:
                if i >= n:
                    raise YamlError('第 %d 行: 单引号标量未闭合' % no)
                ch = s[i]
                if ch == "'":
                    if i + 1 < n and s[i + 1] == "'":
                        out.append("'")
                        i += 2
                        continue
                    return ''.join(out), i + 1
                out.append(ch)
                i += 1
        escapes = {'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f',
                   'v': '\v', '0': '\0', 'a': '\a', 'e': '\x1b',
                   '"': '"', "'": "'", '\\': '\\', '/': '/', ' ': ' '}
        while True:
            if i >= n:
                raise YamlError('第 %d 行: 双引号标量未闭合' % no)
            ch = s[i]
            if ch == '"':
                return ''.join(out), i + 1
            if ch == '\\':
                i += 1
                if i >= n:
                    raise YamlError('第 %d 行: 转义序列不完整' % no)
                e = s[i]
                if e in escapes:
                    out.append(escapes[e])
                    i += 1
                elif e in 'xuU':
                    width = {'x': 2, 'u': 4, 'U': 8}[e]
                    hexpart = s[i + 1:i + 1 + width]
                    try:
                        out.append(chr(int(hexpart, 16)))
                    except (ValueError, OverflowError):
                        raise YamlError('第 %d 行: 非法转义 \\%s%s'
                                        % (no, e, hexpart)) from None
                    i += 1 + width
                else:
                    raise YamlError('第 %d 行: 不支持的转义 \\%s' % (no, e))
            else:
                out.append(ch)
                i += 1

    # -- 词法辅助 --
    @staticmethod
    def _find_key_colon(s):
        """找到块映射键后的冒号位置(跳过引号与流式括号), 找不到返回 None。"""
        depth = 0
        in_s = in_d = False
        i = 0
        n = len(s)
        while i < n:
            ch = s[i]
            if in_d:
                if ch == '\\':
                    i += 2
                    continue
                if ch == '"':
                    in_d = False
            elif in_s:
                if ch == "'":
                    if i + 1 < n and s[i + 1] == "'":
                        i += 2
                        continue
                    in_s = False
            elif ch == '"':
                in_d = True
            elif ch == "'" and (i == 0 or s[i - 1] in ' \t-?:,[]{'):
                in_s = True
            elif ch in '[{':
                depth += 1
            elif ch in ']}':
                depth = max(0, depth - 1)
            elif ch == '#' and i > 0 and s[i - 1] in ' \t':
                return None
            elif ch == ':' and depth == 0 and (i == n - 1 or s[i + 1] in ' \t'):
                return i
            i += 1
        return None

    @staticmethod
    def _strip_comment(s):
        for j in range(1, len(s)):
            if s[j] == '#' and s[j - 1] in ' \t':
                return s[:j].rstrip(' \t')
        return s.rstrip(' \t')

    @staticmethod
    def _plain_scalar(s):
        if s == '' or s == '~':
            return None
        low = s.lower()
        if low == 'null':
            return None
        if low in ('true', 'yes', 'on'):
            return True
        if low in ('false', 'no', 'off'):
            return False
        if low == '.inf' or low == '+.inf':
            return float('inf')
        if low == '-.inf':
            return float('-inf')
        if low == '.nan':
            return float('nan')
        if '_' not in s and s.isascii():
            try:
                return int(s)
            except ValueError:
                pass
            if _NUM_RE.match(s):
                return float(s)
        return s


def yaml_parse_all(text):
    """解析 YAML 文本(子集), 返回按 --- 分隔的文档列表。"""
    return _YamlParser(text).documents()


# ---------------- 迷你 YAML 输出器 ----------------

_MUST_QUOTE_LOWER = frozenset((
    'null', '~', 'true', 'false', 'yes', 'no', 'on', 'off',
    '.inf', '+.inf', '-.inf', '.nan',
))


def _yaml_plain_safe(s):
    """字符串能否以裸标量安全输出(用同一套规则读回后仍是同一字符串)。"""
    if s == '' or s != s.strip():
        return False
    if any(c in s for c in '\n\r\t'):
        return False
    if s[0] in '-?:,[]{}#&*!|>%@`"\'':
        return False
    if ': ' in s or s.endswith(':') or ' #' in s or '\t#' in s:
        return False
    if s.lower() in _MUST_QUOTE_LOWER:
        return False
    if '_' not in s and s.isascii():
        try:
            int(s)
            return False
        except ValueError:
            pass
        if _NUM_RE.match(s):
            return False
    return True


def _yaml_scalar_text(v):
    if v is None:
        return 'null'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, str):
        return v if _yaml_plain_safe(v) else json.dumps(v, ensure_ascii=False)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v:
            return '.nan'
        if v == float('inf'):
            return '.inf'
        if v == float('-inf'):
            return '-.inf'
        return repr(v)
    return _yaml_scalar_text(str(v))


def _emit_map(mapping, ind, width, out, head):
    col = ind + len(head)
    first = True
    for k, val in mapping.items():
        pad = (' ' * ind + head) if first else (' ' * col)
        first = False
        ks = _yaml_scalar_text(k)
        if isinstance(val, dict):
            if val:
                out.append(pad + ks + ':')
                _emit_map(val, col + width, width, out, '')
            else:
                out.append(pad + ks + ': {}')
        elif isinstance(val, list):
            if val:
                out.append(pad + ks + ':')
                _emit_seq(val, col + width, width, out, '')
            else:
                out.append(pad + ks + ': []')
        else:
            out.append(pad + ks + ': ' + _yaml_scalar_text(val))


def _emit_seq(items, ind, width, out, head):
    col = ind + len(head)
    first = True
    for item in items:
        pad = (' ' * ind + head) if first else (' ' * col)
        first = False
        if isinstance(item, dict):
            if item:
                _emit_map(item, col, width, out, '- ')
            else:
                out.append(pad + '- {}')
        elif isinstance(item, list):
            if item:
                _emit_seq(item, col, width, out, '- ')
            else:
                out.append(pad + '- []')
        else:
            out.append(pad + '- ' + _yaml_scalar_text(item))


# ---------------- 命令行 ----------------

def _doc_lines(doc, width):
    if isinstance(doc, dict):
        if not doc:
            return ['--- {}']
        lines = ['---']
        _emit_map(doc, 0, width, lines, '')
        return lines
    if isinstance(doc, list):
        if not doc:
            return ['--- []']
        lines = ['---']
        _emit_seq(doc, 0, width, lines, '')
        return lines
    return ['--- ' + _yaml_scalar_text(doc)]


def _reconfigure_streams():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except Exception:
            pass
    try:
        sys.stdout.reconfigure(newline='')
    except Exception:
        pass


def _read_text(path):
    if path in (None, '-'):
        return sys.stdin.read()
    with open(path, 'r', encoding='utf-8-sig') as f:
        return f.read()


def _open_output(path):
    if path in (None, '-'):
        return sys.stdout, False
    return open(path, 'w', encoding='utf-8', newline=''), True


def main(argv=None):
    _reconfigure_streams()
    parser = argparse.ArgumentParser(
        prog='jsonl2yamldoc',
        description='JSON Lines 与 --- 分隔的 YAML 多文档流双向转换(纯标准库)。')
    parser.add_argument('input', nargs='?', metavar='FILE',
                        help="输入文件; 缺省或 '-' 表示 stdin")
    parser.add_argument('--reverse', action='store_true',
                        help='反向: YAML 多文档流 → JSONL')
    parser.add_argument('--indent', type=int, default=2, metavar='N',
                        help='正向输出 YAML 的块缩进宽度, 默认 2')
    parser.add_argument('-o', '--output', metavar='FILE',
                        help='输出文件; 缺省 stdout')
    args = parser.parse_args(argv)
    if not 1 <= args.indent <= 16:
        raise ValueError('--indent 必须在 1..16 之间')

    text = _read_text(args.input)
    if args.reverse:
        out_lines = [json.dumps(d, ensure_ascii=False)
                     for d in yaml_parse_all(text)]
    else:
        out_lines = []
        for lineno, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if not s:
                continue
            try:
                doc = json.loads(s)
            except json.JSONDecodeError as exc:
                raise ValueError('第 %d 行不是合法 JSON: %s' % (lineno, exc)) from None
            out_lines.extend(_doc_lines(doc, args.indent))

    out, close_out = _open_output(args.output)
    try:
        if out_lines:
            out.write('\n'.join(out_lines) + '\n')
    finally:
        if close_out:
            out.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except (YamlError, ValueError, OSError) as exc:
        print('error: %s' % exc, file=sys.stderr)
        sys.exit(1)
