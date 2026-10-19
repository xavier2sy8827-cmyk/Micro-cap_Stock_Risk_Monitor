# -*- coding: utf-8 -*-
"""因子四态与 R 二次确认的最小单测。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from wp.factors import _confirm_r, compute_states


def test_states_tail_is_masked() -> None:
    idx = pd.bdate_range("2023-01-02", periods=320)
    rng = np.random.default_rng(0)
    ic = pd.Series(rng.normal(0.02, 0.05, len(idx)), index=idx)
    ic.iloc[-20:] = np.nan
    ls = pd.Series(rng.normal(0.0, 0.01, len(idx)), index=idx)
    out, _ = compute_states(ic, ls)
    assert out["judge_nan"].iloc[-20:].eq(1).all()
    # 尾部 IC 为空，不能显示为健康
    assert out.loc[idx[-1], "judge_nan"] == 1


def test_confirm_r_requires_second_hit() -> None:
    idx = pd.bdate_range("2024-01-02", periods=30)
    raw = pd.Series(False, index=idx)
    raw.iloc[5] = True
    raw.iloc[8] = True
    nav = pd.Series(np.linspace(0, 1, len(idx)), index=idx)
    dd = nav - nav.cummax()
    sigma = pd.Series(0.01, index=idx)

    r, events = _confirm_r(raw, nav, dd, sigma)
    assert r.iloc[8] >= 1
    assert any(e["confirmed"] for e in events)

    raw2 = pd.Series(False, index=idx)
    raw2.iloc[5] = True
    r2, events2 = _confirm_r(raw2, nav, dd, sigma)
    assert not r2.any()
    assert events2 and not events2[0]["confirmed"]
