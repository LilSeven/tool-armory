#!/usr/bin/env python3
"""马尔可夫复读机 —— 读取本地文本训练二阶马尔可夫链，生成模仿句子。

默认以“字符”为单位建模（适合中文），英文等按空格分词的文本会自动
切换为“单词”建模；在句号/问号/叹号处断句。--order 可调 1~5 阶
（默认 2 即二阶）。语料越长，复读得越像。

示例命令:
  python markov-chat.py --demo -n 3          # 内置示例语料试玩
  python markov-chat.py novel.txt -n 5       # 用本地文本训练
  python markov-chat.py a.txt b.txt --order 3
  cat chat.txt | python markov-chat.py -n 2  # 从管道读语料
  python markov-chat.py --demo --word 小猫   # 生成的句子尽量包含某词

退出码: 0 成功；1 无语料或语料太短。
"""
import argparse
import random
import sys

END_PUNCT = set("。！？!?…")

DEMO_TEXT = """小猫喜欢在窗台上晒太阳。小猫喜欢在下雨天睡觉。
窗台上有一只小猫。下雨天小猫喜欢睡觉。
今天天气很好，小猫在窗台上晒太阳。天气很好，适合晒太阳。
小猫晒完太阳就开始睡觉。睡觉之前要吃一条小鱼。
小鱼在盘子里，盘子在窗台上。窗台上有阳光，阳光很适合晒太阳。
下雨天没有太阳，小猫只能睡觉。小猫睡觉的时候喜欢做梦。
小猫梦见自己在晒太阳，太阳在盘子里，盘子在下雨。
下雨的时候不能晒太阳，小猫就吃小鱼。吃完小鱼就睡觉。"""


def _setup_streams():
    """管道/重定向时强制 UTF-8 输入输出，避免 Windows 默认 GBK 报错。"""
    for s in (sys.stdout, sys.stderr, sys.stdin):
        try:
            if s is not None and not s.isatty():
                s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def read_file(path):
    """读本地文本，依次尝试 utf-8 / gb18030 / utf-16 编码。"""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def detect_mode(text):
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return "char"
    cjk = sum(1 for c in chars if "\u3000" <= c <= "\u9fff")
    return "char" if cjk >= 0.2 * len(chars) else "word"


def tokenize(text, mode):
    return [c for c in text if not c.isspace()] if mode == "char" \
        else text.split()


def _pure_punct(tok):
    punct = END_PUNCT | set("，,、；;：:·—“”\"'‘’（）()《》<>")
    return all(c in punct for c in tok)


def build_chain(tokens, order):
    chain = {}
    for i in range(len(tokens) - order):
        key = tuple(tokens[i:i + order])
        chain.setdefault(key, []).append(tokens[i + order])
    starts = []
    for i in range(len(tokens) - order + 1):
        if i == 0 or (tokens[i - 1][-1] in END_PUNCT
                      and not _pure_punct(tokens[i])):
            starts.append(tuple(tokens[i:i + order]))
    if not starts:
        starts = list(chain.keys())
    return chain, starts


def gen_sentence(chain, starts, rng, mode, order):
    key = rng.choice(starts)
    out = list(key)
    for _ in range(300):
        if key not in chain:
            break
        nxt = rng.choice(chain[key])
        out.append(nxt)
        if mode == "char" and nxt in END_PUNCT:
            break
        if mode == "word" and nxt[-1:] in END_PUNCT:
            break
        key = tuple(out[-order:])
    s = "".join(out) if mode == "char" else " ".join(out)
    s = s.rstrip("，,、；;：: ")
    if not s.endswith(tuple(END_PUNCT)):
        s += "。"
    return s


def main(argv=None):
    _setup_streams()
    ap = argparse.ArgumentParser(
        description="读取本地文本训练二阶马尔可夫链，生成模仿句子")
    ap.add_argument("files", nargs="*", help="训练用文本文件（可多个）")
    ap.add_argument("-n", dest="count", type=int, default=3,
                    help="生成句数（默认 3）")
    ap.add_argument("--order", type=int, default=2,
                    help="马尔可夫阶数 1~5（默认 2）")
    ap.add_argument("--word", default=None,
                    help="让生成的句子尽量包含该词")
    ap.add_argument("--demo", action="store_true", help="使用内置示例语料")
    ap.add_argument("--seed", type=int, default=None, help="随机种子，可复现")
    a = ap.parse_args(argv)

    if a.demo:
        text = DEMO_TEXT
    elif a.files:
        text = "\n".join(read_file(p) for p in a.files)
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        print("请给文本文件、用 --demo、或用管道喂语料。", file=sys.stderr)
        return 1

    if not 1 <= a.order <= 5:
        print("--order 取值应为 1~5", file=sys.stderr)
        return 1
    count = max(1, a.count)
    rng = random.Random(a.seed)
    mode = detect_mode(text)
    tokens = tokenize(text, mode)
    if len(tokens) <= a.order + 1:
        print("语料太短，训练不了（至少需要几十个字）。", file=sys.stderr)
        return 1

    chain, starts = build_chain(tokens, a.order)
    if a.word:
        w = a.word
        if mode == "char":
            filt = [k for k in starts if w in "".join(k)]
        else:
            filt = [k for k in starts if any(w in t for t in k)]
        if filt:
            starts = filt
        else:
            print(f"（语料里没找到含“{w}”的句首，改为随机起句）",
                  file=sys.stderr)

    lo, hi = (8, 90) if mode == "char" else (2, 60)
    got, tries = [], 0
    while len(got) < count and tries < 200:
        tries += 1
        s = gen_sentence(chain, starts, rng, mode, a.order)
        n = len(s) if mode == "char" else len(s.split())
        if lo <= n <= hi:
            got.append(s)
    if not got:
        print("没生成出合格的句子，试试更长的语料。", file=sys.stderr)
        return 1
    for i, s in enumerate(got, 1):
        print(f"复读机{i}：{s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
