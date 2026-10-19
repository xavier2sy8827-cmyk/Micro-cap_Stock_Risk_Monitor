# -*- coding: utf-8 -*-
"""5 因子面板、Rank IC、五分位多空、四态与事件。"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from wp import series as S
from wp.dataset import Slice

FACTORS = ["F1_SIZE", "F2_DIV", "F3_AMPL", "F4_INTRA_REV", "F5_RESID_REV"]
FACTOR_NAMES = {
    "F1_SIZE": "小市值",
    "F2_DIV": "股息率",
    "F3_AMPL": "振幅",
    "F4_INTRA_REV": "日内反转",
    "F5_RESID_REV": "残差反转",
}
FWD_MAIN = 20
FWD_COLS = (1, 5, 20)
MIN_IC_N = 30
MIN_LS_GROUP = 5


def f5_series(close_qfq: pd.Series, net: pd.Series) -> pd.Series:
    """单股残差反转因子：-ε_T，拟合窗 [T-20,T-1]，S/ret 含 T。"""
    df = pd.DataFrame({"c": close_qfq, "n": net}).dropna()
    if len(df) < 41:
        return pd.Series(dtype=float)
    c = df["c"].to_numpy(float)
    n = df["n"].to_numpy(float)
    L = len(c)
    cs = np.concatenate([[0.0], np.cumsum(n)])
    ca = np.concatenate([[0.0], np.cumsum(np.abs(n))])
    j = np.arange(L)
    lo = np.clip(j - 19, 0, None)
    hi = j + 1
    num = cs[hi] - cs[lo]
    den = ca[hi] - ca[lo]
    fs = np.full(L, np.nan)
    ok = j >= 19
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(den[ok] != 0.0, num[ok] / den[ok], np.nan)
    fs[ok] = np.where(np.isfinite(ratio), ratio, np.nan)
    ret = np.full(L, np.nan)
    ret[20:] = c[20:] / c[:-20] - 1.0

    xs = np.lib.stride_tricks.sliding_window_view(fs, 20)[20 : L - 20]
    ys = np.lib.stride_tricks.sliding_window_view(ret, 20)[20 : L - 20]
    xm = xs.mean(axis=1)
    ym = ys.mean(axis=1)
    cov = ((xs - xm[:, None]) * (ys - ym[:, None])).mean(axis=1)
    var = ((xs - xm[:, None]) ** 2).mean(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        b = cov / var
    a = ym - b * xm
    eps = ret[40:] - (a + b * fs[40:])
    eps = np.where(var < 1e-10, np.nan, eps)
    out = np.full(L, np.nan)
    out[40:] = -eps
    return pd.Series(out, index=df.index)


def _fwd_returns(qfq: pd.DataFrame) -> dict[int, pd.Series]:
    out = {}
    for k in FWD_COLS:
        wide = qfq.shift(-k) / qfq - 1.0
        s = wide.stack().rename(f"fwd{k}")
        s.index.names = ["date", "ts_code"]
        out[k] = s
    return out


def build_factor_panel(sl: Slice, idx: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    frames = [sl.close, sl.pre_close, sl.open, sl.high, sl.low, sl.circ_mv, sl.dv_ttm]
    common = set.intersection(*(set(df.columns) for df in frames if not df.empty))
    for d in idx:
        day = d.strftime("%Y%m%d")
        pool = [c for c in sl.pools_total.get(day, []) if c in common]
        if not pool:
            continue
        close = sl.close.loc[d, pool]
        pre = sl.pre_close.loc[d, pool]
        f1 = -np.log(sl.circ_mv.loc[d, pool].where(sl.circ_mv.loc[d, pool] > 0))
        f2 = sl.dv_ttm.loc[d, pool].fillna(0.0) if d in sl.dv_ttm.index else pd.Series(0.0, index=pool)
        f3 = -(sl.high.loc[d, pool] - sl.low.loc[d, pool]) / pre
        f4 = -(close / sl.open.loc[d, pool] - 1.0)
        rows.append(
            pd.DataFrame(
                {
                    "date": d,
                    "ts_code": pool,
                    "F1_SIZE": f1.to_numpy(),
                    "F2_DIV": f2.to_numpy(),
                    "F3_AMPL": f3.to_numpy(),
                    "F4_INTRA_REV": f4.to_numpy(),
                }
            )
        )
    panel = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if panel.empty:
        return panel

    # F5：只算池成员并集
    codes = sorted(set(panel["ts_code"]))
    f5_map: dict[str, pd.Series] = {}
    for code in codes:
        if code in sl.qfq.columns and code in sl.small_net.columns:
            f5_map[code] = f5_series(sl.qfq[code], sl.small_net[code])
    panel["F5_RESID_REV"] = [
        f5_map.get(code, pd.Series(dtype=float)).get(d, np.nan) for code, d in zip(panel["ts_code"], panel["date"])
    ]

    fwd = _fwd_returns(sl.qfq)
    panel = panel.set_index(["date", "ts_code"])
    for k in FWD_COLS:
        panel[f"fwd{k}"] = fwd[k].reindex(panel.index)
    return panel.reset_index()


def _spearman(x: pd.Series, y: pd.Series) -> float:
    """秩相关 = 秩的 Pearson 相关（避免 scipy 依赖）。"""
    return float(x.rank().corr(y.rank()))


def compute_ic_ls(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.Index(sorted(panel["date"].unique()), name="date")
    ic = pd.DataFrame(index=dates, columns=FACTORS, dtype=float)
    ls = pd.DataFrame(index=dates, columns=FACTORS, dtype=float)
    nav = pd.DataFrame(index=dates, columns=FACTORS, dtype=float)
    for f in FACTORS:
        for d, g in panel.groupby("date", sort=True):
            sub = g[[f, "fwd20"]].dropna()
            if len(sub) >= MIN_IC_N and sub[f].nunique() > 1:
                ic.loc[d, f] = _spearman(sub[f], sub["fwd20"])
            sub1 = g[[f, "fwd1"]].dropna()
            if len(sub1) >= MIN_LS_GROUP * 5 and sub1[f].nunique() >= 5:
                q = pd.qcut(sub1[f].rank(method="first"), 5, labels=False)
                means = sub1.groupby(q)["fwd1"].mean()
                if means.notna().all() and len(means) == 5:
                    ls.loc[d, f] = float(means.loc[4] - means.loc[0])
        nav[f] = ls[f].cumsum()
    return ic, ls, nav


def _confirm_r(raw: pd.Series, nav: pd.Series, dd: pd.Series, sigma: pd.Series) -> tuple[pd.Series, list[dict]]:
    """R 二次确认：首次触发后 10 个交易日内再触发 → 确认，直到 NAV 回到事件前高点。"""
    r = pd.Series(0.0, index=raw.index)
    events: list[dict] = []
    idx = list(raw.index)
    n = len(idx)
    i = 0
    while i < n:
        if not bool(raw.iloc[i]):
            i += 1
            continue
        event_date = idx[i]
        pre_high = float(nav.iloc[: i + 1].max()) if i >= 0 else np.nan
        confirm_i = None
        for j in range(i + 1, min(i + 11, n)):
            if bool(raw.iloc[j]):
                confirm_i = j
                break
        if confirm_i is None:
            events.append(
                {
                    "event_date": event_date,
                    "confirm_date": None,
                    "end_date": None,
                    "confirmed": False,
                    "depth": float(dd.iloc[i]),
                    "sigma_mult": float(abs(dd.iloc[i]) / sigma.iloc[i]) if sigma.iloc[i] else np.nan,
                    "days": 1,
                    "reason": "R首次预警未在10日内复现",
                }
            )
            i += 1
            continue
        end_i = n - 1
        for k in range(confirm_i, n):
            if nav.iloc[k] >= pre_high:
                end_i = k
                break
        r.iloc[confirm_i : end_i + 1] = 1.0
        seg = dd.iloc[i : end_i + 1]
        events.append(
            {
                "event_date": event_date,
                "confirm_date": idx[confirm_i],
                "end_date": idx[end_i],
                "confirmed": True,
                "depth": float(seg.min()),
                "sigma_mult": float(abs(dd.iloc[confirm_i]) / sigma.iloc[confirm_i]) if sigma.iloc[confirm_i] else np.nan,
                "days": int(confirm_i - i + 1),
                "reason": "R二次确认（10个交易日内复现）",
            }
        )
        i = end_i + 1
    return r, events


def compute_states(ic: pd.Series, ls: pd.Series) -> tuple[pd.DataFrame, list[dict]]:
    """单因子四态；返回逐日诊断与事件。"""
    out = pd.DataFrame(index=ic.index)
    ic_mean252 = ic.rolling(252, min_periods=252).mean()
    ic_mean756 = ic.rolling(756, min_periods=756).mean()
    ic_std252 = ic.rolling(252, min_periods=252).std(ddof=0)
    icir = ic_mean252 / ic_std252.replace(0.0, np.nan)
    out["ic_mean_252"] = ic_mean252
    out["ic_mean_756"] = ic_mean756
    out["icir_252"] = icir

    pct = S.expanding_pct_last(ic_mean252, 126)
    out["ic_pct"] = pct
    L = ((pct < 30) | (icir < 0.5)).astype(float)
    L[pct.isna()] = np.nan
    out["L"] = L

    ratio = ic_mean252 / ic_mean756.replace(0.0, np.nan)
    out["d_ratio"] = ratio
    D = pd.Series(np.nan, index=ic.index)
    enough = ic_mean756.notna()
    direct = enough & ((ic_mean756.abs() < 0.02) | (np.sign(ic_mean252) != np.sign(ic_mean756)))
    D[direct] = 1.0
    D[enough & ~direct] = (ratio[enough & ~direct] < 0.5).astype(float)
    out["D"] = D

    nav = ls.cumsum()
    runmax = nav.cummax()
    dd = nav - runmax
    hist_worst = dd.cummin().shift(1)
    sigma = ls.rolling(252, min_periods=252).std(ddof=0) * np.sqrt(252)
    out["ls_nav"] = nav
    out["depth"] = dd
    out["hist_worst_dd"] = hist_worst
    out["sigma_ls_252"] = sigma
    raw_a = (dd <= hist_worst) & hist_worst.notna()
    raw_b = (dd.abs() > 2.0 * sigma) & sigma.notna()
    raw = (raw_a | raw_b).fillna(False)
    out["R_raw"] = raw.astype(float)
    r, events = _confirm_r(raw, nav, dd, sigma)
    out["R"] = r

    # F：最近 3 个已完结自然月的月频 IC 均值均为负
    if ic.notna().any():
        month = ic.index.to_period("M")
        monthly = ic.groupby(month).agg(["mean", "count"])
        valid = monthly[monthly["count"] >= 10]
        flag_by_month = {}
        for m in monthly.index:
            prev = [x for x in valid.index if x < m][-3:]
            if len(prev) == 3:
                flag_by_month[m] = 1.0 if all(valid.loc[x, "mean"] < 0 for x in prev) else 0.0
        flags = pd.Series(
            [flag_by_month.get(m, np.nan) for m in month], index=ic.index, dtype=float
        )
    else:
        flags = pd.Series(np.nan, index=ic.index)
    out["F"] = flags

    judge = out[["L", "D", "R", "F"]]
    ld = ((out["L"] == 1) | (out["D"] == 1)).fillna(False)
    state = pd.Series(0, index=out.index, dtype=int)
    state[ld] = 1
    state[(out["R"] == 1).fillna(False)] = 2
    state[(out["F"] == 1).fillna(False)] = 3
    out["state"] = state
    out["judge_nan"] = (judge.isna().any(axis=1) | ic.isna()).astype(int)
    return out, events


@dataclass
class FactorResult:
    ic: pd.DataFrame
    ls: pd.DataFrame
    nav: pd.DataFrame
    states: dict[str, pd.DataFrame]
    events: pd.DataFrame
    panel_rows: int


def compute_factors(sl: Slice, idx: pd.DatetimeIndex) -> FactorResult:
    panel = build_factor_panel(sl, idx)
    if panel.empty:
        empty = pd.DataFrame(index=idx)
        return FactorResult(empty, empty, empty, {}, pd.DataFrame(), 0)
    ic, ls, nav = compute_ic_ls(panel)
    states: dict[str, pd.DataFrame] = {}
    events = []
    for f in FACTORS:
        st, ev = compute_states(ic[f], ls[f])
        states[f] = st
        for e in ev:
            events.append({"factor": f, **e})
    ev_df = pd.DataFrame(events)
    return FactorResult(ic, ls, nav, states, ev_df, len(panel))


def states_long(result: FactorResult) -> pd.DataFrame:
    frames = []
    for f, st in result.states.items():
        d = st.copy()
        d["factor"] = f
        d["date"] = d.index
        frames.append(d.reset_index(drop=True))
    if not frames:
        return pd.DataFrame()
    cols = ["date", "factor", "L", "D", "R", "F", "state", "R_raw", "ic_pct", "ic_mean_252",
            "ic_mean_756", "icir_252", "ls_nav", "depth", "hist_worst_dd", "sigma_ls_252", "judge_nan"]
    out = pd.concat(frames, ignore_index=True)
    return out[[c for c in cols if c in out.columns]]


def factor_ic_long(result: FactorResult) -> pd.DataFrame:
    rows = []
    for f in FACTORS:
        st = result.states.get(f)
        for d in result.ic.index:
            rows.append(
                {
                    "date": d.strftime("%Y-%m-%d"),
                    "factor": f,
                    "rank_ic": result.ic.loc[d, f],
                    "ls_ret": result.ls.loc[d, f],
                    "ls_nav": result.nav.loc[d, f],
                    "ic_mean_252": st.loc[d, "ic_mean_252"] if st is not None else None,
                    "ic_mean_756": st.loc[d, "ic_mean_756"] if st is not None else None,
                    "icir_252": st.loc[d, "icir_252"] if st is not None else None,
                    "ic_pct": st.loc[d, "ic_pct"] if st is not None else None,
                    "state": st.loc[d, "state"] if st is not None else None,
                }
            )
    return pd.DataFrame(rows)
