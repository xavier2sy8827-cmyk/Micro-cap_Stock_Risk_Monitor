# -*- coding: utf-8 -*-
"""切片运行：取数 -> 计算 -> 写 data 目录。"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from wp import config as C
from wp.checks import write_csv
from wp.dataset import load_slice
from wp.factors import compute_factors, factor_ic_long, states_long
from wp.metrics import compute_metrics, run_meta
from wp.ts_client import TsClient


def _factor_ic_long(result) -> pd.DataFrame:
    return factor_ic_long(result)


def _trim(df: pd.DataFrame, col: str, start: str) -> pd.DataFrame:
    """输出起点裁掉 fetch_start 预热段（指标仍用预热数据计算）。"""
    if df.empty or col not in df.columns:
        return df
    keep = df[col].astype(str).str[:10] >= start
    return df[keep].reset_index(drop=True)


def run_slice(
    start: str,
    end: str,
    fetch_start: str | None = None,
    data_dir: str | Path = C.DEFAULT_DATA_DIR,
    include_margin: bool = True,
    include_moneyflow: bool = True,
) -> dict:
    t0 = time.time()
    client = TsClient(log=print)
    sl = load_slice(
        client,
        start=start,
        end=end,
        fetch_start=fetch_start,
        include_margin=include_margin,
        include_moneyflow=include_moneyflow,
    )
    print(f"[slice] loaded {len(sl.days)} days, {len(sl.close.columns)} codes, {client.stats()['total']} calls")
    metrics, ind = compute_metrics(sl)
    panel_idx = pd.to_datetime(metrics["date"])

    factor_meta = {}
    fic = fst = None
    fres = None
    if include_moneyflow and not sl.small_net.empty:
        fres = compute_factors(sl, panel_idx)
        if fres.panel_rows:
            fic = _trim(_factor_ic_long(fres), "date", start)
            fst = _trim(states_long(fres), "date", start)

    metrics = _trim(metrics, "date", start)
    ind = _trim(ind, "date", start)
    target = Path(data_dir)
    target.mkdir(parents=True, exist_ok=True)
    write_csv(metrics, target / "metrics.csv")
    write_csv(ind, target / "industry_breadth.csv")

    if fic is not None and fst is not None:
        events = _trim(fres.events, "event_date", start)
        write_csv(fic, target / "factor_ic.csv")
        write_csv(fst, target / "factor_states.csv")
        write_csv(events, target / "factor_events.csv")
        valid_ic = fic.dropna(subset=["rank_ic"])["date"]
        factor_meta = {
            "factor_ic_through": str(valid_ic.max()) if len(valid_ic) else None,
            "factor_panel_rows": fres.panel_rows,
        }
        print(f"[slice] factors panel={fres.panel_rows} ic_through={factor_meta['factor_ic_through']}")

    through = str(metrics["date"].max())[:10] if len(metrics) else end
    meta = run_meta(start, end, len(metrics), through, sl.warnings)
    meta.update(factor_meta)
    meta["pipeline_version"] = C.PIPELINE_VERSION
    meta["calls"] = client.stats()
    meta["duration_sec"] = round(time.time() - t0, 1)
    with open(target / "meta.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(
        f"[slice] done rows={len(metrics)} through={through} "
        f"industry_rows={len(ind)} elapsed={time.time() - t0:.1f}s"
    )
    return meta
