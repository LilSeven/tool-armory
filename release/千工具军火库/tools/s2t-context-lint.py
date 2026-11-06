#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""转换结果上下文审查 (s2t-context-lint)。

对简体→繁体机器转换后的文本做上下文抽查, 标记可能选错繁体字形的
位置, 并检测疑似漏转的简体残留字。纯标准库, 内置规则表, 不联网。

两类检查:
  1. 简体残留: 繁体文本中出现只在简体中使用的字形 (如 开/关/东/车)。
  2. 一简对多繁: 根据上下文词组判断繁体字形是否选错
     (如 "頭發" 应为 "頭髮", "面包" 应为 "麵包", "老板" 应为 "老闆")。

用法:
    python s2t-context-lint.py <文件路径|->  [--json] [--fail]

示例命令:
    python s2t-context-lint.py converted.txt
    cat converted.txt | python s2t-context-lint.py -
    python s2t-context-lint.py converted.txt --fail

退出码: 0 = 正常完成(有无发现均如此); 1 = 仅当 --fail 且有发现;
        2 = 读文件失败。
"""

import argparse
import json
import re
import sys

# ---- 规则 1: 只在简体中使用的字形 (繁体文本里出现即疑似漏转) ----
_SIMP_ONLY = (
    "们联归当发为经应变实观见认识说读语诗记价贵买卖县严体报护据怀态总矿确脑腾"
    "断质费资钱铁银钥锁击验难鸡鸭鱼风飞龙马驾车东贝长乐万与专业书头个开关单国"
    "会时这还进远运边达过问间阅网电产厂广义习从众优伤传伟临兰烂粮两谅疗辽猎邻"
    "鳞灵岭领刘聋拢陇楼娄芦卢炉陆虏录虑滤乱论罗络骆妈骂吗迈麦脉瞒满猫么门闷梦"
    "谜弥庙灭悯鸣铭谋亩纳挠恼闹拟腻酿鸟聂宁拧农浓疟盘庞赔喷鹏骗飘频贫苹凭评泼"
    "铺谱齐骑岂弃启迁签谦钳浅谴枪墙抢桥侨窍窃亲轻倾庆琼穷区驱龋权劝让扰热认韧"
    "荣绒软锐闰润洒萨赛伞丧骚涩杀筛晒删闪陕赡缮烧绍摄设绅审肾声湿诗识蚀势释饰"
    "视试寿兽枢输属树竖帅双谁顺说硕丝苏诉肃虽随岁孙损缩态摊谈坛叹汤烫涛讨誊条"
    "厅听烃铜统图团颓蜕脱驮洼袜弯网韦违围维伪卫谓闻稳务雾误戏细虾峡侠狭厦吓纤"
    "鲜贤现献线乡详响项潇销晓啸协挟携胁谐写泻谢兴须许绪续轩悬选学询训讯逊压鸦"
    "哑亚盐颜阎艳厌砚谚验阳养样痒谣摇尧药爷页叶医义议亿忆阴银隐应婴樱鹰营蝇赢"
    "颖忧邮犹诱屿语誉预驭鸳渊园员圆缘约跃杂灾载脏凿枣责择则泽贼赠扎铡闸诈斋债"
    "战张涨帐账赵折针侦诊镇阵挣争郑证织职执纸挚掷帜质种众昼骤烛铸筑转赚庄装壮"
    "状锥谆浊渍踪综总纵邹诅组钻"
)

# ---- 规则 2: 一简对多繁的上下文规则 (错误写法, 建议写法, 说明) ----
_CONTEXT_RULES = [
    (r"頭發|头发", "頭髮", "毛发义应为「髮」"),
    (r"[理剃假]發", "…髮", "毛发义应为「髮」"),
    (r"面包|面條|面条|面食|面館|面馆", "…麵…", "面食义应为「麵」"),
    (r"以后", "以後", "先后义的「后」应为「後」"),
    (r"里面|里边|里头|哪里|这里|那里|心里|手里", "…裡…", "方位义的「里」应为「裡/裏」"),
    (r"干净|干淨|乾净|幹净", "乾淨", "洁净义应为「乾淨」"),
    (r"干部|能干|干活|才干", "…幹…", "做事义应为「幹」"),
    (r"关系|關系|联系|聯系|關繫", "關係/聯繫", "关联义应为「係/繫」"),
    (r"历史|來历|来历|经历|經历|日历|历法|学历|學历|农历|農历",
     "…歷/曆…", "经历义用「歷」, 历法义用「曆」"),
    (r"重复|回复|复杂|复制", "…複/覆…", "重复/复杂义应为「複」, 答复义应为「覆」"),
    (r"台风|台湾|电视台|平台|后台|前台", "…臺…", "多为「臺」; 台风应为「颱風」"),
    (r"松开|轻松|放松|松紧|稀松|松动|松動", "…鬆…", "松弛义应为「鬆」"),
    (r"稻谷|谷子|五谷|谷类", "…穀…", "庄稼义应为「穀」"),
    (r"制作|制造|编制", "…製…", "制造义应为「製」"),
    (r"手表|钟表|腕表|表带", "…錶…", "计时器义应为「錶」"),
    (r"冲突|冲击|冲动|冲劲", "…衝…", "冲突义应为「衝」"),
    (r"生姜|姜汤|姜黄|姜片", "…薑…", "植物义应为「薑」"),
    (r"杂志|日志|墓志|县志", "…誌…", "记录义应为「誌」"),
    (r"汇报|汇总|词汇|汇率|汇款|汇聚", "…彙/匯…", "汇总义用「彙」, 汇款义用「匯」"),
    (r"尽力|尽量|尽管|尽头", "…盡…", "力求/极点义应为「盡」(儘量为「儘」)"),
    (r"采用|采购|采访|采纳|采取|开采", "…採…", "选取义应为「採」"),
    (r"计划|规划", "…劃…", "筹划义应为「劃」"),
    (r"亏损|亏本|吃亏|亏欠", "…虧…", "缺损义应为「虧」"),
    (r"准备|标准|准确|准时", "…準…", "标准义应为「準」"),
    (r"时钟|分钟|闹钟|钟点|钟声", "…鐘…", "计时器义应为「鐘」"),
    (r"老板", "老闆", "店主义应为「闆」"),
    (r"云彩|云层|乌云|云朵|云雾|云海", "…雲…", "云彩义应为「雲」"),
    (r"[一二两兩三四五六七八九十几幾]只", "…隻…", "禽兽量词应为「隻」"),
]

_RULES = [(re.compile(p), s, h) for p, s, h in _CONTEXT_RULES]
_SIMP_RE = re.compile("[" + _SIMP_ONLY + "]")


def lint_line(line):
    """返回本行的发现列表: (列号, 原文片段, 建议, 说明)。"""
    findings = []
    for pat, sug, hint in _RULES:
        for m in pat.finditer(line):
            findings.append((m.start() + 1, m.group(0), sug, hint))
    for m in _SIMP_RE.finditer(line):
        findings.append((m.start() + 1, m.group(0), "对应繁体字形",
                         "疑似未转换的简体字"))
    findings.sort(key=lambda f: f[0])
    return findings


def lint_text(text):
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for col, frag, sug, hint in lint_line(line):
            out.append({"line": lineno, "col": col, "found": frag,
                        "suggest": sug, "hint": hint})
    return out


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="简→繁转换结果上下文审查")
    ap.add_argument("path", nargs="?", default="-",
                    help="输入文件路径, '-' 表示 stdin (默认)")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--fail", action="store_true",
                    help="有发现时退出码置 1")
    args = ap.parse_args(argv)

    try:
        if args.path == "-":
            data = sys.stdin.buffer.read()
        else:
            with open(args.path, "rb") as fh:
                data = fh.read()
    except OSError as exc:
        print(f"错误: 无法读取 {args.path}: {exc}", file=sys.stderr)
        return 2
    text = data.decode("utf-8", errors="replace")

    findings = lint_text(text)
    if args.json:
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    else:
        name = "stdin" if args.path == "-" else args.path
        for f in findings:
            print(f"{name}:{f['line']}:{f['col']}  「{f['found']}」→ 建议"
                  f"「{f['suggest']}」  ({f['hint']})")
        print(f"-- 共 {len(findings)} 处疑似问题。")
    return 1 if (args.fail and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
