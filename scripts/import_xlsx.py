"""把已有的岗位调研 xlsx 导入 CareeSeek run（岗位明细 + 公司与创始人）。

支持参考工作簿的 sheet 结构：
  岗位JD明细 / 公司与创始人 / 统计分析 / JD全文速览 / 创始人背景明细
导入后会生成 raw/jobs.jsonl、profiles/*.json、config.json、state.json，
随后可直接运行 normalize.py / analyze.py / report.py / export.py。

用法：
  python scripts/import_xlsx.py --run runs/shanghai-ai-pm --xlsx "D:/path/to/file.xlsx"
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
FUNDING_VALUES = {"未融资", "天使轮", "A轮", "B轮", "C轮", "D轮及以上", "已上市", "不需要融资"}
URL_RE = re.compile(r"https?://[^\s，,；;]+")


def read_workbook(path: Path):
    zf = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in zf.namelist():
        for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    raw_sheets = [(s.get("name"), s.get(REL_NS)) for s in workbook.find("m:sheets", NS)]
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))}
    sheets = {}
    for name, rid in raw_sheets:
        target = rels[rid]
        part = target.lstrip("/") if target.startswith("/xl/") else "xl/" + target.lstrip("/")
        root = ET.fromstring(zf.read(part))
        rows = []
        for row in root.findall(".//m:sheetData/m:row", NS):
            cells = {}
            for cell in row.findall("m:c", NS):
                ref = cell.get("r") or ""
                col = re.match(r"[A-Z]+", ref).group(0) if re.match(r"[A-Z]+", ref) else ""
                t = cell.get("t")
                v = cell.find("m:v", NS)
                if t == "s":
                    val = shared[int(v.text)] if v is not None else ""
                elif t == "inlineStr":
                    inline = cell.find("m:is", NS)
                    val = "".join(x.text or "" for x in inline.iter()) if inline is not None else ""
                else:
                    val = v.text if v is not None else ""
                cells[col] = val
            rows.append(cells)
        sheets[name] = rows
    return sheets


def sheet_map(rows, required):
    """按内容定位表头行，返回 (headers, data rows as dict keyed by header text)。"""
    header_index = None
    for i, row in enumerate(rows):
        values = {(v or "").strip() for v in row.values()}
        if all(req in values for req in required):
            header_index = i
            break
    if header_index is None:
        return [], []
    header_row = rows[header_index]
    headers = {col: (val or "").strip() for col, val in header_row.items() if (val or "").strip()}
    data = []
    for row in rows[header_index + 1:]:
        if not any((v or "").strip() for v in row.values()):
            continue
        data.append({headers[col]: (row.get(col) or "").strip() for col in headers})
    return list(headers.values()), data


def clean_industry(row):
    """参考表中有 39 行把融资阶段写进了行业列：J 空而 L 是融资值时，移回 J。"""
    funding = (row.get("融资阶段") or "").strip()
    industry = (row.get("行业") or "").strip()
    if industry in FUNDING_VALUES and not funding:
        funding = industry
        industry = "未披露"
    return funding, industry or "未披露"


def map_confidence(raw):
    s = (raw or "").strip()
    if s in ("高", "high"):
        return "high"
    if s in ("中", "中高", "med"):
        return "med"
    return "low"


def main():
    ap = argparse.ArgumentParser(description="导入已有岗位调研 xlsx")
    ap.add_argument("--run", required=True)
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--target-count", type=int, default=100)
    args = ap.parse_args()

    xlsx = Path(args.xlsx).resolve()
    if not xlsx.exists():
        c.die(f"xlsx 不存在: {xlsx}")
    run = Path(args.run).resolve()
    c.ensure_run_layout(run)

    sheets = read_workbook(xlsx)
    if "岗位JD明细" not in sheets:
        c.die("找不到 sheet：岗位JD明细")

    job_rows_all = sheets["岗位JD明细"]
    _, jobs = sheet_map(job_rows_all, ("职位名称", "公司名称"))
    jobs = [row for row in jobs if row.get("职位名称") and row.get("公司名称")]
    if not jobs:
        c.die("岗位JD明细没有解析出有效岗位")

    raw_records = []
    polluted = 0
    for idx, row in enumerate(jobs, start=1):
        funding, industry = clean_industry(row)
        if industry == "未披露" and (row.get("行业") or "") in FUNDING_VALUES:
            polluted += 1
        seq = row.get("序号") or str(idx)
        extras = {
            "序号": seq,
            "口径": row.get("口径", ""),
            "工作区域": row.get("工作区域", ""),
            "是否脱敏": row.get("是否脱敏", ""),
            "法定代表人": row.get("法定代表人", ""),
            "成立日期": row.get("成立日期", ""),
            "企业类型": row.get("企业类型", ""),
            "注册资金": row.get("注册资金", ""),
            "工商全称": row.get("工商全称", ""),
            "创始人": row.get("创始人", ""),
            "联合创始人": row.get("联合创始人", ""),
            "创始人背景": row.get("创始人背景", ""),
            "公司阶段/融资": row.get("公司阶段/融资", ""),
            "工作地址": row.get("工作地址", ""),
            "公司介绍": row.get("公司介绍", ""),
            "JD字数": row.get("JD字数", ""),
        }
        raw_records.append({
            "job_id": f"xlsx-{seq}",
            "source_url": "",
            "search_keyword": "AI产品经理",
            "page": None,
            "card": {
                "title": row.get("职位名称", ""),
                "company": row.get("公司名称", ""),
                "salary_text": row.get("薪资", ""),
                "city": row.get("工作区域", ""),
                "exp_text": row.get("经验要求", ""),
                "edu": row.get("学历", ""),
                "tags": [],
            },
            "detail": {
                "raw_text": row.get("岗位JD原文", ""),
                "posted_at": "",
                "benefits": [],
            },
            "meta": {
                "brand_stage": funding,
                "brand_industry": industry,
                "brand_scale": row.get("公司规模", ""),
            },
            "extras": extras,
        })

    c.write_json(run / "raw" / "records.json", raw_records)
    if (run / "raw" / "jobs.jsonl").exists():
        (run / "raw" / "jobs.jsonl").unlink()
    c.append_jsonl(run / "raw" / "jobs.jsonl", raw_records)

    # 公司与创始人
    profile_count = 0
    if "公司与创始人" in sheets:
        _, companies = sheet_map(sheets["公司与创始人"], ("公司名称", "创始人"))
        for row in companies:
            name = row.get("公司名称") or ""
            if not name:
                continue
            key = c.slug_key(name)
            source_text = " ".join([row.get("来源/备注", ""), row.get("备注", "")])
            urls = URL_RE.findall(source_text)
            sources = [{"title": "公开来源", "url": u, "date": ""} for u in urls[:5]]
            disambiguation = ""
            if (row.get("是否脱敏") or "") == "是":
                disambiguation = "BOSS 直聘脱敏，主体未确认；" + (row.get("来源/备注") or "")[:200]
            profile = {
                "company_key": key,
                "display_name": name,
                "aliases": [],
                "tier": "unknown",
                "funding_stage": row.get("融资阶段", ""),
                "size": row.get("公司规模", ""),
                "industry": row.get("行业", ""),
                "founded": row.get("成立日期", ""),
                "founder": {
                    "name": row.get("创始人", ""),
                    "background": row.get("创始人背景", ""),
                    "confidence": map_confidence(row.get("创始人置信度", "")),
                },
                "recent_news": [],
                "risk_signals": [],
                "sources": sources,
                "confidence": map_confidence(row.get("创始人置信度", "")),
                "disambiguation_note": disambiguation,
                "fetched_at": c.now_iso(),
                "extras": row,
            }
            c.write_json(run / "profiles" / f"{key}.json", profile)
            profile_count += 1

    cfg = {
        "city": ["上海"],
        "exp_years": 2,
        "role_keywords": ["AI产品经理", "大模型产品经理", "AIGC产品经理", "智能产品经理",
                          "算法产品经理", "AI软件产品经理", "AI应用产品经理"],
        "industry": "AI / 互联网",
        "salary_expect": {"min_k": 15, "max_k": 30, "months": 14},
        "company_size_pref": [],
        "ladder_modes": ["same_company", "cross_company", "capability_map", "salary_curve"],
        "bg_scope": "top_n",
        "top_n": 10,
        "target_count": min(int(args.target_count), 100),
        "output_format": "html",
        "export_targets": ["xlsx", "md", "feishu"],
        "pacing_profile": "conservative",
        "questionnaire_answered": ["city", "exp_years", "role_keywords", "industry"],
        "run_id": run.name,
        "created_at": c.now_iso(),
        "imported_from": str(xlsx),
    }
    c.write_json(run / "config.json", cfg)

    state = c.load_state(run)
    state.update({
        "run_id": run.name,
        "stage": "collecting",
        "jobs_collected": len(raw_records),
        "detail_done": sum(1 for r in raw_records if r["detail"].get("raw_text")),
        "pages_done": 0,
    })
    c.save_state(run, state)

    c.emit({
        "run": str(run),
        "jobs": len(raw_records),
        "profiles": profile_count,
        "industry_polluted_rows_cleaned": polluted,
        "next": "python scripts/normalize.py --run <run> && python scripts/analyze.py --run <run>",
    })


if __name__ == "__main__":
    main()
