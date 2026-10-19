# -*- coding: utf-8 -*-
"""每日增量：只重算最近窗口，合并历史后重算分位/因子状态。"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from wp import config as C
from wp import series as S
from wp.checks import read_csv, write_csv
from wp.dataset import load_slice
from wp.factors import FACTORS, compute_factors, compute_states, factor_ic_long
from wp.metrics import compute_metrics
from wp.ts_client import TsClient, to_dash


def _pct_spec(col: str) -> tuple[str, int, int] | None:
    if col.endswith("_pct_exp"):
        return ("exp", 250, 250)
    if not col.endswith("_pct"):
        return None
    base = col[:-4]
    if base in ("breadth10", "pb_spread", "corr60_wp400", "ls_vol_ratio", "qs_share") or re.match(
        r"breadth_L\d+$", base
    ):
        return ("roll", 250, 120)
    return ("roll", 750, 250)


def _recompute_pct(df: pd.DataFrame) -> pd.DataFrame:
    for col in [c for c in df.columns if c.endswith("_pct") or c.endswith("_pct_exp")]:
        spec = _pct_spec(col)
        if spec is None:
            continue
        base = col[: -8] if col.endswith("_pct_exp") else col[:-4]
        if base not in df.columns:
            continue
        kind, win, minp = spec
        if kind == "exp":
            df[col] = S.expanding_pct_last(df[base], minp)
        else:
            df[col] = S.rolling_pct_last(df[base], win, minp)
    if "margin_pool_ratio" in df.columns:
        df["margin_pool_ratio_z"] = S.zscore_rolling(df["margin_pool_ratio"], 90, 30)
    return df


def _merge_metrics(hist: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    both = pd.concat([hist, new], ignore_index=True).drop_duplicates(subset=["date"], keep="last")
    both = both.sort_values("date").reset_index(drop=True)
    return _recompute_pct(both)


def _merge_industry(hist: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if hist.empty:
        return new
    both = pd.concat([hist, new], ignore_index=True)
    return both.drop_duplicates(subset=["date", "industry"], keep="last").sort_values(["date", "industry"])


def _merge_factors(data_dir: Path, new_ic: pd.DataFrame, new_events: pd.DataFrame) -> dict:
    old_path = data_dir / "factor_ic.csv"
    old = read_csv(old_path) if old_path.exists() else pd.DataFrame()
    if not old.empty:
        merged = pd.concat(
            [old[~old["date"].isin(set(new_ic["date"]))], new_ic], ignore_index=True
        )
    else:
        merged = new_ic
    merged = merged.drop_duplicates(subset=["date", "factor"], keep="last").sort_values(["date", "factor"])

    ic = merged.pivot(index="date", columns="factor", values="rank_ic")
    ls = merged.pivot(index="date", columns="factor", values="ls_ret")
    st_frames = []
    ev_rows = []
    for f in FACTORS:
        if f not in ic.columns:
            continue
        st, ev = compute_states(ic[f].astype(float), ls[f].astype(float))
        d = st.copy()
        d["factor"] = f
        d["date"] = d.index
        st_frames.append(d.reset_index(drop=True))
        for e in ev:
            ev_rows.append({"factor": f, **e})
    st_all = pd.concat(st_frames, ignore_index=True) if st_frames else pd.DataFrame()
    if not st_all.empty:
        drop_cols = [
            "L", "D", "R", "F", "state", "R_raw", "ic_pct", "ic_mean_252", "ic_mean_756",
            "icir_252", "ls_nav", "depth", "hist_worst_dd", "sigma_ls_252", "judge_nan",
        ]
        merged = merged.drop(columns=[c for c in drop_cols if c in merged.columns], errors="ignore")
        merged = merged.merge(
            st_all[["date", "factor"] + [c for c in drop_cols if c in st_all.columns]],
            on=["date", "factor"],
            how="left",
        )
    write_csv(merged, data_dir / "factor_ic.csv")
    if not st_all.empty:
        write_csv(st_all, data_dir / "factor_states.csv")
    if ev_rows:
        write_csv(pd.DataFrame(ev_rows), data_dir / "factor_events.csv")
    valid = merged.dropna(subset=["rank_ic"])["date"]
    return {
        "factor_ic_through": str(valid.max()) if len(valid) else None,
        "factor_events": len(ev_rows),
    }


def run_daily(
    data_dir: str | Path,
    day: str | None = None,
    window: int = 100,
) -> dict:
    t0 = time.time()
    target = Path(data_dir)
    target.mkdir(parents=True, exist_ok=True)
    client = TsClient(log=print)

    today = date.today().strftime("%Y%m%d")
    if day is None:
        days = client.trade_days(f"{today[:4]}0101", today)
        if not days:
            raise SystemExit("无法获取交易日历")
        day = days[-1]
    day = to_dash(day)

    hist = read_csv(target / "metrics.csv", dtype={"date": str}) if (target / "metrics.csv").exists() else pd.DataFrame()
    if not hist.empty and str(hist["date"].max()) >= day:
        print(f"[daily] {day} 已存在，跳过")
        return {"status": "noop", "data_through": day}

    all_days = client.trade_days(
        (pd.Timestamp(day) - pd.Timedelta(days=400)).strftime("%Y%m%d"), day.replace("-", "")
    )
    if len(all_days) < 80:
        raise SystemExit(f"交易日不足: {len(all_days)}")

    # 收盘后 Tushare 的当日 daily 可能尚未落库；回退到最近有数据的一天，避免写入空行。
    avail = None
    for d in reversed(all_days):
        got = client.daily(d)
        if got is not None and not got.empty and got["close"].notna().any():
            avail = d
            break
    if avail is None:
        raise SystemExit("[daily] 窗口内没有任何可用日线")
    if avail != day.replace("-", ""):
        print(f"[daily] {day} 日线未落库，回退到 {to_dash(avail)}")
        day = to_dash(avail)
        all_days = [x for x in all_days if x <= avail]

    fetch_start = all_days[-window]
    print(f"[daily] {day} window {fetch_start} ~ {day.replace('-', '')}")

    sl = load_slice(client, start=fetch_start, end=day, fetch_start=fetch_start)
    metrics_new, ind_new = compute_metrics(sl)
    new_dates = set(metrics_new["date"].astype(str)) - set(hist["date"].astype(str)) if not hist.empty else set(
        metrics_new["date"].astype(str)
    )
    if not new_dates:
        print("[daily] 无新日期")
        return {"status": "noop", "data_through": day}
    metrics = _merge_metrics(hist, metrics_new) if not hist.empty else _recompute_pct(metrics_new)
    ind_hist = read_csv(target / "industry_breadth.csv", dtype={"date": str}) if (target / "industry_breadth.csv").exists() else pd.DataFrame()
    ind = _merge_industry(ind_hist, ind_new[ind_new["date"].astype(str).isin(new_dates)])
    write_csv(metrics, target / "metrics.csv")
    write_csv(ind, target / "industry_breadth.csv")

    factor_meta = {}
    if not sl.small_net.empty:
        fres = compute_factors(sl, pd.to_datetime(metrics_new["date"]))
        if fres.panel_rows:
            new_ic = factor_ic_long(fres)
            new_ic = new_ic[new_ic["date"].isin(new_dates)]
            if not new_ic.empty:
                factor_meta = _merge_factors(target, new_ic, fres.events)
                print(f"[daily] factors updated {len(new_ic)} rows; ic_through={factor_meta.get('factor_ic_through')}")

    meta_path = target / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta.update(
        {
            "schema_version": 1,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_through": str(metrics["date"].max()),
            "margin_through": str(metrics.loc[metrics["margin_pool_ratio"].notna(), "date"].max())
            if "margin_pool_ratio" in metrics
            else None,
            "factor_ic_through": factor_meta.get("factor_ic_through", meta.get("factor_ic_through")),
            "days": int(len(metrics)),
            "source": "tushare",
            "pipeline_version": C.PIPELINE_VERSION,
            "calls": client.stats(),
            "duration_sec": round(time.time() - t0, 1),
        }
    )
    with open(meta_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(f"[daily] done {day} rows={len(metrics)} elapsed={time.time() - t0:.1f}s")
    return {"status": "ok", "data_through": day, **factor_meta}
