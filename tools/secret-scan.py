#!/usr/bin/env python3
"""密钥泄露扫描(secret-scan)

递归扫描目录下的文本文件,用常见 API key/token/AWS 凭据等模式识别疑似泄露,
输出清单(文件、行号、命中的模式类别、打码后的片段)。

内置模式包括:
  AWS Access Key ID / Secret Key   AKIA...
  通用 API key / token 赋值        api_key = "..."  token: '...'
  Google API Key                   AIza...
  Slack token                      xox[abpr]-...
  GitHub token                     ghp_/gho_/ghu_/ghs_/ghr_...
  Stripe key                       sk_live_/pk_live_...
  私钥块                           -----BEGIN ... PRIVATE KEY-----
  Bearer / JWT                     eyJ...
  数据库连接串                     postgres://user:pass@...
  通用十六进制/随机串凭据          长随机赋值右侧

用法:
  python secret-scan.py <目录或文件> [--ext py,js,txt] [--max-size 1048576]
                        [-o 输出文件] [--json]

示例:
  python secret-scan.py ./myproject
  python secret-scan.py ./myproject --ext py,env,yaml --json -o findings.json
"""
import argparse
import json
import os
import re
import sys

# (类别, 编译后的正则, 是否跳过当前命中片段的后续模式去重)
PATTERNS = [
    ("aws-access-key-id", re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b')),
    ("aws-secret", re.compile(r'(?i)aws.{0,30}?["\']([0-9a-zA-Z/+]{40})["\']')),
    ("google-api-key", re.compile(r'\bAIza[0-9A-Za-z_\-]{35}\b')),
    ("github-token", re.compile(r'\bgh[pousr]_[0-9A-Za-z]{36,255}\b')),
    ("slack-token", re.compile(r'\bxox[a-z]-[0-9A-Za-z\-]{10,}\b')),
    ("stripe-live-key", re.compile(r'\b[sr]k_live_[0-9a-zA-Z]{20,}\b')),
    ("jwt", re.compile(r'\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b')),
    ("private-key-block", re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ("db-conn-string", re.compile(r'\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:@/\']+:[^\s@\'/]+@[^\s\'"]+')),
    ("credential-assignment", re.compile(
        r'(?i)\b(?:api[_\-]?key|apikey|secret|token|password|passwd|pwd|access[_\-]?key|auth[_\-]?token)\b'
        r'\s*[=:]\s*["\']?([^\s"\',;)]{8,64})["\']?')),
    ("bearer-header", re.compile(r'(?i)\bbearer\s+[0-9a-zA-Z_\-\.=+/]{16,}\b')),
]
# credential-assignment 右值太常见(如 true/false/占位词),做一次粗降噪
NOISE_VALUES = {'', 'true', 'false', 'null', 'none', 'changeme', 'change-me',
                'xxx', 'xxxx', 'your_api_key_here', 'example', 'placeholder',
                'password', 'token', 'secret', '12345678', '12345678901234567890'}

DEFAULT_SKIP_DIRS = {'.git', '.hg', '.svn', 'node_modules', '__pycache__',
                     '.venv', 'venv', '.idea', '.vscode', 'dist', 'build'}
BINARY_SAMPLE = re.compile(rb'[\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0e\x0f\x7f]')


def mask_fragment(text, keep=4):
    """对命中的敏感片段打码,保留前 keep 个字符。"""
    if len(text) <= keep:
        return '*' * len(text)
    return text[:keep] + '*' * min(len(text) - keep, 12)


def iter_files(root, exts, max_size, follow_symlinks=False):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_SKIP_DIRS]
        for name in sorted(filenames):
            if exts and os.path.splitext(name)[1].lstrip('.').lower() not in exts:
                continue
            path = os.path.join(dirpath, name)
            try:
                if os.path.getsize(path) > max_size:
                    continue
            except OSError:
                continue
            yield path


def scan_file(path, size_limit_read):
    findings = []
    try:
        with open(path, 'rb') as f:
            data = f.read(size_limit_read)
    except OSError as e:
        return [{'file': path, 'line': 0, 'kind': 'read-error',
                 'fragment': str(e), 'match': False}]
    if BINARY_SAMPLE.search(data[:8192]):
        return findings  # 视为二进制文件,跳过
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text = data.decode('gbk')
        except UnicodeDecodeError:
            text = data.decode('utf-8', errors='replace')
    seen = set()
    for lineno, line in enumerate(text.splitlines(), 1):
        for kind, rx in PATTERNS:
            m = rx.search(line)
            if not m:
                continue
            # 取分组(右值)或整段命中作为片段
            frag = m.group(1) if m.groups() else m.group(0)
            if kind == 'credential-assignment' and frag.lower() in NOISE_VALUES:
                continue
            if kind == 'credential-assignment' and frag.isdigit() and len(frag) < 12:
                continue
            key = (lineno, kind, frag)
            if key in seen:
                continue
            seen.add(key)
            findings.append({
                'file': path, 'line': lineno, 'kind': kind,
                'fragment': mask_fragment(frag),
                'match': True,
            })
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description='按常见凭据模式扫描文件树,输出疑似泄露清单')
    ap.add_argument('root', help='要扫描的目录或单个文件')
    ap.add_argument('--ext', default='', help='只扫描这些扩展名(逗号分隔,如 py,js,yaml);默认全部')
    ap.add_argument('--max-size', type=int, default=1024 * 1024, help='跳过超过此字节数的文件(默认 1MB)')
    ap.add_argument('-o', '--output', help='结果写入文件,默认打印到 stdout')
    ap.add_argument('--json', action='store_true', help='以 JSON 数组输出')
    args = ap.parse_args(argv)

    if not os.path.exists(args.root):
        print(f'错误: 路径不存在: {args.root}', file=sys.stderr)
        return 2

    exts = {e.strip().lstrip('.').lower() for e in args.ext.split(',') if e.strip()}
    findings = []
    for path in iter_files(args.root, exts, args.max_size):
        findings.extend(scan_file(path, max(args.max_size, 4096)))

    if args.json:
        out = json.dumps(findings, ensure_ascii=False, indent=2)
    else:
        lines = [f'共发现 {len(findings)} 处疑似泄露:'] if findings else ['未发现疑似泄露。']
        for f in findings:
            lines.append(f"{f['file']}:{f['line']}  [{f['kind']}]  {f['fragment']}")
        out = '\n'.join(lines) + '\n'

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as fh:
            fh.write(out)
        print(f'{len(findings)} 处结果已写入 {args.output}')
    else:
        sys.stdout.write(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
