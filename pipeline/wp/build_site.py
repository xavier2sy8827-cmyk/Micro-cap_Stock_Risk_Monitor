# -*- coding: utf-8 -*-
"""metrics.csv -> 前端 JSON（按页拆分）。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from wp import config as C


def _num(v, digits: int = 6):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        return None
    return round(float(v), digits)


def _arr(s: pd.Series, digits: int = 6) -> list:
    return [_num(v, digits) for v in s.tolist()]


def _col(m: pd.DataFrame, name: str) -> pd.Series:
    return m[name] if name in m.columns else pd.Series(np.nan, index=m.index, dtype=float)


def _last_valid(s: pd.Series):
    s = s.dropna()
    return s.iloc[-1] if len(s) else None


def _last_date(s: pd.Series, dates: pd.Series):
    ok = s.notna()
    return str(dates[ok].iloc[-1]) if ok.any() else None


def _level(key: str, pct, z=None) -> str:
    if key == "margin_pool_ratio":
        if z is not None and pd.notna(z):
            if z >= 2:
                return "warn"
            if z <= -2:
                return "cold"
        return "normal"
    if pct is None or pd.isna(pct):
        return "normal"
    if key == "breadth10":
        return "cold" if pct <= 20 else ("hot" if pct >= 80 else "normal")
    if key == "pb_spread":
        return "danger" if pct >= 90 else ("warn" if pct >= 80 else "normal")
    if key == "corr60_wp400":
        return "warn" if pct >= 85 else "normal"
    if key == "ls_vol_ratio":
        return "warn" if pct >= 90 else "normal"
    return "normal"


def _signal(key: str, label: str, m: pd.DataFrame, dates: pd.Series, value_col: str, pct_col: str | None,
            unit: str = "", z_col: str | None = None) -> dict:
    value = _last_valid(m[value_col]) if value_col in m else None
    pct = _last_valid(m[pct_col]) if pct_col and pct_col in m else None
    z = _last_valid(m[z_col]) if z_col and z_col in m else None
    asof = _last_date(m[value_col], dates) if value_col in m else None
    return {
        "key": key,
        "label": label,
        "value": _num(value),
        "pct": _num(pct),
        "z": _num(z),
        "unit": unit,
        "level": _level(key, pct, z),
        "asof": asof,
    }


def build(data_dir: str | Path, out_dir: str | Path) -> dict:
    src = Path(data_dir)
    m = pd.read_csv(src / "metrics.csv", dtype={"date": str}).sort_values("date").reset_index(drop=True)
    ind = pd.read_csv(src / "industry_breadth.csv", dtype={"date": str})
    meta_src = json.loads((src / "meta.json").read_text(encoding="utf-8")) if (src / "meta.json").exists() else {}
    dates = m["date"].astype(str)

    last = m.iloc[-1]
    margin_through = _last_date(_col(m, "margin_pool_ratio"), dates)
    meta = {
        "schema_version": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_through": str(last["date"]),
        "margin_through": margin_through,
        "factor_ic_through": None,
        "industry_version": "SW2021" if str(last["date"]) >= C.INDUSTRY_SWITCH_DATE else "SW2014",
        "warnings": meta_src.get("warnings", []),
        "pipeline_version": meta_src.get("pipeline_version", C.PIPELINE_VERSION),
        "days": int(len(m)),
        "calls": meta_src.get("calls", {}),
        "duration_sec": meta_src.get("duration_sec"),
    }

    signals = [
        _signal("breadth10", "微盘400 宽度分位", m, dates, "breadth10", "breadth10_pct", "%"),
        _signal("pb_spread", "PB 价差分位", m, dates, "pb_spread", "pb_spread_pct", "倍"),
        _signal("corr60_wp400", "截面相关分位", m, dates, "corr60_wp400", "corr60_wp400_pct", ""),
        _signal("ls_vol_ratio", "多空波动比分位", m, dates, "ls_vol_ratio", "ls_vol_ratio_pct", ""),
        _signal("qs_share", "小成交额∩高换手占比", m, dates, "qs_share", "qs_share_pct", "%"),
        _signal("margin_pool_ratio", "两融池占比", m, dates, "margin_pool_ratio", None, "%", "margin_pool_ratio_z"),
    ]
    spark_n = min(30, len(m))
    spark = {
        "dates": dates.tail(spark_n).tolist(),
        "series": [
            {"key": "breadth10", "values": _arr(m["breadth10"].tail(spark_n))},
            {"key": "pb_spread", "values": _arr(m["pb_spread"].tail(spark_n))},
            {"key": "corr60_wp400", "values": _arr(m["corr60_wp400"].tail(spark_n))},
            {"key": "ls_vol_ratio", "values": _arr(m["ls_vol_ratio"].tail(spark_n))},
            {"key": "qs_share", "values": _arr(m["qs_share"].tail(spark_n))},
        ],
    }

    crowding = {
        "dates": dates.tolist(),
        "breadth10": {
            "v": _arr(m["breadth10"]),
            "pct": _arr(m["breadth10_pct"]),
            "pct_exp": _arr(m["breadth10_pct_exp"]),
        },
        "wp400_index": _arr(m["wp400_index"], 3),
        "pb_spread": {
            "v": _arr(m["pb_spread"]),
            "pct": _arr(m["pb_spread_pct"]),
            "pct_exp": _arr(m["pb_spread_pct_exp"]),
        },
        "corr60_wp400": {
            "v": _arr(m["corr60_wp400"]),
            "pct": _arr(m["corr60_wp400_pct"]),
            "pct_exp": _arr(m["corr60_wp400_pct_exp"]),
        },
        "ls_vol_ratio": {
            "v": _arr(m["ls_vol_ratio"]),
            "pct": _arr(m["ls_vol_ratio_pct"]),
            "pct_exp": _arr(m["ls_vol_ratio_pct_exp"]),
        },
        "qs": {
            "v": _arr(m["qs_share"]),
            "pct": _arr(m["qs_share_pct"]),
            "pct_exp": _arr(m["qs_share_pct_exp"]),
            "subset_n": _arr(m["qs_subset_n"], 0),
            "valid_n": _arr(m["qs_valid_n"], 0),
            "abs": _arr(m["qs_share_abs"]),
        },
    }

    ind_names = sorted(ind["industry"].dropna().unique().tolist()) if not ind.empty else []
    ind_pivot = (
        ind.pivot_table(index="date", columns="industry", values="breadth", aggfunc="last")
        .reindex(columns=ind_names)
        .reindex(dates)
        if not ind.empty
        else pd.DataFrame(index=dates, columns=ind_names)
    )
    alla = {
        "dates": dates.tolist(),
        "industries": {"names": ind_names, "matrix": [_arr(ind_pivot[n]) for n in ind_names]},
        "s_width": _arr(m["s_width"], 3),
        "s_width_pct": _arr(m["s_width_pct"], 3),
        "n_industries": _arr(m["n_industries"], 0),
        "top5": {"v": _arr(m["ratio_top5"]), "pct": _arr(m["ratio_top5_pct"])},
        "top10": {"v": _arr(m["ratio_top10"]), "pct": _arr(m["ratio_top10_pct"])},
        "five_layer": {
            "names": ["300", "500", "1000", "2000", "wp400"],
            "money": {n: _arr(m[f"money_{n}"], 3) for n in ("300", "500", "1000", "2000", "wp400")},
            "share": {n: _arr(m[f"share_{n}"]) for n in ("300", "500", "1000", "2000", "wp400")},
            "share_pct": {n: _arr(m[f"share_{n}_pct"]) for n in ("300", "500", "1000", "2000", "wp400")},
            "ret_ma5": {n: _arr(m[f"ret_ma5_{n}"]) for n in ("300", "500", "1000", "2000", "wp400")},
        },
    }

    layers = {
        "dates": dates.tolist(),
        "layers": [
            {
                "key": f"L{i}",
                "breadth": _arr(m[f"breadth_L{i}"]),
                "pct": _arr(m[f"breadth_L{i}_pct"]),
                "ret_ma5": _arr(m[f"ret_ma5_L{i}"]),
                "n_valid": _arr(m[f"n_valid_L{i}"], 0),
            }
            for i in range(1, 11)
        ],
    }

    margin = {
        "dates": dates.tolist(),
        "through": margin_through,
        "ratio": _arr(_col(m, "margin_pool_ratio")),
        "ratio_z": _arr(_col(m, "margin_pool_ratio_z")),
        "buy_ratio": _arr(_col(m, "margin_pool_buy_ratio")),
        "n": _arr(_col(m, "margin_pool_n"), 0),
        "wp400_ratio": _arr(_col(m, "margin_wp400_ratio")),
        "wp400_n": _arr(_col(m, "margin_wp400_n"), 0),
    }

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payloads = {
        "meta.json": meta,
        "overview.json": {"signals": signals, "spark": spark},
        "crowding.json": crowding,
        "alla.json": alla,
        "layers.json": layers,
        "margin.json": margin,
        "factors.json": {"dates": dates.tolist(), "stub": True},
    }
    for name, obj in payloads.items():
        (out / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return meta
