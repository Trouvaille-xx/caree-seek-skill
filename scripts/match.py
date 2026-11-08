"""简历 × 岗位匹配：读取 resume.json / resume-profile.json，产出 match.json（含排序、差距、建议）。"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402
import normalize as nz  # noqa: E402
import analyze as an  # noqa: E402

CITY_LIST = ["北京", "上海", "广州", "深圳", "杭州", "成都", "南京", "武汉", "西安", "苏州", "天津"]
EDU_RANK = {"博士": 4, "硕士": 3, "本科": 2, "大专": 1, "不限": 0, "": 0}
ROLE_HINTS = ["AI产品经理", "大模型", "AIGC", "数据产品", "策略产品", "智能产品", "算法产品",
              "产品经理", "产品运营", "用户增长", "商业化"]


def exp_text(exp):
    if not exp or exp.get("min") is None:
        return "不限"
    emin, emax = exp.get("min"), exp.get("max")
    if emin == 0 and (emax is None or emax >= 99):
        return "不限"
    if emax is None or emax >= 99:
        return f"{emin}年以上"
    return f"{emin}-{emax}年"


def edu_rank(value):
    text = value or ""
    for level in ("博士", "硕士", "本科", "大专"):
        if level in text:
            return EDU_RANK[level]
    return 0


def extract_years(text):
    patterns = [
        r"(\d+)\s*年(?:以上)?(?:工作|相关|产品|互联网|经验)",
        r"(?:工作|经验|从业)\s*(\d+)\s*年",
    ]
    years = []
    for pattern in patterns:
        years += [int(x) for x in re.findall(pattern, text)]
    return max(years) if years else 0


def extract_salary(text):
    m = re.search(r"(?:期望|薪资|月薪|待遇)[^\d]{0,8}(\d+(?:\.\d+)?)\s*[-~—至]\s*(\d+(?:\.\d+)?)\s*[kK]", text)
    if not m:
        return {"min_k": None, "max_k": None}
    lo, hi = float(m.group(1)), float(m.group(2))
    return {"min_k": lo, "max_k": hi}


def build_profile(resume: dict, matcher):
    profile = dict(resume.get("profile") or {})
    text = resume.get("text") or ""
    profile.setdefault("raw_text", text)
    profile["years_experience"] = profile.get("years_experience") or extract_years(text)
    profile["education"] = profile.get("education") or next(
        (level for level in ("博士", "硕士", "本科", "大专") if level in text), "本科"
    )
    profile["city"] = profile.get("city") or next((city for city in CITY_LIST if city in text), "")
    salary = profile.get("expected_salary") or extract_salary(text)
    profile["expected_salary"] = salary
    skills = [str(x).strip() for x in (profile.get("skills") or []) if str(x).strip()]
    skills = nz.tag_skills(" ".join(skills + [text]), matcher) if (skills or text) else []
    profile["skills"] = sorted(set(skills))
    profile["titles"] = profile.get("titles") or [hint for hint in ROLE_HINTS if hint.lower() in text.lower()][:5]
    profile["industries"] = profile.get("industries") or [
        x for x in ["互联网", "电商", "金融", "教育", "医疗", "游戏", "SaaS", "人工智能", "广告"] if x in text
    ]
    return profile


def score_job(job, profile, matcher):
    job_skills = [s for s in (job.get("skills") or []) if s]
    candidate_skills = set(profile.get("skills") or [])
    matched = [s for s in job_skills if s in candidate_skills]
    missing = [s for s in job_skills if s not in candidate_skills]
    if job_skills:
        skill_score = 40.0 * len(matched) / len(job_skills)
    else:
        skill_score = 18.0

    years = profile.get("years_experience") or 0
    exp = job.get("exp") or {}
    emin, emax = exp.get("min"), exp.get("max")
    if emin is None:
        exp_score = 10.0
        exp_note = "岗位未标注经验"
    elif years < emin:
        if years >= emin - 1:
            exp_score = 12.0
            exp_note = f"要求 {exp_text(exp)}，简历 {years} 年（略低于下限）"
        else:
            exp_score = 4.0
            exp_note = f"要求 {exp_text(exp)}，简历 {years} 年（差距较大）"
    elif emax is not None and emax <= 1 and years >= 3:
        exp_score = 6.0
        exp_note = f"岗位面向应届/在校（{exp_text(exp)}），简历 {years} 年（经验偏高，校招岗不建议优先）"
    else:
        over = years - (emax if emax is not None and emax < 99 else years)
        if over <= 1:
            exp_score = 20.0
            exp_note = f"要求 {exp_text(exp)}，简历 {years} 年（契合）"
        elif over <= 3:
            exp_score = 14.0
            exp_note = f"要求 {exp_text(exp)}，简历 {years} 年（略高于上限，可冲刺）"
        else:
            exp_score = 8.0
            exp_note = f"要求 {exp_text(exp)}，简历 {years} 年（明显高于上限）"

    candidate_edu = edu_rank(profile.get("education"))
    job_edu = edu_rank(job.get("education"))
    edu_score = 10.0 if candidate_edu >= job_edu else 4.0

    salary = job.get("salary") or {}
    mid = salary.get("mid_k")
    expect = profile.get("expected_salary") or {}
    elo, ehi = expect.get("min_k"), expect.get("max_k")
    if elo and ehi and mid:
        expect_mid = (float(elo) + float(ehi)) / 2.0
        diff = abs(mid - expect_mid) / expect_mid if expect_mid else 1.0
        salary_score = 15.0 * max(0.0, 1.0 - min(diff, 1.0))
        salary_note = f"岗位中位 {mid}K vs 期望 {expect_mid}K"
    else:
        salary_score = 7.5
        salary_note = "期望薪资或岗位薪资缺失"

    city = profile.get("city") or ""
    job_city = job.get("city") or ""
    city_score = 5.0 if (city and city in job_city) else (2.5 if not city else 0.0)
    city_note = f"简历城市 {city or '未填'}，岗位 {job_city or '未知'}"

    titles = profile.get("titles") or []
    title_text = (job.get("title") or "") + " " + (job.get("title_family") or "")
    role_hit = sum(1 for t in titles if t and t.lower() in title_text.lower())
    role_score = (10.0 * role_hit / len(titles)) if titles else 5.0
    role_note = f"方向命中 {role_hit}/{len(titles) or 0}"

    total = round(skill_score + exp_score + edu_score + salary_score + city_score + role_score, 1)
    reasons = [
        f"技能覆盖 {len(matched)}/{len(job_skills)}" + (f"：命中 {'、'.join(matched[:4])}" if matched else ""),
        exp_note, salary_note, city_note,
        f"学历要求 {job.get('education') or '不限'}",
        role_note,
    ]
    return {
        "job_id": job["job_id"],
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "company_key": job.get("company_key", ""),
        "city": job_city,
        "salary_mid_k": mid,
        "months": salary.get("months") or 12,
        "annual_mid_k": salary.get("mid_annual_k"),
        "level": job.get("level_guess", "未知"),
        "exp_text": exp_text(job.get("exp")),
        "education": job.get("education", "不限"),
        "skills": job_skills,
        "matched_skills": matched,
        "missing_skills": missing,
        "score": total,
        "breakdown": {
            "技能": round(skill_score, 1), "经验": exp_score, "学历": edu_score,
            "薪资": round(salary_score, 1), "城市": city_score, "方向": round(role_score, 1),
        },
        "reasons": reasons,
        "url": job.get("url", ""),
    }


def commute_penalty(job, commute, commute_idx):
    """通勤惩罚：只在用户启用通勤且该岗位已计算时生效。"""
    if not commute.get("enabled"):
        return 0.0, ""
    info = commute_idx.get(job.get("job_id"))
    if not info:
        return 0.0, "通勤未计算"
    minutes = float(info.get("minutes") or 0)
    limit = float(commute.get("max_minutes") or 60)
    if minutes <= limit:
        return 0.0, ""
    if minutes <= limit * 1.2 + 10:
        return 5.0, "通勤略超"
    if minutes <= limit * 1.5:
        return 10.0, "通勤偏远"
    return 20.0, "通勤明显超出上限"


def main():
    ap = argparse.ArgumentParser(description="简历 × 岗位匹配")
    ap.add_argument("--run", help="run 目录（缺省使用最新）")
    ap.add_argument("--resume", help="resume.json / resume-profile.json 路径")
    args = ap.parse_args()

    run = c.resolve_run(args.run)
    if not args.resume:
        c.die("需要 --resume（先用 extract_resume.py 提取文本，并让 agent 结构化）")
    resume = c.read_json(Path(args.resume).resolve(), None)
    if not resume:
        c.die(f"简历文件无效: {args.resume}")

    normalized = c.read_json(run / "normalized" / "jobs.json", None)
    if not normalized:
        c.die("缺少 normalized/jobs.json，先运行 normalize.py")
    jobs = normalized.get("jobs") or []
    if not jobs:
        c.die("岗位数据为空")

    matcher = nz.build_matcher()
    profile = build_profile(resume, matcher)

    cfg = c.read_json(run / "config.json", {}) or {}
    commute = an.load_commute(run, cfg)
    commute_idx = an.commute_index(jobs, commute)
    commute_sum = an.commute_summary(jobs, commute)
    rec_cfg = dict(cfg)
    if not ((rec_cfg.get("salary_expect") or {}).get("min_k")):
        rec_cfg["salary_expect"] = profile.get("expected_salary") or {}
    recommendation = an.recommendation_summary(jobs, rec_cfg, commute)

    def enrich(job):
        item = score_job(job, profile, matcher)
        penalty, penalty_note = commute_penalty(job, commute, commute_idx)
        item["base_score"] = item["score"]
        item["commute_penalty"] = penalty
        item["score"] = round(max(0.0, item["score"] - penalty), 1)
        info = commute_idx.get(job["job_id"])
        item["commute"] = {
            "label": info["label"] if info else ("未计算" if commute.get("enabled") else "未启用"),
            "minutes": info["minutes"] if info else None,
            "mode": info["mode"] if info else "",
            "within_max": info["within_max"] if info else None,
            "penalty": penalty,
            "note": penalty_note,
        }
        rec = recommendation["labels"].get(job["job_id"]) or {}
        item["recommendation"] = rec.get("label") or "待核实"
        item["recommendation_reason"] = rec.get("reason") or ""
        if penalty_note and penalty_note not in item["reasons"]:
            item["reasons"].append(penalty_note)
        return item

    ranked = sorted((enrich(job) for job in jobs), key=lambda x: -x["score"])
    scores = [x["score"] for x in ranked]
    best = ranked[0] if ranked else None
    top20 = ranked[:20]

    missing_counter = Counter()
    demand_counter = Counter()
    for item in ranked:
        for skill in item["skills"]:
            demand_counter[skill] += 1
        for skill in item["missing_skills"]:
            missing_counter[skill] += 1
    gaps = [{"skill": skill, "missing_count": count, "demand_count": demand_counter.get(skill, 0)}
            for skill, count in missing_counter.most_common(15)]

    radar_skills = [skill for skill, _ in demand_counter.most_common(8)]
    total_jobs = len(ranked) or 1
    radar = {
        "indicators": radar_skills,
        "demand": [round(demand_counter[s] / total_jobs * 100, 1) for s in radar_skills],
        "candidate": [100 if s in set(profile.get("skills") or []) else 0 for s in radar_skills],
    }

    def band_item(x):
        return {
            "job_id": x["job_id"], "title": x["title"], "company": x["company"],
            "score": x["score"], "url": x.get("url", ""),
            "recommendation": x.get("recommendation", ""),
        }

    def band(lo, hi):
        return [x for x in ranked if lo <= x["score"] < hi]
    bands = {
        "冲": [band_item(x) for x in band(75, 101)[:10]],
        "稳": [band_item(x) for x in band(60, 75)[:10]],
        "保": [band_item(x) for x in band(45, 60)[:10]],
    }

    expect = profile.get("expected_salary") or {}
    expected_mid = (float(expect.get("min_k") or 0) + float(expect.get("max_k") or 0)) / 2 if expect.get("min_k") or expect.get("max_k") else None
    top_mids = [x["salary_mid_k"] for x in top20 if x["salary_mid_k"] is not None]
    matched_median = statistics.median(top_mids) if top_mids else None
    salary_gap = {
        "expected_mid": expected_mid,
        "matched_median": matched_median,
        "delta_pct": round((expected_mid - matched_median) / matched_median * 100, 1) if expected_mid and matched_median else None,
    }

    suggestions = []
    if gaps:
        suggestions.append("优先补齐：" + "、".join(g["skill"] for g in gaps[:5]) +
                           "（在 Top 20 岗位中分别被 " + "、".join(str(g["missing_count"]) for g in gaps[:5]) + " 个岗位要求）。")

    gap_advice = {
        "产品设计": "补充完整产品设计案例：需求洞察 → 原型/PRD → 上线 → 指标复盘。",
        "团队管理": "补充跨团队推动、带人或项目负责经历，量化协作范围与结果。",
        "用户体验": "补充用户研究、可用性测试或体验优化案例。",
        "AIGC": "补充生成式 AI（文生图/视频/内容生产）的落地案例与效果指标。",
        "多模态": "补充多模态（图文/语音/视频）项目经验。",
        "数据分析": "补充 SQL、指标体系、A/B 实验与数据驱动的决策证据。",
        "大模型": "补充 LLM 应用选型、评测方法、Prompt 设计与效果指标。",
        "商业化": "补充商业化路径、收入指标或 ROI 相关项目。",
        "B端产品": "补充 B 端客户/业务流程/权限体系等复杂场景经验。",
    }
    for gap in gaps[:3]:
        advice = gap_advice.get(gap["skill"])
        if advice:
            suggestions.append(f"{gap['skill']}：{advice}")

    if salary_gap["delta_pct"] is not None:
        if salary_gap["delta_pct"] > 20:
            suggestions.append(f"期望薪资比匹配岗位中位高 {salary_gap['delta_pct']}%，建议冲刺更高职级，或把预期调整到 {round((matched_median or 0) * 1.1, 1)}K 附近。")
        elif salary_gap["delta_pct"] > 10:
            suggestions.append(f"期望薪资比匹配岗位中位高 {salary_gap['delta_pct']}%，略高于市场；面试中用可量化成果支撑溢价。")
        elif salary_gap["delta_pct"] < -20:
            suggestions.append(f"期望薪资低于匹配岗位中位 {abs(salary_gap['delta_pct'])}%，可适当上调预期。")

    best_score = best["score"] if best else 0
    if best_score < 60:
        suggestions.append("整体匹配度偏低：建议补充 AI 产品项目证据（需求-方案-上线-指标），并强化 JD 高频关键词。")
    if len(profile.get("skills") or []) < 6:
        suggestions.append("简历技能标签偏少，建议补充可验证的工具/方法（如 RAG、Agent、Prompt、SQL、数据分析）。")
    if (profile.get("years_experience") or 0) < 2:
        suggestions.append("经验年限偏短：优先投「经验不限 / 应届」岗位，并用项目深度弥补年限。")

    chong = len(band(75, 101))
    if chong:
        suggestions.append(f"投递节奏：可尝试的冲刺岗 {chong} 个，先投匹配分最高的 5 个；每投 5 个复盘一次反馈，再调整简历。")
    suggestions.append("把与 Top 岗位 JD 重合的关键词前置到简历摘要与项目首行，并为每个项目写清「背景-动作-结果」与量化指标。")

    if recommendation["status"] == "insufficient":
        suggestions.insert(0, "结论：本次没有找到符合期望的岗位，不强行推荐。" +
                           (recommendation["insufficient_reason"] or ""))
        for alt in recommendation["alternatives"][:3]:
            suggestions.append("调整建议：" + alt)
    elif recommendation["status"] == "partial":
        counts = recommendation["counts"]
        suggestions.insert(0, f"结论：{counts['recommended']} 个推荐、{counts['consider']} 个可考虑，"
                               f"{counts['pending']} 个通勤待核实；部分岗位在薪资或通勤上有轻微偏差。")

    result = {
        "run_id": run.name,
        "generated_at": c.now_iso(),
        "resume": profile,
        "stats": {
            "jobs": len(ranked),
            "best": best["score"] if best else None,
            "best_job": {"title": best["title"], "company": best["company"]} if best else None,
            "avg": round(sum(scores) / len(scores), 1) if scores else None,
            "median": round(statistics.median(scores), 1) if scores else None,
            "band_counts": {"冲": len(band(75, 101)), "稳": len(band(60, 75)), "保": len(band(45, 60)), "不推荐": len(band(0, 45))},
        },
        "ranked": ranked[:50],
        "top": ranked[:10],
        "gaps": gaps,
        "radar": radar,
        "bands": bands,
        "salary_gap": salary_gap,
        "commute": commute_sum,
        "recommendation": {
            "status": recommendation["status"],
            "counts": recommendation["counts"],
            "reason": recommendation["insufficient_reason"],
            "alternatives": recommendation["alternatives"],
            "salary_expected_min": recommendation["salary_expected_min"],
            "salary_found_top_p50": recommendation["salary_found_top_p50"],
            "commute_median": recommendation["commute_median"],
            "commute_max": recommendation["commute_max"],
        },
        "suggestions": suggestions,
    }
    out = run / "match.json"
    c.write_json(out, result)
    c.emit({
        "out": str(out),
        "best": result["stats"]["best"],
        "best_job": result["stats"]["best_job"],
        "avg": result["stats"]["avg"],
        "bands": result["stats"]["band_counts"],
        "top_gaps": [g["skill"] for g in gaps[:5]],
        "commute": commute_sum,
        "recommendation": {"status": recommendation["status"], "counts": recommendation["counts"]},
        "next": "运行 report.py 生成岗位报告与简历匹配报告",
    })


if __name__ == "__main__":
    main()
