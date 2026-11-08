"""生成演示用合成数据（不联网），用于离线验证 normalize/analyze/report 全管线。"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402

LEVEL_ORDER = ["初级", "中级", "高级", "资深", "专家", "管理"]
LEVEL_SPEC = {
    "初级": {"prefixes": ["", "初级"], "sal": (8, 16), "exp": (0, 2)},
    "中级": {"prefixes": [""], "sal": (15, 28), "exp": (1, 3)},
    "高级": {"prefixes": ["高级"], "sal": (25, 45), "exp": (3, 6)},
    "资深": {"prefixes": ["资深"], "sal": (35, 60), "exp": (5, 9)},
    "专家": {"prefixes": ["专家"], "sal": (50, 90), "exp": (8, 15)},
    "管理": {"prefixes": ["负责人", "主管"], "sal": (40, 80), "exp": (6, 15)},
}
LEVEL_WEIGHTS = [0.15, 0.30, 0.30, 0.15, 0.05, 0.05]

CITIES = [
    ("上海", "浦东新区", 0.30), ("北京", "海淀区", 0.20), ("深圳", "南山区", 0.20),
    ("杭州", "余杭区", 0.15), ("广州", "天河区", 0.08), ("成都", "高新区", 0.07),
]
COMPANIES = [
    ("字节跳动", "tier1", 0.10), ("阿里巴巴", "tier1", 0.08), ("腾讯", "tier1", 0.08),
    ("美团", "tier1", 0.08), ("拼多多", "tier1", 0.05), ("京东", "tier1", 0.05),
    ("网易", "tier1", 0.05), ("快手", "tier1", 0.04), ("小红书", "tier2", 0.06),
    ("蚂蚁集团", "tier1", 0.05), ("得物", "tier2", 0.04), ("携程", "tier2", 0.04),
    ("蔚来", "tier2", 0.03), ("理想汽车", "tier2", 0.03), ("米哈游", "tier2", 0.04),
    ("商汤科技", "tier2", 0.03), ("地平线", "tier2", 0.02), ("星辰科技", "tier3", 0.04),
    ("云帆数据", "tier3", 0.04),
]
LADDER_COMPANIES = ["字节跳动", "美团", "小红书", "商汤科技", "星辰科技", "云帆数据"]
ROLES = [
    ("后端工程师", ["Java", "Spring Boot", "MySQL", "Redis", "Kafka", "微服务", "高并发", "Docker", "Kubernetes"], 0.95),
    ("前端工程师", ["JavaScript", "TypeScript", "React", "Vue", "Webpack", "HTML/CSS", "Vite"], 0.95),
    ("数据分析师", ["SQL", "Python", "数据分析", "Tableau", "数据仓库", "Hive", "数据驱动"], 0.95),
    ("AI产品经理", ["需求分析", "PRD", "用户研究", "数据驱动", "大模型", "AIGC", "B端产品"], 1.10),
    ("算法工程师", ["Python", "机器学习", "深度学习", "PyTorch", "NLP", "推荐系统", "大模型"], 1.20),
    ("产品经理", ["需求分析", "PRD", "用户研究", "数据驱动", "商业化"], 1.00),
    ("运营专员", ["用户增长", "内容运营", "活动运营", "投放", "数据分析", "私域"], 0.82),
    ("UI设计师", ["Figma", "交互设计", "视觉设计", "用户体验", "UI设计"], 0.85),
    ("测试工程师", ["自动化测试", "性能测试", "Python", "CI/CD", "监控"], 0.88),
]
BENEFITS = ["五险一金", "弹性工作", "年终奖", "股票期权", "餐补", "免费班车"]
PROFILES = {
    "字节跳动": {
        "tier": "tier1", "funding_stage": "已上市", "size": "10000人以上", "industry": "互联网",
        "founded": "2012", "confidence": "high",
        "recent_news": [{"headline": "字节跳动持续加码 AI 产品线", "date": "2026-09-18"}],
        "risk_signals": [],
        "sources": [{"title": "公司官网", "url": "https://www.bytedance.com", "date": "2026-10-01"}],
    },
    "美团": {
        "tier": "tier1", "funding_stage": "已上市", "size": "10000人以上", "industry": "本地生活",
        "founded": "2010", "confidence": "high",
        "recent_news": [{"headline": "美团调整部分业务线组织架构", "date": "2026-08-02"}],
        "risk_signals": ["2025 年部分业务线裁员传闻（待核实）"],
        "sources": [{"title": "公司官网", "url": "https://www.meituan.com", "date": "2026-10-01"}],
    },
    "小红书": {
        "tier": "tier2", "funding_stage": "D 轮", "size": "1000-9999人", "industry": "社区电商",
        "founded": "2013", "confidence": "med",
        "recent_news": [{"headline": "小红书商业化提速", "date": "2026-07-11"}],
        "risk_signals": [],
        "sources": [{"title": "公开报道", "url": "https://example.com/news/xiaohongshu", "date": "2026-07-11"}],
    },
    "商汤科技": {
        "tier": "tier2", "funding_stage": "已上市", "size": "1000-9999人", "industry": "人工智能",
        "founded": "2014", "confidence": "med",
        "recent_news": [{"headline": "商汤发布新一代多模态模型", "date": "2026-06-20"}],
        "risk_signals": ["持续亏损，2025 年裁员传闻（待核实）"],
        "sources": [{"title": "公开报道", "url": "https://example.com/news/sensetime", "date": "2026-06-20"}],
    },
    "米哈游": {
        "tier": "tier2", "funding_stage": "未上市", "size": "1000-9999人", "industry": "游戏",
        "founded": "2012", "confidence": "high",
        "recent_news": [{"headline": "米哈游新作公布", "date": "2026-09-05"}],
        "risk_signals": [],
        "sources": [{"title": "公司官网", "url": "https://www.mihoyo.com", "date": "2026-09-05"}],
    },
    "星辰科技": {
        "tier": "tier3", "funding_stage": "天使轮", "size": "50-99人", "industry": "企业服务",
        "founded": "2024", "confidence": "low",
        "recent_news": [],
        "risk_signals": [],
        "sources": [],
        "disambiguation_note": "名称与另一家同名公司易混淆，公开信息有限，仅作参考",
    },
    "云帆数据": {
        "tier": "tier3", "funding_stage": "A 轮", "size": "100-499人", "industry": "数据服务",
        "founded": "2021", "confidence": "low",
        "recent_news": [],
        "risk_signals": ["网络爆料欠薪（未核实）"],
        "sources": [{"title": "论坛爆料", "url": "https://example.com/forum/post", "date": "2026-05-09"}],
        "disambiguation_note": "同名公司较多，未完全确认主体",
    },
}


def weighted(items):
    names = [x[0] for x in items]
    weights = [x[-1] for x in items]
    return random.choices(names, weights=weights, k=1)[0]


def build_title(family, level):
    if level == "管理":
        if "产品" in family:
            return "产品总监"
        if family.endswith("工程师"):
            return family[:-3] + "技术负责人"
        return family + "负责人"
    prefix = random.choice(LEVEL_SPEC[level]["prefixes"])
    return (prefix + family) if prefix else family


def build_salary(level, role_mult):
    base_lo, base_hi = LEVEL_SPEC[level]["sal"]
    lo = round(base_lo * role_mult * random.uniform(0.9, 1.12))
    hi = round(base_hi * role_mult * random.uniform(0.92, 1.15))
    if hi <= lo:
        hi = lo + random.randint(3, 8)
    months = random.choice([12, 12, 13, 14, 15, 16])
    return lo, hi, months


def build_exp(level, missing=False):
    if missing:
        return None
    if random.random() < 0.05:
        return "经验不限"
    lo, hi = LEVEL_SPEC[level]["exp"]
    lo = max(0, lo + random.randint(-1, 1))
    hi = max(lo + 1, hi + random.randint(-1, 1))
    return f"{lo}-{hi}年"


def build_job(idx, company, role_family, role_skills, role_mult, level, city, district):
    title = build_title(role_family, level)
    lo, hi, months = build_salary(level, role_mult)
    salary_text = f"{lo}-{hi}K·{months}薪" if random.random() > 0.05 else "面议"
    exp_text = build_exp(level, missing=random.random() < 0.05)
    edu = random.choices(["本科", "硕士", "大专"], weights=[0.7, 0.2, 0.1], k=1)[0]
    skills = random.sample(role_skills, k=min(len(role_skills), random.randint(2, 4)))
    jd = (
        f"岗位职责：负责 {role_family} 相关业务，参与需求分析、方案设计与落地；"
        f"与团队协作推动项目按期交付。任职要求：熟悉 {'、'.join(skills)}；"
        f"{level}水平，{exp_text or '经验不限'}相关经验，{edu}及以上学历。"
    )
    detail = {}
    if random.random() < 0.75:
        detail = {
            "raw_text": jd,
            "posted_at": (dt.date(2026, 8, 1) + dt.timedelta(days=random.randint(0, 98))).isoformat(),
            "benefits": random.sample(BENEFITS, k=random.randint(2, 4)),
        }
    return {
        "job_id": f"demo-{idx:04d}",
        "source_url": f"https://www.zhipin.com/job_detail/demo-{idx:04d}.html",
        "search_keyword": role_family,
        "page": random.randint(1, 5),
        "card": {
            "title": title,
            "company": company,
            "salary_text": salary_text,
            "city": f"{city}·{district}",
            "exp_text": exp_text or "",
            "edu": edu,
            "tags": skills,
        },
        "detail": detail,
        "flags": [],
    }


def main():
    ap = argparse.ArgumentParser(description="生成 CareeSeek 演示 run（合成数据）")
    ap.add_argument("--run", default="runs/demo")
    ap.add_argument("--count", type=int, default=120)
    ap.add_argument("--seed", type=int, default=20261108)
    args = ap.parse_args()
    random.seed(args.seed)

    run = (c.ROOT / args.run).resolve() if not Path(args.run).is_absolute() else Path(args.run).resolve()
    c.ensure_run_layout(run)

    records = []
    for i in range(args.count):
        if i < 48:
            company = LADDER_COMPANIES[i % len(LADDER_COMPANIES)]
            level = LEVEL_ORDER[(i // len(LADDER_COMPANIES)) % len(LEVEL_ORDER)]
        else:
            company = weighted(COMPANIES)
            level = random.choices(LEVEL_ORDER, weights=LEVEL_WEIGHTS, k=1)[0]
        family, skills, mult = random.choice(ROLES)
        city, district, _ = random.choices(CITIES, weights=[x[2] for x in CITIES], k=1)[0]
        records.append(build_job(i, company, family, skills, mult, level, city, district))

    for k in range(5):
        clone = random.choice(records[:48])
        clone = {**clone, "job_id": f"demo-dup-{k}", "source_url": f"https://www.zhipin.com/job_detail/demo-dup-{k}.html"}
        records.append(clone)

    jobs_file = run / "raw" / "jobs.jsonl"
    if jobs_file.exists():
        jobs_file.unlink()
    c.append_jsonl(jobs_file, records)

    for name, profile in PROFILES.items():
        key = c.slug_key(name)
        data = {"company_key": key, "display_name": name, **profile, "aliases": [], "fetched_at": c.now_iso()}
        c.write_json(run / "profiles" / f"{key}.json", data)

    cfg = {
        "city": ["上海"],
        "exp_years": 2,
        "role_keywords": ["AI产品经理", "产品经理"],
        "industry": "互联网/电商",
        "salary_expect": {"min_k": 20, "max_k": 35, "months": 14},
        "company_size_pref": ["大厂", "中厂"],
        "ladder_modes": ["same_company", "cross_company", "capability_map", "salary_curve"],
        "bg_scope": "top_n",
        "top_n": 5,
        "target_count": 90,
        "output_format": "html",
        "export_targets": ["csv", "md", "xlsx"],
        "pacing_profile": "standard",
        "questionnaire_answered": ["city", "exp_years", "role_keywords", "industry"],
        "run_id": run.name,
        "created_at": c.now_iso(),
    }
    c.write_json(run / "config.json", cfg)

    unique = len({r["job_id"] for r in records})
    with_detail = sum(1 for r in records if r.get("detail"))
    state = c.load_state(run)
    state.update({
        "run_id": run.name,
        "stage": "collecting",
        "jobs_collected": unique,
        "detail_done": with_detail,
        "pages_done": 12,
    })
    c.save_state(run, state)

    c.emit({
        "run": str(run),
        "records": len(records),
        "unique_jobs": unique,
        "with_detail": with_detail,
        "profiles": len(PROFILES),
        "next": "依次运行 normalize.py / analyze.py / report.py",
    })


if __name__ == "__main__":
    main()
