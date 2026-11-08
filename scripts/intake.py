"""意向配置：把访谈答案与默认值深合并，创建 run 目录、config.json 与 state.json。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402

LADDER_MODES = {"same_company", "cross_company", "capability_map", "salary_curve"}
BG_SCOPES = {"top_n", "shallow_all", "manual"}
EXPORTS = {"csv", "xlsx", "md", "feishu"}


def deep_merge(base, override):
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for key, val in override.items():
            out[key] = deep_merge(base[key], val) if key in base else val
        return out
    return override if override is not None else base


def validate(cfg: dict):
    warnings = []

    try:
        target = int(cfg.get("target_count", 60))
    except (TypeError, ValueError):
        target = 60
    if target < 1:
        target = 1
    if target > 100:
        warnings.append(f"target_count={target} 超过单次硬上限，已收敛为 100")
        target = 100
    cfg["target_count"] = target

    modes = [m for m in cfg.get("ladder_modes", []) if m in LADDER_MODES]
    if not modes:
        modes = ["same_company", "salary_curve"]
        warnings.append("ladder_modes 无效或为空，使用默认 [same_company, salary_curve]")
    cfg["ladder_modes"] = modes

    if cfg.get("bg_scope") not in BG_SCOPES:
        cfg["bg_scope"] = "top_n"
        warnings.append("bg_scope 无效，使用 top_n")
    try:
        cfg["top_n"] = max(1, min(20, int(cfg.get("top_n", 5))))
    except (TypeError, ValueError):
        cfg["top_n"] = 5

    cfg["export_targets"] = [e for e in cfg.get("export_targets", []) if e in EXPORTS]
    if cfg.get("output_format") != "html":
        cfg["output_format"] = "html"

    cfg.setdefault("city", [])
    cfg.setdefault("role_keywords", [])
    cfg.setdefault("industry", "")
    cfg.setdefault("company_size_pref", [])
    cfg.setdefault("questionnaire_answered", [])
    cfg.setdefault("pacing_profile", "standard")

    se = cfg.get("salary_expect") or {}
    for key in ("min_k", "max_k"):
        val = se.get(key)
        if val is not None:
            try:
                se[key] = float(val)
            except (TypeError, ValueError):
                se[key] = None
    try:
        se["months"] = int(se.get("months") or 12)
    except (TypeError, ValueError):
        se["months"] = 12
    cfg["salary_expect"] = se
    return warnings


def load_answers(args):
    answers = {}
    if args.answers:
        answers = c.read_json(Path(args.answers).resolve(), None)
        if answers is None:
            c.die(f"答案文件不存在或不是有效 JSON: {args.answers}")
    for item in args.set:
        if "=" not in item:
            c.die(f"--set 格式应为 key=jsonvalue，收到: {item}")
        key, raw = item.split("=", 1)
        try:
            answers[key] = json.loads(raw)
        except json.JSONDecodeError:
            answers[key] = raw
    return answers


def main():
    ap = argparse.ArgumentParser(description="CareeSeek 意向配置")
    ap.add_argument("--run", help="run 目录（缺省自动创建 runs/<时间戳>）")
    ap.add_argument("--answers", help="答案 JSON 文件路径")
    ap.add_argument("--set", action="append", default=[], help="覆盖字段，形如 --set target_count=80")
    args = ap.parse_args()

    defaults = c.read_json(c.ROOT / "templates" / "defaults.intake.json", {})
    cfg = deep_merge(defaults, load_answers(args))
    warnings = validate(cfg)

    run = Path(args.run).resolve() if args.run else (c.ROOT / "runs" / c.new_run_id())
    c.ensure_run_layout(run)
    cfg["run_id"] = run.name
    cfg["created_at"] = c.now_iso()
    c.write_json(run / "config.json", cfg)

    state = c.load_state(run)
    state["run_id"] = run.name
    state["target_count"] = cfg["target_count"]
    if state["stage"] == "created":
        state["stage"] = "intake_done"
    c.save_state(run, state)

    c.emit({
        "run": str(run),
        "target_count": cfg["target_count"],
        "city": cfg["city"],
        "role_keywords": cfg["role_keywords"],
        "ladder_modes": cfg["ladder_modes"],
        "bg_scope": cfg["bg_scope"],
        "export_targets": cfg["export_targets"],
        "warnings": warnings,
        "next": "运行 preflight.py 并探测浏览器，然后按 references/playbook-boss.md 开始检索",
    })


if __name__ == "__main__":
    main()
