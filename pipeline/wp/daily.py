# -*- coding: utf-8 -*-
"""每日增量：只重算最近窗口，合并历史后重算分位/因子状态。"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
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
    if base == "pb_spread":
        return ("roll", 750, 250)
    if base.startswith("share_") and base[6:] in ("300", "500", "1000", "2000", "wp400"):
        return ("roll", 250, 250)
    if base in ("breadth10", "corr60_wp400", "ls_vol_ratio", "qs_share") or re.match(
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


def _norm_dates(df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
    """date 统一成 YYYY-MM-DD 字符串，避免 Timestamp/str 混排。"""
    if df.empty or col not in df.columns:
        return df
    out = df.copy()
    out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d")
    return out


def _merge_metrics(hist: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """历史行保持 INIT 原值，只追加新日期；窗口内只回填两融列（T-1 次日才发布）。"""
    hist = _norm_dates(hist)
    new = _norm_dates(new)
    old_dates = set(hist["date"].astype(str))
    append = new[~new["date"].isin(old_dates)]
    both = pd.concat([hist, append], ignore_index=True)

    margin_cols = [c for c in new.columns if c.startswith("margin_") and c in both.columns and c != "margin_pool_ratio_z"]
    changed = False
    if margin_cols:
        m = new.set_index("date")
        mask = both["date"].isin(set(m.index))
        for col in margin_cols:
            nv = both.loc[mask, "date"].map(m[col])
            if not np.allclose(both.loc[mask, col].astype(float), nv.astype(float), equal_nan=True):
                changed = True
            both.loc[mask, col] = nv

    both = both.sort_values("date").reset_index(drop=True)
    newmask = ~both["date"].isin(old_dates)
    if newmask.any():
        calc = _recompute_pct(both.copy())
        for col in [c for c in both.columns if c.endswith(("_pct", "_pct_exp"))] + ["margin_pool_ratio_z"]:
            if col in calc.columns:
                both.loc[newmask, col] = calc.loc[newmask, col]
        both.loc[newmask, "s_width_pct"] = both.loc[newmask, "s_width"] / both.loc[newmask, "n_industries"]
        idx = both["wp400_index"].copy()
        for i in both.index[newmask]:
            if i == 0 or pd.isna(idx.iloc[i - 1]):
                idx.iloc[i] = np.nan
            else:
                ret = both.loc[i, "wp400_ret"]
                idx.iloc[i] = idx.iloc[i - 1] * (1.0 + (0.0 if pd.isna(ret) else ret))
        both["wp400_index"] = idx
    if changed and margin_cols and len(m):
        start = both.index[both["date"] == m.index.min()]
        if len(start):
            calc = _recompute_pct(both.copy())
            both.loc[start[0]:, "margin_pool_ratio_z"] = calc.loc[start[0]:, "margin_pool_ratio_z"]
    return both


def _merge_industry(hist: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if hist.empty:
        return _norm_dates(new)
    both = pd.concat([_norm_dates(hist), _norm_dates(new)], ignore_index=True)
    return both.drop_duplicates(subset=["date", "industry"], keep="last").sort_values(["date", "industry"])


def _merge_factors(data_dir: Path, new_ic: pd.DataFrame, new_events: pd.DataFrame) -> dict:
    old_path = data_dir / "factor_ic.csv"
    old = read_csv(old_path) if old_path.exists() else pd.DataFrame()
    old = _norm_dates(old)
    new_ic = _norm_dates(new_ic)
    if not old.empty:
        merged = pd.concat(
            [old[~old["date"].isin(set(new_ic["date"]))], new_ic], ignore_index=True
        )
    else:
        merged = new_ic
    merged = merged.drop_duplicates(subset=["date", "factor"], keep="last").sort_values(["date", "factor"])

    ic = merged.assign(date=pd.to_datetime(merged["date"])).pivot(index="date", columns="factor", values="rank_ic")
    ls = merged.assign(date=pd.to_datetime(merged["date"])).pivot(index="date", columns="factor", values="ls_ret")
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
    st_all = _norm_dates(st_all)
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
    hist = _norm_dates(hist)
    if not hist.empty and str(hist["date"].max()) >= day:
        print(f"[daily] {day} 已存在，仅刷新因子窗口")

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

    warmup = 80  # 覆盖 MA20/corr60 等窗口，避免重写窗口时把有效值算成 NaN
    fetch_start = all_days[-(window + warmup)] if len(all_days) >= window + warmup else all_days[0]
    merge_start = to_dash(all_days[-window])
    print(f"[daily] {day} window {merge_start} ~ {day.replace('-', '')} (fetch {fetch_start})")

    sl = load_slice(client, start=fetch_start, end=day, fetch_start=fetch_start)
    metrics_new, ind_new = compute_metrics(sl)
    metrics_new = _norm_dates(metrics_new)
    ind_new = _norm_dates(ind_new)
    new_dates = set(metrics_new["date"].astype(str)) - set(hist["date"].astype(str)) if not hist.empty else set(
        metrics_new["date"].astype(str)
    )
    win_mask = metrics_new["date"].astype(str) >= merge_start
    if not hist.empty:
        # 只重写最近 window 个交易日，且带 80 日预热；历史行保持全量 INIT 的结果。
        metrics = _merge_metrics(hist, metrics_new[win_mask])
        ind_hist = read_csv(target / "industry_breadth.csv", dtype={"date": str}) if (target / "industry_breadth.csv").exists() else pd.DataFrame()
        ind_hist = _norm_dates(ind_hist)
        ind = _merge_industry(ind_hist, ind_new[ind_new["date"].astype(str) >= merge_start])
        write_csv(metrics, target / "metrics.csv")
        write_csv(ind, target / "industry_breadth.csv")
    else:
        metrics = _recompute_pct(metrics_new)
        ind = ind_new
        write_csv(metrics, target / "metrics.csv")
        write_csv(ind, target / "industry_breadth.csv")
    if not new_dates:
        print("[daily] 无新日期，仅刷新窗口/因子")

    factor_meta = {}
    if not sl.small_net.empty:
        fres = compute_factors(sl, pd.to_datetime(metrics_new["date"]))
        if fres.panel_rows:
            # 窗口内能算出 fwd20 的日期都回填，IC 才会随每日运行向前推进。
            new_ic = factor_ic_long(fres)
            if not new_ic.empty:
                factor_meta = _merge_factors(target, new_ic, fres.events)
                print(f"[daily] factors refreshed {len(new_ic)} rows; ic_through={factor_meta.get('factor_ic_through')}")

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
