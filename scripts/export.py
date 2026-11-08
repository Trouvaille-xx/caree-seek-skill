"""导出：多 sheet XLSX（对齐调研工作簿）+ CSV / Markdown / 飞书 payload。"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402

TIER_CN = {"tier1": "一线大厂", "tier2": "成长型", "tier3": "初创小微", "unknown": "未标注"}
CONF_CN = {"high": "高", "med": "中", "low": "低", "none": "未背调"}


def exp_text(exp):
    if not exp or exp.get("min") is None:
        return "不限"
    emin, emax = exp.get("min"), exp.get("max")
    if emin == 0 and (emax is None or emax >= 99):
        return "不限"
    if emax is None or emax >= 99:
        return f"{emin}年以上"
    if emin == 0:
        return f"{emax}年以内"
    return f"{emin}-{emax}年"


def scope_label(job):
    exp = job.get("exp") or {}
    emin, emax = exp.get("min"), exp.get("max")
    if emin is None:
        return "其他"
    if emin == 1 and emax == 3:
        return "核心(1-3年)"
    if emin == 0 and (emax is None or emax >= 99):
        return "扩展(经验不限)"
    if emin == 0 and emax is not None and emax <= 1:
        return "扩展(在校/应届)"
    return "其他"


def desensitized(job, extras):
    raw = str((extras or {}).get("是否脱敏") or "").strip()
    if raw in ("是", "否"):
        return raw
    name = job.get("company") or ""
    return "是" if ("某" in name and "公司" in name) else "否"


def load_run(run: Path):
    cfg = c.read_json(run / "config.json", {}) or {}
    normalized = c.read_json(run / "normalized" / "jobs.json", None)
    analysis = c.read_json(run / "analysis.json", None)
    if not normalized or not analysis:
        c.die("缺少 normalized/jobs.json 或 analysis.json，先运行 normalize.py 与 analyze.py")
    profiles = {}
    for path in sorted((run / "profiles").glob("*.json")):
        data = c.read_json(path, None)
        if data:
            profiles[data.get("company_key") or path.stem] = data
    match = c.read_json(run / "match.json", None)
    return cfg, normalized, analysis, profiles, match


def commute_text(analysis, job_id):
    idx = (analysis.get("commute_index") or {}).get(job_id)
    if idx and idx.get("label"):
        return idx["label"]
    return "未计算" if (analysis.get("commute") or {}).get("enabled") else ""


def recommendation_text(analysis, job_id):
    rec = ((analysis.get("recommendation") or {}).get("labels") or {}).get(job_id) or {}
    label = rec.get("label") or ""
    reason = rec.get("reason") or ""
    return f"{label}（{reason}）" if label and reason else label


def build_main(analysis, normalized, profiles):
    score_map = {s["job_id"]: s["score"] for s in analysis.get("scores", [])}
    team_map = {e.get("company_key"): (e.get("team_score") or {}) for e in analysis.get("company_index", [])}
    headers = [
        "序号", "职位名称", "薪资", "月薪下限K", "月薪上限K", "月薪中值K", "折算年薪K", "薪数", "区间宽度K",
        "经验要求", "口径", "学历", "工作区域", "公司名称", "是否脱敏", "融资阶段", "公司规模", "行业",
        "法定代表人", "成立日期", "企业类型", "注册资金", "工商全称", "创始人", "联合创始人", "创始人背景",
        "公司阶段/融资", "工作地址", "公司介绍", "岗位JD原文", "JD字数", "职级推断", "技能", "匹配分",
        "通勤距离", "推荐结论", "老板/团队评分", "评分依据",
    ]
    rows = []
    for idx, job in enumerate(normalized.get("jobs", []), start=1):
        extras = job.get("extras") or {}
        profile = profiles.get(job.get("company_key")) or {}
        p_extras = profile.get("extras") or {}
        salary = job.get("salary") or {}
        meta = job.get("company_meta") or {}
        founder = profile.get("founder") or {}
        team = team_map.get(job.get("company_key")) or {}
        mid = salary.get("mid_k")
        months = salary.get("months") or 12
        rows.append([
            extras.get("序号") or idx,
            job.get("title", ""),
            salary.get("text", ""),
            salary.get("min_k", ""),
            salary.get("max_k", ""),
            mid if mid is not None else "",
            round(mid * months, 1) if mid is not None else "",
            months if mid is not None else "",
            salary.get("width_k", ""),
            exp_text(job.get("exp")),
            extras.get("口径") or scope_label(job),
            job.get("education", "不限"),
            extras.get("工作区域") or (job.get("city", "") + ("·" + job.get("district") if job.get("district") else "")),
            job.get("company", ""),
            desensitized(job, extras),
            extras.get("融资阶段") or meta.get("stage") or profile.get("funding_stage") or "",
            extras.get("公司规模") or meta.get("scale") or profile.get("size") or "",
            extras.get("行业") or meta.get("industry") or profile.get("industry") or "",
            extras.get("法定代表人") or p_extras.get("法定代表人") or "",
            extras.get("成立日期") or profile.get("founded") or p_extras.get("成立日期") or "",
            extras.get("企业类型") or p_extras.get("企业类型") or "",
            extras.get("注册资金") or p_extras.get("注册资金") or "",
            extras.get("工商全称") or p_extras.get("工商全称") or "",
            extras.get("创始人") or founder.get("name") or p_extras.get("创始人") or "",
            extras.get("联合创始人") or p_extras.get("联合创始人") or "",
            extras.get("创始人背景") or founder.get("background") or p_extras.get("创始人背景") or "",
            extras.get("公司阶段/融资") or p_extras.get("公司阶段/融资") or profile.get("funding_stage") or "",
            extras.get("工作地址") or p_extras.get("工作地址") or "",
            extras.get("公司介绍") or p_extras.get("公司介绍") or "",
            job.get("jd_text") or "",
            job.get("jd_length") or "",
            job.get("level_guess", "未知"),
            "、".join(job.get("skills", [])),
            score_map.get(job.get("job_id"), ""),
            commute_text(analysis, job.get("job_id")),
            recommendation_text(analysis, job.get("job_id")),
            f"{team.get('score')} {team.get('label')}" if team.get("score") is not None else "未评估",
            "；".join(team.get("signals") or []),
        ])
    return headers, rows


def build_companies(analysis, normalized, profiles):
    headers = [
        "序号", "公司名称", "工商全称", "是否脱敏", "融资阶段", "公司规模", "行业", "法定代表人", "成立日期",
        "注册资金", "企业类型", "创始人", "联合创始人", "创始人背景", "公司阶段/融资",
        "在招岗位数", "薪资中位K", "创始人置信度", "老板/团队评分", "评分等级", "评分依据", "来源/备注",
    ]
    company_index = {e.get("company_key"): e for e in analysis.get("company_index", [])}
    counts = {}
    mids = {}
    for job in normalized.get("jobs", []):
        key = job.get("company_key")
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        mid = (job.get("salary") or {}).get("mid_k")
        if mid is not None:
            mids.setdefault(key, []).append(mid)
    rows = []
    ordered = sorted(profiles.items(), key=lambda kv: -counts.get(kv[0], 0))
    for idx, (key, profile) in enumerate(ordered, start=1):
        extras = profile.get("extras") or {}
        founder = profile.get("founder") or {}
        values = sorted(mids.get(key, []))
        median = values[len(values) // 2] if values else ""
        sources = "；".join(s.get("url", "") for s in (profile.get("sources") or []) if s.get("url"))
        entry = company_index.get(key) or {}
        team = entry.get("team_score") or {}
        rows.append([
            idx,
            profile.get("display_name", ""),
            extras.get("工商全称", ""),
            extras.get("是否脱敏", ""),
            entry.get("funding_stage") or profile.get("funding_stage", ""),
            profile.get("size", ""),
            entry.get("industry") or profile.get("industry", ""),
            extras.get("法定代表人", ""),
            profile.get("founded", ""),
            extras.get("注册资金", ""),
            extras.get("企业类型", ""),
            founder.get("name", ""),
            extras.get("联合创始人", ""),
            founder.get("background", ""),
            extras.get("公司阶段/融资", ""),
            counts.get(key, 0),
            median,
            CONF_CN.get(profile.get("confidence"), ""),
            team.get("score") if team.get("score") is not None else "未评估",
            team.get("label", ""),
            "；".join(team.get("signals") or []),
            (profile.get("disambiguation_note") or sources or extras.get("来源/备注", "")),
        ])
    return headers, rows


def build_stats(analysis):
    s = analysis.get("salary") or {}
    overall = s.get("overall") or {}
    annual = s.get("annualized") or {}
    width = s.get("width") or {}
    dq = analysis.get("data_quality") or {}
    founders = analysis.get("founders") or {}
    rows = [
        ["岗位总数", analysis.get("n", 0)],
        ["有效薪资样本", overall.get("n", 0)],
        ["月薪 P25", overall.get("p25")], ["月薪中位", overall.get("p50")],
        ["月薪 P75", overall.get("p75")], ["月薪均值", overall.get("mean")],
        ["折算年薪 P25（K/年）", annual.get("p25")], ["折算年薪中位（K/年）", annual.get("p50")],
        ["折算年薪 P75（K/年）", annual.get("p75")],
        ["薪资区间宽度中位", width.get("p50")],
        ["超过 12 薪占比", dq.get("months_over12_pct")],
        ["JD 详情覆盖率", dq.get("detail_coverage_pct")],
        ["公司数", founders.get("companies", 0)],
        ["查到创始人姓名的公司数", founders.get("with_founder", 0)],
    ]
    commute = analysis.get("commute") or {}
    rec = analysis.get("recommendation") or {}
    rec_counts = rec.get("counts") or {}
    rows += [
        ["通勤匹配启用", "是" if commute.get("enabled") else "否"],
        ["通勤工具", commute.get("tool", "")],
        ["通勤上限（分钟）", commute.get("max_minutes")],
        ["通勤已计算岗位数", commute.get("calculated", 0)],
        ["通勤未计算岗位数", commute.get("missing", 0)],
        ["通勤在范围内岗位数", commute.get("within_max", 0)],
        ["推荐结论状态", rec.get("status", "")],
        ["推荐岗位数", rec_counts.get("recommended", 0)],
        ["可考虑岗位数", rec_counts.get("consider", 0)],
        ["待核实岗位数", rec_counts.get("pending", 0)],
        ["不推荐岗位数", rec_counts.get("not_recommended", 0)],
    ]
    if rec.get("insufficient_reason"):
        rows.append(["不推荐原因/调整建议", rec.get("insufficient_reason")])
    for label, key in [("经验", "by_experience"), ("融资阶段", "by_funding"), ("公司规模", "by_size"),
                       ("行业", "by_industry"), ("区域", "by_district")]:
        for item in (s.get(key) or [])[:12]:
            rows.append([f"{label}:{item['label']} 样本", item.get("n")])
            rows.append([f"{label}:{item['label']} 月薪中位", item.get("p50")])
    for item in (s.get("histogram") or []):
        rows.append([f"月薪分箱:{item['label']}", item.get("count")])
    for item in (s.get("annual_histogram") or []):
        rows.append([f"折算年薪分箱:{item['label']}", item.get("count")])

    cr = analysis.get("company_research") or {}
    coverage = cr.get("coverage") or {}
    concentration = cr.get("concentration") or {}
    rows += [
        ["公司调研公司数", cr.get("companies", 0)],
        ["融资披露率", coverage.get("funding_pct")],
        ["领域披露率", coverage.get("industry_pct")],
        ["成立年份覆盖率", coverage.get("founded_pct")],
        ["Top5 招聘集中度", concentration.get("top5_share_pct")],
        ["Top10 招聘集中度", concentration.get("top10_share_pct")],
        ["单岗位公司占比", concentration.get("single_job_company_pct")],
        ["HHI", concentration.get("hhi")],
    ]
    for label, key in [("公司融资", "by_funding"), ("公司领域", "by_industry"),
                       ("企业规模", "by_size"), ("公司年龄", "by_age")]:
        for item in (cr.get(key) or []):
            rows.append([f"{label}:{item['label']} 公司数", item.get("companies")])
            rows.append([f"{label}:{item['label']} 月薪中位", item.get("p50")])
    team = founders.get("team_score") or {}
    for label in ["强", "较好", "一般", "有限", "未评估"]:
        rows.append([f"老板/团队评分:{label}", team.get(label, 0)])
    return ["指标", "数值"], rows


def build_jd_index(normalized):
    headers = ["序号", "口径", "公司", "职位", "薪资", "经验", "JD全文"]
    rows = []
    for idx, job in enumerate(normalized.get("jobs", []), start=1):
        rows.append([
            (job.get("extras") or {}).get("序号") or idx,
            (job.get("extras") or {}).get("口径") or scope_label(job),
            job.get("company", ""),
            job.get("title", ""),
            (job.get("salary") or {}).get("text", ""),
            exp_text(job.get("exp")),
            job.get("jd_text") or "",
        ])
    return headers, rows


def build_founders(analysis, normalized, profiles):
    headers = ["序号", "公司名称", "创始人", "联合创始人", "创始人背景", "公司阶段/融资",
               "法定代表人", "成立日期", "是否脱敏", "在招岗位数", "置信度",
               "老板/团队评分", "评分等级", "评分依据", "来源", "备注"]
    company_index = {e.get("company_key"): e for e in analysis.get("company_index", [])}
    counts = {}
    for job in normalized.get("jobs", []):
        counts[job.get("company_key")] = counts.get(job.get("company_key"), 0) + 1
    rows = []
    idx = 0
    for key, profile in sorted(profiles.items(), key=lambda kv: -counts.get(kv[0], 0)):
        founder = profile.get("founder") or {}
        extras = profile.get("extras") or {}
        if not founder.get("name") and not founder.get("background"):
            continue
        entry = company_index.get(key) or {}
        team = entry.get("team_score") or {}
        idx += 1
        rows.append([
            idx, profile.get("display_name", ""), founder.get("name", ""), extras.get("联合创始人", ""),
            founder.get("background", ""), extras.get("公司阶段/融资", ""), extras.get("法定代表人", ""),
            profile.get("founded", ""), extras.get("是否脱敏", ""), counts.get(key, 0),
            CONF_CN.get(profile.get("confidence"), ""),
            team.get("score") if team.get("score") is not None else "未评估",
            team.get("label", ""),
            "；".join(team.get("signals") or []),
            "；".join(s.get("url", "") for s in (profile.get("sources") or []) if s.get("url")),
            profile.get("disambiguation_note", ""),
        ])
    return headers, rows


def build_match(match):
    if not match:
        return None, []
    headers = ["排名", "职位", "公司", "城市", "月薪中值K", "匹配分", "命中技能", "缺失技能",
               "通勤距离", "推荐结论", "匹配说明", "链接"]
    rows = []
    for idx, item in enumerate(match.get("ranked", []), start=1):
        commute = (item.get("commute") or {}).get("label", "")
        rec = item.get("recommendation", "")
        reason = item.get("recommendation_reason", "")
        rows.append([
            idx, item.get("title", ""), item.get("company", ""), item.get("city", ""),
            item.get("salary_mid_k", ""), item.get("score", ""),
            "、".join(item.get("matched_skills") or []), "、".join(item.get("missing_skills") or []),
            commute, f"{rec}（{reason}）" if rec and reason else rec,
            "；".join(item.get("reasons") or []), item.get("url", ""),
        ])
    return headers, rows


def col_letter(idx):
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def xml_escape(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def sheet_xml(headers, rows):
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']

    def row_xml(row_idx, cells):
        out = []
        for col_idx, value in enumerate(cells):
            if value is None or value == "":
                continue
            ref = f"{col_letter(col_idx)}{row_idx}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                out.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{xml_escape(value)}</t></is></c>')
        return f'<row r="{row_idx}">' + "".join(out) + "</row>"

    parts.append(row_xml(1, headers))
    for i, row in enumerate(rows, start=2):
        parts.append(row_xml(i, row))
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


def safe_sheet_name(name):
    cleaned = re.sub(r"[\[\]:*?/\\]", "_", name or "Sheet")
    return cleaned[:31] or "Sheet"


def write_xlsx(path: Path, sheets):
    sheets = [(safe_sheet_name(name), headers, rows) for name, headers, rows in sheets]
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
        f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, len(sheets) + 1)
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + overrides + "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    sheet_entries = "".join(
        f'<sheet name="{xml_escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
        for i, (name, _, _) in enumerate(sheets, start=1)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_entries}</sheets></workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(sheets) + 1)
        )
        + "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        for i, (_, headers, rows) in enumerate(sheets, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", sheet_xml(headers, rows))


def export_csv(path: Path, headers, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def md_escape(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def export_md(path: Path, headers, rows, cfg, analysis):
    overall = (analysis.get("salary") or {}).get("overall") or {}
    annual = (analysis.get("salary") or {}).get("annualized") or {}
    lines = [
        "# CareeSeek 求职市场分析报告",
        "",
        f"- 岗位数：{analysis.get('n', len(rows))}",
        f"- 有效薪资样本：{overall.get('n')}",
        f"- 月薪 P25 / 中位 / P75：{overall.get('p25')} / {overall.get('p50')} / {overall.get('p75')} K",
        f"- 折算月薪中位：{round(annual.get('p50', 0) / 12, 1) if annual.get('p50') else None} K",
        f"- 意向：城市 {'/'.join(cfg.get('city') or ['不限'])}；经验 {cfg.get('exp_years', '未填')} 年；岗位 {'/'.join(cfg.get('role_keywords') or ['未填'])}",
        "",
        "## 岗位总表",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(md_escape(v) for v in row) + " |")
    lines += ["", "---", "> 本报告为个人求职参考，数据来自公开招聘信息，请遵守各平台服务条款。", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="CareeSeek 导出")
    ap.add_argument("--run", help="run 目录（缺省使用最新）")
    ap.add_argument("--format", default="xlsx,csv,md", help="xlsx,csv,md,feishu 或 all")
    ap.add_argument("--out-dir", help="导出目录（缺省 <run>/exports）")
    args = ap.parse_args()

    run = c.resolve_run(args.run)
    cfg, normalized, analysis, profiles, match = load_run(run)
    main_headers, main_rows = build_main(analysis, normalized, profiles)

    formats = {x.strip().lower() for x in args.format.split(",") if x.strip()}
    if "all" in formats:
        formats = {"xlsx", "csv", "md", "feishu"}

    out_dir = Path(args.out_dir).resolve() if args.out_dir else (run / "exports")
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = []

    if "xlsx" in formats:
        sheets = [
            ("岗位JD明细", main_headers, main_rows),
            ("公司与创始人", *build_companies(analysis, normalized, profiles)),
            ("统计分析", *build_stats(analysis)),
            ("JD全文速览", *build_jd_index(normalized)),
            ("创始人背景明细", *build_founders(analysis, normalized, profiles)),
        ]
        match_headers, match_rows = build_match(match)
        if match_headers:
            sheets.append(("简历匹配结果", match_headers, match_rows))
        path = out_dir / "岗位调研汇总.xlsx"
        write_xlsx(path, sheets)
        outputs.append({"format": "xlsx", "path": str(path), "sheets": [s[0] for s in sheets]})

    if "csv" in formats:
        path = out_dir / "jobs.csv"
        export_csv(path, main_headers, main_rows)
        outputs.append({"format": "csv", "path": str(path), "note": "UTF-8 BOM"})

    if "md" in formats:
        path = out_dir / "report.md"
        export_md(path, main_headers, main_rows, cfg, analysis)
        outputs.append({"format": "md", "path": str(path)})

    if "feishu" in formats:
        path = out_dir / "feishu_payload.json"
        c.write_json(path, {
            "generated_at": c.now_iso(),
            "sheets": {
                "岗位JD明细": {"columns": main_headers, "rows": main_rows},
            },
            "instructions": "若 agent 有飞书/Feishu MCP：用 columns/rows 创建多维表格；否则用 CSV/XLSX 导入。",
        })
        outputs.append({"format": "feishu", "path": str(path)})

    c.emit({"run": str(run), "rows": len(main_rows), "outputs": outputs,
            "unknown_formats": sorted(formats - {"xlsx", "csv", "md", "feishu"})})


if __name__ == "__main__":
    main()
