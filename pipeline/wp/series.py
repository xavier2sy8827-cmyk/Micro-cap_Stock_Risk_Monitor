# -*- coding: utf-8 -*-
"""纯计算工具：宽表、前收链复权、滚动分位、截面相关、集中度等。

约定：输入宽表 index=交易日（升序），columns=ts_code；不复权价格与 pre_close 同源。
"""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

TRD_DAYS = 252


def pivot(
    df: pd.DataFrame,
    value: str,
    index: str = "trade_date",
    columns: str = "ts_code",
) -> pd.DataFrame:
    """长表 -> 宽表，index 转 datetime 并升序。"""
    if df.empty:
        return pd.DataFrame()
    out = df.pivot_table(index=index, columns=columns, values=value, aggfunc="last")
    idx = pd.to_datetime(out.index.astype(str), format="%Y%m%d", errors="coerce")
    out.index = idx
    return out[~out.index.isna()].sort_index()


def reindex_days(df: pd.DataFrame, days: list[str]) -> pd.DataFrame:
    """按交易日列表重排（缺失日补 NaN）。"""
    idx = pd.to_datetime([str(d)[:10] for d in days])
    return df.reindex(idx)


def qfq_chain(close: pd.DataFrame, pre_close: pd.DataFrame) -> pd.DataFrame:
    """用 close/pre_close 收益链构造前复权价格（窗口内自洽）。

    Tushare 的 pre_close 已按除权调整，因此 close/pre_close 是真实日收益；
    从窗口首个有效收盘起复利，即得到窗口内的前复权序列。
    """
    ret = close / pre_close - 1.0
    ret = ret.mask(~np.isfinite(ret))
    first = close.apply(lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan)
    adj = (1.0 + ret.fillna(0.0)).cumprod().mul(first, axis=1)
    # 缺 close 或 pre_close 的点无法定义复权价（第一行 pre_close 常缺，仍由后续收益链承接）
    return adj.where(close.notna() & pre_close.notna())


def ffill_to_days(df: pd.DataFrame, days: list[str]) -> pd.DataFrame:
    """按交易日重排后 ffill（停牌沿用最后收盘，与蒋老师口径一致）。"""
    return reindex_days(df, days).ffill()


def _pct_last(x: np.ndarray) -> float:
    x = x[~np.isnan(x)]
    if x.size == 0:
        return np.nan
    return float((x <= x[-1]).mean() * 100.0)


def rolling_pct_last(s: pd.Series, win: int, min_periods: int) -> pd.Series:
    return s.rolling(win, min_periods=min_periods).apply(_pct_last, raw=True)


def expanding_pct_last(s: pd.Series, min_periods: int) -> pd.Series:
    return s.expanding(min_periods=min_periods).apply(_pct_last, raw=True)


def zscore_rolling(s: pd.Series, win: int = 90, min_periods: int = 30) -> pd.Series:
    mu = s.rolling(win, min_periods=min_periods).mean()
    sd = s.rolling(win, min_periods=min_periods).std(ddof=0)
    return (s - mu) / sd.replace(0.0, np.nan)


def equal_weight_ret(ret: pd.DataFrame, mask: pd.DataFrame) -> pd.Series:
    """按 mask 取有效成员等权平均；当日无有效成员记 NaN。"""
    vals = ret.where(mask)
    n = vals.notna().sum(axis=1)
    return (vals.mean(axis=1)).where(n > 0)


def equal_weight_index(ret: pd.Series, base: float = 1000.0) -> pd.Series:
    """等权指数：收益按天复利；缺日按 0 处理（已在 ret 中体现）。"""
    return (1.0 + ret.fillna(0.0)).cumprod() * base


def corr60(ret: pd.DataFrame, window: int = 60, min_n: int = 30) -> pd.Series:
    """池内日收益两两 60 日相关系数的算术均值（剔除 NaN / 零方差成员）。"""
    out = pd.Series(np.nan, index=ret.index, dtype=float)
    arr = ret.to_numpy(dtype=float)
    for i in range(window - 1, len(ret)):
        w = arr[i - window + 1 : i + 1]
        keep = ~np.isnan(w).any(axis=0)
        w = w[:, keep]
        if w.shape[1] < min_n:
            continue
        sd = w.std(axis=0, ddof=0)
        w = w[:, sd > 0]
        n = w.shape[1]
        if n < min_n:
            continue
        z = (w - w.mean(axis=0)) / w.std(axis=0, ddof=0)
        c = z.T @ z / (window - 1)
        iu = np.triu_indices(n, 1)
        out.iloc[i] = float(np.clip(np.nanmean(c[iu]), -1.0, 1.0))
    return out


def ls_vol_ratio(pool_ret: pd.Series, all_ret: pd.Series, window: int = 20) -> pd.Series:
    """（池等权多 - 全A等权空）20 日年化波动 / 全A 20 日年化波动。"""
    diff = pool_ret - all_ret
    vol_ls = diff.rolling(window, min_periods=window).std(ddof=0) * np.sqrt(TRD_DAYS)
    vol_all = all_ret.rolling(window, min_periods=window).std(ddof=0) * np.sqrt(TRD_DAYS)
    return vol_ls / vol_all.replace(0.0, np.nan)


def pb_spread(
    pb: pd.DataFrame,
    total_mv: pd.DataFrame,
    frac: float = 0.2,
    min_pos: int = 20,
) -> pd.DataFrame:
    """全A按总市值两端各 frac 组，组内 pb>0 的中位数；返回 small/large/spread。"""
    cols = ["pb_small_med", "pb_large_med", "pb_spread"]
    out = pd.DataFrame(np.nan, index=pb.index, columns=cols, dtype=float)
    common_idx = pb.index.intersection(total_mv.index)
    for d in common_idx:
        p = pb.loc[d]
        m = total_mv.loc[d]
        df = pd.DataFrame({"pb": p, "mv": m}).dropna(subset=["mv"])
        df = df[df["mv"] > 0]
        n = len(df)
        if n == 0:
            continue
        k = max(1, round(n * frac))
        s = df.sort_values("mv", kind="stable")
        small, large = s.head(k), s.tail(k)
        ps = small.loc[small["pb"] > 0, "pb"]
        pl = large.loc[large["pb"] > 0, "pb"]
        if len(ps) < min_pos or len(pl) < min_pos:
            continue
        a, b = float(ps.median()), float(pl.median())
        if b <= 0:
            continue
        out.loc[d] = [a, b, a / b]
    return out


def top_ratio(amount: pd.DataFrame, frac: float) -> pd.Series:
    """全A成交额前 frac 占比（%）。"""
    out = pd.Series(np.nan, index=amount.index, dtype=float)
    for d in amount.index:
        s = amount.loc[d].dropna()
        if s.empty:
            continue
        k = max(1, round(len(s) * frac))
        out.loc[d] = float(s.nlargest(k).sum() / s.sum() * 100.0)
    return out


def breadth(above: pd.DataFrame, valid: pd.DataFrame) -> pd.Series:
    """逐日 `above & valid` 占比 *100；无有效成员记 NaN。"""
    n = valid.sum(axis=1)
    hit = (above.fillna(False).astype(bool) & valid.fillna(False).astype(bool)).sum(axis=1)
    return (hit * 100.0 / n).where(n > 0)


def industry_breadth(
    above: pd.DataFrame,
    valid: pd.DataFrame,
    industry: Mapping[str, str],
    min_valid: int = 1,
) -> pd.DataFrame:
    """逐日各行业 breadth（%），列为行业名；有效成员 < min_valid 的行业记 NaN。"""
    cols = pd.Index(list(above.columns))
    ind = pd.Series(industry, index=cols).dropna()
    keep = ind.index.intersection(above.columns)
    if len(keep) == 0:
        return pd.DataFrame(index=above.index)
    a = above[keep].astype(bool)
    v = valid[keep].astype(bool)
    out = {}
    for name, codes in ind.loc[keep].groupby(ind.loc[keep]):
        sub_v = v[codes.index]
        sub_a = a[codes.index]
        n = sub_v.sum(axis=1)
        hit = (sub_a & sub_v).sum(axis=1)
        out[name] = (hit * 100.0 / n).where(n >= min_valid)
    return pd.DataFrame(out, index=above.index)
