# -*- coding: utf-8 -*-
"""只重算 pb_spread 历史（用于修复早期全量 INIT 的样本口径）。

全量 INIT 时 total_mv 会对停牌/退市股 ffill，若 pb_spread 的分组样本按 mv 计数，
退市股会稀释两端分组。本脚本按“pb 与 total_mv 同时有效”的股票重算，并重算分位。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from wp import config as C
from wp import series as S
from wp.checks import read_csv, write_csv
from wp.ts_client import TsClient


def _one(df: pd.DataFrame) -> tuple[float, float, float]:
    d = df[["pb", "total_mv"]].dropna()
    d = d[d["total_mv"] > 0]
    n = len(d)
    if n == 0:
        return (np.nan, np.nan, np.nan)
    k = max(1, round(n * 0.2))
    s = d.sort_values("total_mv", kind="stable")
    ps = s.head(k)
    pl = s.tail(k)
    ps = ps.loc[ps["pb"] > 0, "pb"]
    pl = pl.loc[pl["pb"] > 0, "pb"]
    if len(ps) < 20 or len(pl) < 20:
        return (np.nan, np.nan, np.nan)
    a, b = float(ps.median()), float(pl.median())
    if b <= 0:
        return (np.nan, np.nan, np.nan)
    return (a, b, a / b)


def rebuild(data_dir: str | Path) -> dict:
    t0 = time.time()
    target = Path(data_dir)
    m = read_csv(target / "metrics.csv", dtype={"date": str}).sort_values("date").reset_index(drop=True)
    client = TsClient(log=print)
    vals = []
    for i, day in enumerate(m["date"].astype(str)):
        df = client.daily_basic(day.replace("-", ""))
        if df is None or df.empty:
            vals.append((np.nan, np.nan, np.nan))
            continue
        df = df[~df["ts_code"].astype(str).str.endswith(C.EXCLUDE_SUFFIXES)]
        vals.append(_one(df))
        if (i + 1) % 250 == 0:
            print(f"[pb] {i + 1}/{len(m)} calls={client.stats()['total']}", flush=True)

    m["pb_small_med"] = [v[0] for v in vals]
    m["pb_large_med"] = [v[1] for v in vals]
    m["pb_spread"] = [v[2] for v in vals]
    m["pb_spread_pct"] = S.rolling_pct_last(m["pb_spread"], 250, 120)
    m["pb_spread_pct_exp"] = S.expanding_pct_last(m["pb_spread"], 250)
    write_csv(m, target / "metrics.csv")

    meta_path = target / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["pb_rebuilt_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    meta["pb_rebuild_calls"] = client.stats()["total"]
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    last = m.dropna(subset=["pb_spread"]).iloc[-1]
    print(
        f"[pb] done rows={len(m)} last={last['date']} spread={last['pb_spread']:.6f} "
        f"elapsed={time.time() - t0:.1f}s calls={client.stats()['total']}"
    )
    return {"rows": len(m), "last": str(last["date"]), "spread": float(last["pb_spread"])}
