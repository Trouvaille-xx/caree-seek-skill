"""环境自检：Python、标准库、目录可写、模板齐全，并输出浏览器能力探测清单。"""
from __future__ import annotations

import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caree_common as c  # noqa: E402

REQUIRED_STDLIB = ["json", "csv", "statistics", "zipfile", "hashlib", "argparse", "string"]
REQUIRED_FILES = [
    "templates/report.html",
    "templates/resume-match.html",
    "templates/defaults.intake.json",
    "references/selectors.json",
    "references/skill-dictionary.json",
    "references/company-tiers.json",
    "references/compliance.md",
    "references/commute-matching.md",
]

BROWSER_PROBE_ORDER = ["ego-browser", "claude-in-chrome", "playwright-mcp", "tabbit"]
BROWSER_OPS = [
    "navigate", "read_text", "read_dom", "click", "type",
    "screenshot", "scroll", "execute_js", "profile_reuse",
]
MAP_PROBE_ORDER = ["amap-mcp", "baidu-maps-mcp", "google-maps-mcp"]
MAP_OPS = ["geocode", "route_transit", "route_driving", "route_walking", "route_cycling"]


def main():
    checks = []

    ver = sys.version_info
    checks.append({
        "check": "python>=3.9",
        "ok": ver >= (3, 9),
        "detail": platform.python_version(),
    })

    for mod in REQUIRED_STDLIB:
        try:
            __import__(mod)
            checks.append({"check": f"stdlib:{mod}", "ok": True})
        except Exception as exc:  # pragma: no cover
            checks.append({"check": f"stdlib:{mod}", "ok": False, "detail": str(exc)})

    try:
        runs = c.ROOT / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        probe = runs / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append({"check": "runs/ 可写", "ok": True})
    except Exception as exc:
        checks.append({"check": "runs/ 可写", "ok": False, "detail": str(exc)})

    for rel in REQUIRED_FILES:
        exists = (c.ROOT / rel).exists()
        checks.append({"check": f"文件存在:{rel}", "ok": exists})

    ok = all(item["ok"] for item in checks)
    warnings = []
    if not (c.ROOT / "assets" / "echarts.min.js").exists():
        warnings.append("assets/echarts.min.js 缺失：报告图表会降级为提示；请重新下载 ECharts 5.x 或使用 CDN 版本")
    result = {
        "ok": ok,
        "warnings": warnings,
        "python": platform.python_version(),
        "root": str(c.ROOT),
        "checks": checks,
        "browser_probe_order": BROWSER_PROBE_ORDER,
        "browser_capability_contract": BROWSER_OPS,
        "map_probe_order": MAP_PROBE_ORDER,
        "map_capability_contract": MAP_OPS,
        "map_optional": True,
        "agent_next": [
            "1) 如果本机存在多种浏览器工具，按 browser_probe_order 实测（见 references/browser-contract.md）",
            "2) 把选中的工具写回状态：python scripts/ingest.py --run <run> --state-set active_adapter=\"ego-browser\"",
            "3) 未通过任何浏览器探测时停止自动采集，向用户给出 browser_install_hints；不要用 requests/curl 直接抓招聘网站",
            "4) 用户没有浏览器工具但有旧调研工作簿时，可用 no_browser_fallback 继续分析与报告",
            "5) 仅当用户提出通勤要求时探测地图工具：按 map_probe_order 实测地理编码与路线规划，先取得用户授权再发送地址",
            "6) 无地图工具时不要猜通勤时间，引导安装高德 MCP（见 references/commute-matching.md）",
        ],
        "browser_install_hints": {
            "ego-browser": "在宿主 agent 中安装 ego-browser / ego lite，并用你本机已登录 Boss直聘的浏览器完成一次登录",
            "claude-in-chrome": "安装 Claude in Chrome 扩展，登录扩展账号并授权控制当前 Chrome；天然复用登录态",
            "playwright-mcp": "配置 Playwright MCP（常见：npx @playwright/mcp@latest），优先有头模式；无持久化 profile 时每次可能要重新登录",
            "tabbit": "按 tabbit CLI 官方文档安装并完成登录，确认可复用登录态",
        },
        "no_browser_fallback": "没有浏览器工具时不要用 requests/curl 直接抓招聘网站。可以让用户提供已有调研工作簿，运行 python scripts/import_xlsx.py --run <run> --xlsx <path> 继续做分析与报告；或安装上面的任一浏览器工具后重跑。",
        "hint_python": "未安装 Python 时可执行: winget install Python.Python.3.12",
        "hint_amap": "高德 MCP：https://lbs.amap.com 创建 Web 服务 Key，npx -y @amap/amap-maps-mcp-server",
        "hint_encoding": "Windows 控制台出现乱码时设置环境变量 PYTHONUTF8=1",
    }
    c.emit(result)
    raise SystemExit(0 if ok else 2)


if __name__ == "__main__":
    main()
