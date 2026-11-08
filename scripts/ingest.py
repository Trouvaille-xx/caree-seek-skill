"""数据入库：接收 agent 抽取的岗位/公司 JSON，校验、去重、追加到 run 目录并更新状态。

agent 不直接写文件，统一调用本脚本，保证格式一致、可断点续跑。

用法：
  python scripts/ingest.py --run runs/x --kind jobs --file batch.json --extraction-mode card_only
  python scripts/ingest.py --run runs/x --kind jobs --file -            # 从 stdin 读
  python scripts/ingest.py --run runs/x --kind profile --file profiles.json
  python scripts/ingest.py --run runs/x --state-set active_adapter="ego-browser"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402

STAGE_ORDER = ["created", "intake_done", "preflight_done", "login_done", "collecting", "normalized", "profiled", "analyzed", "reported"]


def advance_stage(state: dict, stage: str):
    current = state.get("stage", "created")
    cur_idx = STAGE_ORDER.index(current) if current in STAGE_ORDER else -1
    new_idx = STAGE_ORDER.index(stage) if stage in STAGE_ORDER else -1
    if new_idx > cur_idx:
        state["stage"] = stage


def load_input(path_arg: str):
    if path_arg == "-":
        text = sys.stdin.read()
        source = "stdin"
    else:
        p = Path(path_arg).resolve()
        if not p.exists():
            c.die(f"输入文件不存在: {p}")
        text = p.read_text(encoding="utf-8")
        source = str(p)
    text = text.strip()
    if not text:
        return [], source
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return [data], source
        if isinstance(data, list):
            return data, source
        c.die("输入 JSON 必须是对象或数组")
    except json.JSONDecodeError:
        records = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    c.die(f"JSONL 第 {len(records) + 1} 行解析失败: {exc}")
        return records, source


def selector_version():
    sel = c.read_json(c.ROOT / "references" / "selectors.json", {}) or {}
    return sel.get("version", "unknown")


def normalize_job_record(rec: dict, mode: str | None, fallback: dict | None = None):
    if not isinstance(rec, dict):
        return None, "记录不是对象"
    fallback = fallback or {}
    fb_card = fallback.get("card") or {}
    fb_detail = fallback.get("detail") or {}
    card = rec.get("card") or {}
    detail = rec.get("detail") or {}
    company = (
        card.get("company") or detail.get("company") or rec.get("company") or fb_card.get("company") or ""
    ).strip()
    title = (
        card.get("title") or detail.get("title") or rec.get("title") or fb_card.get("title") or ""
    ).strip()
    if not company or not title:
        return None, "缺少公司或岗位名称"

    url = (rec.get("source_url") or rec.get("url") or fallback.get("source_url") or "").strip()
    city = str(card.get("city") or detail.get("city") or fb_card.get("city") or "").strip()
    salary_text = str(
        card.get("salary_text") or detail.get("salary_text") or fb_card.get("salary_text") or ""
    ).strip()
    job_id = str(rec.get("job_id") or fallback.get("job_id") or "").strip()
    if not job_id:
        if url:
            job_id = c.sha1(url)
        else:
            job_id = c.sha1("|".join([company, title, city, salary_text]))

    # 详情记录可能只带部分字段：用已有卡片数据补齐，避免覆盖/丢失
    merged_card = dict(card)
    for key, value in fb_card.items():
        if not merged_card.get(key):
            merged_card[key] = value
    merged_detail = dict(detail)
    for key, value in fb_detail.items():
        if not merged_detail.get(key):
            merged_detail[key] = value
    merged_meta = dict(rec.get("meta") if isinstance(rec.get("meta"), dict) else {})
    for key, value in (fallback.get("meta") or {}).items():
        if not merged_meta.get(key):
            merged_meta[key] = value
    merged_extras = dict(rec.get("extras") if isinstance(rec.get("extras"), dict) else {})
    for key, value in (fallback.get("extras") or {}).items():
        if not merged_extras.get(key):
            merged_extras[key] = value

    has_detail = bool(detail.get("raw_text") or detail.get("fields") or detail.get("benefits"))
    extraction_mode = mode or ("detail" if has_detail else "card_only")
    if extraction_mode not in ("card_only", "detail"):
        extraction_mode = "card_only"

    dup_hash = fallback.get("dup_hash") or c.sha1("|".join([
        company.strip().lower(), title.strip().lower(), city.lower(), salary_text.lower(),
    ]))

    return {
        "job_id": job_id,
        "source_url": url,
        "collected_at": c.now_iso(),
        "search_keyword": rec.get("search_keyword") or fallback.get("search_keyword", ""),
        "page": rec.get("page") if rec.get("page") is not None else fallback.get("page"),
        "card": merged_card,
        "detail": merged_detail,
        "meta": merged_meta,
        "extras": merged_extras,
        "extraction_mode": extraction_mode,
        "selector_version": selector_version(),
        "dup_hash": dup_hash,
        "flags": rec.get("flags", []),
    }, None


def ingest_jobs(run: Path, records: list, mode: str | None):
    jobs_file = run / "raw" / "jobs.jsonl"
    existing = c.read_jsonl(jobs_file)
    existing_ids = {r.get("job_id") for r in existing}
    detail_ids = {r.get("job_id") for r in existing if r.get("extraction_mode") == "detail"}
    existing_by_id = {r.get("job_id"): r for r in existing if r.get("job_id")}

    accepted, rejected = [], []
    added = 0
    skipped = 0
    for raw in records:
        hint = str(raw.get("job_id") or "").strip() if isinstance(raw, dict) else ""
        fallback = existing_by_id.get(hint) if hint else None
        rec, err = normalize_job_record(raw, mode, fallback)
        if err:
            rejected.append({"reason": err, "record": raw if isinstance(raw, dict) else None})
            continue
        jid = rec["job_id"]
        if jid not in existing_ids:
            accepted.append(rec)
            existing_ids.add(jid)
            added += 1
            continue
        if rec["extraction_mode"] == "detail" and jid not in detail_ids:
            accepted.append(rec)
            detail_ids.add(jid)
            added += 1
            continue
        skipped += 1

    if accepted:
        c.append_jsonl(jobs_file, accepted)

    all_recs = c.read_jsonl(jobs_file)
    unique_ids = {r.get("job_id") for r in all_recs}
    done_detail = {r.get("job_id") for r in all_recs if r.get("extraction_mode") == "detail"}

    state = c.load_state(run)
    state["jobs_collected"] = len(unique_ids)
    state["detail_done"] = len(done_detail)
    state["pending_queue"] = sorted(unique_ids - done_detail)
    advance_stage(state, "collecting")
    c.save_state(run, state)

    return {
        "kind": "jobs",
        "added": added,
        "skipped_duplicates": skipped,
        "rejected": rejected[:10],
        "rejected_count": len(rejected),
        "total_unique": len(unique_ids),
        "detail_done": len(done_detail),
        "pending_detail": len(state["pending_queue"]),
        "state_stage": state["stage"],
    }


def ingest_profiles(run: Path, records: list):
    added, skipped, rejected = 0, 0, []
    for raw in records:
        if not isinstance(raw, dict):
            rejected.append({"reason": "记录不是对象"})
            continue
        name = (raw.get("display_name") or raw.get("company") or "").strip()
        if not name:
            rejected.append({"reason": "缺少 display_name", "record": raw})
            continue
        company_key = raw.get("company_key") or c.slug_key(name)
        profile = dict(raw)
        profile["company_key"] = company_key
        profile["display_name"] = name
        profile.setdefault("aliases", [])
        profile.setdefault("risk_signals", [])
        profile.setdefault("recent_news", [])
        profile.setdefault("sources", [])
        profile.setdefault("confidence", "low")
        profile["fetched_at"] = profile.get("fetched_at") or c.now_iso()
        target = run / "profiles" / f"{company_key}.json"
        if target.exists():
            skipped += 1
        else:
            added += 1
        c.write_json(target, profile)

    profile_keys = sorted(p.stem for p in (run / "profiles").glob("*.json"))
    state = c.load_state(run)
    state["profiles_done"] = profile_keys
    advance_stage(state, "profiled")
    c.save_state(run, state)

    return {
        "kind": "profile",
        "added": added,
        "overwritten": skipped,
        "rejected": rejected,
        "profiles_total": len(profile_keys),
        "state_stage": state["stage"],
    }


def update_state(run: Path, pairs: list, pages_done=None):
    state = c.load_state(run)
    updated = {}
    for item in pairs:
        if "=" not in item:
            c.die(f"--state-set 格式应为 key=json，收到: {item}")
        key, raw = item.split("=", 1)
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        state[key] = value
        updated[key] = value
    if pages_done is not None:
        state["pages_done"] = max(int(state.get("pages_done") or 0), int(pages_done))
        updated["pages_done"] = state["pages_done"]
    c.save_state(run, state)
    return {"kind": "state", "updated": updated, "state_stage": state.get("stage")}


def main():
    ap = argparse.ArgumentParser(description="CareeSeek 数据入库")
    ap.add_argument("--run", help="run 目录（缺省使用最新）")
    ap.add_argument("--kind", choices=["jobs", "profile", "state"], default="jobs")
    ap.add_argument("--file", help="输入 JSON/JSONL 路径，- 表示 stdin")
    ap.add_argument("--extraction-mode", choices=["card_only", "detail"], help="覆盖抽取模式")
    ap.add_argument("--state-set", action="append", default=[], help='更新状态字段，如 active_adapter="ego-browser"')
    ap.add_argument("--pages-done", type=int, help="已完成的搜索页数（单调递增）")
    args = ap.parse_args()

    run = c.resolve_run(args.run)
    c.ensure_run_layout(run)

    # 仅更新状态字段时，允许省略 --kind state：ingest.py --state-set key=value / --pages-done N
    if args.kind == "state" or ((args.state_set or args.pages_done is not None) and not args.file):
        c.emit(update_state(run, args.state_set, args.pages_done))
        return

    if not args.file:
        c.die("--kind jobs/profile 需要 --file（- 表示 stdin）")
    records, source = load_input(args.file)
    if args.kind == "jobs":
        result = ingest_jobs(run, records, args.extraction_mode)
    else:
        result = ingest_profiles(run, records)
    result["source"] = source
    result["next"] = "继续采集，或运行 normalize.py"
    c.emit(result)


if __name__ == "__main__":
    main()
