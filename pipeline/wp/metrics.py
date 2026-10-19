# -*- coding: utf-8 -*-
"""指标计算：从 Slice 生成 metrics 表 + 行业宽度长表。

口径见 docs/口径.md / docs/UI.md；所有分位与阈值在 build_site 再定。
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from wp import config as C
from wp import series as S
from wp.dataset import Slice


def _breadth(above: pd.DataFrame, valid: pd.DataFrame, mask: pd.DataFrame, min_n: int = 1) -> pd.Series:
    v = valid & mask
    a = above & mask
    n = v.sum(axis=1)
    hit = a.sum(axis=1)
    return (hit * 100.0 / n).where(n >= min_n)


def _pct_pair(s: pd.Series, win: int, minp: int) -> tuple[pd.Series, pd.Series]:
    return S.rolling_pct_last(s, win, minp), S.expanding_pct_last(s, 250)


def _mask_from_pools(pools: dict[str, list[str]], idx: pd.DatetimeIndex, columns: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(False, index=idx, columns=columns)
    for d in idx:
        codes = pools.get(d.strftime("%Y%m%d"))
        if not codes:
            continue
        cols = [c for c in codes if c in df.columns]
        df.loc[d, cols] = True
    return df


def _margin_row(md: pd.DataFrame, pool: list[str], pool_wp: list[str]) -> dict:
    if md is None or md.empty:
        return {}
    md = md.dropna(subset=["rzye"])
    if md.empty:
        return {}
    codes = set(md["ts_code"].astype(str))
    p = [c for c in pool if c in codes]
    wp = [c for c in pool_wp if c in codes]
    mkt_rzye = float(md["rzye"].sum())
    mkt_rzmre = float(md["rzmre"].sum()) if "rzmre" in md else np.nan
    out = {
        "margin_mkt_rzye": mkt_rzye,
        "margin_mkt_rzmre": mkt_rzmre,
        "margin_pool_n": len(p),
        "margin_pool_rzye": float(md.loc[md["ts_code"].isin(p), "rzye"].sum()) if p else np.nan,
        "margin_pool_rzmre": float(md.loc[md["ts_code"].isin(p), "rzmre"].sum()) if p else np.nan,
        "margin_wp400_n": len(wp),
        "margin_wp400_rzye": float(md.loc[md["ts_code"].isin(wp), "rzye"].sum()) if wp else np.nan,
    }
    out["margin_pool_ratio"] = (
        out["margin_pool_rzye"] / mkt_rzye * 100.0
        if mkt_rzye and pd.notna(out["margin_pool_rzye"])
        else np.nan
    )
    out["margin_pool_buy_ratio"] = (
        out["margin_pool_rzmre"] / mkt_rzmre * 100.0
        if mkt_rzmre and pd.notna(out["margin_pool_rzmre"])
        else np.nan
    )
    out["margin_wp400_ratio"] = (
        out["margin_wp400_rzye"] / mkt_rzye * 100.0
        if mkt_rzye and pd.notna(out["margin_wp400_rzye"])
        else np.nan
    )
    return out


def compute_metrics(sl: Slice) -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = pd.to_datetime([f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in sl.days[1:]])
    codes = list(sl.close.columns)
    above = sl.above_incl.reindex(index=idx, columns=codes)
    valid = sl.valid_incl.reindex(index=idx, columns=codes)
    above_s = sl.above_shift.reindex(index=idx, columns=codes)
    valid_s = sl.valid_shift.reindex(index=idx, columns=codes)
    ret = sl.ret.reindex(index=idx, columns=codes)
    amount = sl.amount.reindex(index=idx, columns=codes)
    turnover = sl.turnover.reindex(index=idx, columns=codes)
    pb = sl.pb.reindex(index=idx, columns=codes)
    total_mv = sl.total_mv.reindex(index=idx)

    m_total = _mask_from_pools(sl.pools_total, idx, codes)
    m_circ = _mask_from_pools(sl.pools_circ, idx, codes)
    out = pd.DataFrame(index=idx)
    out.index.name = "date"

    # ---- 微盘400 宽度 / 等权指数 ----
    n10 = (valid & m_total).sum(axis=1)
    out["breadth10"] = _breadth(above, valid, m_total, 30).where(n10 >= 30)
    out["n_valid10"] = n10
    out["n_pool"] = m_total.sum(axis=1)
    out["n_pool_circ"] = m_circ.sum(axis=1)
    wp_ret = ret.where(m_total).mean(axis=1)
    out["wp400_ret"] = wp_ret
    out["wp400_index"] = S.equal_weight_index(wp_ret)
    out["breadth10_pct"], out["breadth10_pct_exp"] = _pct_pair(out["breadth10"], 250, 120)

    # ---- 集中度（剔北交所） ----
    amt_all = amount[[c for c in codes if not str(c).endswith(C.EXCLUDE_SUFFIXES)]]
    out["ratio_top5"] = S.top_ratio(amt_all, 0.05)
    out["ratio_top10"] = S.top_ratio(amt_all, 0.10)
    out["ratio_top5_pct"], out["ratio_top5_pct_exp"] = _pct_pair(out["ratio_top5"], 750, 250)
    out["ratio_top10_pct"], out["ratio_top10_pct_exp"] = _pct_pair(out["ratio_top10"], 750, 250)

    # ---- 五层成交额 / 收益 ----
    all_money = amt_all.sum(axis=1) / 1e5
    out["all_money"] = all_money
    for key, name in (("csi300", "300"), ("csi500", "500"), ("csi1000", "1000"), ("gz2000", "2000")):
        out[f"money_{name}"] = sl.index_money.get(key, pd.Series(np.nan, index=idx)).reindex(idx)
    out["money_wp400"] = amount.where(m_total).sum(axis=1) / 1e5
    for name in ("300", "500", "1000", "2000", "wp400"):
        share = out[f"money_{name}"] / out["all_money"] * 100.0
        out[f"share_{name}"] = share
        out[f"share_{name}_pct"], out[f"share_{name}_pct_exp"] = _pct_pair(share, 250, 250)
    for key, name in (("csi300", "300"), ("csi500", "500"), ("csi1000", "1000"), ("gz2000", "2000")):
        r = sl.index_ret.get(key, pd.Series(np.nan, index=idx)).reindex(idx)
        out[f"ret_ma5_{name}"] = r.rolling(5).mean() * 100.0
    out["ret_ma5_wp400"] = wp_ret.rolling(5).mean() * 100.0

    # ---- 拥挤度三维度 ----
    pb_codes = [c for c in codes if not str(c).endswith(C.EXCLUDE_SUFFIXES)]
    pbs = S.pb_spread(pb[pb_codes], total_mv[pb_codes])
    for col in pbs.columns:
        out[col] = pbs[col]
    out["pb_spread_pct"], out["pb_spread_pct_exp"] = _pct_pair(out["pb_spread"], 250, 120)

    corr = pd.Series(np.nan, index=idx, dtype=float)
    for i, d in enumerate(idx):
        if i < 59:
            continue
        day = d.strftime("%Y%m%d")
        pool = [c for c in sl.pools_total.get(day, []) if c in ret.columns]
        if len(pool) < 30:
            continue
        corr.iloc[i] = S.corr60_last(ret.iloc[i - 59 : i + 1][pool], min_n=30)
    out["corr60_wp400"] = corr
    out["corr60_wp400_pct"], out["corr60_wp400_pct_exp"] = _pct_pair(corr, 250, 120)

    out["ls_vol_ratio"] = S.ls_vol_ratio(wp_ret, sl.all_ret.reindex(idx), 20)
    out["ls_vol_ratio_pct"], out["ls_vol_ratio_pct_exp"] = _pct_pair(out["ls_vol_ratio"], 250, 120)

    # ---- qs_share ----
    qs, qsub, qvalid, qs_abs = [], [], [], []
    for d in idx:
        day = d.strftime("%Y%m%d")
        pool = [c for c in sl.pools_total.get(day, []) if c in amount.columns]
        money = amount.loc[d, pool]
        turn = turnover.loc[d, pool]
        ok = money.notna() & turn.notna()
        n = int(ok.sum())
        qvalid.append(n)
        if n < 300:
            qs.append(np.nan)
            qsub.append(np.nan)
            qs_abs.append(np.nan)
            continue
        m, t = money[ok], turn[ok]
        sub = (m.rank(pct=True) * 100 < 40) & (t.rank(pct=True) * 100 > 60)
        qsub.append(int(sub.sum()))
        qs.append(0.0 if not sub.any() else float(m[sub].sum() / m.sum() * 100.0))
        sub_abs = (m < 40000) & (t > 3.0)
        qs_abs.append(0.0 if not sub_abs.any() else float(m[sub_abs].sum() / m.sum() * 100.0))
    out["qs_share"] = qs
    out["qs_subset_n"] = qsub
    out["qs_valid_n"] = qvalid
    out["qs_share_abs"] = qs_abs
    out["qs_share_pct"], out["qs_share_pct_exp"] = _pct_pair(out["qs_share"], 250, 120)

    # ---- 内部 10 层 ----
    layer_masks = {}
    for L in range(1, 11):
        layer_masks[L] = (sl.layer == L).reindex(index=idx, columns=codes).fillna(False).astype(bool)
        mask = layer_masks[L]
        nv = (valid_s & mask).sum(axis=1)
        br = _breadth(above_s, valid_s, mask, 30).where(nv >= 30)
        out[f"breadth_L{L}"] = br
        out[f"breadth_L{L}_pct"] = S.rolling_pct_last(br, 250, 120)
        out[f"n_valid_L{L}"] = nv
        r = ret.where(mask).mean(axis=1)
        out[f"ret_ma5_L{L}"] = r.rolling(5).mean() * 100.0

    # ---- 行业宽度 ----
    ind = sl.industry.reindex(index=idx, columns=codes)
    ind_rows = []
    for name in sl.industry_names:
        mask = (ind == name)
        if not mask.any().any():
            continue
        nv = (valid & mask).sum(axis=1)
        hit = (above & mask).sum(axis=1)
        br = (hit * 100.0 / nv).where(nv > 0)
        for d, v, n in zip(idx, br, nv):
            if pd.notna(v):
                ind_rows.append(
                    {"date": d.strftime("%Y-%m-%d"), "industry": name, "breadth": float(v), "n_valid": int(n)}
                )
    ind_df = pd.DataFrame(ind_rows)
    if not ind_df.empty:
        tmp = ind_df.copy()
        tmp["br_round"] = tmp["breadth"].round()
        s_width = tmp.groupby("date")["br_round"].sum()
        n_ind = tmp.groupby("date")["breadth"].apply(lambda s: int((s > 0).sum()))
        s_width.index = pd.to_datetime(s_width.index)
        out["s_width"] = s_width.reindex(out.index)
        n_ind.index = pd.to_datetime(n_ind.index)
        out["n_industries"] = n_ind.reindex(out.index)
        out["s_width_pct"] = out["s_width"] / out["n_industries"]
    else:
        out["s_width"] = np.nan
        out["n_industries"] = np.nan
        out["s_width_pct"] = np.nan

    # ---- 两融 ----
    rows = []
    for d in idx:
        day = d.strftime("%Y%m%d")
        rows.append(_margin_row(sl.margin.get(day), sl.pools_circ.get(day, []), sl.pools_total.get(day, [])))
    mdf = pd.DataFrame(rows, index=idx)
    for col in mdf.columns:
        out[col] = mdf[col]
    out["margin_pool_ratio_z"] = S.zscore_rolling(out.get("margin_pool_ratio", pd.Series(np.nan, index=idx)), 90, 30)

    out["data_through"] = idx.strftime("%Y-%m-%d")
    return out.reset_index(), ind_df


def run_meta(start: str, end: str, days: int, data_through: str, warnings: list[str]) -> dict:
    return {
        "schema_version": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "tushare",
        "slice_start": start,
        "slice_end": end,
        "days": days,
        "data_through": data_through,
        "warnings": warnings,
    }
