#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing_check.py —— 家族修仙 / 系统文「单章写作体检」工具（纯标准库，无第三方依赖）

用途：把一章（或一批章）正文丢进来，立刻拿到一份可执行的体检报告，用于
「番茄 / 起点」手机阅读纪律自查。所有判定规则都写在代码注释里，方便按需改阈值。

检查项（对应 references/08-自检清单.md 的「单章自检」）：
  1. 中文字符数          —— 判断本章体量是否够（番茄约 2000-2600 字 / 起点约 2000-4000 字）。
  2. 去标点字数          —— 真实信息量，和上项一起看，比值过低说明标点/对话壳子太多。
  3. 段落数 / 平均段长   —— 手机阅读段落宜 1-3 行，平均段长过高会被划走。
  4. 超长段落清单        —— 按「每行 N 字」估算显示行数，超过 3 行（默认）的段落逐条列出。
  5. 对话段落占比        —— 家族文/系统文对话过少会闷，过多会像剧本，给出参考区间。
  6. 注水词 / 套话命中表 —— 高频重复的虚词与万能套话，命中最多的先改。
  7. 重复 4-8 字短语 topN —— 一章内反复出现的短语，通常是作者自己的口癖。
  8. 章末钩子打分        —— 按钩子关键词、结尾句式、弱结尾词给 0-10 分并写明依据。
  9. 「本章自检」行      —— 缺自检行的章节单独点名。

输入支持：
  * 一个或多个文件路径（.txt / .md / 无扩展名的章节文本均可）
  * 一个或多个目录（递归收集 *.txt / *.md / 无扩展名文本文件）
  * 从标准输入读取（管道或重定向）
  * 章节切分：识别「第X章」「第X节」「第X回」标题行，以及 序章/楔子/尾声/番外

退出码：0 正常；2 用法错误（含无参数）；1 输入/读取错误。
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import string
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 0. 控制台中文输出：Windows 控制台默认代码页常为 936/GBK，直接打印 UTF-8 会乱码。
#    这里把 stdout/stderr 重配置为 UTF-8（失败则退化为 errors="replace" 保证不崩），
#    并把 Windows 控制台输出代码页切到 65001。全部包在 try 里，任何失败都静默跳过。
# ---------------------------------------------------------------------------
def setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            try:
                buf = getattr(stream, "buffer", None)
                if buf is not None:
                    new = io.TextIOWrapper(buf, encoding="utf-8", errors="replace", line_buffering=True)
                    if stream is sys.stdout:
                        sys.stdout = new  # type: ignore[assignment]
                    else:
                        sys.stderr = new  # type: ignore[assignment]
            except Exception:
                pass
    if os.name == "nt":
        try:
            import ctypes  # 标准库
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 1. 字符与标点工具
# ---------------------------------------------------------------------------
# 中日韩统一表意文字（含扩展A与兼容区），用于统计「中文字符数」
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# 标点集合：ASCII 标点 + 中文标点。去标点字数 = 去掉空白与这些标点后的字数。
CJK_PUNCT = "，。！？；：、“”‘’（）【】《》〈〉…—～·「」『』〔〕〖〗－–—＃＠＆＊＋＝％￥＄／＼｜"
PUNCT_CHARS = set(string.punctuation) | set(CJK_PUNCT) | {"\u3000", "\ufe0f", "\u200b"}


def count_cjk(text: str) -> int:
    """中文字符数（只数汉字，不含标点、数字、字母）。"""
    return len(CJK_RE.findall(text))


def strip_punct(text: str) -> str:
    """去掉所有空白与中英标点，返回纯内容串。"""
    return "".join(ch for ch in text if not ch.isspace() and ch not in PUNCT_CHARS)


# ---------------------------------------------------------------------------
# 2. 注水词 / 套话词表
#    规则：这些词不是错别字，但一章内高频出现＝作者在凑字数、节奏被拖慢。
#    每种给出「建议动作」，命中表里直接输出，方便照着改。
# ---------------------------------------------------------------------------
FILLER_WORDS: List[Tuple[str, str]] = [
    ("不由得", "删掉，动作直接写"),
    ("不禁", "删掉，或换成具体反应"),
    ("不由自主", "删掉，改为主动作选择"),
    ("下意识的", "删掉"),
    ("心中一凛", "换成身体反应（手心出汗/退半步）"),
    ("心中一喜", "换成具体表情或对话"),
    ("心中一沉", "换成具体判断句"),
    ("心中五味杂陈", "直接写他做了什么决定"),
    ("思绪万千", "删掉，写一条具体念头"),
    ("眼底深处", "删掉，改成眼神落点"),
    ("嘴角勾起", "换成一句话或一个动作"),
    ("勾起一抹", "换成一句话或一个动作"),
    ("淡淡的", "删掉副词"),
    ("微微", "删掉或换具体幅度"),
    ("缓缓", "删掉，换成节奏词"),
    ("顿时", "删掉，靠事件本身制造冲击"),
    ("瞬间", "一章最多留 1-2 次"),
    ("仿佛", "删掉比喻，直接写事实"),
    ("似乎", "删掉模糊词，给确定信息"),
    ("与此同时", "换成场景硬切"),
    ("而在另一边", "换成场景硬切"),
    ("毫无疑问", "删掉，结论让读者自己得出"),
    ("不得不说", "删掉，这是作者插话"),
    ("众所周知", "删掉，这是作者插话"),
    ("总而言之", "删掉"),
    ("空气仿佛凝固", "套话，换成具体沉默动作"),
    ("鸦雀无声", "套话，换成一个人咳嗽/椅子响"),
    ("倒吸一口凉气", "套话，换成旁观者台词"),
    ("瞳孔骤缩", "套话，换成退步/握紧东西"),
    ("眼神一凝", "套话，换成具体判断"),
    ("杀气腾腾", "套话，换成其他人不敢靠近的行为"),
    ("风云变色", "套话，换成天象以外的人的反应"),
    ("一时间", "删掉"),
    ("紧接着", "删掉，段落切分即可"),
    ("随后", "删掉"),
    ("于是", "删掉，因果靠情节呈现"),
    ("就在这时", "一章最多 1 次"),
    ("就在此时", "一章最多 1 次"),
    ("这一刻", "一章最多 1 次"),
    ("时间仿佛静止", "套话，删"),
    ("仿佛过了一个世纪", "套话，删"),
    ("如果他知道", "作者视角剧透，删"),
    ("多年以后", "作者视角剧透，删"),
    ("没有人知道", "作者视角剧透，删"),
]

# 结尾「弱钩子」词：章末落到这些词上，基本等于告诉读者「可以关掉了」。
WEAK_ENDING_WORDS = [
    "从此", "就这样", "于是", "终于", "平静下来", "心满意足", "安心",
    "沉沉睡去", "睡了过去", "回到家中", "不再多想", "无话", "罢了",
    "松了一口气", "放下心来", "皆大欢喜", "告一段落",
]

# 章末钩子关键词分组：命中越多，钩子越强。分组只用于解释依据。
HOOK_GROUPS: Dict[str, List[str]] = {
    "悬念/疑问": ["究竟", "到底", "是谁", "为什么", "难道", "怎么会", "意味着", "不对劲", "蹊跷", "古怪"],
    "转折/意外": ["然而", "可是", "却", "竟然", "居然", "没想到", "不料", "偏偏", "反而", "突然"],
    "威胁/危机": ["杀意", "冷笑", "阴冷", "血", "死", "危", "坏", "糟", "逃", "杀", "断", "塌", "裂", "爆"],
    "新信息/新人物": ["来人", "声音", "身影", "气息", "敲门", "门外", "身后", "抬头", "睁眼", "令牌", "信", "玉简", "传音"],
    "异常/变化": ["新的", "不属于", "陌生", "异样", "多出", "少了", "不见了", "消失", "第一次", "从未", "不该", "反常"],
    "未完成动作": ["正要", "刚刚", "还没", "尚未", "只差", "就在", "下一步", "即将", "准备"],
}

# 「本章自检」行：技能包要求每章末尾留一行自检。
# 这一行是写作纪律记录，不是正文，参与字数/段长/钩子统计会污染指标，所以先摘出来。
SELFCHECK_RE = re.compile(r"^\s*本章自检")

# 自检行之前的装饰分隔线（——、---、=== 等）：它是排版符号不是正文。
# 若留在正文里，会被当成「章节末行」，导致钩子打分永远命中「以—收尾（+0）」，
# 把真实存在的章末钩子判成弱钩子（实测《补天眼》第1-3章即被低估）。
SEPARATOR_RE = re.compile(r"^\s*(?:[—–\-=*_·•~]{2,}|[—–=*_·•~]{1})\s*$")

# 结尾标点加分规则（疑问/省略号最抓人，感叹次之，句号最平）
END_PUNCT_SCORE = {"?": 2, "？": 2, "…": 2, "！": 1, "!": 1, "。": 0, ".": 0}


# ---------------------------------------------------------------------------
# 3. 章节切分
#    规则：只有「整行就是标题」才算章节标题（标题后允许跟不超过 20 字的标题名），
#    这样不会把正文里的「第三章的内容」误判成标题。
# ---------------------------------------------------------------------------
_CN_NUM = "0-9零一二三四五六七八九十百千万两〇"
CHAP_HEAD_RE = re.compile(
    r"^\s{0,8}(?:"
    r"第\s*[" + _CN_NUM + r"]+\s*[章回节](?:\s*[：:、.．·\-—]?\s*\S{0,20})?"
    r"|(?:序章|序言|楔子|序幕|尾声|终章|后记|番外)\s*[" + _CN_NUM + r"]*(?:\s*[：:、.．·\-—]?\s*\S{0,20})?"
    r")\s*$"
)
VOLUME_HEAD_RE = re.compile(r"^\s{0,8}第\s*[" + _CN_NUM + r"]+\s*卷(?:\s*\S{0,20})?\s*$")


class Chapter:
    def __init__(self, title: str, source: str, body: List[str]) -> None:
        self.title = title
        self.source = source
        self.body = body  # 段落列表（每个非空行算一段，已剔除「本章自检」行）
        self.selfcheck_lines: List[str] = []  # 被摘出来的自检行

    @property
    def text(self) -> str:
        return "\n".join(self.body)

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def cjk_count(self) -> int:
        return count_cjk(self.text)

    @property
    def content_count(self) -> int:
        return len(strip_punct(self.text))


def split_chapters(text: str, source: str) -> List[Chapter]:
    """把一份文本切成章节。找不到标题就整体当一章。"""
    chapters: List[Chapter] = []
    cur_title: Optional[str] = None
    cur_body: List[str] = []

    def flush() -> None:
        nonlocal cur_title, cur_body
        if cur_title is not None or cur_body:
            chapters.append(Chapter(cur_title or f"（{source}·未检测到章节标题）", source, cur_body))
        cur_title, cur_body = None, []

    for raw in text.splitlines():
        line = raw.strip()
        if line and CHAP_HEAD_RE.match(line):
            flush()
            cur_title = line
            continue
        if line and VOLUME_HEAD_RE.match(line):
            continue  # 卷标题不是章，跳过但用于分卷
        if line:
            cur_body.append(line)
        else:
            # 空行保留为段落分隔信息；这里用哨兵把「被空行分隔的块」也切开，
            # 因为中文网文多数仍是一行一段，空行通常意味着场景切换。
            if cur_body and cur_body[-1] != "":
                cur_body.append("")
    flush()

    # 去掉纯空段落，并把「本章自检」行摘出来（不参与正文指标，只用于判断有没有写）
    # 同时剥掉自检行紧邻上方的分隔线，避免它冒充章节末行污染钩子判定。
    for ch in chapters:
        kept: List[str] = []
        raw_body = list(ch.body)
        drop_idx: set = set()
        for i, p in enumerate(raw_body):
            if not SELFCHECK_RE.match(p):
                continue
            ch.selfcheck_lines.append(p)
            j = i - 1
            while j >= 0 and not raw_body[j].strip():
                j -= 1  # 跨过自检行与正文之间的空行
            if j >= 0 and SEPARATOR_RE.match(raw_body[j]):
                drop_idx.add(j)
        for i, p in enumerate(raw_body):
            if i in drop_idx or SELFCHECK_RE.match(p):
                continue
            if p.strip():
                kept.append(p)
        ch.body = kept
    # 去掉没有正文、也不是带标题的空章
    return [c for c in chapters if c.body or c.title]


# ---------------------------------------------------------------------------
# 4. 单章指标
# ---------------------------------------------------------------------------
DIALOG_RE = re.compile(r"[「『“\"][^」』”\"]{1,}[」』”\"]")


def paragraph_rows(ch: Chapter) -> List[Dict[str, Any]]:
    """逐段算术：字数、估算显示行数。"""
    rows = []
    for i, p in enumerate(ch.body, 1):
        n = len(p)
        rows.append({"index": i, "chars": n, "text": p})
    return rows


def dialog_stats(ch: Chapter) -> Dict[str, Any]:
    """对话统计：既有「段落级」占比（多少段在说话），也有「字符级」引号内占比。

    判定：段落里出现成对引号（「」『』“”""）中的任意一种，即算对话段。
    家族文建议 25%-55%：低于 25% 容易闷，高于 55% 像剧本、缺画面。
    """
    total = len(ch.body) or 1
    dlg_paras = sum(1 for p in ch.body if DIALOG_RE.search(p))
    quoted_chars = sum(len(m.group(0)) for m in DIALOG_RE.finditer(ch.text))
    total_chars = ch.char_count or 1
    return {
        "dialog_paragraphs": dlg_paras,
        "total_paragraphs": len(ch.body),
        "dialog_ratio": round(dlg_paras / total, 4),
        "quoted_char_ratio": round(quoted_chars / total_chars, 4),
    }


def filler_hits(ch: Chapter) -> List[Dict[str, Any]]:
    """注水词命中。按出现次数降序，只保留命中>=1 的。"""
    text = ch.text
    hits = []
    for word, advice in FILLER_WORDS:
        c = text.count(word)
        if c > 0:
            hits.append({"word": word, "count": c, "advice": advice})
    hits.sort(key=lambda x: (-x["count"], x["word"]))
    return hits


def repeated_phrases(ch: Chapter, n_range: Iterable[int] = range(4, 9),
                     min_count: int = 3) -> List[Dict[str, Any]]:
    """重复的 4-8 字短语。

    算法：在「去标点纯文本」上滑窗统计 4~8 字 n-gram 的出现次数；
    只保留 count >= min_count 的；打分 = count * (n - 2)（越长越像口癖越值得改）；
    再做一次「包含消重」：如果某个候选短语是已入选更长短语的子串，就跳过，
    避免同一个问题刷屏（例如「不由得」和「不由得心生」）。
    """
    pure = strip_punct(ch.text)
    candidates: List[Tuple[str, int, int]] = []
    for n in n_range:
        if len(pure) < n:
            continue
        counts: Dict[str, int] = {}
        for i in range(len(pure) - n + 1):
            g = pure[i:i + n]
            counts[g] = counts.get(g, 0) + 1
        for g, c in counts.items():
            if c >= min_count:
                candidates.append((g, c, n))
    candidates.sort(key=lambda x: (-(x[1] * (x[2] - 2)), -x[2], x[0]))
    picked: List[Tuple[str, int, int]] = []
    for g, c, n in candidates:
        if any(g in p for p, _, _ in picked if len(p) > len(g)):
            continue  # 已被更长的重复短语覆盖
        if any(g == p for p, _, _ in picked):
            continue
        picked.append((g, c, n))
        if len(picked) >= 40:
            break
    return [{"phrase": g, "count": c, "length": n, "score": c * (n - 2)} for g, c, n in picked]


def score_hook(ch: Chapter, tail_chars: int = 200) -> Dict[str, Any]:
    """章末钩子打分（0-10 分）+ 逐条依据。

    打分逻辑（每一项都会写进 reasons，方便判断是不是误判）：
      A. 结尾标点：问号/省略号 +2；感叹号 +1；句号 +0（满分 2）。
      B. 末 200 字命中钩子关键词分组：每命中一组 +1，最多 +4（满分 4）。
      C. 末 60 字出现新信息/新人物/未完成动作/异常变化类词：+1。
      D. 最后一段命中弱结尾词（从此/就这样/终于…）：-3。
      E. 末段 <= 6 字且无标点：-1（读起来像半句，不是设计过的钩子）。
      F. 本章不足 300 汉字：-1（体量太小谈不上章末节奏）。
    理论满分 = 2 + 4 + 1 = 7，所以分档阈值按 7 分制设定：
      >=6 强钩子；3-5 中等钩子；<=2 弱/无钩子（建议重写最后 3 行）。
    """
    text = ch.text.strip()
    score = 0
    reasons: List[str] = []
    if not text:
        return {"score": 0, "level": "无正文", "reasons": ["章节没有正文内容"], "keywords": [], "strong": False}

    tail = text[-tail_chars:]
    stripped_tail = tail.rstrip()
    # 结尾常带右引号/右括号（“……”），先剥掉这些包壳，再看真正的结句标点
    core = stripped_tail.rstrip("”』」\"'）)】》〉")
    core = core.rstrip()
    end_char = core[-1] if core else ""
    if end_char in ("？", "?"):
        score += 2
        reasons.append("A 以疑问句收尾（+2）：把悬念直接摆到读者眼前")
    elif core.endswith("……") or core.endswith("...") or end_char == "…":
        score += 2
        reasons.append("A 以省略号收尾（+2）：留白式悬念，读者会想翻下一章")
    elif end_char in ("！", "!"):
        score += 1
        reasons.append("A 以感叹号收尾（+1）：情绪收束，但悬念感弱于问号/省略号")
    else:
        reasons.append(f"A 以「{end_char or '空'}」收尾（+0）：最平的收尾，若内容无悬念则钩子很弱")

    hit_kw: List[str] = []
    for group, words in HOOK_GROUPS.items():
        g_hits = [w for w in words if w in tail]
        if g_hits:
            score += 1
            hit_kw.append(f"{group}：{'/'.join(g_hits[:3])}")
    score = min(score, 2 + 4)  # A 最多 2，B 最多 4
    if hit_kw:
        reasons.append("B 末 200 字命中钩子关键词（每类 +1，上限 +4）：" + "；".join(hit_kw))
    else:
        reasons.append("B 末 200 字没有任何钩子关键词（+0）：结尾是平的")

    tail60 = text[-60:]
    new_info = [w for w in (HOOK_GROUPS["新信息/新人物"] + HOOK_GROUPS["未完成动作"]
                            + HOOK_GROUPS["异常/变化"]) if w in tail60]
    if new_info:
        score += 1
        reasons.append("C 末 60 字出现新信息/未完成动作/异常变化（+1）：" + "/".join(new_info[:4]))

    last_line = ch.body[-1] if ch.body else ""
    tail_line = last_line[-60:]
    weak = [w for w in WEAK_ENDING_WORDS if w in tail_line]
    if weak:
        score -= 3
        reasons.append("D 结尾句命中弱结尾词（-3）：" + "/".join(weak) + "　—— 这是「可以关掉了」的信号")

    if len(last_line.strip()) <= 6 and not re.search(r"[。！？!?…]", last_line):
        score -= 1
        reasons.append("E 末段 <=6 字且无句读（-1）：像半句，不是设计过的钩子")

    if ch.cjk_count < 300:
        score -= 1
        reasons.append("F 本章不足 300 汉字（-1）：体量太小，章末节奏无从谈起")

    score = max(0, min(10, score))
    level = "强钩子" if score >= 6 else ("中等钩子" if score >= 3 else "弱/无钩子")
    if score <= 2:
        reasons.append("结论：建议重写最后 3 行 —— 抛一个新信息、一句提问或一个未完成的动作")
    return {"score": score, "level": level, "reasons": reasons, "keywords": hit_kw, "strong": score >= 3}


def check_selfcheck(ch: Chapter) -> bool:
    """是否写了「本章自检」行（技能包的写作纪律：每章末尾留一行自检）。
    注意：自检行已在 split_chapters 里摘出，不参与字数/段长/钩子统计。"""
    return bool(ch.selfcheck_lines) or "本章自检" in ch.text


# ---------------------------------------------------------------------------
# 5. 输入采集
# ---------------------------------------------------------------------------
TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".text"}


def read_text(path: str, encoding: str) -> str:
    """读取文本；先按指定编码，失败回退 gbk / gb18030（中文 Windows 常见）。"""
    tried = []
    for enc in [encoding, "utf-8-sig", "utf-8", "gb18030", "gbk"]:
        if enc in tried:
            continue
        tried.append(enc)
        try:
            with open(path, "r", encoding=enc, errors="strict") as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
        except OSError:
            raise
    with open(path, "r", encoding=encoding, errors="replace") as f:
        return f.read()


def is_text_candidate(path: str) -> bool:
    """目录扫描时的入选规则：.txt/.md 或无扩展名的文件（章节纯文本），且非空。"""
    name = os.path.basename(path)
    if name.startswith("."):
        return False
    ext = os.path.splitext(name)[1].lower()
    if ext:
        return ext in TEXT_SUFFIXES
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def read_stdin_bytes(encoding: str) -> Optional[str]:
    """从标准输入读「原始字节」再解码，依次尝试 --encoding / utf-8-sig / utf-8 / gb18030 / gbk。

    为什么要读 bytes：Windows PowerShell 5.1 的控制台默认 GBK，管道给子进程的字节也是 GBK；
    而 Python 3.12 的 sys.stdin 文本模式也会按控制台代码页解码。直接 sys.stdin.read()
    在「UTF-8 管道 + GBK 解码」组合下会得到乱码和虚高的字数。按字节读再回退解码最稳。
    """
    stream = getattr(sys.stdin, "buffer", None)
    if stream is not None:
        try:
            raw = stream.read()
        except Exception:
            raw = b""
        if raw.strip():
            for enc in [encoding, "utf-8-sig", "utf-8", "gb18030", "gbk"]:
                try:
                    return raw.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    continue
            return raw.decode(encoding, errors="replace")
        return None
    data = sys.stdin.read()
    return data if data.strip() else None


def collect_inputs(paths: List[str]) -> List[Tuple[str, str]]:
    """返回 [(显示名, 正文)]；目录递归收集。"""
    out: List[Tuple[str, str]] = []
    for p in paths:
        if os.path.isdir(p):
            found = []
            for root, _dirs, files in os.walk(p):
                for fn in sorted(files):
                    fp = os.path.join(root, fn)
                    if is_text_candidate(fp):
                        found.append(fp)
            for fp in sorted(found):
                out.append((fp, read_text(fp, _ENC)))
        elif os.path.isfile(p):
            out.append((p, read_text(p, _ENC)))
        else:
            raise FileNotFoundError(p)
    return out


# ---------------------------------------------------------------------------
# 6. 报告渲染
# ---------------------------------------------------------------------------
def analyze_chapter(ch: Chapter, args: argparse.Namespace) -> Dict[str, Any]:
    rows = paragraph_rows(ch)
    paras = len(rows)
    avg_len = round(sum(r["chars"] for r in rows) / paras, 1) if paras else 0.0
    long_paras = []
    for r in rows:
        lines = max(1, math.ceil(r["chars"] / max(1, args.chars_per_line)))
        if lines > args.max_lines:
            long_paras.append({
                "index": r["index"],
                "chars": r["chars"],
                "est_lines": lines,
                "preview": r["text"][:24] + ("…" if len(r["text"]) > 24 else ""),
            })
    long_paras.sort(key=lambda x: -x["chars"])
    return {
        "source": ch.source,
        "title": ch.title,
        "cjk_chars": ch.cjk_count,
        "content_chars": ch.content_count,
        "total_chars": ch.char_count,
        "paragraphs": paras,
        "avg_paragraph_chars": avg_len,
        "long_paragraphs": long_paras[: args.top_long],
        "long_paragraph_total": len(long_paras),
        "dialog": dialog_stats(ch),
        "filler_hits": filler_hits(ch),
        "repeated_phrases": repeated_phrases(ch, min_count=args.min_repeat)[: args.top_repeat],
        "hook": score_hook(ch),
        "selfcheck_present": check_selfcheck(ch),
    }


def bar(ratio: float, width: int = 20) -> str:
    n = int(round(max(0.0, min(1.0, ratio)) * width))
    return "█" * n + "·" * (width - n)


def render_text(report: Dict[str, Any], args: argparse.Namespace) -> str:
    lines: List[str] = []
    add = lines.append
    for f in report["files"]:
        add("=" * 78)
        add(f"文件：{f['source']}")
        add("=" * 78)
        for ch in f["chapters"]:
            add("")
            add(f"── 章节：{ch['title']}")
            add(f"   中文字符数：{ch['cjk_chars']}　去标点字数：{ch['content_chars']}　"
                f"含标点总长：{ch['total_chars']}")
            if ch["cjk_chars"] and ch["content_chars"]:
                add(f"   去标点字数 / 含标点总长：{ch['content_chars'] / max(1, ch['total_chars']):.2f}"
                    f"（去标点字数含数字与字母；比值过高说明标点与对话壳子撑了篇幅）")
            add(f"   段落数：{ch['paragraphs']}　平均段长：{ch['avg_paragraph_chars']} 字")
            d = ch["dialog"]
            add(f"   对话段占比：{d['dialog_ratio'] * 100:.1f}% "
                f"[{bar(d['dialog_ratio'])}]（参考 25%-55%）　"
                f"引号内字符占比：{d['quoted_char_ratio'] * 100:.1f}%")

            # 长段落（手机阅读纪律）
            add(f"   长段落（估算 >{args.max_lines} 行，按每行 {args.chars_per_line} 字）："
                f"{ch['long_paragraph_total']} 段")
            for lp in ch["long_paragraphs"]:
                add(f"     · 第 {lp['index']} 段 {lp['chars']} 字 ≈{lp['est_lines']} 行：{lp['preview']}")
            if ch["long_paragraph_total"] > len(ch["long_paragraphs"]):
                add(f"     …（其余 {ch['long_paragraph_total'] - len(ch['long_paragraphs'])} 段省略，"
                    f"用 --top-long 调整）")

            # 注水词
            if ch["filler_hits"]:
                total_hits = sum(h["count"] for h in ch["filler_hits"])
                add(f"   注水词/套话命中：{len(ch['filler_hits'])} 种，共 {total_hits} 次")
                add("     词　次数　建议")
                for h in ch["filler_hits"][:15]:
                    add(f"     {h['word']}　{h['count']}　{h['advice']}")
            else:
                add("   注水词/套话命中：无 ✓")

            # 重复短语
            if ch["repeated_phrases"]:
                add(f"   重复 {args.min_repeat}+ 次的 4-8 字短语 top{len(ch['repeated_phrases'])}：")
                for rp in ch["repeated_phrases"]:
                    add(f"     「{rp['phrase']}」×{rp['count']}（{rp['length']} 字，权重 {rp['score']}）")
            else:
                add(f"   重复 4-8 字短语：无（阈值 {args.min_repeat} 次）✓")

            # 钩子
            hk = ch["hook"]
            add(f"   章末钩子打分：{hk['score']}/10 —— {hk['level']}")
            for reason in hk["reasons"]:
                add(f"     · {reason}")

            # 自检行
            if args.no_selfcheck:
                add("   「本章自检」行：跳过检查（--no-selfcheck）")
            else:
                add(f"   「本章自检」行：{'已写 ✓' if ch['selfcheck_present'] else '缺失 ✗（章末补一行）'}")
        add("")
        add(f"◆ {os.path.basename(f['source'])} 小结：{len(f['chapters'])} 章；"
            f"总汉字 {f['file_cjk']}；平均段长 {f['file_avg_para']} 字；"
            f"平均钩子分 {f['file_hook_avg']}/10；缺自检行 {f['selfcheck_missing']} 章")
    add("=" * 78)
    s = report["summary"]
    add(f"总计：{s['files']} 个文件 / {s['chapters']} 章 / 汉字 {s['cjk_chars']} / "
        f"去标点 {s['content_chars']} / 长段落 {s['long_paragraphs']} 段 / "
        f"注水命中 {s['filler_hits']} 次 / 重复短语 {s['repeated_phrases']} 条")
    add(f"钩子分档：强 {s['hook_strong']} 章　中等 {s['hook_medium']} 章　弱/无 {s['hook_weak']} 章")
    if s["hook_weak_list"]:
        add("待重写章末的章节：" + "；".join(s["hook_weak_list"]))
    if s["selfcheck_missing_list"]:
        add("缺「本章自检」的章节：" + "；".join(s["selfcheck_missing_list"]))
    add("说明：本报告只给纪律性提示，不替代人工判断；阈值可用 --chars-per-line / --max-lines / --min-repeat 调。")
    return "\n".join(lines)


def build_report(inputs: List[Tuple[str, str]], args: argparse.Namespace) -> Dict[str, Any]:
    files = []
    summary = {
        "files": 0, "chapters": 0, "cjk_chars": 0, "content_chars": 0,
        "paragraphs": 0, "long_paragraphs": 0, "filler_hits": 0, "repeated_phrases": 0,
        "hook_strong": 0, "hook_medium": 0, "hook_weak": 0,
        "hook_weak_list": [], "selfcheck_missing_list": [],
    }
    for src, text in inputs:
        chapters = split_chapters(text, src)
        analyzed = [analyze_chapter(c, args) for c in chapters]
        file_cjk = sum(a["cjk_chars"] for a in analyzed)
        file_paras = [a["avg_paragraph_chars"] for a in analyzed if a["paragraphs"]]
        hooks = [a["hook"]["score"] for a in analyzed]
        missing = [a["title"] for a in analyzed if not a["selfcheck_present"]]
        files.append({
            "source": src,
            "chapters": analyzed,
            "file_cjk": file_cjk,
            "file_avg_para": round(sum(file_paras) / len(file_paras), 1) if file_paras else 0.0,
            "file_hook_avg": round(sum(hooks) / len(hooks), 1) if hooks else 0.0,
            "selfcheck_missing": len(missing),
        })
        summary["files"] += 1
        summary["chapters"] += len(analyzed)
        summary["cjk_chars"] += file_cjk
        summary["content_chars"] += sum(a["content_chars"] for a in analyzed)
        summary["paragraphs"] += sum(a["paragraphs"] for a in analyzed)
        summary["long_paragraphs"] += sum(a["long_paragraph_total"] for a in analyzed)
        summary["filler_hits"] += sum(h["count"] for a in analyzed for h in a["filler_hits"])
        summary["repeated_phrases"] += sum(len(a["repeated_phrases"]) for a in analyzed)
        for a in analyzed:
            sc = a["hook"]["score"]
            if sc >= 6:
                summary["hook_strong"] += 1
            elif sc >= 3:
                summary["hook_medium"] += 1
            else:
                summary["hook_weak"] += 1
                summary["hook_weak_list"].append(f"{os.path.basename(src)}·{a['title']}({sc}分)")
            if not a["selfcheck_present"] and not args.no_selfcheck:
                summary["selfcheck_missing_list"].append(f"{os.path.basename(src)}·{a['title']}")
    return {"tool": "writing_check", "version": "1.0", "files": files, "summary": summary}


# ---------------------------------------------------------------------------
# 7. 命令行
# ---------------------------------------------------------------------------
USAGE_TEXT = """writing_check.py —— 家族修仙/系统文单章写作体检（纯标准库）

用法：
  python writing_check.py [选项] 文件1 [文件2 ...]
  python writing_check.py [选项] 目录1 [目录2 ...]      # 递归收集 *.txt / *.md / 无扩展名文本
  type 章节.txt | python writing_check.py [选项]        # 从标准输入读取

常用示例：
  python writing_check.py 第001章.txt
  python writing_check.py --json 草稿\\ > 体检.json
  python writing_check.py --chars-per-line 20 --max-lines 3 卷一\\
  Get-Content 章节.txt -Raw | python writing_check.py --quiet

检查项：中文字符数 / 去标点字数 / 段落数 / 平均段长 / 超长段落清单 /
        对话段占比 / 注水词套话命中表 / 重复 4-8 字短语 / 章末钩子打分 / 「本章自检」行

退出码：0 正常；2 用法错误（含无参数）；1 输入或读取错误。
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="writing_check.py",
        description="家族修仙/系统文单章写作体检：字数、段长、注水词、重复短语、章末钩子、自检行。",
        epilog="不传路径且标准输入是终端时，会打印本说明并以退出码 2 结束。",
        add_help=True,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("paths", nargs="*", help="文件或目录路径（可多个）；留空则读标准输入")
    p.add_argument("--json", action="store_true", help="以 JSON 输出，便于二次处理")
    p.add_argument("--chars-per-line", type=int, default=22, metavar="N",
                   help="手机端每行估算字数（番茄约 20，起点约 24；默认 22）")
    p.add_argument("--max-lines", type=int, default=3, metavar="N",
                   help="段落估算超过 N 行算长段落（默认 3）")
    p.add_argument("--top-long", type=int, default=20, metavar="N", help="长段落清单上限（默认 20）")
    p.add_argument("--top-repeat", type=int, default=15, metavar="N", help="重复短语清单上限（默认 15）")
    p.add_argument("--min-repeat", type=int, default=3, metavar="N", help="重复短语最低出现次数（默认 3）")
    p.add_argument("--encoding", default="utf-8-sig", metavar="ENC",
                   help="读取编码，失败会依次回退 utf-8/gb18030/gbk（默认 utf-8-sig）")
    p.add_argument("--no-selfcheck", action="store_true", help="不检查「本章自检」行")
    p.add_argument("--quiet", action="store_true", help="只输出总计摘要")
    return p


_ENC = "utf-8-sig"


def main(argv: Optional[List[str]] = None) -> int:
    global _ENC
    setup_console()
    args = build_parser().parse_args(argv)
    _ENC = args.encoding

    inputs: List[Tuple[str, str]] = []
    try:
        if args.paths:
            inputs = collect_inputs(args.paths)
        else:
            if sys.stdin is None or sys.stdin.isatty():
                print(USAGE_TEXT.replace("writing_check.py", os.path.basename(__file__)), file=sys.stderr)
                print("[错误] 没有输入：请给出文件/目录路径，或从标准输入管道传入正文。", file=sys.stderr)
                return 2
            data = read_stdin_bytes(args.encoding)
            if not data:
                print(USAGE_TEXT.replace("writing_check.py", os.path.basename(__file__)), file=sys.stderr)
                print("[错误] 标准输入为空。", file=sys.stderr)
                return 2
            inputs = [("<stdin>", data)]
    except FileNotFoundError as e:
        print(f"[错误] 找不到路径：{e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"[错误] 读取失败：{e}", file=sys.stderr)
        return 1

    if not inputs:
        print("[错误] 没有收集到任何文本文件（目录筛选规则：*.txt / *.md / 无扩展名非空文件）。",
              file=sys.stderr)
        return 2

    report = build_report(inputs, args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.quiet:
        s = report["summary"]
        print(f"文件 {s['files']} / 章 {s['chapters']} / 汉字 {s['cjk_chars']} / "
              f"长段落 {s['long_paragraphs']} / 注水命中 {s['filler_hits']} / "
              f"弱钩子 {s['hook_weak']} 章 / 缺自检 {len(s['selfcheck_missing_list'])} 章")
    else:
        print(render_text(report, args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
