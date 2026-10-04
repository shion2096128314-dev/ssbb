#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""family_check.py —— 家族修仙文「族谱一致性」校验器（纯标准库，无第三方依赖）

家族修仙最容易崩的不是战力，是辈分：字辈用乱、父子倒挂、年龄和辈分对不上、
称呼按错一辈，读者立刻出戏。这个脚本把族谱当数据来查，一次给出 6 类问题。

六项校验（判定规则见各 check_* 函数的中文注释）：
  1. 同辈字辈一致      —— 同一世代的人必须共用同一个辈分字；同一辈分字不得跨代复用。
  2. 父子辈分倒挂      —— 子世代必须严格大于父世代；父辈字必须在辈分表里排在子辈字之前。
  3. 世代成环          —— 父辈链不能形成环（A 的父是 B、B 的父是 A）。
  4. 年龄与辈分矛盾    —— 父亲必须比子女年长（默认至少 12 岁）；世代越大平均年龄应越小。
  5. 称呼与血缘距离匹配 —— 按「世代差 + 直系/旁系 + 最近共同祖先的距离」推断该叫什么，
                          与填写的称呼/关系比对（如第三代的亲弟被称「族叔」＝错）。
  6. 重名 / 近似重名    —— 完全同名报错；同姓且编辑距离 ≤1 的名字提醒（读者会混）。

输入格式（每行一人，字段顺序推荐如下，分隔符支持 | 、逗号、制表符、多个空格）：
    姓名 | 辈分字 | 世代 | 父辈 | 年龄 | 修为 | 称呼(对主角) | 与主角关系 | 备注
  * 「世代」：整数，主家第一代填 1，越大越晚辈；可留空，由辈分字表或父辈链推断。
  * 「父辈」：填父亲姓名；也可写 父=李承业。
  * 「称呼」与「与主角关系」二者填其一即可，用于第 5 项校验。
  也支持表头行（中文列名）与 key=value 行：
    姓名=李文昭;辈分字=文;世代=3;父辈=李元昊;年龄=20;称呼=本人;关系=主角;修为=炼气三层
  以 # 或 // 开头的行是注释。

用法：
  python family_check.py 族谱.txt
  python family_check.py --lead 李文昭 --zipai-order 承,元,文,明,德 族谱.txt
  python family_check.py --inline "李文昭|文|3|李元昊|20|炼气三层|本人|主角"
  Get-Content 族谱.txt -Raw | python family_check.py --json

退出码：0 正常；2 用法错误或没有解析到任何人物；1 文件错误；加 --strict 时存在「错误」级问题返回 1。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# 0. Windows 控制台中文输出：重配 stdout/stderr 为 UTF-8 并切控制台代码页 65001，
#    任何一步失败都静默跳过（保证脚本永远不会因为编码问题崩掉）。
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
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 1. 列名别名：表头行与 key=value 行都用这套别名识别字段
# ---------------------------------------------------------------------------
HEADER_ALIASES: Dict[str, Set[str]] = {
    "name": {"姓名", "名字", "名称", "人物", "角色", "name"},
    "zipai": {"辈分字", "辈分", "字辈", "辈字", "行辈", "zipai"},
    "gen": {"世代", "代", "辈", "第几代", "辈数", "代数", "gen", "generation"},
    "parent": {"父辈", "父亲", "父", "父亲名", "家长", "上一辈", "parent", "father"},
    "age": {"年龄", "岁数", "年纪", "年岁", "age"},
    "title": {"称呼", "称谓", "叫法", "对主角称呼", "称呼对主角", "title"},
    "rel": {"关系", "与主角关系", "血缘", "亲属关系", "亲属", "rel", "relation"},
    "cultivation": {"修为", "境界", "实力", "cultivation"},
    "note": {"备注", "说明", "note", "memo"},
}
_ALIAS_LOOKUP: Dict[str, str] = {}
for _field, _names in HEADER_ALIASES.items():
    for _n in _names:
        _ALIAS_LOOKUP[_n] = _field

# 中文数字（用于「第三代」这种写法）
CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def cn_to_int(s: str) -> Optional[int]:
    """把「3」「三」「第三代」「第3代」这类写法转成整数，无法解析返回 None。"""
    if s is None:
        return None
    s = s.strip()
    m = re.search(r"\d+", s)
    if m:
        return int(m.group(0))
    body = s.strip("第代辈 ")
    if not body:
        return None
    if "十" in body:  # 处理 十三 / 二十 / 三十五 这类
        parts = body.split("十")
        tens = CN_DIGITS.get(parts[0], 1) if parts[0] else 1
        ones = CN_DIGITS.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return tens * 10 + ones
    if all(ch in CN_DIGITS for ch in body):
        return int("".join(str(CN_DIGITS[ch]) for ch in body))
    return None


# ---------------------------------------------------------------------------
# 2. 数据模型与解析
# ---------------------------------------------------------------------------
class Person:
    __slots__ = ("name", "zipai", "gen_raw", "gen", "parent", "age", "title",
                 "rel", "cultivation", "note", "lineno", "source", "zipai_index")

    def __init__(self, **kw: Any) -> None:
        for k in self.__slots__:
            setattr(self, k, kw.get(k))
        self.gen = kw.get("gen")
        self.zipai_index = None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Person {self.name} 辈分{self.zipai} 世代{self.gen}>"


def _clean(v: Optional[str]) -> str:
    if v is None:
        return ""
    return v.strip().strip('"').strip("'").strip("　")


def split_fields(line: str) -> List[str]:
    """按 | 、制表符、逗号、中文逗号、顿号、多个空格 依次尝试切分。"""
    for sep in ("|", "\t", "，", ",", "、"):
        if sep in line:
            return [_clean(x) for x in line.split(sep)]
    if re.search(r"\s{2,}", line):
        return [_clean(x) for x in re.split(r"\s{2,}", line)]
    return [_clean(x) for x in line.split()]


def parse_kv_line(line: str) -> Optional[Dict[str, str]]:
    """解析 key=value / key：value 行（分隔符 ; ； | 空格）。识别不了返回 None。"""
    if "=" not in line and "：" not in line and ":" not in line:
        return None
    body = line
    chunks = re.split(r"[;；|]", body) if re.search(r"[;；|]", body) else [body]
    kv: Dict[str, str] = {}
    for chunk in chunks:
        m = re.match(r"\s*([^=：:]{1,8})\s*[=：:]\s*(.+?)\s*$", chunk)
        if not m:
            continue
        key = _ALIAS_LOOKUP.get(_clean(m.group(1)))
        if key:
            kv[key] = _clean(m.group(2))
    return kv or None


def is_header(fields: List[str]) -> bool:
    if len(fields) < 2:
        return False
    hits = sum(1 for f in fields if f in _ALIAS_LOOKUP)
    return hits >= 2 and hits >= len(fields) - 1


def parse_text(text: str, source: str) -> Tuple[List[Person], List[str]]:
    """解析族谱文本，返回 (人物列表, 无法解析的行说明)。"""
    people: List[Person] = []
    bad_lines: List[str] = []
    header: Optional[List[str]] = None

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        # 允许「字辈：承,元,文,明」这样的元信息行，不当作人物
        if re.match(r"^\s*(字辈|辈分序列|字辈表|zipai)\s*[=：:]", line):
            continue

        kv = parse_kv_line(line)
        if kv and "name" not in kv:
            bad_lines.append(f"第 {lineno} 行：key=value 里没有「姓名」（{line[:30]}）")
            continue
        if kv and "name" in kv:
            people.append(Person(
                name=kv.get("name", ""), zipai=kv.get("zipai", ""),
                gen_raw=kv.get("gen"), gen=cn_to_int(kv.get("gen", "")),
                parent=kv.get("parent", ""), age=cn_to_int(kv.get("age", "")),
                title=kv.get("title", ""), rel=kv.get("rel", ""),
                cultivation=kv.get("cultivation", ""), note=kv.get("note", ""),
                lineno=lineno, source=source))
            continue

        fields = split_fields(line)
        if is_header(fields):
            # 把中文表头翻译成内部字段名（name/zipai/gen/...），后面按字段名取值
            header = [_ALIAS_LOOKUP.get(f, f) for f in fields]
            continue
        if header:
            row = {header[i]: (fields[i] if i < len(fields) else "") for i in range(len(header))}
        else:
            # 无表头：按推荐顺序 姓名|辈分字|世代|父辈|年龄|修为|称呼|关系|备注 落位
            order = ["name", "zipai", "gen", "parent", "age", "cultivation", "title", "rel", "note"]
            if len(fields) > len(order):
                bad_lines.append(f"第 {lineno} 行：字段过多（{len(fields)} 列 > {len(order)}），已按顺序取前 9 列")
            row = {order[i]: fields[i] for i in range(min(len(fields), len(order)))}

        name = _clean(row.get("name", ""))
        if not name:
            bad_lines.append(f"第 {lineno} 行：没有姓名（{line[:30]}）")
            continue
        parent = _clean(row.get("parent", ""))
        parent = re.sub(r"^(父|父亲|父辈)\s*[=：:]\s*", "", parent)
        people.append(Person(
            name=name, zipai=_clean(row.get("zipai", "")), gen_raw=row.get("gen", ""),
            gen=cn_to_int(row.get("gen", "")), parent=parent,
            age=cn_to_int(row.get("age", "")), title=_clean(row.get("title", "")),
            rel=_clean(row.get("rel", "")), cultivation=_clean(row.get("cultivation", "")),
            note=_clean(row.get("note", "")), lineno=lineno, source=source))
    return people, bad_lines


# ---------------------------------------------------------------------------
# 3. 谱系推断：世代、辈分字序号、最近共同祖先
# ---------------------------------------------------------------------------
def resolve_generations(people: List[Person], zipai_order: List[str]) -> List[str]:
    """世代推断（三轮收敛）：
    优先级：显式「世代」 > 父辈世代 + 1 > 辈分字表序号（相对锚点）。
    注意：字辈表是相对关系——若名册里已有显式世代，则字辈表只用于校验相邻世代是否按表推进，
    不再把「表首字」硬当成第 1 代（族谱常常不从表首那代开始写）。
    返回推断说明列表（便于用户确认推断是否合理）。"""
    notes: List[str] = []
    if zipai_order:
        for i, z in enumerate(zipai_order, 1):
            for p in people:
                if p.zipai and p.zipai[0] == z:
                    p.zipai_index = i
    by_name = {p.name: p for p in people}

    # 若名册里已有显式世代，用「最小显式世代 − 对应字辈序号」求出锚点偏移，
    # 使字辈序号能推断出与显式世代同一坐标系下的世代。
    shift = 0
    explicit = [(p.gen, p.zipai_index) for p in people
                if p.gen is not None and p.zipai_index is not None]
    if explicit:
        shift = min(g - i for g, i in explicit)

    inferred: List[str] = []
    for p in people:
        if p.gen is None and p.zipai_index is not None:
            p.gen = p.zipai_index + shift
            inferred.append(p.name)
    for _ in range(3):
        changed = False
        for p in people:
            if p.gen is None and p.parent and p.parent in by_name:
                pg = by_name[p.parent].gen
                if pg is not None:
                    p.gen = pg + 1
                    changed = True
                    if p.name not in inferred:
                        inferred.append(p.name)
        if not changed:
            break
    if inferred:
        notes.append("以下人物世代是推断值（由辈分字表或父辈链推出），请核对：" + "、".join(inferred))
    missing = [p.name for p in people if p.gen is None]
    if missing:
        notes.append("以下人物世代无法确定（未填世代、无辈分字、父辈也不在名册）：" + "、".join(missing))
    return notes


def parent_of(p: Person, by_name: Dict[str, Person]) -> Optional[Person]:
    return by_name.get(p.parent) if p.parent else None


def ancestors_of(p: Person, by_name: Dict[str, Person], limit: int = 50) -> List[Person]:
    """返回 p 及其所有祖先（含自己），按从近到远排序。成环时靠 limit 兜底。"""
    out: List[Person] = []
    seen: Set[str] = set()
    cur: Optional[Person] = p
    while cur is not None and len(out) < limit:
        if id(cur) in seen:
            break
        seen.add(id(cur))
        out.append(cur)
        cur = parent_of(cur, by_name)
    return out


def common_ancestor(a: Person, b: Person, by_name: Dict[str, Person]) -> Tuple[Optional[Person], int]:
    """最近共同祖先：取双方祖先链交集里「世代最大（最靠下）」的那位。
    返回 (共同祖先, 距离 = 主角世代 - 共同祖先世代)；无交集返回 (None, -1)。"""
    anc_a = ancestors_of(a, by_name)
    anc_b = {id(x): x for x in ancestors_of(b, by_name)}
    common = [x for x in anc_a if id(x) in anc_b]
    if not common:
        return None, -1
    common.sort(key=lambda x: (-(x.gen or 0)))
    ca = common[0]
    if ca.gen is None or a.gen is None:
        return ca, -1
    return ca, a.gen - ca.gen


def levenshtein(a: str, b: str) -> int:
    """编辑距离（只做名字这种短串，O(len^2) 足够）。"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# ---------------------------------------------------------------------------
# 4. 六项校验
# ---------------------------------------------------------------------------
class Issue:
    def __init__(self, level: str, rule: str, people: List[str], detail: str, advice: str) -> None:
        self.level = level      # 错误 / 警告 / 提示
        self.rule = rule
        self.people = people
        self.detail = detail
        self.advice = advice

    def as_dict(self) -> Dict[str, Any]:
        return {"level": self.level, "rule": self.rule, "people": self.people,
                "detail": self.detail, "advice": self.advice}


def check_zipai_consistency(people: List[Person], zipai_order: List[str]) -> List[Issue]:
    """规则 1：同辈字辈一致。
    (a) 同一世代内出现两个以上辈分字 → 错误（同辈不同字＝读者记不住）。
    (b) 同一辈分字出现在两个世代 → 错误（字辈跨代复用）。
    (c) 给了字辈表时，人物的辈分字必须等于 表[世代-1]。
    """
    issues: List[Issue] = []
    by_gen: Dict[int, List[Person]] = {}
    for p in people:
        if p.gen is not None:
            by_gen.setdefault(p.gen, []).append(p)

    for gen in sorted(by_gen):
        members = [p for p in by_gen[gen] if p.zipai]
        groups: Dict[str, List[str]] = {}
        for p in members:
            groups.setdefault(p.zipai[0], []).append(p.name)
        if len(groups) > 1:
            desc = "；".join(f"「{z}」字辈：{'、'.join(ns)}" for z, ns in groups.items())
            issues.append(Issue(
                "错误", "同辈字辈一致", sorted(sum(groups.values(), [])),
                f"第 {gen} 代出现了 {len(groups)} 个不同辈分字 —— {desc}",
                "同代只能用一个辈分字；把不合群的那位改到正确世代，或补一句过继/外姓收养的设定。"))

    zipai_gens: Dict[str, Set[int]] = {}
    for p in people:
        if p.zipai and p.gen is not None:
            zipai_gens.setdefault(p.zipai[0], set()).add(p.gen)
    for z, gens in sorted(zipai_gens.items()):
        if len(gens) > 1:
            who = [p.name for p in people if p.zipai and p.zipai[0] == z]
            issues.append(Issue(
                "错误", "同辈字辈一致", who,
                f"辈分字「{z}」同时出现在第 {'、'.join(str(g) for g in sorted(gens))} 代",
                "字辈是一次性排好的诗序，不能跨代复用；另一个世代换用相邻的那个字。"))

    if zipai_order:
        # 字辈表与「世代」是相对关系，不是绝对关系：
        # 书里常常不写族谱第一代（表首那代人已作古），所以不能假设「第 1 代 = 表首字」。
        # 这里按数据里实际出现的最小字辈序号作为锚点，只校验「相邻世代的字辈必须按表顺序推进」。
        order_anchor = None
        seen_idx = [p.zipai_index for p in people if p.zipai_index is not None]
        if seen_idx:
            order_anchor = min(seen_idx)
        for p in people:
            if p.gen is None or not p.zipai:
                continue
            if order_anchor is not None and p.zipai_index is not None:
                # 相对校验：此人字辈在表中的序号，减去锚点，应等于「它相对锚点那一代的偏移」
                offset = p.gen - min(g for g in (q.gen for q in people) if g is not None)
                want_idx = order_anchor + offset
                if want_idx > len(zipai_order):
                    issues.append(Issue(
                        "提示", "同辈字辈一致", [p.name],
                        f"{p.name} 是第 {p.gen} 代，已超出字辈表长度（{len(zipai_order)} 字）",
                        "把字辈表加长，或改用「祖字+自选字」的家族规矩说明。"))
                    continue
                want = zipai_order[want_idx - 1]
                if p.zipai[0] != want:
                    issues.append(Issue(
                        "错误", "同辈字辈一致", [p.name],
                        f"{p.name} 是第 {p.gen} 代，按字辈表应排「{want}」字辈，实际写的是「{p.zipai[0]}」"
                        f"（字辈表 {','.join(zipai_order)}，以表中第 {order_anchor} 字对应第 1 代为基准）",
                        f"改为「{want}」字辈；若族谱确实不从表首起算，把缺失的祖辈补进名册或调整字辈表。"))
            elif p.gen > len(zipai_order):
                issues.append(Issue(
                    "提示", "同辈字辈一致", [p.name],
                    f"{p.name} 是第 {p.gen} 代，超出字辈表长度（{len(zipai_order)}）",
                    "把字辈表加长，或改用「祖字+自选字」的家族规矩说明。"))
    return issues


def check_parent_inversion(people: List[Person], by_name: Dict[str, Person]) -> List[Issue]:
    """规则 2：父子辈分倒挂。
    子世代必须 > 父世代（严格递增）；父辈字在字辈表里的序号必须 < 子辈字序号。
    父辈名字不在名册里 → 警告（要么补人，要么是笔误）。
    """
    issues: List[Issue] = []
    for p in people:
        if not p.parent:
            continue
        par = by_name.get(p.parent)
        if par is None:
            issues.append(Issue(
                "警告", "父子辈分倒挂", [p.name],
                f"{p.name} 的父辈「{p.parent}」不在名册里",
                "把父辈补进名册（推荐），或检查是否写错了名字/字号。"))
            continue
        if p.gen is not None and par.gen is not None and p.gen <= par.gen:
            issues.append(Issue(
                "错误", "父子辈分倒挂", [p.name, par.name],
                f"{p.name}（第 {p.gen} 代）是 {par.name}（第 {par.gen} 代）的子女，"
                f"世代没有变大而是持平/变小",
                "把子女世代改为父世代 +1，并同步改辈分字。"))
        if (p.zipai and par.zipai and p.zipai_index is not None
                and par.zipai_index is not None and p.zipai_index <= par.zipai_index):
            issues.append(Issue(
                "错误", "父子辈分倒挂", [p.name, par.name],
                f"{p.name} 的辈分字「{p.zipai}」不比父亲 {par.name} 的「{par.zipai}」晚辈"
                f"（字辈序号 {p.zipai_index} ≤ {par.zipai_index}）",
                "子女必须用父亲后面一位的辈分字；对照字辈表逐字核对。"))
    return issues


def check_generation_cycle(people: List[Person], by_name: Dict[str, Person]) -> List[Issue]:
    """规则 3：世代成环。
    对父辈链做 DFS 三色标记；发现环就把整条环打印出来（含自环：自己当自己的父辈）。
    """
    issues: List[Issue] = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {p.name: WHITE for p in people}

    def dfs(p: Person, stack: List[str]) -> None:
        color[p.name] = GRAY
        stack.append(p.name)
        par = parent_of(p, by_name)
        if par is not None:
            if color.get(par.name, WHITE) == GRAY:
                idx = stack.index(par.name)
                cycle = stack[idx:] + [par.name]
                issues.append(Issue(
                    "错误", "世代成环", sorted(set(cycle)),
                    "父辈链成环：" + " → ".join(cycle),
                    "其中至少有一条「父辈」填错方向；父子关系必须单向，改成明确的一父多子。"))
            elif color.get(par.name, WHITE) == WHITE:
                dfs(par, stack)
        stack.pop()
        color[p.name] = BLACK

    for p in people:
        if color.get(p.name, WHITE) == WHITE:
            dfs(p, [])
    # 合并重复报告的同一个环
    uniq: Dict[str, Issue] = {}
    for it in issues:
        uniq["|".join(it.people)] = it
    return list(uniq.values())


def check_age_consistency(people: List[Person], by_name: Dict[str, Person],
                          min_gap: int = 12) -> List[Issue]:
    """规则 4：年龄与辈分矛盾。
    (a) 父龄 <= 子龄 → 错误（年龄倒挂）。
    (b) 父龄 - 子龄 < min_gap（默认 12） → 警告（修仙文可以早育，但低于 12 岁不合理）。
    (c) 相邻两代的平均年龄如果不降反升 → 警告（说明世代/年龄有一处填错）。
    """
    issues: List[Issue] = []
    for p in people:
        par = parent_of(p, by_name)
        if par is None or p.age is None or par.age is None:
            continue
        gap = par.age - p.age
        if gap <= 0:
            issues.append(Issue(
                "错误", "年龄与辈分矛盾", [p.name, par.name],
                f"父 {par.name} {par.age} 岁，子 {p.name} {p.age} 岁 —— 父亲不比子女年长",
                "核对两人年龄；修仙文里「驻颜」可以解释外貌，但不能解释年龄倒挂。"))
        elif gap < min_gap:
            issues.append(Issue(
                "警告", "年龄与辈分矛盾", [p.name, par.name],
                f"父 {par.name} {par.age} 岁，子 {p.name} {p.age} 岁，相差 {gap} 岁（< {min_gap}）",
                "要么调大父辈年龄，要么在设定里明确这是罕见的早育/夺舍/血脉觉醒特例。"))

    by_gen: Dict[int, List[int]] = {}
    for p in people:
        if p.gen is not None and p.age is not None:
            by_gen.setdefault(p.gen, []).append(p.age)
    gens = sorted(by_gen)
    for g1, g2 in zip(gens, gens[1:]):
        if g2 != g1 + 1:
            continue
        avg1 = sum(by_gen[g1]) / len(by_gen[g1])
        avg2 = sum(by_gen[g2]) / len(by_gen[g2])
        if avg2 >= avg1:
            issues.append(Issue(
                "警告", "年龄与辈分矛盾", [],
                f"第 {g1} 代平均 {avg1:.1f} 岁，第 {g2} 代平均 {avg2:.1f} 岁 —— 晚辈反而更老",
                "检查是不是把两个人的世代填反了，或者这一代漏了年龄偏大的长辈。"))
    return issues


# ---------------------------------------------------------------------------
# 5. 称呼规则表（第 5 项校验的核心）
#
# 思路：不硬编码「应该叫什么」，而是先算两个量，再比对：
#   d      = 主角世代 - 此人世代（正数＝此人比主角高一辈，是主角的长辈；
#            因为族谱里「世代 1」是老祖宗，数字越大越晚辈，所以要用主角减对方）
#   ca_gap = 主角世代 - 最近共同祖先的世代（共同祖先离主角几代）
#   direct = 是否直系（共同祖先就是主角本人，或此人本身就是主角的祖先）
#   bucket = ca_gap - d —— 分支点相对于此人所在世代的「高度」：
#            bucket <= 1 → 亲支（亲叔伯、亲兄弟、叔公）
#            bucket == 2 → 堂支（堂伯、堂兄）
#            bucket >= 3 → 从/族支（远房）
#
# 称呼表把每个称呼词翻译成「隐含的世代差 + 亲疏档位」：
#   档位权重：直=0 亲=1 堂=2 从=3 族=3（从与族都算远支，避免误报）
# 校验分两级：
#   ① 隐含世代差 ≠ d → 警告（硬伤：把祖父辈叫成平辈，读者立刻出戏）
#   ② 世代差对、亲疏档位不一致 → 提示（软性：远房写成「堂」还是「族」，
#      各家族规矩不同，只提醒不判错）
# ---------------------------------------------------------------------------
TITLE_TABLE: List[Tuple[str, int, Optional[str]]] = [
    # 直系
    ("父亲大人", 1, "直"), ("父亲", 1, "直"), ("爸爸", 1, "直"), ("爹", 1, "直"), ("爸", 1, "直"),
    ("母亲大人", 1, "直"), ("母亲", 1, "直"), ("妈妈", 1, "直"), ("娘", 1, "直"), ("妈", 1, "直"),
    ("太爷爷", 3, "直"), ("太奶奶", 3, "直"),
    ("曾祖父", 3, "直"), ("曾祖母", 3, "直"), ("曾祖", 3, "直"),
    ("祖父大人", 2, "直"), ("祖父", 2, "直"), ("祖母", 2, "直"), ("爷爷", 2, "直"), ("奶奶", 2, "直"),
    ("长子", -1, "直"), ("次子", -1, "直"), ("长女", -1, "直"),
    ("儿子", -1, "直"), ("女儿", -1, "直"), ("孩儿", -1, "直"),
    ("孙子", -2, "直"), ("孙女", -2, "直"), ("孙儿", -2, "直"),
    ("本人", 0, "直"), ("自己", 0, "直"), ("主角", 0, "直"),
    # 亲支旁系
    ("叔爷爷", 2, "亲"), ("伯爷爷", 2, "亲"), ("二爷爷", 2, "亲"), ("三爷爷", 2, "亲"),
    ("叔公", 2, "亲"), ("伯公", 2, "亲"), ("叔祖", 2, "亲"), ("伯祖", 2, "亲"), ("姑婆", 2, "亲"),
    ("大伯", 1, "亲"), ("叔父", 1, "亲"), ("伯父", 1, "亲"), ("叔叔", 1, "亲"),
    ("姑姑", 1, "亲"), ("姑母", 1, "亲"), ("姑妈", 1, "亲"), ("姨母", 1, "亲"), ("舅父", 1, "亲"),
    ("大兄", 0, "亲"), ("亲兄", 0, "亲"), ("亲弟", 0, "亲"), ("亲姐", 0, "亲"), ("亲妹", 0, "亲"),
    ("兄长", 0, "亲"), ("胞兄", 0, "亲"), ("胞弟", 0, "亲"),
    ("哥哥", 0, "亲"), ("弟弟", 0, "亲"), ("姐姐", 0, "亲"), ("妹妹", 0, "亲"),
    ("侄女", -1, "亲"), ("侄儿", -1, "亲"), ("侄子", -1, "亲"),
    ("侄孙", -2, "亲"), ("侄孙女", -2, "亲"),
    # 堂支
    ("堂伯", 1, "堂"), ("堂叔", 1, "堂"), ("堂姑", 1, "堂"),
    ("堂兄", 0, "堂"), ("堂弟", 0, "堂"), ("堂姐", 0, "堂"), ("堂妹", 0, "堂"),
    ("堂侄女", -1, "堂"), ("堂侄", -1, "堂"),
    # 从支 / 族支
    ("从伯", 1, "从"), ("从叔", 1, "从"),
    ("再从兄", 0, "从"), ("再从弟", 0, "从"), ("从兄", 0, "从"), ("从弟", 0, "从"),
    ("从侄", -1, "从"),
    ("族叔祖", 2, "族"), ("族伯祖", 2, "族"), ("族公", 2, "族"),
    ("族叔", 1, "族"), ("族伯", 1, "族"), ("族姑", 1, "族"),
    ("族兄", 0, "族"), ("族弟", 0, "族"), ("族姐", 0, "族"), ("族妹", 0, "族"),
    ("表兄", 0, "族"), ("表弟", 0, "族"), ("表姐", 0, "族"), ("表妹", 0, "族"),
    ("族侄", -1, "族"), ("族侄女", -1, "族"), ("族孙", -2, "族"),
]
# 长词优先匹配（避免「族叔」被「叔」抢先命中）
_TITLE_SORTED = sorted(TITLE_TABLE, key=lambda x: -len(x[0]))
ROUTE_RANK = {"直": 0, "亲": 1, "堂": 2, "从": 3, "族": 3}


def match_title(said: str) -> Tuple[Optional[int], Optional[str], List[str]]:
    """从填写的称呼里识别 (隐含世代差, 亲疏档位, 命中的词)。

    取最长匹配为主（「太爷爷」优先于「爷爷」、「族叔」优先于「叔」）；
    判断歧义时只看「不被最长词包含」的那些命中，避免「太爷爷」里的「爷爷」
    被误判成第二种意思。
    """
    hits = [(kw, d, route) for kw, d, route in _TITLE_SORTED if kw in said]
    if not hits:
        return None, None, []
    primary = hits[0]
    others = [h for h in hits if h[0] not in primary[0]]
    deltas = {h[1] for h in others}
    delta = primary[1] if len(deltas) <= 1 and (not deltas or primary[1] in deltas) else None
    return delta, primary[2], [h[0] for h in hits[:4]]


def expected_route(d: int, direct: bool, ca_gap: int) -> Optional[str]:
    """按血缘距离算「应该用哪一档称呼」。direct=True 为直系；ca_gap<0 表示查不到共同祖先。"""
    if direct:
        return "直"
    if ca_gap is None or ca_gap < 0:
        return None
    bucket = ca_gap - d
    if bucket <= 1:
        return "亲"
    if bucket == 2:
        return "堂"
    if bucket == 3:
        return "从"
    return "族"


def route_word(route: Optional[str], d: int) -> str:
    """把档位翻译成人类可读的示例称呼，写进建议里。"""
    table = {
        (1, "亲"): "叔父/伯父", (1, "堂"): "堂叔/堂伯", (1, "从"): "从叔", (1, "族"): "族叔",
        (2, "亲"): "叔公/伯公", (2, "族"): "族叔祖",
        (3, "直"): "曾祖父", (3, "族"): "族太公",
        (0, "直"): "本人", (0, "亲"): "亲兄/亲弟", (0, "堂"): "堂兄/堂弟",
        (0, "从"): "从兄/从弟", (0, "族"): "族兄/族弟",
        (-1, "直"): "儿子/女儿", (-1, "亲"): "侄子/侄女", (-1, "堂"): "堂侄", (-1, "族"): "族侄",
        (-2, "直"): "孙子/孙女", (-2, "亲"): "侄孙", (-2, "族"): "族孙",
    }
    if route == "直":
        return table.get((d, "直"), "直系长/晚辈")
    return table.get((d, route), "按族规的对应称呼")


def check_titles(people: List[Person], by_name: Dict[str, Person], lead_name: Optional[str]) -> List[Issue]:
    """规则 5：称呼是否与「此人到主角的血缘距离」匹配。
    主角识别顺序：--lead 指定 > 称呼/关系里带「本人/主角/我」 > 世代最大（最晚辈）的那位。
    对每个人算出隐含档位，先查世代差（硬伤＝警告），再查亲疏档位（软性＝提示）。
    """
    issues: List[Issue] = []
    lead: Optional[Person] = None
    if lead_name:
        lead = by_name.get(lead_name)
        if lead is None:
            issues.append(Issue("警告", "称呼匹配", [lead_name],
                                f"--lead 指定的主角「{lead_name}」不在名册里",
                                "核对主角姓名，或去掉 --lead 让脚本自动识别。"))
    if lead is None:
        for p in people:
            tag = (p.title or "") + (p.rel or "")
            if any(k in tag for k in ("本人", "主角", "我")):
                lead = p
                break
    if lead is None:
        cands = [p for p in people if p.gen is not None]
        if cands:
            lead = max(cands, key=lambda p: p.gen or 0)
            issues.append(Issue("提示", "称呼匹配", [lead.name],
                                f"未显式标注主角，已按「世代最大者」推断主角为 {lead.name}",
                                "在名册里给主角填「称呼=本人」或「关系=主角」，或用 --lead 指定。"))
    if lead is None:
        issues.append(Issue("提示", "称呼匹配", [], "无法确定主角，跳过称呼校验",
                            "至少给一位人物填「称呼=本人」或「关系=主角」。"))
        return issues

    for p in people:
        if p is lead:
            continue
        said = (p.title or "") or (p.rel or "")
        if not said:
            continue
        if p.gen is None or lead.gen is None:
            issues.append(Issue("提示", "称呼匹配", [p.name],
                                f"{p.name} 或主角 {lead.name} 的世代未知，无法判断称呼「{said}」",
                                "补齐世代或辈分字后再查。"))
            continue
        d = lead.gen - p.gen  # 正数＝此人是主角的长辈（族谱里世代数字越大越晚辈）
        said_d, said_route, hit_words = match_title(said)
        if said_d is None and not hit_words:
            continue  # 表里没有的称呼（如客卿/供奉/师父），不判错
        if said_d is None:
            issues.append(Issue("提示", "称呼匹配", [p.name],
                                f"{p.name} 的称呼「{said}」同时命中 {'、'.join(hit_words)}，辈分含义有歧义",
                                "用最具体的那个称呼，或把其他叫法写进备注。"))
            continue
        ca, ca_gap = common_ancestor(lead, p, by_name)
        direct = ca is not None and ca.name in (lead.name, p.name)
        want_route = expected_route(d, direct, ca_gap)
        who = f"{p.name}（第 {p.gen} 代，与主角 {lead.name} 世代差 {d:+d}"
        who += f"，{ '直系' if direct else '旁系' }）"
        if said_d != d:
            level = "长辈" if d > 0 else ("平辈" if d == 0 else "晚辈")
            issues.append(Issue(
                "警告", "称呼匹配", [p.name, lead.name],
                f"{who} 被记作「{said}」，该称呼隐含的是「世代差 {said_d:+d}」的"
                f"{'长辈' if said_d > 0 else ('平辈' if said_d == 0 else '晚辈')}；"
                f"按血缘这位是主角的{level}",
                f"改成 {route_word(want_route, d)} 一类称呼；只有过继、赐姓、师徒这类"
                f"特殊关系才可以例外，请在备注里写明理由。"))
            continue
        if (said_route is not None and want_route is not None
                and ROUTE_RANK.get(said_route, 9) != ROUTE_RANK.get(want_route, 9)):
            issues.append(Issue(
                "提示", "称呼匹配", [p.name, lead.name],
                f"{who} 记作「{said}」（{said_route}支），按最近共同祖先算是 {want_route}支",
                f"软性问题：更精确的写法是 {route_word(want_route, d)}。"
                f"若族规习惯统称「堂/族」，保留即可。"))
    return issues


def check_duplicate_names(people: List[Person]) -> List[Issue]:
    """规则 6：重名 / 近似重名。
    (a) 完全同名 → 错误（读者会以为是同一人）。
    (b) 同姓、编辑距离 ≤1，且辈分字不同/缺失 → 警告。
        这类才是真麻烦：不同辈的人名字几乎一样，读者分不清谁是谁。
    (c) 同姓、编辑距离 ≤1，但辈分字相同 → 提示。
        同辈兄弟名字只差一个字在家族文里很常见（李文昭/李文远），
        只提醒「差异化不足、注意读者混淆」，不判错。
    最多列 12 组近似名，避免一族几十口人时刷屏。
    """
    issues: List[Issue] = []
    names: Dict[str, List[Person]] = {}
    for p in people:
        names.setdefault(p.name, []).append(p)
    for name, ps in sorted(names.items()):
        if len(ps) > 1:
            issues.append(Issue(
                "错误", "重名/近似重名", [name],
                f"「{name}」出现 {len(ps)} 次（第 {'、'.join(str(x.lineno) for x in ps)} 行）",
                "同名不同人必须改名（可加排行：李大郎/李二郎），或明确写清是同一人的两笔记录。"))

    uniq = sorted({p.name for p in people})
    near: List[Issue] = []
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            a, b = uniq[i], uniq[j]
            if a == b or len(a) < 2 or len(b) < 2:
                continue
            if a[0] != b[0] or levenshtein(a, b) > 1:
                continue
            pa = next((x for x in people if x.name == a), None)
            pb = next((x for x in people if x.name == b), None)
            za = pa.zipai[0] if (pa and pa.zipai) else ""
            zb = pb.zipai[0] if (pb and pb.zipai) else ""
            if za and zb and za == zb:
                near.append(Issue(
                    "提示", "重名/近似重名", [a, b],
                    f"「{a}」与「{b}」同辈分字、只差一个字",
                    "同辈近似名在家族文里常见，但一段里同时出现会拖慢阅读；"
                    "可给其中一个换偏旁，或固定用「排行+名」区分。"))
            else:
                near.append(Issue(
                    "警告", "重名/近似重名", [a, b],
                    f"「{a}」与「{b}」同姓、只差一个字，且辈分字"
                    f"{'不同' if za and zb else '缺失'}",
                    "这种最容易被读者当成同一人；至少改掉一个字，或写明字号区分。"))
    tail_notes: List[Issue] = []
    if len(near) > 12:
        tail_notes.append(Issue(
            "提示", "重名/近似重名", [],
            f"还有 {len(near) - 12} 组近似名未列出（共 {len(near)} 组）",
            "说明这一代命名差异化不足；开写前统一重排一次名字。"))
    return issues + near[:12] + tail_notes


# ---------------------------------------------------------------------------
# 6. 报告
# ---------------------------------------------------------------------------
LEVEL_ORDER = {"错误": 0, "警告": 1, "提示": 2}


def build_report(people: List[Person], args: argparse.Namespace,
                 bad_lines: List[str], infer_notes: List[str]) -> Dict[str, Any]:
    by_name: Dict[str, Person] = {}
    for p in people:
        by_name.setdefault(p.name, p)

    issues: List[Issue] = []
    issues += check_zipai_consistency(people, args.zipai_order)
    issues += check_parent_inversion(people, by_name)
    issues += check_generation_cycle(people, by_name)
    issues += check_age_consistency(people, by_name, args.min_age_gap)
    issues += check_titles(people, by_name, args.lead)
    issues += check_duplicate_names(people)
    issues.sort(key=lambda x: (LEVEL_ORDER.get(x.level, 9), x.rule))

    counts = {"错误": 0, "警告": 0, "提示": 0}
    for it in issues:
        counts[it.level] = counts.get(it.level, 0) + 1

    by_gen: Dict[int, List[Person]] = {}
    for p in people:
        if p.gen is not None:
            by_gen.setdefault(p.gen, []).append(p)
    overview = []
    for gen in sorted(by_gen):
        members = by_gen[gen]
        ages = [x.age for x in members if x.age is not None]
        zips = sorted({x.zipai[0] for x in members if x.zipai})
        overview.append({
            "gen": gen, "count": len(members),
            "zipai": "/".join(zips) if zips else "（未填）",
            "age_range": f"{min(ages)}-{max(ages)}" if ages else "（未填）",
            "members": "、".join(x.name for x in members),
        })
    return {
        "tool": "family_check", "version": "1.0",
        "people": len(people),
        "unresolved_gen": [p.name for p in people if p.gen is None],
        "parse_warnings": bad_lines,
        "infer_notes": infer_notes,
        "overview": overview,
        "issues": [it.as_dict() for it in issues],
        "counts": counts,
    }


def render_text(report: Dict[str, Any], args: argparse.Namespace) -> str:
    L: List[str] = []
    add = L.append
    add("=" * 78)
    add(f"族谱一致性校验：{report['people']} 人")
    add("=" * 78)
    for note in report["infer_notes"]:
        add(f"[推断] {note}")
    for w in report["parse_warnings"]:
        add(f"[解析] {w}")

    add("")
    add("── 世代概览")
    add("世代　人数　辈分字　年龄区间　成员")
    for row in report["overview"]:
        add(f"第{row['gen']}代　{row['count']}　{row['zipai']}　{row['age_range']}　{row['members']}")
    if not report["overview"]:
        add("（没有可推断出世代的人物）")

    add("")
    for rule in ["同辈字辈一致", "父子辈分倒挂", "世代成环", "年龄与辈分矛盾",
                 "称呼匹配", "重名/近似重名"]:
        items = [x for x in report["issues"] if x["rule"] == rule]
        mark = "✓" if not items else ("✗" if any(i["level"] == "错误" for i in items) else "!")
        add(f"── 校验【{rule}】：{len(items)} 条 {mark}")
        for i in items:
            who = f"（{'、'.join(i['people'])}）" if i["people"] else ""
            add(f"　[{i['level']}]{who} {i['detail']}")
            add(f"　　建议：{i['advice']}")
        if not items:
            add("　无问题")
    add("")
    add("=" * 78)
    c = report["counts"]
    add(f"结论：错误 {c.get('错误', 0)} 条　警告 {c.get('警告', 0)} 条　提示 {c.get('提示', 0)} 条")
    if c.get("错误"):
        add("先修「错误」级：辈分错了读者会直接出戏，比错别字严重得多。")
    elif c.get("警告"):
        add("无硬错误，但有警告项；开写前把这几条确认掉。")
    else:
        add("族谱一致 ✓")
    add("说明：本工具只校验「数据自洽」，不判断设定好不好看；判定阈值见脚本内注释。")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 7. 命令行
# ---------------------------------------------------------------------------
USAGE_TEXT = """family_check.py —— 家族修仙文族谱一致性校验（纯标准库）

用法：
  python family_check.py [选项] 族谱文件 [更多文件 ...]
  python family_check.py [选项] --inline "李文昭|文|3|李元昊|20|炼气三层|本人|主角"
  Get-Content 族谱.txt -Raw | python family_check.py [选项]

名册格式（每行一人，分隔符支持 | 、逗号、制表符、多个空格）：
  姓名 | 辈分字 | 世代 | 父辈 | 年龄 | 修为 | 称呼(对主角) | 与主角关系 | 备注
  · 世代：整数，主家第一代填 1，越大越晚辈；留空可由辈分字表或父辈链推断
  · 父辈：填父亲姓名，也可写「父=李承业」
  · 也支持表头行（中文列名）与 key=value 行：
    姓名=李文昭;辈分字=文;世代=3;父辈=李元昊;年龄=20;称呼=本人;关系=主角
  · # 或 // 开头的行是注释

六项校验：
  1 同辈字辈一致   2 父子辈分倒挂   3 世代成环
  4 年龄与辈分矛盾 5 称呼与血缘距离匹配   6 重名/近似重名

常用示例：
  python family_check.py --zipai-order 承,元,文,明,德 --lead 李文昭 族谱.txt
  python family_check.py --json 族谱.txt > 族谱体检.json
  python family_check.py --min-age-gap 15 --strict 族谱.txt

退出码：0 正常；2 用法错误或没解析到人物；1 文件错误；--strict 时有「错误」返回 1。
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="family_check.py",
        description="家族修仙文族谱一致性校验：字辈、辈分倒挂、世代成环、年龄、称呼、重名。",
        epilog="不传任何输入且标准输入是终端时，打印用法说明并以退出码 2 结束。",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paths", nargs="*", help="族谱清单文件（可多个）；留空则读标准输入")
    p.add_argument("--inline", action="append", default=[], metavar="数据",
                   help="内联名册数据（可重复），格式同一行一人，用 \\n 分隔多人")
    p.add_argument("--lead", metavar="主角名", help="指定主角（默认自动识别）")
    p.add_argument("--zipai-order", metavar="字1,字2,...",
                   help="字辈表顺序，如 承,元,文,明,德（用于校验与推断世代）")
    p.add_argument("--min-age-gap", type=int, default=12, metavar="N",
                   help="父子最小年龄差，低于此值报警告（默认 12）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    p.add_argument("--encoding", default="utf-8-sig", metavar="ENC",
                   help="读取编码，失败回退 gb18030/gbk（默认 utf-8-sig）")
    p.add_argument("--strict", action="store_true", help="存在「错误」级问题时退出码为 1")
    return p


def read_text(path: str, encoding: str) -> str:
    for enc in [encoding, "utf-8-sig", "utf-8", "gb18030", "gbk"]:
        try:
            with open(path, "r", encoding=enc, errors="strict") as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
        except OSError:
            raise
    with open(path, "r", encoding=encoding, errors="replace") as f:
        return f.read()


def read_stdin_text(encoding: str) -> Optional[str]:
    """从标准输入读原始字节再回退解码（原因同 writing_check：PS 5.1 管道可能是 GBK）。"""
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


def main(argv: Optional[List[str]] = None) -> int:
    setup_console()
    parser = build_parser()
    # 无参数时给出中文用法并退出非零：先解析，再看是否有任何输入来源。
    args = parser.parse_args(argv)

    if args.zipai_order is not None:
        args.zipai_order = [z.strip() for z in re.split(r"[,，、\s]+", args.zipai_order) if z.strip()]

    sources: List[Tuple[str, str]] = []
    try:
        for path in args.paths:
            if os.path.isdir(path):
                for root, _d, files in os.walk(path):
                    for fn in sorted(files):
                        if fn.lower().endswith((".txt", ".md", ".csv", ".tsv")):
                            fp = os.path.join(root, fn)
                            sources.append((fp, read_text(fp, args.encoding)))
            elif os.path.isfile(path):
                sources.append((path, read_text(path, args.encoding)))
            else:
                print(f"[错误] 找不到文件：{path}", file=sys.stderr)
                return 1
    except OSError as e:
        print(f"[错误] 读取失败：{e}", file=sys.stderr)
        return 1

    for inline in args.inline:
        sources.append(("<inline>", inline.replace("\\n", "\n")))

    if not sources:
        if sys.stdin is not None and not sys.stdin.isatty():
            data = read_stdin_text(args.encoding)
            if data:
                sources.append(("<stdin>", data))
        if not sources:
            print(USAGE_TEXT.replace("family_check.py", os.path.basename(__file__)), file=sys.stderr)
            print("[错误] 没有输入：请给出族谱文件、--inline 数据，或从标准输入传入。", file=sys.stderr)
            return 2

    people: List[Person] = []
    bad_lines: List[str] = []
    for src, text in sources:
        ps, bad = parse_text(text, src)
        people += ps
        bad_lines += [f"{os.path.basename(src)} {b}" for b in bad]

    if not people:
        print(USAGE_TEXT.replace("family_check.py", os.path.basename(__file__)), file=sys.stderr)
        print("[错误] 解析到 0 个人物。请检查：每行至少要有「姓名」，字段用 | 或逗号分隔。", file=sys.stderr)
        if bad_lines:
            print("解析失败的明细：", file=sys.stderr)
            for b in bad_lines:
                print("  - " + b, file=sys.stderr)
        return 2

    infer_notes = resolve_generations(people, args.zipai_order or [])
    report = build_report(people, args, bad_lines, infer_notes)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report, args))
    if args.strict and report["counts"].get("错误", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
