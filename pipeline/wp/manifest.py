# -*- coding: utf-8 -*-
"""INIT 可复现证明与验收检查。"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from wp import config as C
from wp.checks import read_csv, sha256_file
from wp.ts_client import TsClient, to_dash

FILES = [
    "metrics.csv",
    "industry_breadth.csv",
    "factor_ic.csv",
    "factor_states.csv",
    "factor_events.csv",
]


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=C.PROJECT_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:  # noqa: BLE001
        return None


def make_manifest(data_dir: str | Path, start: str, end: str) -> dict:
    src = Path(data_dir)
    outputs = []
    for name in FILES:
        p = src / name
        if not p.exists():
            continue
        try:
            rows = len(read_csv(p))
        except Exception:  # noqa: BLE001
            rows = 0
        outputs.append({"path": name, "rows": rows, "bytes": p.stat().st_size, "sha256": sha256_file(p)})
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8")) if (src / "meta.json").exists() else {}
    import numpy
    import pandas
    import tushare

    manifest = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "code_commit": _git_commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {
            "pandas": pandas.__version__,
            "numpy": numpy.__version__,
            "tushare": tushare.__version__,
        },
        "init_start": start,
        "init_end": end,
        "data_through": meta.get("data_through"),
        "pipeline_version": C.PIPELINE_VERSION,
        "outputs": outputs,
        "tushare_schema_snapshot": C.FIELDS,
        "calls": meta.get("calls"),
        "duration_sec": meta.get("duration_sec"),
        "warnings": meta.get("warnings", []),
        "degraded": meta.get("degraded", []),
        "factor_ic_through": meta.get("factor_ic_through"),
    }
    with open(src / "init_manifest.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def verify(data_dir: str | Path, start: str, end: str) -> dict:
    src = Path(data_dir)
    m = read_csv(src / "metrics.csv", dtype={"date": str})
    days = [to_dash(d) for d in TsClient().trade_days(to_dash(start), to_dash(end))]
    dset = set(m["date"].astype(str))
    missing = [d for d in days if d not in dset]
    dup = int(m["date"].duplicated().sum())
    issues: list[str] = []
    if missing:
        issues.append(f"缺交易日 {len(missing)} 个: {missing[:5]}")
    if dup:
        issues.append(f"重复日期 {dup}")

    def check_range(col: str, lo: float, hi: float) -> None:
        if col not in m:
            return
        s = m[col].dropna()
        bad = int(((s < lo) | (s > hi)).sum())
        if bad:
            issues.append(f"{col} 越界 {bad} 行")

    check_range("share_wp400", 0, 100)
    check_range("pb_spread", 0, 100)
    check_range("corr60_wp400", -1, 1)
    check_range("ls_vol_ratio", 0, 100)
    check_range("qs_share", 0, 100)
    check_range("s_width_pct", 0, 100)
    pool_bad = int((m["n_pool"] != C.POOL_TOTAL_N).sum()) if "n_pool" in m else -1
    if pool_bad > 0:
        issues.append(f"n_pool != 400 的天数 {pool_bad}")
    factor_ok = True
    fst_path = src / "factor_states.csv"
    if fst_path.exists():
        fst = read_csv(fst_path, dtype={"date": str})
        bad_state = int(((fst["state"] < 0) | (fst["state"] > 3)).sum())
        if bad_state:
            issues.append(f"factor state 越界 {bad_state}")
        factor_ok = bad_state == 0
    report = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "start": start,
        "end": end,
        "rows": int(len(m)),
        "date_min": str(m["date"].min()),
        "date_max": str(m["date"].max()),
        "missing_days": len(missing),
        "duplicates": dup,
        "pool_bad_days": pool_bad,
        "factor_ok": factor_ok,
        "issues": issues,
        "ok": not issues,
    }
    with open(src / "verify_report.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report
