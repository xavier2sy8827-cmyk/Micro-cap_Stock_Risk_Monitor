# -*- coding: utf-8 -*-
"""TsClient：重试/权限分类/字段断言。"""
from __future__ import annotations

import pandas as pd
import pytest

from wp import config as C
from wp.checks import SchemaError
from wp.ts_client import TsClient, TsError, TsParamError, TsPermissionError


class DummyPro:
    def __init__(self, failures: int = 0, exc: Exception | None = None, df: pd.DataFrame | None = None) -> None:
        self.failures = failures
        self.exc = exc
        self.calls = 0
        self.df = df if df is not None else pd.DataFrame({"ts_code": ["000001.SZ"]})

    def query(self, api: str, **kwargs):  # noqa: ANN001
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        if self.calls <= self.failures:
            raise TimeoutError("timeout")
        return self.df


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch) -> None:
    monkeypatch.setattr(C, "API_BACKOFF", (0.0, 0.0, 0.0))


def make_client(pro: DummyPro, retries: int = 2) -> TsClient:
    c = TsClient(token="x", min_interval=0.0, max_retries=retries)
    c._pro = pro
    return c


def test_retry_then_success() -> None:
    pro = DummyPro(failures=2)
    c = make_client(pro)
    out = c.call("daily", trade_date="20261016")
    assert len(out) == 1
    assert pro.calls == 3
    assert c.stats()["calls"]["daily"] == 1
    assert c.stats()["attempts"]["daily"] == 3


def test_retry_exhausted() -> None:
    pro = DummyPro(exc=TimeoutError("timeout"))
    c = make_client(pro, retries=1)
    with pytest.raises(TsError):
        c.call("daily")
    assert pro.calls == 2


def test_permission_not_retried() -> None:
    pro = DummyPro(exc=Exception("抱歉，您没有接口(daily)访问权限"))
    c = make_client(pro, retries=3)
    with pytest.raises(TsPermissionError):
        c.call("daily")
    assert pro.calls == 1


def test_param_not_retried() -> None:
    pro = DummyPro(exc=Exception("参数错误"))
    c = make_client(pro, retries=3)
    with pytest.raises(TsParamError):
        c.call("daily")
    assert pro.calls == 1


def test_schema_error() -> None:
    pro = DummyPro()
    c = make_client(pro)
    with pytest.raises(SchemaError):
        c.df("daily", expected=["close"])


def test_missing_token(monkeypatch) -> None:
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(TsError):
        TsClient(token=None)
