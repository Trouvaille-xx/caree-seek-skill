"""报告渲染：岗位 seek 报告 + 可选简历匹配报告（ECharts 离线内嵌）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402


def inline_echarts(template: str) -> str:
    path = c.ROOT / "assets" / "echarts.min.js"
    if path.exists():
        js = path.read_text(encoding="utf-8").replace("</script", "<\\/script")
    else:
        js = "/* assets/echarts.min.js 缺失：图表将降级为提示 */"
    return template.replace("/*__ECHARTS__*/", js)


def render(template_path: Path, payload: dict, out: Path):
    template = template_path.read_text(encoding="utf-8")
    if "__PAYLOAD__" not in template:
        c.die(f"模板缺少 __PAYLOAD__ 占位符: {template_path}")
    template = inline_echarts(template)
    data_js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(template.replace("__PAYLOAD__", data_js), encoding="utf-8")
    return round(out.stat().st_size / 1024, 1)


def main():
    ap = argparse.ArgumentParser(description="CareeSeek HTML 报告")
    ap.add_argument("--run", help="run 目录（缺省使用最新）")
    ap.add_argument("--out", help="岗位报告输出路径（缺省 <run>/report.html）")
    args = ap.parse_args()

    run = c.resolve_run(args.run)
    cfg = c.read_json(run / "config.json", {}) or {}
    normalized = c.read_json(run / "normalized" / "jobs.json", None)
    analysis = c.read_json(run / "analysis.json", None)
    if not normalized:
        c.die("缺少 normalized/jobs.json，先运行 normalize.py")
    if not analysis:
        c.die("缺少 analysis.json，先运行 analyze.py")

    profiles = []
    for path in sorted((run / "profiles").glob("*.json")):
        data = c.read_json(path, None)
        if data:
            profiles.append(data)

    compliance = ""
    compliance_path = c.ROOT / "references" / "compliance.md"
    if compliance_path.exists():
        compliance = compliance_path.read_text(encoding="utf-8")

    state = c.load_state(run)
    meta = {
        "run_id": run.name,
        "generated_at": c.now_iso(),
        "stage": state.get("stage"),
        "active_adapter": state.get("active_adapter"),
    }

    payload = {
        "meta": meta,
        "config": cfg,
        "analysis": analysis,
        "jobs": normalized.get("jobs") or [],
        "profiles": profiles,
        "compliance": compliance,
    }
    out = Path(args.out).resolve() if args.out else (run / "report.html")
    size_kb = render(c.ROOT / "templates" / "report.html", payload, out)

    resume_out = None
    match = c.read_json(run / "match.json", None)
    if match:
        resume_out = run / "resume-match.html"
        render(c.ROOT / "templates" / "resume-match.html",
               {"meta": meta, "config": cfg, "match": match, "compliance": compliance},
               resume_out)

    state["stage"] = "reported"
    c.save_state(run, state)

    c.emit({
        "run": str(run),
        "report": str(out),
        "size_kb": size_kb,
        "jobs": len(payload["jobs"]),
        "profiles": len(profiles),
        "resume_report": str(resume_out) if resume_out else None,
        "next": "用浏览器打开报告；如需导出运行 export.py",
    })


if __name__ == "__main__":
    main()
