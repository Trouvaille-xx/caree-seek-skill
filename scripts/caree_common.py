"""CareeSeek 共享工具：路径、状态、JSON I/O（仅标准库）。"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent

DEFAULT_STATE = {
    "run_id": "",
    "stage": "created",
    "active_adapter": None,
    "logged_in": False,
    "jobs_collected": 0,
    "detail_done": 0,
    "pages_done": 0,
    "profiles_done": [],
    "pending_queue": [],
    "captcha_events": 0,
    "aborted": False,
    "last_update": "",
}


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def new_run_id() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def die(msg: str, code: int = 1):
    print(f"[caree-seek] 错误: {msg}", file=sys.stderr)
    raise SystemExit(code)


def emit(obj):
    """向 stdout 输出 JSON（供 agent 读取）。"""
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def sha1(text: str, size: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:size]


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_jsonl(path):
    path = Path(path)
    records = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def append_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def ensure_run_layout(run):
    run = Path(run)
    for sub in ("raw", "normalized", "profiles", "exports"):
        (run / sub).mkdir(parents=True, exist_ok=True)
    return run


def load_state(run) -> dict:
    state = dict(DEFAULT_STATE)
    state.update(read_json(Path(run) / "state.json", {}) or {})
    return state


def save_state(run, state: dict):
    state["last_update"] = now_iso()
    write_json(Path(run) / "state.json", state)


def resolve_run(arg):
    """解析 --run 参数；缺省时使用 runs/ 下最新的 run。"""
    if arg:
        p = Path(arg)
        if not p.is_absolute():
            p = Path.cwd() / p
        p = p.resolve()
        if not p.exists():
            die(f"run 目录不存在: {p}")
        return p
    runs_dir = ROOT / "runs"
    if not runs_dir.exists():
        die("还没有任何 run。先运行 intake.py 创建：python scripts/intake.py --answers answers.json")
    candidates = sorted([d for d in runs_dir.iterdir() if d.is_dir() and not d.name.startswith(".")])
    if not candidates:
        die("runs/ 为空。先运行 intake.py。")
    return candidates[-1]


def slug_key(name: str) -> str:
    """把公司名转成稳定的 company_key（保留中英文数字 + 短哈希）。"""
    cleaned = "".join(ch for ch in (name or "").strip().lower() if ch.isalnum() or "一" <= ch <= "鿿")
    cleaned = cleaned[:40] or "company"
    return f"{cleaned}-{sha1(name or 'company', 6)}"
