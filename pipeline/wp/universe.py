# -*- coding: utf-8 -*-
"""股票池：universe 过滤 + 两个池（total400 / circ1000）。

池在 T 日盘前即可确定：用 T-1 收盘的 `daily_basic` 市值排序，T 日生效。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from wp import config as C
from wp.ts_client import TsClient, TsError, to_compact, to_dash

PoolKind = Literal["total400", "circ1000"]

_KIND_MAP: dict[str, tuple[str, int]] = {
    "total400": ("total_mv", C.POOL_TOTAL_N),
    "circ1000": ("circ_mv", C.POOL_CIRC_N),
}


class UniverseError(RuntimeError):
    """池构建失败（样本不足/字段缺失）。"""


@dataclass(frozen=True)
class StInfo:
    st: frozenset[str]
    delist_period: frozenset[str]
    source: str
    degraded: bool


@dataclass
class PoolResult:
    kind: str
    trade_date: str
    prev_trade_date: str
    df: pd.DataFrame
    st_info: StInfo
    name_mismatch: int
    suspended_filled: int = 0

    @property
    def codes(self) -> list[str]:
        return self.df["ts_code"].tolist()


def _le(series: pd.Series, compact: str) -> pd.Series:
    """series 中 YYYYMMDD 字符串（或空）<= compact。"""
    s = series.astype("string")
    return s.notna() & (s <= compact)


def _ge(series: pd.Series, compact: str) -> pd.Series:
    s = series.astype("string")
    return s.notna() & (s >= compact)


def load_st_info(client: TsClient, day: str) -> StInfo:
    """按日取 ST 与退市整理期。

    - ST：`stock_st` 权威；失败时回退 `namechange`（再回退 `stock_basic` 名称），并记 degraded。
    - 退市整理期：`namechange` 的 change_reason / 名称后缀；名称只作补充。
    """
    d = to_compact(day)
    st: set[str] = set()
    source = "stock_st"
    degraded = False

    try:
        df = client.stock_st(day)
        if not df.empty:
            st = set(df["ts_code"].astype(str))
    except TsError:
        degraded = True
        source = "namechange"

    delist: set[str] = set()
    nc = None
    try:
        nc = client.namechange(f"{d[:4]}0101", day)
    except TsError:
        nc = None

    if nc is not None and not nc.empty:
        eff = nc[_le(nc["start_date"], d) & (_ge(nc["end_date"], d) | nc["end_date"].isna())]
        if degraded:
            st |= set(eff[eff["name"].astype(str).str.contains("ST", na=False)]["ts_code"])
        reason = eff["change_reason"].astype(str)
        name = eff["name"].astype(str)
        delist |= set(
            eff[reason.str.contains("退市整理", na=False) | name.str.endswith("退")]["ts_code"]
        )

    if degraded and not st:
        basic = client.stock_basic()
        if not basic.empty:
            st = set(basic[basic["name"].astype(str).str.contains("ST", na=False)]["ts_code"])
            source = "stock_basic"

    return StInfo(frozenset(st), frozenset(delist), source, degraded)


def _potential_codes(basic: pd.DataFrame, t: pd.Timestamp) -> pd.DataFrame:
    """可能进池的证券（只做板块/上市/退市过滤，不含 ST 与市值）。"""
    list_dt = pd.to_datetime(basic["list_date"], format="%Y%m%d", errors="coerce")
    delist_dt = pd.to_datetime(basic["delist_date"], format="%Y%m%d", errors="coerce")
    mask = (
        ~basic["ts_code"].str.endswith(C.EXCLUDE_SUFFIXES)
        & ~basic["ts_code"].str.startswith(C.EXCLUDE_PREFIXES)
        & list_dt.notna()
        & (list_dt <= t - pd.Timedelta(days=C.MIN_LIST_DAYS))
        & (delist_dt.isna() | (delist_dt > t))
    )
    return basic[mask].copy()


def load_valuation(
    client: TsClient,
    day: str,
    lookback_days: int = C.VALUATION_LOOKBACK_DAYS,
    max_fill: int = C.VALUATION_MAX_FILL,
) -> pd.DataFrame:
    """T-1 估值截面；对停牌股（daily_basic 无行）按个股向前取最近一次估值。

    Tushare `daily_basic(trade_date)` 不返回停牌股，而旧池包含停牌股。
    不补会把停牌股挤出池子，历史对拍会大幅偏移。
    """
    d = to_compact(day)
    db = client.daily_basic(day)
    basic = client.stock_basic()
    if db.empty or basic.empty:
        return db

    t = pd.Timestamp(to_dash(day))
    potential = _potential_codes(basic, t)
    missing = sorted(set(potential["ts_code"]) - set(db["ts_code"]))
    rows: list[dict] = []
    start = (t - pd.Timedelta(days=lookback_days)).strftime("%Y%m%d")
    for code in missing[:max_fill]:
        hist = client.daily_basic_history(code, start, d)
        if hist.empty:
            continue
        hist = hist.sort_values("trade_date")
        last = hist.iloc[-1].to_dict()
        last["valuation_date"] = str(last.get("trade_date", d))
        last["valuation_stale"] = True
        rows.append(last)

    if rows:
        filler = pd.DataFrame(rows)
        db = pd.concat([db, filler], ignore_index=True)

    db["valuation_date"] = db["valuation_date"].fillna(db["trade_date"]) if "valuation_date" in db else db["trade_date"]
    db["valuation_stale"] = db["valuation_stale"].fillna(False) if "valuation_stale" in db else False
    return db


def build_universe(
    client: TsClient,
    trade_date: str,
    st_info: StInfo | None = None,
    fill_suspended: bool = True,
) -> tuple[pd.DataFrame, str, StInfo]:
    """返回 (universe, prev_trade_date, st_info)。

    universe 列：ts_code, name, market, list_date, delist_date, total_mv, circ_mv,
    turnover_rate, pb, dv_ttm, st, delist_period, is_star, valuation_date, valuation_stale。
    """
    day = to_dash(trade_date)
    d = to_compact(day)
    prev = client.prev_trade_day(day)
    info = st_info or load_st_info(client, prev)

    db = load_valuation(client, prev) if fill_suspended else client.daily_basic(prev)
    basic = client.stock_basic()
    if db.empty:
        raise UniverseError(f"{prev} 的 daily_basic 为空")
    if basic.empty:
        raise UniverseError("stock_basic 为空")

    u = db.merge(basic, on="ts_code", how="inner", suffixes=("", "_basic"))
    if u.empty:
        raise UniverseError(f"{prev} daily_basic 与 stock_basic 无交集")

    u["list_date_dt"] = pd.to_datetime(u["list_date"], format="%Y%m%d", errors="coerce")
    u["delist_date_dt"] = pd.to_datetime(u["delist_date"], format="%Y%m%d", errors="coerce")
    t = pd.Timestamp(day)

    is_star = u["ts_code"].str.startswith(("688", "689"))
    name = u["name"].astype("string").fillna("")
    name_st = name.str.contains("ST", na=False)
    name_delist = name.str.endswith("退") | name.str.contains("退市", na=False)

    keep = (
        ~u["ts_code"].str.endswith(C.EXCLUDE_SUFFIXES)
        & ~u["ts_code"].str.startswith(C.EXCLUDE_PREFIXES)
        & ~is_star
        & u["list_date_dt"].notna()
        & (u["list_date_dt"] <= t - pd.Timedelta(days=C.MIN_LIST_DAYS))
        & (u["delist_date_dt"].isna() | (u["delist_date_dt"] > t))
        & ~u["ts_code"].isin(info.st)
        & ~u["ts_code"].isin(info.delist_period)
        & ~name_st
        & ~name_delist
    )
    u = u[keep].copy()

    u["st"] = u["ts_code"].isin(info.st)
    u["delist_period"] = u["ts_code"].isin(info.delist_period)
    u["is_star"] = is_star[keep].to_numpy()
    u = u.sort_values(["ts_code"]).reset_index(drop=True)
    return u, prev, info


def _select_pool(universe: pd.DataFrame, kind: PoolKind, n: int, mv_col: str) -> pd.DataFrame:
    s = universe[universe[mv_col].notna() & (universe[mv_col] > 0)].copy()
    s = s.sort_values([mv_col, "ts_code"], kind="stable").head(n).reset_index(drop=True)
    s["rank_in_pool"] = range(1, len(s) + 1)
    return s


def build_pool(
    client: TsClient,
    trade_date: str,
    kind: PoolKind,
    n: int | None = None,
    st_info: StInfo | None = None,
) -> PoolResult:
    """构建 T 日股票池；样本不足直接失败（硬门禁）。"""
    if kind not in _KIND_MAP:
        raise ValueError(f"kind 必须是 {list(_KIND_MAP)}，收到 {kind!r}")
    mv_col, default_n = _KIND_MAP[kind]
    size = default_n if n is None else int(n)

    universe, prev, info = build_universe(client, trade_date, st_info=st_info)
    pool = _select_pool(universe, kind, size, mv_col)
    if len(pool) < size:
        raise UniverseError(
            f"{kind} 样本不足：需要 {size}，实际 {len(pool)}（prev={prev}，universe={len(universe)}）"
        )

    name = pool["name"].astype("string").fillna("")
    name_mismatch = int(
        (name.str.contains("ST", na=False) | name.str.endswith("退")).sum()
        - int(pool["ts_code"].isin(info.st).sum())
    )
    return PoolResult(
        kind=kind,
        trade_date=to_dash(trade_date),
        prev_trade_date=to_dash(prev),
        df=pool,
        st_info=info,
        name_mismatch=max(name_mismatch, 0),
        suspended_filled=int(pool["valuation_stale"].fillna(False).sum()),
    )
