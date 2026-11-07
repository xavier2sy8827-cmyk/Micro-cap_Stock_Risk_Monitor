# -*- coding: utf-8 -*-
"""涨停情绪：连板/晋级/断板/过滤/缺失/摘要与失败隔离。"""
from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd

from wp.build_site import _build_limit_sentiment
from wp.checks import write_csv
from wp.daily import _refresh_limit_sentiment
from wp.limit_sentiment import (
    _merge_events,
    _merge_metrics,
    compute_limit_sentiment,
    render_summary,
    write_limit_sentiment_failure,
)

DAYS = ["20240102", "20240103", "20240104", "20240105"]
CODES = ["000001.SZ", "000002.SZ", "300001.SZ", "000004.SZ"]
IDX = pd.to_datetime(DAYS)


def _matrix(value: float = 9.0) -> pd.DataFrame:
    return pd.DataFrame(value, index=IDX, columns=CODES, dtype=float)


def make_slice() -> SimpleNamespace:
    close = _matrix()
    openp = _matrix()
    high = _matrix()
    low = _matrix()
    pre = _matrix()
    # 第1天：A/创业/ST 首板；第2天：A 二板、B 首板、创业炸板。
    close.loc[IDX[0], ["000001.SZ", "300001.SZ", "000004.SZ"]] = 10.0
    high.loc[IDX[0], ["000001.SZ", "300001.SZ", "000004.SZ"]] = 10.0
    close.loc[IDX[1], ["000001.SZ", "000002.SZ", "000004.SZ"]] = 10.0
    high.loc[IDX[1], ["000001.SZ", "000002.SZ", "000004.SZ", "300001.SZ"]] = 10.0
    close.loc[IDX[1], "300001.SZ"] = 9.5
    # 第3天：A 断板且炸板、B 二板、创业首板、ST 跌停（ST 不纳入统计）。
    close.loc[IDX[2], "000001.SZ"] = 9.7
    high.loc[IDX[2], "000001.SZ"] = 10.0
    close.loc[IDX[2], ["000002.SZ", "300001.SZ"]] = 10.0
    high.loc[IDX[2], ["000002.SZ", "300001.SZ"]] = 10.0
    close.loc[IDX[2], "000004.SZ"] = 8.0
    low.loc[IDX[2], "000004.SZ"] = 8.0
    # 第4天：B 断板未触板、创业二板。
    close.loc[IDX[3], "000002.SZ"] = 9.8
    close.loc[IDX[3], "300001.SZ"] = 10.0
    high.loc[IDX[3], "300001.SZ"] = 10.0
    for i in range(1, len(DAYS)):
        pre.iloc[i] = close.iloc[i - 1]
    basic = pd.DataFrame(
        {
            "ts_code": CODES,
            "name": ["A", "B", "G", "ST"],
            "market": ["主板", "主板", "创业板", "主板"],
            "list_date": ["20000101"] * 4,
            "delist_date": [None] * 4,
        }
    )
    pools = {day: CODES[:3] for day in DAYS}
    return SimpleNamespace(
        days=DAYS,
        close=close,
        pre_close=pre,
        open=openp,
        high=high,
        low=low,
        stock_basic=basic,
        pools_total=pools,
    )


def make_inputs():
    frames = {}
    for day in DAYS:
        frames[day] = pd.DataFrame(
            {
                "ts_code": CODES,
                "trade_date": [day] * 4,
                "pre_close": [9.0] * 4,
                "up_limit": [10.0] * 4,
                "down_limit": [8.0] * 4,
            }
        )
    st = {day: pd.DataFrame({"ts_code": ["000004.SZ"]}) for day in DAYS}
    nc = pd.DataFrame(columns=["ts_code", "name", "start_date", "end_date", "change_reason"])
    return frames, st, nc


def test_height_width_promotion_broken_and_universe() -> None:
    frames, st, nc = make_inputs()
    metrics, events = compute_limit_sentiment(make_slice(), frames, st, nc)
    row = metrics[(metrics["date"] == "2024-01-04") & (metrics["universe"] == "main")].iloc[0]
    assert row["max_height"] == 2
    assert row["width_1"] == 0
    assert row["width_2"] == 1
    assert row["promote_1_2"] == 100.0
    assert row["promote_2_3"] == 0.0
    assert np.isclose(row["broken_close_mean"], -3.0)
    assert np.isclose(row["broken_multi_close_mean"], -3.0)
    assert np.isnan(row["broken_first_close_mean"])
    assert np.isclose(row["prev_limit_close_mean"], -1.5)
    assert row["failed_rate"] == 50.0
    assert row["limit_down_n"] == 0  # ST 跌停不得混入主板口径
    wp_row = metrics[(metrics["date"] == "2024-01-04") & (metrics["universe"] == "wp400")].iloc[0]
    assert np.isnan(wp_row["max_height"])  # 现有池不足 400 只时不伪造微盘400指标

    day2 = metrics[(metrics["date"] == "2024-01-03") & (metrics["universe"] == "main")].iloc[0]
    assert day2["width_1"] == 1
    assert day2["width_2"] == 1
    assert day2["promote_1_2"] == 100.0
    assert np.isnan(day2["promote_2_3"])

    day4 = metrics[(metrics["date"] == "2024-01-05") & (metrics["universe"] == "main")].iloc[0]
    assert day4["broken_n"] == 1
    assert np.isclose(day4["broken_close_mean"], -2.0)
    assert np.isclose(day4["broken_multi_close_mean"], -2.0)
    assert np.isnan(day4["broken_first_close_mean"])
    assert day4["failed_n"] == 0

    day3_events = events[events["date"].eq("2024-01-04")]
    assert set(day3_events["ts_code"]) == set(CODES[:3])
    a = day3_events[day3_events["ts_code"].eq("000001.SZ")].iloc[0]
    assert bool(a["is_failed_proxy"]) and bool(a["is_broken"])
    assert a["prev_streak"] == 2


def test_missing_limit_day_is_nan_and_breaks_streak() -> None:
    frames, st, nc = make_inputs()
    frames["20240103"] = pd.DataFrame()
    metrics, _ = compute_limit_sentiment(make_slice(), frames, st, nc)
    missing = metrics[(metrics["date"] == "2024-01-03") & (metrics["universe"] == "main")].iloc[0]
    assert np.isnan(missing["max_height"])
    assert np.isnan(missing["width_1"])
    following = metrics[(metrics["date"] == "2024-01-04") & (metrics["universe"] == "main")].iloc[0]
    assert np.isnan(following["promote_1_2_den"])
    assert np.isnan(following["prev_limit_n"])
    assert np.isnan(following["broken_n"])
    assert np.isnan(following["broken_return_n"])
    assert np.isnan(following["prev_limit_suspended_n"])
    assert following["width_2"] == 0  # 缺失日不得隐式延续连板


def test_merge_is_idempotent_and_summary_has_three_universes() -> None:
    frames, st, nc = make_inputs()
    metrics, _ = compute_limit_sentiment(make_slice(), frames, st, nc)
    merged = _merge_metrics(metrics, metrics)
    assert len(merged) == len(metrics)
    assert not merged.duplicated(["date", "universe"]).any()
    text = render_summary(merged, "20240105", "完整", {"U": 2, "Z": 1, "D": 0})
    assert text.startswith("## 涨停情绪监控")
    assert all(name in text for name in ("主板", "微盘400", "创业板"))
    assert "仅展示盘后事实，不构成离场建议" in text


def test_failure_summary_redacts_token(tmp_path) -> None:
    write_limit_sentiment_failure(tmp_path, "20240105", RuntimeError("bad secret-token"), "secret-token")
    text = (tmp_path / "limit_sentiment_summary.md").read_text(encoding="utf-8")
    assert "核心：失败" in text
    assert "secret-token" not in text
    assert "[REDACTED]" in text


def test_daily_guard_does_not_raise(tmp_path, monkeypatch) -> None:
    def fail(client, sl, data_dir):  # noqa: ANN001
        raise RuntimeError("monitor unavailable")

    monkeypatch.setattr("wp.daily.update_limit_sentiment", fail)
    client = SimpleNamespace(token="x")
    out = _refresh_limit_sentiment(client, SimpleNamespace(), tmp_path, "2024-01-05")
    assert out["status"] == "error"
    assert (tmp_path / "limit_sentiment_summary.md").exists()


def test_window_shift_does_not_rewrite_history() -> None:
    frames, st, nc = make_inputs()
    original_metrics, original_events = compute_limit_sentiment(make_slice(), frames, st, nc)

    full = make_slice()
    later = SimpleNamespace(**vars(full))
    later.days = DAYS[1:]
    for field in ("close", "pre_close", "open", "high", "low"):
        setattr(later, field, getattr(full, field).iloc[1:].copy())
    later_frames = {day: frames[day] for day in DAYS[1:]}
    later_st = {day: st[day] for day in DAYS[1:]}
    later_metrics, later_events = compute_limit_sentiment(later, later_frames, later_st, nc)

    merged = _merge_metrics(original_metrics, later_metrics, run_day=DAYS[-1])
    old = original_metrics[(original_metrics["date"] == "2024-01-04") & (original_metrics["universe"] == "main")].iloc[0]
    kept = merged[(merged["date"] == "2024-01-04") & (merged["universe"] == "main")].iloc[0]
    assert kept["max_height"] == old["max_height"] == 2
    assert kept["promote_1_2"] == old["promote_1_2"] == 100.0
    assert kept["broken_n"] == old["broken_n"] == 1

    merged_events = _merge_events(original_events, later_events, run_day=DAYS[-1])
    a = merged_events[(merged_events["date"] == "2024-01-04") & (merged_events["ts_code"] == "000001.SZ")].iloc[0]
    assert bool(a["is_broken"])
    assert a["prev_streak"] == 2


def test_wp400_is_not_filtered_again_when_member_becomes_st() -> None:
    frames, st, nc = make_inputs()
    sl = make_slice()
    sl.pools_total = {day: CODES + ["MISSING"] * 396 for day in DAYS}
    metrics, _ = compute_limit_sentiment(sl, frames, st, nc)
    row = metrics[(metrics["date"] == "2024-01-03") & (metrics["universe"] == "wp400")].iloc[0]
    assert row["max_height"] == 2
    assert row["limit_up_n"] == 3  # 当日新 ST 的既有池成员仍属当日池，不做二次过滤


def test_one_word_height_and_suspended_cohort() -> None:
    frames, st, nc = make_inputs()
    sl = make_slice()
    sl.open.loc[IDX[1], "000001.SZ"] = 10.0
    sl.high.loc[IDX[1], "000001.SZ"] = 10.0
    sl.low.loc[IDX[1], "000001.SZ"] = 10.0
    metrics, _ = compute_limit_sentiment(sl, frames, st, nc)
    row = metrics[(metrics["date"] == "2024-01-03") & (metrics["universe"] == "main")].iloc[0]
    assert row["max_height"] == 2
    assert row["max_height_non_one_word"] == 1

    sl.close.loc[IDX[2], "000001.SZ"] = np.nan
    metrics, _ = compute_limit_sentiment(sl, frames, st, nc)
    suspended = metrics[(metrics["date"] == "2024-01-04") & (metrics["universe"] == "main")].iloc[0]
    assert suspended["broken_n"] == 1
    assert suspended["broken_return_n"] == 0
    assert suspended["prev_limit_suspended_n"] == 1


def test_build_limit_sentiment_json_and_empty_stub(tmp_path) -> None:
    assert _build_limit_sentiment(tmp_path) == {
        "dates": [], "through": None, "latest": [], "height": {}, "height_pct": {}
    }
    frames, st, nc = make_inputs()
    metrics, _ = compute_limit_sentiment(make_slice(), frames, st, nc)
    metrics = _merge_metrics(pd.DataFrame(), metrics, run_day=DAYS[-1])
    write_csv(metrics, tmp_path / "limit_sentiment.csv")
    out = _build_limit_sentiment(tmp_path)
    assert out["through"] == "2024-01-05"
    assert len(out["dates"]) == len(DAYS)
    assert len(out["latest"]) == 3
    main = next(row for row in out["latest"] if row["universe"] == "main")
    assert main["max_height"] == 0.0
    assert main["broken_close_mean"] is not None
    assert out["height"]["main"][-1] == 0.0
    json.dumps(out, ensure_ascii=False, allow_nan=False)
