"""Shared helpers for the evaluation scripts (run from the repository root)."""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("EMBEDDING_BACKEND", "fastembed")

RESULTS = ROOT / "eval" / "results"
DATA = ROOT / "data" / "demo"


def git_rev() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        return None


def write_result(name: str, payload: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "git_rev": git_rev(),
               "python": sys.version.split()[0], **payload}
    path = RESULTS / f"{name}_latest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def p50(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": None if p is None else round(p, 3),
            "recall": None if r is None else round(r, 3), "f1": None if f is None else round(f, 3)}
