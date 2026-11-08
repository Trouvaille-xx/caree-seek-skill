"""通勤数据：列出待计算岗位，或校验并合并地图工具返回的 commute.json。

浏览器/地图 MCP 由宿主 agent 调用；本脚本只做数据校验、去重与落盘。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402

MODES = {"transit", "driving", "walking", "cycling"}
MODE_CN = {"transit": "地铁/公交", "driving": "驾车", "walking": "步行", "cycling": "骑行"}
STATUSES = {"ok", "no_route", "error"}


def load_jobs(run: Path):
    normalized = c.read_json(run / "normalized" / "jobs.json", None)
    if not normalized:
        c.die("缺少 normalized/jobs.json，先运行 normalize.py")
    return normalized.get("jobs") or []


def load_existing(run: Path, cfg: dict) -> dict:
    data = c.read_json(run / "commute.json", None) or {}
    commute_cfg = cfg.get("commute") or {}
    entries = {}
    for entry in data.get("entries") or []:
        job_id = str(entry.get("job_id") or "").strip()
        if job_id:
            entries[job_id] = entry
    return {
        "generated_at": data.get("generated_at") or c.now_iso(),
        "tool": data.get("tool") or commute_cfg.get("tool") or "",
        "approved": bool(data.get("approved", commute_cfg.get("enabled", False))),
        "home": data.get("home") or ({"address": commute_cfg.get("home_address", "")} if commute_cfg.get("home_address") else {}),
        "modes": data.get("modes") or commute_cfg.get("modes") or [],
        "max_minutes": data.get("max_minutes") if data.get("max_minutes") is not None else commute_cfg.get("max_minutes"),
        "entries": entries,
    }


def normalize_entry(raw: dict, valid_ids: set):
    job_id = str(raw.get("job_id") or "").strip()
    if job_id not in valid_ids:
        return None, f"job_id 不存在: {job_id or '(空)'}"
    mode = str(raw.get("mode") or "").strip()
    if mode not in MODES:
        return None, f"mode 无效: {mode or '(空)'}"
    try:
        minutes = round(float(raw.get("minutes")), 1)
    except (TypeError, ValueError):
        return None, f"minutes 无效: {raw.get('minutes')}"
    if minutes < 0 or minutes > 300:
        return None, f"minutes 超出 0–300: {minutes}"
    try:
        distance = round(float(raw.get("distance_km")), 2) if raw.get("distance_km") not in (None, "") else None
    except (TypeError, ValueError):
        distance = None
    status = str(raw.get("status") or "ok")
    if status not in STATUSES:
        status = "ok"
    return {
        "job_id": job_id,
        "mode": mode,
        "minutes": minutes,
        "distance_km": distance,
        "status": status,
        "note": str(raw.get("note") or ""),
        "source": str(raw.get("source") or "map"),
        "checked_at": str(raw.get("checked_at") or c.now_iso()),
    }, None


def main():
    ap = argparse.ArgumentParser(description="CareeSeek 通勤数据")
    ap.add_argument("--run", help="run 目录（缺省使用最新）")
    ap.add_argument("--list", action="store_true", help="列出待计算通勤的岗位与地址")
    ap.add_argument("--file", help="地图工具返回的 commute JSON（数组或 {entries:[]}）")
    ap.add_argument("--tool", help="实际使用的工具名，如 amap-mcp")
    ap.add_argument("--approved", choices=["true", "false"], help="用户是否已授权发送地址给地图工具")
    args = ap.parse_args()

    run = c.resolve_run(args.run)
    cfg = c.read_json(run / "config.json", {}) or {}
    jobs = load_jobs(run)
    valid_ids = {j.get("job_id") for j in jobs}
    existing = load_existing(run, cfg)

    if args.list:
        entries = existing["entries"]
        rows = []
        for job in jobs:
            extras = job.get("extras") or {}
            meta = job.get("company_meta") or {}
            address = extras.get("工作地址") or extras.get("公司地址") or ""
            if not address:
                address = " · ".join(x for x in [job.get("city", ""), job.get("district", "")] if x)
            rows.append({
                "job_id": job.get("job_id"),
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "city": job.get("city", ""),
                "district": job.get("district", ""),
                "work_address": address,
                "salary": (job.get("salary") or {}).get("text", ""),
                "has_commute": job.get("job_id") in entries,
            })
        c.emit({
            "run": str(run),
            "commute_enabled": bool((cfg.get("commute") or {}).get("enabled")),
            "max_minutes": (cfg.get("commute") or {}).get("max_minutes"),
            "modes": (cfg.get("commute") or {}).get("modes") or [],
            "tool": existing.get("tool") or "",
            "jobs": rows,
            "next": "用地图 MCP 逐条计算后写 commute.json，再运行 --file 合并",
        })
        return

    if not args.file:
        c.die("需要 --list 或 --file")

    payload = c.read_json(Path(args.file).resolve(), None)
    if payload is None:
        c.die(f"commute 文件无效: {args.file}")
    if isinstance(payload, dict):
        raw_entries = payload.get("entries") or []
        if payload.get("tool"):
            existing["tool"] = payload["tool"]
        if payload.get("approved") is not None:
            existing["approved"] = bool(payload["approved"])
        if payload.get("home"):
            existing["home"] = payload["home"]
        if payload.get("modes"):
            existing["modes"] = payload["modes"]
        if payload.get("max_minutes") is not None:
            existing["max_minutes"] = payload["max_minutes"]
    elif isinstance(payload, list):
        raw_entries = payload
    else:
        c.die("commute 文件必须是数组或带 entries 的对象")

    if args.tool:
        existing["tool"] = args.tool
    if args.approved is not None:
        existing["approved"] = args.approved == "true"

    added = updated = rejected = 0
    for raw in raw_entries:
        entry, err = normalize_entry(raw, valid_ids)
        if err:
            print(f"[commute] 跳过: {err}", file=sys.stderr)
            rejected += 1
            continue
        job_id = entry["job_id"]
        old = existing["entries"].get(job_id)
        if old is None:
            existing["entries"][job_id] = entry
            added += 1
        elif entry["minutes"] < float(old.get("minutes", 1e9)):
            existing["entries"][job_id] = entry
            updated += 1

    existing["generated_at"] = c.now_iso()
    c.write_json(run / "commute.json", {
        "generated_at": existing["generated_at"],
        "tool": existing.get("tool", ""),
        "approved": bool(existing.get("approved")),
        "home": existing.get("home", {}),
        "modes": existing.get("modes", []),
        "max_minutes": existing.get("max_minutes"),
        "entries": sorted(existing["entries"].values(), key=lambda x: x["job_id"]),
    })

    # 只要用户批准并算过通勤，就把配置标记为启用
    if existing["entries"] and existing.get("approved"):
        commute_cfg = cfg.get("commute") if isinstance(cfg.get("commute"), dict) else {}
        commute_cfg["enabled"] = True
        cfg["commute"] = commute_cfg
        c.write_json(run / "config.json", cfg)

    c.emit({
        "run": str(run),
        "added": added,
        "updated": updated,
        "rejected": rejected,
        "total_entries": len(existing["entries"]),
        "missing_jobs": len(valid_ids - set(existing["entries"])),
        "tool": existing.get("tool", ""),
        "approved": bool(existing.get("approved")),
        "output": str(run / "commute.json"),
    })


if __name__ == "__main__":
    main()
