"""归一化：合并 raw 记录、解析薪资/经验/学历/城市、标记职级与技能，产出 normalized/jobs.json。"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402

LEVEL_ORDER = ["初级", "中级", "高级", "资深", "专家", "管理"]

# 按优先级排列：管理 > 专家 > 资深 > 高级 > 初级 > 中级
LEVEL_PATTERNS = [
    (re.compile(r"总监|主管|负责人|组长|leader|head", re.I), "管理"),
    (re.compile(r"专家|principal", re.I), "专家"),
    (re.compile(r"资深|staff|senior ii", re.I), "资深"),
    (re.compile(r"高级|senior", re.I), "高级"),
    (re.compile(r"初级|junior", re.I), "初级"),
    (re.compile(r"中级|intermediate", re.I), "中级"),
    (re.compile(r"实习|应届|intern", re.I), "初级"),
]
TITLE_STRIP_RE = re.compile(r"实习|应届|初级|中级|高级|资深|专家|principal|senior|junior|intern|staff|[（(]?急招[)）]?", re.I)

SALARY_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[kK]?\s*[-~—至]\s*(\d+(?:\.\d+)?)\s*[kK]?")
SALARY_SINGLE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[kK]")
MONTHS_RE = re.compile(r"[·\*x×]?\s*(\d{1,2})\s*薪")

EXP_RANGE_RE = re.compile(r"(\d+)\s*[-~—]\s*(\d+)\s*年")
EXP_MIN_RE = re.compile(r"(\d+)\s*年以上")

EDU_ORDER = ["博士", "硕士", "本科", "大专", "中专", "高中"]


def build_matcher():
    data = c.read_json(c.ROOT / "references" / "skill-dictionary.json", {}) or {}
    compiled = []
    for category, items in (data.get("categories") or {}).items():
        for item in items:
            name = item["name"]
            aliases = set([name] + list(item.get("aliases", [])))
            for alias in aliases:
                alias_l = alias.lower().strip()
                if not alias_l:
                    continue
                if re.search(r"[a-z0-9+#.]", alias_l):
                    pattern = re.compile(r"(?<![a-z0-9])" + re.escape(alias_l) + r"(?![a-z0-9])", re.I)
                else:
                    pattern = re.compile(re.escape(alias_l))
                compiled.append((name, category, pattern))
    return compiled


def tag_skills(text: str, matcher) -> list:
    if not text:
        return []
    lowered = text.lower()
    found = {}
    for name, category, pattern in matcher:
        if pattern.search(lowered):
            found.setdefault(name, category)
    return sorted(found)


def parse_salary(text: str) -> dict:
    result = {"min_k": None, "max_k": None, "months": 12, "text": (text or "").strip(), "unparsed": False}
    if not text:
        result["unparsed"] = True
        return result
    t = text.replace("千", "K").replace("ｋ", "K").strip()

    months_match = MONTHS_RE.search(t)
    if months_match:
        months = int(months_match.group(1))
        result["months"] = months if 12 <= months <= 24 else 12

    if re.search(r"面议|元/天|元/时|元/小时|天/元", t):
        result["unparsed"] = True
        return result

    range_match = SALARY_RANGE_RE.search(t)
    if range_match and re.search(r"[kK]|元", t):
        lo, hi = float(range_match.group(1)), float(range_match.group(2))
        if "元" in t and "K" not in t:
            lo, hi = lo / 1000.0, hi / 1000.0
        if lo > hi:
            lo, hi = hi, lo
        result["min_k"], result["max_k"] = lo, hi
        return result

    single_match = SALARY_SINGLE_RE.search(t)
    if single_match:
        value = float(single_match.group(1))
        result["min_k"] = result["max_k"] = value
        return result

    result["unparsed"] = True
    return result


def parse_exp(text: str):
    if not text:
        return None
    t = text.strip()
    if re.search(r"不限|无经验|无需经验", t):
        return {"min": 0, "max": 99}
    if re.search(r"应届|在校|实习", t):
        return {"min": 0, "max": 1}
    m = EXP_RANGE_RE.search(t)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        return {"min": lo, "max": hi}
    m = EXP_MIN_RE.search(t)
    if m:
        return {"min": int(m.group(1)), "max": 99}
    m = re.search(r"(\d+)\s*年", t)
    if m:
        return {"min": int(m.group(1)), "max": int(m.group(1))}
    return None


def parse_edu(text: str) -> str:
    if not text:
        return "不限"
    for edu in EDU_ORDER:
        if edu in text:
            return edu
    if re.search(r"不限|无要求", text):
        return "不限"
    return "不限"


def split_city(text: str):
    t = (text or "").strip()
    if not t:
        return "", ""
    parts = re.split(r"[·・\-—\s]+", t)
    city = parts[0].strip()
    district = parts[1].strip() if len(parts) > 1 else ""
    return city, district


def guess_level(title: str, exp):
    for pattern, level in LEVEL_PATTERNS:
        if pattern.search(title or ""):
            return level
    if exp and exp.get("min") is not None:
        years = exp["min"]
        if years <= 1:
            return "初级"
        if years <= 3:
            return "中级"
        if years <= 5:
            return "高级"
        if years <= 8:
            return "资深"
        return "专家"
    return "未知"


def title_family(title: str) -> str:
    family = TITLE_STRIP_RE.sub("", title or "")
    family = re.sub(r"[\-—_/|（）()]+", " ", family)
    family = re.sub(r"\s+", " ", family).strip()
    return family or (title or "").strip()


def merge_records(records: list) -> dict:
    merged = {}
    for rec in records:
        jid = rec.get("job_id")
        if not jid:
            continue
        base = merged.setdefault(jid, {
            "job_id": jid,
            "card": {},
            "detail": {},
            "meta": {},
            "extras": {},
            "source_url": "",
            "search_keyword": "",
            "dup_hash": "",
            "flags": [],
        })
        for key in ("card", "detail", "meta", "extras"):
            values = rec.get(key) or {}
            for k, v in values.items():
                if v not in (None, "", [], {}):
                    base[key][k] = v
        base["source_url"] = base["source_url"] or rec.get("source_url", "")
        base["search_keyword"] = base["search_keyword"] or rec.get("search_keyword", "")
        base["dup_hash"] = base["dup_hash"] or rec.get("dup_hash", "")
        base["flags"] = sorted(set(base["flags"]) | set(rec.get("flags") or []))
    return merged


def main():
    args = _parse_run()
    run = c.resolve_run(args)
    records = c.read_jsonl(run / "raw" / "jobs.jsonl")
    if not records:
        c.die("raw/jobs.jsonl 为空，先采集岗位数据")

    matcher = build_matcher()
    merged = merge_records(records)
    jobs = []
    missing_salary = 0
    detail_count = 0
    quality_excluded = []

    for jid, rec in merged.items():
        card, detail = rec["card"], rec["detail"]
        company = (card.get("company") or detail.get("company") or "").strip()
        title = (card.get("title") or detail.get("title") or "").strip()
        if not company or not title:
            quality_excluded.append({"job_id": jid, "reason": "缺少公司或岗位"})
            continue

        city, district = split_city(card.get("city") or detail.get("city") or "")
        salary = parse_salary(card.get("salary_text") or detail.get("salary_text"))
        exp = parse_exp(card.get("exp_text") or detail.get("exp_text"))
        edu = parse_edu(card.get("edu") or detail.get("edu"))
        level = guess_level(title, exp)
        family = title_family(title)
        tags = card.get("tags") or []
        raw_text = detail.get("raw_text") or ""
        meta = rec.get("meta") or {}
        skills = tag_skills(" ".join([title, str(card.get("salary_text", "")), raw_text, " ".join(map(str, tags))]), matcher)
        summary = re.sub(r"\s+", " ", raw_text).strip()[:200]

        quality_flags = []
        if salary["min_k"] is None:
            missing_salary += 1
            quality_flags.append("salary_missing")
        if exp is None:
            quality_flags.append("exp_missing")
        if level == "未知":
            quality_flags.append("level_unknown")
        if not district:
            quality_flags.append("district_missing")

        mid_annual = None
        mid_k = None
        width_k = None
        if salary["min_k"] is not None and salary["max_k"] is not None:
            mid_k = round((salary["min_k"] + salary["max_k"]) / 2.0, 2)
            width_k = round(salary["max_k"] - salary["min_k"], 2)
            mid_annual = round(mid_k * salary["months"], 1)

        has_detail = bool(raw_text or detail.get("benefits"))
        if has_detail:
            detail_count += 1
        jd_text = raw_text.strip()
        jd_length = len(re.sub(r"\s+", "", jd_text))

        jobs.append({
            "job_id": jid,
            "title": title,
            "title_family": family,
            "level_guess": level,
            "company": company,
            "company_key": c.slug_key(company),
            "salary": {
                "min_k": salary["min_k"],
                "max_k": salary["max_k"],
                "months": salary["months"],
                "mid_k": mid_k,
                "mid_annual_k": mid_annual,
                "width_k": width_k,
                "text": salary["text"],
            },
            "city": city,
            "district": district,
            "exp": exp or {"min": None, "max": None},
            "education": edu,
            "skills": skills,
            "company_meta": {
                "stage": meta.get("brand_stage") or meta.get("stage") or "",
                "industry": meta.get("brand_industry") or meta.get("industry") or "",
                "scale": meta.get("brand_scale") or meta.get("scale") or "",
            },
            "benefits": detail.get("benefits") or [],
            "jd_text": jd_text,
            "jd_length": jd_length,
            "extras": rec.get("extras") or {},
            "jd_summary": summary,
            "posted_at": detail.get("posted_at") or "",
            "url": rec["source_url"],
            "dup_hash": rec["dup_hash"],
            "search_keyword": rec["search_keyword"],
            "detail_available": has_detail,
            "quality_flags": quality_flags,
        })

    n = len(jobs)
    quality = {
        "n": n,
        "excluded": len(quality_excluded),
        "excluded_examples": quality_excluded[:10],
        "missing_salary": missing_salary,
        "missing_salary_pct": round(missing_salary / n * 100, 1) if n else 0,
        "detail_coverage_pct": round(detail_count / n * 100, 1) if n else 0,
    }

    out = {
        "generated_at": c.now_iso(),
        "n": n,
        "quality": quality,
        "jobs": jobs,
    }
    c.write_json(run / "normalized" / "jobs.json", out)

    state = c.load_state(run)
    state["stage"] = "normalized"
    state["jobs_collected"] = n
    c.save_state(run, state)

    c.emit({
        "run": str(run),
        "n": n,
        "quality": quality,
        "output": str(run / "normalized" / "jobs.json"),
        "next": "运行 analyze.py（如需背调，先按 background-check.md 采集公司档案）",
    })


def _parse_run():
    import argparse
    ap = argparse.ArgumentParser(description="CareeSeek 归一化")
    ap.add_argument("--run", help="run 目录（缺省使用最新）")
    args = ap.parse_args()
    return args.run


if __name__ == "__main__":
    main()
