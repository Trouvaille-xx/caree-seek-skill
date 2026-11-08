"""分析：月薪口径的薪资结构、分层驱动、技能溢价、JD 特征、公司与阶梯。纯计算，不联网。"""
from __future__ import annotations

import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402

LEVEL_ORDER = ["初级", "中级", "高级", "资深", "专家", "管理"]
EXP_ORDER = ["1-3年", "经验不限", "在校/应届", "3-5年", "5-10年", "10年以上", "未标注"]
FUNDING_ORDER = ["未融资", "天使轮", "A轮", "B轮", "C轮", "D轮及以上", "已上市", "不需要融资", "未披露"]
SIZE_ORDER = ["0-20人", "20-99人", "100-499人", "500-999人", "1000-9999人", "10000人以上", "未披露"]

# 固定 10 箱，与参考报告口径一致；空箱不输出
HIST_EDGES = [
    (0, 10, "<10K"), (10, 15, "10–15K"), (15, 20, "15–20K"), (20, 25, "20–25K"),
    (25, 30, "25–30K"), (30, 35, "30–35K"), (35, 40, "35–40K"),
    (40, 50, "40–50K"), (50, 60, "50–60K"), (60, None, "60K+"),
]
JD_EDGES = [(0, 400, "<400字"), (400, 700, "400–700字"), (700, 1000, "700–1000字"),
            (1000, 1500, "1000–1500字"), (1500, None, "1500字+")]

TITLE_GROUPS = [
    ("AI产品经理", ["ai产品经理", "ai 产品经理", "ai产品", "人工智能产品"]),
    ("大模型", ["大模型", "llm"]),
    ("AIGC", ["aigc", "生成式"]),
    ("数据产品", ["数据产品"]),
    ("策略产品", ["策略产品"]),
    ("智能产品", ["智能产品"]),
    ("算法产品", ["算法产品"]),
]

SALARY_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[kK]?\s*[-~—]\s*(\d+(?:\.\d+)?)\s*[kK]?")
LEGAL_SUFFIX_RE = re.compile(
    r"(股份有限公司|有限责任公司|有限公司|集团|控股|科技|技术|网络|信息|服务|"
    r"中国|北京|上海|深圳|杭州|广州|成都|南京|武汉|西安|苏州|天津)"
)


def percentile(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return round(float(s[0]), 1)
    idx = (len(s) - 1) * q
    lo = int(math.floor(idx))
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return round(s[lo] * (1 - frac) + s[hi] * frac, 1)


def dist_stats(vals):
    if not vals:
        return {"n": 0, "min": None, "p25": None, "p50": None, "p75": None, "max": None, "mean": None}
    return {
        "n": len(vals),
        "min": round(float(min(vals)), 1),
        "p25": percentile(vals, 0.25),
        "p50": percentile(vals, 0.5),
        "p75": percentile(vals, 0.75),
        "max": round(float(max(vals)), 1),
        "mean": round(sum(vals) / len(vals), 1),
    }


def monthly_mid(job):
    sal = job.get("salary") or {}
    if sal.get("mid_k") is not None:
        return sal["mid_k"]
    if sal.get("mid_annual_k") is not None and sal.get("months"):
        return round(sal["mid_annual_k"] / sal["months"], 2)
    return None


def salary_width(job):
    sal = job.get("salary") or {}
    if sal.get("width_k") is not None:
        return sal["width_k"]
    if sal.get("min_k") is not None and sal.get("max_k") is not None:
        return round(sal["max_k"] - sal["min_k"], 2)
    return None


def histogram_fixed(vals):
    out = []
    for lo, hi, label in HIST_EDGES:
        count = sum(1 for v in vals if v >= lo and (hi is None or v < hi))
        if count:
            out.append({"label": label, "lo": lo, "hi": hi, "count": count})
    return out


def template_range(text):
    t = (text or "").replace("千", "K").strip()
    if not t or "面议" in t:
        return None
    m = SALARY_RANGE_RE.search(t)
    if not m:
        return None
    if "元" in t and "K" not in t:
        return float(m.group(1)) / 1000.0, float(m.group(2)) / 1000.0
    return float(m.group(1)), float(m.group(2))


def salary_templates(jobs):
    counter = Counter()
    for job in jobs:
        text = (job.get("salary") or {}).get("text") or ""
        if text:
            counter[text] += 1
    out = []
    for text, count in counter.most_common(15):
        rng = template_range(text)
        if not rng:
            continue
        out.append({"text": text, "lo": rng[0], "hi": rng[1], "count": count})
    return out


def exp_bucket(job):
    exp = job.get("exp") or {}
    emin, emax = exp.get("min"), exp.get("max")
    if emin is None:
        return "未标注"
    if emin == 0 and (emax is None or emax >= 99):
        return "经验不限"
    if emin == 0 and emax is not None and emax <= 1:
        return "在校/应届"
    if emin <= 3 and emax is not None and emax <= 3:
        return "1-3年"
    if emax is None or emax >= 99:
        return f"{emin}年以上"
    return f"{emin}-{emax}年"


def scope_bucket(job):
    bucket = exp_bucket(job)
    if bucket == "1-3年":
        return "核心(1-3年)"
    if bucket in ("经验不限", "在校/应届"):
        return "扩展(经验不限/应届)"
    return "其他"


def funding_label(raw):
    s = (raw or "").strip()
    if not s:
        return "未披露"
    if "上市" in s:
        return "已上市"
    if "不需要融资" in s:
        return "不需要融资"
    if "未融资" in s:
        return "未融资"
    for key in ["天使轮", "A轮", "B轮", "C轮", "D轮及以上"]:
        if key in s:
            return key
    return s


def desensitized_label(job):
    raw = str((job.get("extras") or {}).get("是否脱敏") or "").strip()
    if raw in ("是", "否"):
        return raw
    name = job.get("company") or ""
    return "是" if ("某" in name and "公司" in name) else "否"


def group_stats(jobs, key_fn, order=None):
    groups = defaultdict(list)
    for job in jobs:
        mid = monthly_mid(job)
        if mid is None:
            continue
        groups[key_fn(job)].append(mid)
    items = [(label, dist_stats(vals)) for label, vals in groups.items()]
    if order:
        index = {label: i for i, label in enumerate(order)}
        items.sort(key=lambda kv: (index.get(kv[0], 999), -kv[1]["n"]))
    else:
        items.sort(key=lambda kv: -kv[1]["n"])
    return [{"label": label, **stats} for label, stats in items]


def pearson(xs, ys):
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else None


def load_profiles(run: Path) -> dict:
    profiles = {}
    for path in sorted((run / "profiles").glob("*.json")):
        data = c.read_json(path, {}) or {}
        profiles[data.get("company_key") or path.stem] = data
    return profiles


def load_builtin_tiers() -> dict:
    data = c.read_json(c.ROOT / "references" / "company-tiers.json", {}) or {}
    return data.get("companies", {}) or {}


def builtin_tier(company: str, tiers: dict):
    if not company or not tiers:
        return None
    if company in tiers:
        return tiers[company]
    stripped = LEGAL_SUFFIX_RE.sub("", company)
    if stripped in tiers:
        return tiers[stripped]
    for known in sorted(tiers, key=len, reverse=True):
        if known and (known in company or stripped.startswith(known)):
            return tiers[known]
    return None


def match_score(job, cfg, profile):
    score = 0.0
    keywords = [str(k).lower() for k in cfg.get("role_keywords", []) if k]
    text = " ".join([job.get("title", ""), job.get("title_family", ""), job.get("jd_summary", ""),
                     " ".join(job.get("skills", []))]).lower()
    if keywords:
        score += 40.0 * sum(1 for k in keywords if k in text) / len(keywords)
    else:
        score += 20.0

    se = cfg.get("salary_expect") or {}
    lo, hi = se.get("min_k"), se.get("max_k")
    mid = monthly_mid(job)
    if lo and hi and mid:
        expect_mid = (float(lo) + float(hi)) / 2.0
        diff = abs(mid - expect_mid) / expect_mid if expect_mid else 1.0
        score += 25.0 * max(0.0, 1.0 - min(diff, 1.0))
    else:
        score += 12.5

    cities = cfg.get("city") or []
    if cities:
        if job.get("city") in cities:
            score += 15.0
    else:
        score += 10.0

    years = cfg.get("exp_years")
    exp = job.get("exp") or {}
    emin, emax = exp.get("min"), exp.get("max")
    if years is not None and emin is not None:
        if emin <= years <= (emax if emax is not None else 99):
            score += 10.0
        elif emin - 1 <= years <= (emax if emax is not None else 99) + 1:
            score += 6.0
        else:
            score += 2.0
    else:
        score += 5.0

    conf = (profile or {}).get("confidence")
    score += {"high": 10.0, "med": 7.0, "low": 4.0}.get(conf, 5.0)
    return round(min(100.0, score), 1)


def same_company_ladder(jobs, profiles):
    grouped = defaultdict(lambda: defaultdict(list))
    for job in jobs:
        level = job.get("level_guess")
        if level in LEVEL_ORDER:
            grouped[job["company_key"]][level].append(job)
    blocks = []
    for company_key, levels in grouped.items():
        rows = []
        for level in LEVEL_ORDER:
            items = levels.get(level) or []
            if not items:
                continue
            vals = [monthly_mid(x) for x in items if monthly_mid(x) is not None]
            rows.append({"level": level, "n": len(items), "median": percentile(vals, 0.5),
                         "titles": sorted({x["title"] for x in items})[:4]})
        if len(rows) < 2:
            continue
        prev = None
        for row in rows:
            row["step_pct"] = round((row["median"] - prev) / prev * 100, 1) if row["median"] is not None and prev else None
            if row["median"] is not None:
                prev = row["median"]
        total = sum(row["n"] for row in rows)
        display = (profiles.get(company_key) or {}).get("display_name") or next(
            (x["company"] for x in jobs if x["company_key"] == company_key), company_key)
        blocks.append({"company_key": company_key, "company": display, "rows": rows, "n": total,
                       "confidence": "ok" if len(rows) >= 3 and total >= 6 else "low"})
    blocks.sort(key=lambda b: -b["n"])
    return blocks


def cross_company_matrix(jobs, profiles, max_companies=12):
    counts = Counter(job["company_key"] for job in jobs)
    keys = [key for key, _ in counts.most_common(max_companies)]
    levels = [level for level in LEVEL_ORDER if any(job.get("level_guess") == level for job in jobs)]
    rows = []
    for company_key in keys:
        buckets = defaultdict(list)
        company_name = ""
        for job in jobs:
            if job["company_key"] != company_key:
                continue
            company_name = company_name or job["company"]
            if job.get("level_guess") in levels:
                buckets[job["level_guess"]].append(job)
        if not buckets:
            continue
        cells = {}
        for level, items in buckets.items():
            vals = [monthly_mid(x) for x in items if monthly_mid(x) is not None]
            cells[level] = {"n": len(items), "median": percentile(vals, 0.5)}
        rows.append({"company_key": company_key,
                     "company": (profiles.get(company_key) or {}).get("display_name") or company_name,
                     "cells": cells})
    rows.sort(key=lambda r: -sum(cell["n"] for cell in r["cells"].values()))
    return {"levels": levels, "rows": rows}


def capability_map(jobs, base_median):
    per_skill = defaultdict(list)
    for job in jobs:
        for skill in job.get("skills", []):
            per_skill[skill].append(job)
    total = len(jobs) or 1
    rows = []
    for skill, items in per_skill.items():
        if len(items) < 3:
            continue
        vals = [monthly_mid(x) for x in items if monthly_mid(x) is not None]
        if not vals:
            continue
        median = percentile(vals, 0.5)
        level_dist = Counter(x.get("level_guess") for x in items)
        rows.append({"skill": skill, "n": len(items), "coverage_pct": round(len(items) / total * 100, 1),
                     "median": median, "lift": round(median - (base_median or 0), 1),
                     "levels": [lvl for lvl, _ in level_dist.most_common(3) if lvl and lvl != "未知"]})
    rows.sort(key=lambda r: (-(max(r["lift"], 0) * r["coverage_pct"]), -r["n"]))
    return rows


def salary_curve(jobs):
    buckets = [(0, 1, "0-1年"), (1, 3, "1-3年"), (3, 5, "3-5年"), (5, 8, "5-8年"), (8, 99, "8年+")]
    rows = []
    for lo, hi, label in buckets:
        vals = []
        for job in jobs:
            years = (job.get("exp") or {}).get("min")
            mid = monthly_mid(job)
            if years is None or mid is None:
                continue
            if lo <= years < hi:
                vals.append(mid)
        if vals:
            rows.append({"bucket": label, "n": len(vals), "p25": percentile(vals, 0.25),
                         "median": percentile(vals, 0.5), "p75": percentile(vals, 0.75)})
    return rows


def title_stats(jobs):
    out = []
    for label, aliases in TITLE_GROUPS:
        hits = [j for j in jobs if any(a in (j.get("title") or "").lower() for a in aliases)]
        vals = [monthly_mid(j) for j in hits if monthly_mid(j) is not None]
        if hits:
            st = dist_stats(vals)
            out.append({"label": label, "n": len(hits), "p50": st["p50"], "p75": st["p75"]})
    return out


def skill_stats(jobs, base_median):
    total = len(jobs) or 1
    per_skill = defaultdict(list)
    for job in jobs:
        for skill in job.get("skills", []):
            per_skill[skill].append(job)
    top = []
    for skill, items in per_skill.items():
        vals = [monthly_mid(x) for x in items if monthly_mid(x) is not None]
        if not vals:
            continue
        median = percentile(vals, 0.5)
        top.append({"skill": skill, "n": len(items), "pct": round(len(items) / total * 100, 1),
                    "median": median, "lift": round(median - (base_median or 0), 1)})
    top.sort(key=lambda x: -x["n"])
    lift = [x for x in top if x["n"] >= 5]
    lift.sort(key=lambda x: (-x["lift"], -x["n"]))
    entry = [x for x in top if x["n"] >= 10 and x["lift"] <= 1.0]
    entry.sort(key=lambda x: -x["n"])
    return {"top": top[:20], "lift": lift[:15], "entry": entry[:8]}


def jd_stats(jobs):
    lengths = []
    pairs = []
    for job in jobs:
        length = job.get("jd_length") or len(re.sub(r"\s+", "", job.get("jd_text") or ""))
        if length:
            lengths.append(length)
        mid = monthly_mid(job)
        if length and mid is not None:
            pairs.append((length, mid))
    corr = pearson([a for a, _ in pairs], [b for _, b in pairs])
    hist = []
    for lo, hi, label in JD_EDGES:
        count = sum(1 for x in lengths if x >= lo and (hi is None or x < hi))
        if count:
            hist.append({"label": label, "count": count})
    st = dist_stats(lengths)
    return {"n": st["n"], "min": st["min"], "p25": st["p25"], "p50": st["p50"],
            "p75": st["p75"], "max": st["max"],
            "corr_salary": round(corr, 3) if corr is not None else None, "histogram": hist}


def founder_stats(profiles):
    confidence = Counter()
    with_name = 0
    for profile in profiles.values():
        if (profile.get("founder") or {}).get("name"):
            with_name += 1
        confidence[profile.get("confidence") or "low"] += 1
    return {"companies": len(profiles), "with_founder": with_name, "confidence": dict(confidence)}


def main():
    import argparse

    ap = argparse.ArgumentParser(description="CareeSeek 分析")
    ap.add_argument("--run", help="run 目录（缺省使用最新）")
    args = ap.parse_args()
    run = c.resolve_run(args.run)

    cfg = c.read_json(run / "config.json", {}) or {}
    normalized = c.read_json(run / "normalized" / "jobs.json", None)
    if not normalized:
        c.die("找不到 normalized/jobs.json，先运行 normalize.py")
    jobs = normalized.get("jobs") or []
    if not jobs:
        c.die("normalized 数据为空，无法分析")
    profiles = load_profiles(run)
    builtin_tiers = load_builtin_tiers()

    company_index = {}
    for job in jobs:
        key = job["company_key"]
        profile = profiles.get(key) or {}
        profile_tier = profile.get("tier")
        if profile_tier in ("tier1", "tier2", "tier3"):
            tier, tier_source = profile_tier, "profile"
        else:
            guess = builtin_tier(job.get("company", ""), builtin_tiers)
            tier, tier_source = (guess, "builtin") if guess else ("unknown", "unknown")
        meta = job.get("company_meta") or {}
        entry = company_index.setdefault(key, {
            "company_key": key,
            "display_name": profile.get("display_name") or job["company"],
            "tier": tier,
            "tier_source": tier_source,
            "funding_stage": profile.get("funding_stage") or meta.get("stage") or "",
            "size": profile.get("size") or meta.get("scale") or "",
            "industry": profile.get("industry") or meta.get("industry") or "",
            "confidence": profile.get("confidence") or "none",
            "risk_signals": profile.get("risk_signals") or [],
            "desensitized": desensitized_label(job) == "是",
            "jobs": 0,
        })
        entry["jobs"] += 1

    mids = [monthly_mid(j) for j in jobs if monthly_mid(j) is not None]
    overall = dist_stats(mids)
    annualized = dist_stats([
        monthly_mid(j) * ((j.get("salary") or {}).get("months") or 12) for j in jobs if monthly_mid(j) is not None
    ])
    widths = [salary_width(j) for j in jobs if salary_width(j) is not None]
    months_counter = Counter((j.get("salary") or {}).get("months") or 12 for j in jobs if monthly_mid(j) is not None)

    def funding_of(job):
        profile = profiles.get(job["company_key"]) or {}
        return funding_label((job.get("company_meta") or {}).get("stage") or profile.get("funding_stage"))

    def size_of(job):
        profile = profiles.get(job["company_key"]) or {}
        return (job.get("company_meta") or {}).get("scale") or profile.get("size") or "未披露"

    def industry_of(job):
        profile = profiles.get(job["company_key"]) or {}
        return (job.get("company_meta") or {}).get("industry") or profile.get("industry") or "未披露"

    salary = {
        "overall": overall,
        "annualized": annualized,
        "histogram": histogram_fixed(mids),
        "templates": salary_templates(jobs),
        "months": [{"months": m, "count": n} for m, n in sorted(months_counter.items())],
        "width": dist_stats(widths),
        "by_experience": group_stats(jobs, exp_bucket, EXP_ORDER),
        "by_scope": group_stats(jobs, scope_bucket),
        "by_funding": group_stats(jobs, funding_of, FUNDING_ORDER),
        "by_size": group_stats(jobs, size_of, SIZE_ORDER),
        "by_industry": group_stats(jobs, industry_of),
        "by_district": group_stats(jobs, lambda j: j.get("district") or "未标注"),
        "by_education": group_stats(jobs, lambda j: j.get("education") or "不限"),
        "by_desensitized": group_stats(jobs, desensitized_label, ["否", "是"]),
    }

    ladders = {
        "same_company": same_company_ladder(jobs, profiles),
        "cross_company": cross_company_matrix(jobs, profiles),
        "capability_map": capability_map(jobs, overall["p50"]),
        "salary_curve": salary_curve(jobs),
    }

    scores = []
    for job in jobs:
        scores.append({"job_id": job["job_id"], "score": match_score(job, cfg, profiles.get(job["company_key"]))})
    score_map = {x["job_id"]: x["score"] for x in scores}
    ranked = sorted([
        {"job_id": j["job_id"], "title": j["title"], "company": j["company"], "city": j.get("city", ""),
         "mid_k": monthly_mid(j), "score": score_map[j["job_id"]]}
        for j in jobs
    ], key=lambda x: -x["score"])[:20]

    anomalies = []
    for job in jobs:
        sal = job.get("salary") or {}
        mid = monthly_mid(job)
        if sal.get("min_k") is not None and sal.get("max_k") is not None and sal["min_k"] > sal["max_k"]:
            anomalies.append({"type": "salary_inverted", "job_id": job["job_id"], "detail": sal.get("text", "")})
        if mid is not None and (mid < 3 or mid > 150):
            anomalies.append({"type": "salary_extreme", "job_id": job["job_id"], "detail": mid})
    dup_groups = defaultdict(list)
    for job in jobs:
        dup_groups[job.get("dup_hash") or job["job_id"]].append(job["job_id"])
    duplicates = [ids for ids in dup_groups.values() if len(ids) > 1]
    if duplicates:
        anomalies.append({"type": "duplicate_posts", "count": len(duplicates),
                          "examples": [ids[:3] for ids in duplicates[:5]]})

    data_quality = dict(normalized.get("quality") or {})
    data_quality.update({
        "job_count": len(jobs),
        "salary_valid": overall["n"],
        "width_median": percentile(widths, 0.5),
        "months_over12_pct": round(sum(1 for m, n in months_counter.items() if m > 12 for _ in range(n)) / overall["n"] * 100, 1) if overall["n"] else 0,
    })

    companies = []
    grouped = defaultdict(list)
    for job in jobs:
        grouped[job["company_key"]].append(job)
    for key, items in grouped.items():
        vals = [monthly_mid(x) for x in items if monthly_mid(x) is not None]
        st = dist_stats(vals)
        entries = company_index.get(key) or {}
        companies.append({"company_key": key, "display_name": entries.get("display_name") or items[0]["company"],
                          "n": len(items), "p50": st["p50"], "p75": st["p75"],
                          "tier": entries.get("tier", "unknown"), "desensitized": desensitized_label(items[0]) == "是"})
    companies.sort(key=lambda x: -x["n"])

    low_confidence_flags = []
    if overall["n"] < 20:
        low_confidence_flags.append(f"有效薪资样本仅 {overall['n']} 条，结论置信度低")
    if data_quality.get("missing_salary_pct", 0) > 30:
        low_confidence_flags.append(f"{data_quality['missing_salary_pct']}% 岗位缺失薪资")
    if data_quality.get("detail_coverage_pct", 0) < 50:
        low_confidence_flags.append("JD 详情覆盖率不足 50%，技能分析可能偏差")
    if data_quality.get("width_median") and data_quality["width_median"] > 8:
        low_confidence_flags.append(
            f"薪资区间宽度中位 {data_quality['width_median']}K，用中值单点代表岗位约有 ±{data_quality['width_median'] / 2:.1f}K 误差")
    founders = founder_stats(profiles)
    if founders["companies"] and founders["with_founder"] / founders["companies"] < 0.6:
        low_confidence_flags.append(
            f"仅 {founders['with_founder']}/{founders['companies']} 家公司查到创始人姓名，背调覆盖不完整")

    analysis = {
        "run_id": run.name,
        "generated_at": c.now_iso(),
        "n": len(jobs),
        "salary": salary,
        "skills": skill_stats(jobs, overall["p50"]),
        "titles": title_stats(jobs),
        "jd": jd_stats(jobs),
        "founders": founders,
        "companies": companies[:12],
        "ladders": ladders,
        "scores": scores,
        "ranked_jobs": ranked,
        "company_index": sorted(company_index.values(), key=lambda x: -x["jobs"]),
        "anomalies": anomalies,
        "data_quality": data_quality,
        "low_confidence_flags": low_confidence_flags,
    }
    c.write_json(run / "analysis.json", analysis)

    state = c.load_state(run)
    state["stage"] = "analyzed"
    c.save_state(run, state)

    c.emit({
        "run": str(run),
        "n": len(jobs),
        "salary_monthly": overall,
        "salary_annualized": annualized,
        "width_median": data_quality.get("width_median"),
        "top_companies": [x["display_name"] for x in companies[:5]],
        "skills_top": [x["skill"] for x in analysis["skills"]["top"][:8]],
        "founders": founders,
        "low_confidence_flags": low_confidence_flags,
        "output": str(run / "analysis.json"),
        "next": "运行 report.py 生成 HTML 报告",
    })


if __name__ == "__main__":
    main()
