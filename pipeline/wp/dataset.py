# -*- coding: utf-8 -*-
"""切片数据装配：取数 -> 宽表 -> 两个池 -> 行业映射。

只依赖 Tushare；所有指标计算在 metrics.py。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from wp import config as C
from wp import series as S
from wp.ts_client import TsClient, to_compact, to_dash


@dataclass
class Slice:
    days: list[str]
    close: pd.DataFrame
    pre_close: pd.DataFrame
    amount: pd.DataFrame
    total_mv: pd.DataFrame
    circ_mv: pd.DataFrame
    turnover: pd.DataFrame
    pb: pd.DataFrame
    qfq: pd.DataFrame
    qfq_ffill: pd.DataFrame
    ma20: pd.DataFrame
    above_incl: pd.DataFrame
    valid_incl: pd.DataFrame
    above_shift: pd.DataFrame
    valid_shift: pd.DataFrame
    ret: pd.DataFrame
    all_ret: pd.Series
    pools_total: dict[str, list[str]]
    pools_circ: dict[str, list[str]]
    layer: pd.DataFrame
    industry: pd.DataFrame
    industry_names: list[str]
    index_money: dict[str, pd.Series]
    index_ret: dict[str, pd.Series]
    margin: dict[str, pd.DataFrame]
    stock_basic: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


def _pivot(d: pd.DataFrame, value: str) -> pd.DataFrame:
    if d is None or d.empty or value not in d.columns:
        return pd.DataFrame()
    return S.pivot(d, value)


def _reindex(df: pd.DataFrame, days: list[str]) -> pd.DataFrame:
    return S.reindex_days(df, days)


def _effective_names(nc: pd.DataFrame, day: str) -> tuple[dict[str, str], set[str]]:
    """namechange 在 day 的有效名称 + 退市整理期代码。"""
    if nc is None or nc.empty:
        return {}, set()
    d = to_compact(day)
    s = nc["start_date"].astype("string")
    e = nc["end_date"].astype("string")
    eff = nc[(s <= d) & (e.isna() | (e >= d))]
    if eff.empty:
        return {}, set()
    eff = eff.sort_values("start_date").drop_duplicates("ts_code", keep="last")
    names = dict(zip(eff["ts_code"], eff["name"].astype(str)))
    reason = eff["change_reason"].astype(str)
    name = eff["name"].astype(str)
    dp = set(eff[reason.str.contains("退市整理", na=False) | name.str.endswith("退")]["ts_code"])
    return names, dp


def _industry_members(client: TsClient, start: str, end: str) -> pd.DataFrame:
    frames = []
    for src, version in (("SW2014", "SW2014"), ("SW2021", "SW2021")):
        cls = client.index_classify(level="L1", src=src)
        if cls.empty:
            continue
        for _, row in cls.iterrows():
            code = str(row["index_code"])
            mem = client.index_member(code)
            if mem.empty:
                continue
            mem = mem.copy()
            mem["l1_code"] = code
            mem["l1_name"] = str(row["industry_name"])
            mem["version"] = version
            frames.append(mem)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(["version", "l1_code", "con_code", "in_date", "out_date"])


def _industry_panel(members: pd.DataFrame, days: list[str]) -> tuple[pd.DataFrame, list[str]]:
    if members.empty:
        return pd.DataFrame(index=pd.to_datetime(days)), []
    names = sorted(members["l1_name"].unique().tolist())
    out = pd.DataFrame(np.nan, index=pd.to_datetime(days), columns=[], dtype=object)
    rows = {}
    for day in days:
        d = to_compact(day)
        ver = "SW2014" if day < C.INDUSTRY_SWITCH_DATE else "SW2021"
        sub = members[members["version"] == ver]
        s = sub["in_date"].astype("string")
        e = sub["out_date"].astype("string")
        eff = sub[(s <= d) & (e.isna() | (e >= d))]
        if eff.empty:
            continue
        eff = eff.sort_values("in_date").drop_duplicates("con_code", keep="last")
        rows[to_dash(day)] = dict(zip(eff["con_code"], eff["l1_name"]))
    out = pd.DataFrame(rows).T
    out.index = pd.to_datetime(out.index)
    return out, names


def _fetch_by_day(client: TsClient, days: list[str], fn, label: str) -> dict[str, pd.DataFrame]:
    def one(d: str) -> pd.DataFrame:
        try:
            return fn(d)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"{label} {d} 取数失败: {exc}") from exc

    return client.fetch_many(days, one)


def load_slice(
    client: TsClient,
    start: str,
    end: str,
    fetch_start: str | None = None,
    include_margin: bool = True,
) -> Slice:
    """取 [fetch_start, end] 的日频数据，构建宽表、两个池、行业与层级。

    指标计算区间由调用方决定；fetch_start 通常比输出起点早 70~300 个交易日。
    """
    fetch_start = fetch_start or start
    days = client.trade_days(fetch_start, end)
    if len(days) < 30:
        raise ValueError(f"交易日不足: {days[0] if days else '?'} ~ {end}")

    daily = _fetch_by_day(client, days, client.daily, "daily")
    basic = _fetch_by_day(client, days, client.daily_basic, "daily_basic")
    st = _fetch_by_day(client, days, client.stock_st, "stock_st")
    margin = _fetch_by_day(client, days, client.margin_detail, "margin") if include_margin else {}

    idx = {}
    for key, code in C.INDEX_CODES.items():
        idx[key] = client.index_daily(code, days[0], days[-1])

    sb = client.stock_basic()
    start_year = int(days[0][:4])
    end_year = int(days[-1][:4])
    nc_frames = [client.namechange(f"{y}0101", f"{y}1231") for y in range(start_year - 1, end_year + 1)]
    nc = pd.concat([x for x in nc_frames if x is not None and not x.empty], ignore_index=True)

    # ---- 宽表 ----
    close = _reindex(_pivot(pd.concat(daily.values(), ignore_index=True), "close"), days)
    pre = _reindex(_pivot(pd.concat(daily.values(), ignore_index=True), "pre_close"), days)
    amount = _reindex(_pivot(pd.concat(daily.values(), ignore_index=True), "amount"), days)
    bdf = pd.concat(basic.values(), ignore_index=True)
    total_mv = _reindex(_pivot(bdf, "total_mv"), days).ffill()
    circ_mv = _reindex(_pivot(bdf, "circ_mv"), days).ffill()
    turnover = _reindex(_pivot(bdf, "turnover_rate"), days)
    pb = _reindex(_pivot(bdf, "pb"), days)

    qfq = S.qfq_chain(close, pre)
    qfq_ffill = S.ffill_to_days(qfq, days)
    ma20 = qfq_ffill.rolling(20).mean()
    valid_incl = qfq_ffill.notna() & ma20.notna()
    above_incl = (qfq_ffill > ma20) & valid_incl
    ma20_s = ma20.shift(1)
    valid_shift = qfq_ffill.notna() & ma20_s.notna()
    above_shift = (qfq_ffill > ma20_s) & valid_shift
    ret = close / pre - 1.0

    codes = [c for c in close.columns if not str(c).endswith(C.EXCLUDE_SUFFIXES)]
    all_ret = ret[codes].mean(axis=1)

    # ---- 两个池 + 分层 ----
    sb = sb.set_index("ts_code")
    list_dt = pd.to_datetime(sb["list_date"], format="%Y%m%d", errors="coerce")
    delist_dt = pd.to_datetime(sb["delist_date"], format="%Y%m%d", errors="coerce")
    base_codes = [
        c
        for c in total_mv.columns
        if not str(c).endswith(C.EXCLUDE_SUFFIXES)
        and not str(c).startswith(C.EXCLUDE_PREFIXES)
        and c in sb.index
    ]

    pools_total: dict[str, list[str]] = {}
    pools_circ: dict[str, list[str]] = {}
    layer_rows: dict[str, dict[str, int]] = {}
    warnings: list[str] = []
    for i, day in enumerate(days):
        if i == 0:
            continue
        prev = days[i - 1]
        t = pd.Timestamp(day)
        cand = [
            c
            for c in base_codes
            if pd.notna(list_dt.get(c)) and list_dt[c] <= t - pd.Timedelta(days=C.MIN_LIST_DAYS)
            and (pd.isna(delist_dt.get(c)) or delist_dt[c] > t)
        ]
        st_set = set(st[prev]["ts_code"].astype(str)) if prev in st and not st[prev].empty else set()
        _, dp = _effective_names(nc, prev)
        mv_t = total_mv.loc[prev]
        mv_c = circ_mv.loc[prev]
        cand = [c for c in cand if c not in st_set and c not in dp]
        ct = sorted([c for c in cand if pd.notna(mv_t.get(c)) and mv_t[c] > 0], key=lambda c: (mv_t[c], c))
        cc = sorted([c for c in cand if pd.notna(mv_c.get(c)) and mv_c[c] > 0], key=lambda c: (mv_c[c], c))
        if len(ct) < C.POOL_TOTAL_N or len(cc) < C.POOL_CIRC_N:
            warnings.append(f"{day} 池样本不足 total={len(ct)} circ={len(cc)}")
        pools_total[day] = ct[: C.POOL_TOTAL_N]
        pools_circ[day] = cc[: C.POOL_CIRC_N]
        layer_rows[day] = {c: (j // (C.POOL_TOTAL_N // 10)) + 1 for j, c in enumerate(pools_total[day])}

    layer = pd.DataFrame(layer_rows).T
    layer.index = pd.to_datetime(layer.index)

    # ---- 行业 ----
    members = _industry_members(client, days[0], days[-1])
    industry, industry_names = _industry_panel(members, days)
    if industry.empty:
        warnings.append("行业映射为空")

    # ---- 指数 ----
    index_money: dict[str, pd.Series] = {}
    index_ret: dict[str, pd.Series] = {}
    for key, df in idx.items():
        if df is None or df.empty:
            continue
        s = df.copy()
        s["dt"] = pd.to_datetime(s["trade_date"], format="%Y%m%d")
        s = s.set_index("dt").sort_index()
        money = (s["amount"] / 1e5).reindex(pd.to_datetime(days)).ffill()
        index_money[key] = money
        index_ret[key] = (s["close"] / s["pre_close"] - 1.0).reindex(pd.to_datetime(days)).ffill()

    return Slice(
        days=days,
        close=close,
        pre_close=pre,
        amount=amount,
        total_mv=total_mv,
        circ_mv=circ_mv,
        turnover=turnover,
        pb=pb,
        qfq=qfq,
        qfq_ffill=qfq_ffill,
        ma20=ma20,
        above_incl=above_incl,
        valid_incl=valid_incl,
        above_shift=above_shift,
        valid_shift=valid_shift,
        ret=ret,
        all_ret=all_ret,
        pools_total=pools_total,
        pools_circ=pools_circ,
        layer=layer,
        industry=industry,
        industry_names=industry_names,
        index_money=index_money,
        index_ret=index_ret,
        margin=margin,
        stock_basic=sb.reset_index(),
        warnings=warnings,
    )
