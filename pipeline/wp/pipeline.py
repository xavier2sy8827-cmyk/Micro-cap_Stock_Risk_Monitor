# -*- coding: utf-8 -*-
"""切片运行：取数 -> 计算 -> 写 data 目录。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from wp import config as C
from wp.checks import write_csv
from wp.dataset import load_slice
from wp.metrics import compute_metrics, run_meta
from wp.ts_client import TsClient


def run_slice(
    start: str,
    end: str,
    fetch_start: str | None = None,
    data_dir: str | Path = C.DEFAULT_DATA_DIR,
    include_margin: bool = True,
) -> dict:
    t0 = time.time()
    client = TsClient(log=print)
    sl = load_slice(client, start=start, end=end, fetch_start=fetch_start, include_margin=include_margin)
    print(f"[slice] loaded {len(sl.days)} days, {len(sl.close.columns)} codes, {client.stats()['total']} calls")
    metrics, ind = compute_metrics(sl)
    target = Path(data_dir)
    target.mkdir(parents=True, exist_ok=True)
    write_csv(metrics, target / "metrics.csv")
    write_csv(ind, target / "industry_breadth.csv")
    through = str(metrics["date"].max())[:10] if len(metrics) else end
    meta = run_meta(start, end, len(metrics), through, sl.warnings)
    meta["pipeline_version"] = C.PIPELINE_VERSION
    meta["calls"] = client.stats()
    meta["duration_sec"] = round(time.time() - t0, 1)
    (target / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[slice] done rows={len(metrics)} through={through} "
        f"industry_rows={len(ind)} elapsed={time.time() - t0:.1f}s"
    )
    return meta
