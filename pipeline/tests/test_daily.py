# -*- coding: utf-8 -*-
"""daily 合并：历史行不重写、两融回填后重算 z。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from wp.daily import _merge_metrics


def test_daily_append_only_and_margin_z() -> None:
    idx = pd.bdate_range("2026-01-02", periods=40)
    dates = [d.strftime("%Y-%m-%d") for d in idx]
    hist = pd.DataFrame(
        {
            "date": dates,
            "margin_pool_ratio": np.linspace(1.0, 2.0, 40),
            "margin_pool_ratio_z": np.zeros(40),
            "breadth10": np.arange(40, dtype=float),
            "wp400_ret": np.full(40, 0.001),
            "wp400_index": np.cumprod(np.full(40, 1.001)) * 1000.0,
        }
    )
    new = hist.copy()
    new["breadth10"] = 999.0  # 历史行不允许被窗口值覆盖
    new.loc[new.index[-1], "margin_pool_ratio"] = 3.0  # 两融 T-1 回填
    out = _merge_metrics(hist, new)

    assert out["breadth10"].iloc[-2] == 38.0
    assert out["margin_pool_ratio"].iloc[-1] == 3.0
    assert out["margin_pool_ratio_z"].iloc[-1] != 0.0
