# -*- coding: utf-8 -*-
"""series 纯计算测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wp import series as S


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2024-01-02", periods=n)


def test_qfq_chain_handles_split() -> None:
    idx = _dates(3)
    close = pd.DataFrame({"A": [10.0, 11.0, 5.5]}, index=idx)
    pre = pd.DataFrame({"A": [10.0, 10.0, 5.5]}, index=idx)  # 1 拆 2，pre_close 已调整
    adj = S.qfq_chain(close, pre)
    assert adj["A"].tolist() == pytest.approx([10.0, 11.0, 11.0])


def test_qfq_chain_missing_preclose() -> None:
    idx = _dates(3)
    close = pd.DataFrame({"A": [10.0, np.nan, 12.0]}, index=idx)
    pre = pd.DataFrame({"A": [10.0, 10.0, np.nan]}, index=idx)
    adj = S.qfq_chain(close, pre)
    assert np.isnan(adj["A"].iloc[1])
    assert np.isnan(adj["A"].iloc[2])


def test_rolling_and_expanding_pct() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert S.rolling_pct_last(s, 4, 4).iloc[-1] == pytest.approx(100.0)
    assert S.rolling_pct_last(s.iloc[::-1], 4, 4).iloc[-1] == pytest.approx(25.0)
    assert S.expanding_pct_last(s, 4).iloc[-1] == pytest.approx(100.0)
    assert np.isnan(S.rolling_pct_last(s, 4, 4).iloc[0])


def test_corr60_identical_and_zero_var() -> None:
    idx = _dates(80)
    rng = np.random.default_rng(0)
    base = rng.normal(0, 0.01, len(idx))
    ret = pd.DataFrame({"A": base, "B": base, "C": np.zeros(len(idx))}, index=idx)
    out = S.corr60(ret, window=60, min_n=2)
    assert np.isnan(out.iloc[58])
    assert out.iloc[-1] == pytest.approx(1.0)


def test_corr60_needs_min_members() -> None:
    idx = _dates(80)
    rng = np.random.default_rng(1)
    ret = pd.DataFrame(rng.normal(0, 0.01, (len(idx), 10)), index=idx)
    out = S.corr60(ret, window=60, min_n=30)
    assert out.isna().all()


def test_ls_vol_ratio() -> None:
    idx = _dates(30)
    rng = np.random.default_rng(2)
    pool = pd.Series(rng.normal(0, 0.02, len(idx)), index=idx)
    allr = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    out = S.ls_vol_ratio(pool, allr, window=20)
    assert np.isnan(out.iloc[18])
    assert np.isfinite(out.iloc[-1])


def test_pb_spread() -> None:
    idx = _dates(1)
    mv = pd.DataFrame({"A": [1.0], "B": [2.0], "C": [3.0], "D": [4.0], "E": [5.0]}, index=idx)
    pb = pd.DataFrame({"A": [2.0], "B": [1.0], "C": [3.0], "D": [4.0], "E": [5.0]}, index=idx)
    out = S.pb_spread(pb, mv, frac=0.4, min_pos=2)
    # k=round(5*0.4)=2，小市值 A/B -> 1.5，大市值 D/E -> 4.5
    assert out["pb_small_med"].iloc[0] == pytest.approx(1.5)
    assert out["pb_large_med"].iloc[0] == pytest.approx(4.5)
    assert out["pb_spread"].iloc[0] == pytest.approx(1.5 / 4.5)


def test_top_ratio() -> None:
    idx = _dates(1)
    amount = pd.DataFrame({f"S{i}": [float(i)] for i in range(1, 101)}, index=idx)
    out = S.top_ratio(amount, 0.05)
    # 前 5 只：96..100，占 1..100 总和的 490/5050
    assert out.iloc[0] == pytest.approx(490.0 / 5050.0 * 100.0)


def test_breadth_and_industry() -> None:
    idx = _dates(2)
    above = pd.DataFrame({"A": [True, False], "B": [True, True]}, index=idx)
    valid = pd.DataFrame({"A": [True, True], "B": [True, True]}, index=idx)
    assert S.breadth(above, valid).tolist() == pytest.approx([100.0, 50.0])
    ind = {"A": "银行", "B": "医药"}
    out = S.industry_breadth(above, valid, ind)
    assert out["银行"].tolist() == pytest.approx([100.0, 0.0])
    assert out["医药"].tolist() == pytest.approx([100.0, 100.0])
