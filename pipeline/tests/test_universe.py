# -*- coding: utf-8 -*-
"""universe / 两个池的离线测试（FakeClient，不联网）。"""
from __future__ import annotations

import pandas as pd
import pytest

from wp import config as C
from wp.universe import UniverseError, build_pool, build_universe, load_st_info
from wp.ts_client import TsError


def _basic() -> pd.DataFrame:
    rows = [
        ("000001.SZ", "平安银行", "主板", "20100101", None),
        ("000002.SZ", "万科A", "主板", "20110101", None),
        ("000003.SZ", "ST某某", "主板", "20120101", None),
        ("000004.SZ", "国华网安", "主板", "20130101", None),
        ("000005.SZ", "退市样本", "主板", "20140101", "20261010"),
        ("000006.SZ", "次新样本", "主板", "20260901", None),
        ("000007.SZ", "整理样本", "主板", "20150101", None),
        ("000008.SZ", "*ST名称", "主板", "20160101", None),
        ("688001.SH", "华兴源创", "科创板", "20190722", None),
        ("830001.BJ", "北交样本", "北交所", "20200101", None),
        ("900901.SH", "云赛B股", "主板", "19920101", None),
    ]
    return pd.DataFrame(rows, columns=["ts_code", "name", "market", "list_date", "delist_date"])


def _daily_basic() -> pd.DataFrame:
    mv = {
        "000001.SZ": (100.0, 80.0),
        "000002.SZ": (90.0, 70.0),
        "000003.SZ": (80.0, 60.0),
        "000004.SZ": (70.0, 50.0),
        "000005.SZ": (60.0, 40.0),
        "000006.SZ": (50.0, 30.0),
        "000007.SZ": (10.0, 4.0),
        "000008.SZ": (9.0, 3.0),
        "688001.SH": (40.0, 20.0),
        "830001.BJ": (30.0, 10.0),
        "900901.SH": (20.0, 5.0),
    }
    rows = [
        (code, "20261015", 10.0, 1.0, 1.0, total, circ, 0.0)
        for code, (total, circ) in mv.items()
    ]
    return pd.DataFrame(
        rows,
        columns=["ts_code", "trade_date", "close", "turnover_rate", "pb", "total_mv", "circ_mv", "dv_ttm"],
    )


def _namechange() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("000007.SZ", "整理样本退", "20261001", None, "退市整理期"),
            ("000003.SZ", "ST某某", "20260101", None, "ST"),
        ],
        columns=["ts_code", "name", "start_date", "end_date", "change_reason"],
    )


class FakeClient:
    def __init__(self, st_raises: bool = False) -> None:
        self.st_raises = st_raises

    def prev_trade_day(self, day: str) -> str:
        return "20261015"

    def daily_basic(self, day: str) -> pd.DataFrame:
        return _daily_basic()

    def stock_basic(self) -> pd.DataFrame:
        return _basic()

    def stock_st(self, day: str) -> pd.DataFrame:
        if self.st_raises:
            raise TsError("boom")
        return pd.DataFrame(
            [("000003.SZ", "ST某某", "20261015", "ST", "风险警示板")],
            columns=["ts_code", "name", "trade_date", "type", "type_name"],
        )

    def namechange(self, start: str, end: str) -> pd.DataFrame:
        return _namechange()


def test_universe_filters() -> None:
    u, prev, info = build_universe(FakeClient(), "2026-10-16")
    assert prev == "20261015"
    assert sorted(u["ts_code"]) == ["000001.SZ", "000002.SZ", "000004.SZ"]
    assert info.source == "stock_st"
    assert not info.degraded


def test_pools_select_by_mv() -> None:
    c = FakeClient()
    total = build_pool(c, "2026-10-16", "total400", n=2)
    circ = build_pool(c, "2026-10-16", "circ1000", n=2)
    assert total.df["ts_code"].tolist() == ["000004.SZ", "000002.SZ"]
    assert circ.df["ts_code"].tolist() == ["000004.SZ", "000002.SZ"]
    assert total.df["rank_in_pool"].tolist() == [1, 2]


def test_pool_short_raises() -> None:
    with pytest.raises(UniverseError):
        build_pool(FakeClient(), "2026-10-16", "total400", n=5)


def test_st_fallback_to_namechange() -> None:
    info = load_st_info(FakeClient(st_raises=True), "2026-10-15")
    assert info.degraded is True
    assert info.source == "namechange"
    assert "000003.SZ" in info.st
    assert "000007.SZ" in info.delist_period


def test_name_rule_catches_missing_st() -> None:
    u, _, _ = build_universe(FakeClient(), "2026-10-16")
    assert "000008.SZ" not in set(u["ts_code"])


def test_kind_validation() -> None:
    with pytest.raises(ValueError):
        build_pool(FakeClient(), "2026-10-16", "bad", n=1)


def test_pool_size_defaults() -> None:
    assert C.POOL_TOTAL_N == 400
    assert C.POOL_CIRC_N == 1000
