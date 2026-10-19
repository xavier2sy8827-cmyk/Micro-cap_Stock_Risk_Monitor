# -*- coding: utf-8 -*-
"""修补全量 INIT 中 2026-05-25~06-17 的 QFQ 数据缺口。

现象：该 18 个交易日的 qfq 相关指标（breadth/层宽度/行业宽度/corr/ret_ma5）为空，
但 close/成交额/两融正常。用后来补抓的 132 日切片回填同一交易日，并重算分位、
wp400_index、因子 IC 缺口与四态。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wp import series as S  # noqa: E402
from wp.checks import read_csv, write_csv  # noqa: E402
from wp.daily import _merge_factors, _recompute_pct  # noqa: E402

GAP_START = "2026-05-25"
GAP_END = "2026-06-17"

SAME_DAY = [
    "breadth10", "n_valid10", "n_pool", "n_pool_circ", "wp400_ret",
    "ratio_top5", "ratio_top10", "all_money",
    "money_300", "money_500", "money_1000", "money_2000", "money_wp400",
    "share_300", "share_500", "share_1000", "share_2000", "share_wp400",
    "pb_small_med", "pb_large_med", "pb_spread",
    "qs_share", "qs_subset_n", "qs_valid_n", "qs_share_abs",
    "margin_mkt_rzye", "margin_mkt_rzmre", "margin_pool_n", "margin_pool_rzye",
    "margin_pool_rzmre", "margin_wp400_n", "margin_wp400_rzye",
    "margin_pool_ratio", "margin_pool_buy_ratio", "margin_wp400_ratio",
    "s_width", "n_industries", "ls_vol_ratio",
    "ret_ma5_300", "ret_ma5_500", "ret_ma5_1000", "ret_ma5_2000", "ret_ma5_wp400",
]
for _i in range(1, 11):
    SAME_DAY += [f"breadth_L{_i}", f"n_valid_L{_i}", f"ret_ma5_L{_i}"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", required=True)
    ap.add_argument("--fresh", required=True)
    ap.add_argument("--two-year", required=True, help="2 年切片，用于 corr60")
    args = ap.parse_args()
    full, fresh, two = Path(args.full), Path(args.fresh), Path(args.two_year)

    m = read_csv(full / "metrics.csv", dtype={"date": str})
    f = read_csv(fresh / "metrics.csv", dtype={"date": str})
    y = read_csv(two / "metrics.csv", dtype={"date": str})
    gap = [d for d in m["date"] if GAP_START <= d <= GAP_END]
    print(f"[patch] gap days={len(gap)}")

    fmap = f.set_index("date")
    ymap = y.set_index("date")
    cols = [c for c in SAME_DAY if c in m.columns and c in f.columns]
    for d in gap:
        if d not in fmap.index:
            raise SystemExit(f"fresh 缺少 {d}")
        m.loc[m["date"] == d, cols] = fmap.loc[d, cols].to_numpy()
    # corr60 需要 60 日窗口，fresh 起点不够；用 2 年切片覆盖缺口及其后 60 日。
    for d in [x for x in m["date"] if GAP_START <= x <= "2026-08-14"]:
        if d in ymap.index and "corr60_wp400" in ymap.columns:
            m.loc[m["date"] == d, "corr60_wp400"] = ymap.loc[d, "corr60_wp400"]

    m = _recompute_pct(m)
    m["wp400_index"] = S.equal_weight_index(m["wp400_ret"])
    m["s_width_pct"] = m["s_width"] / m["n_industries"]
    write_csv(m, full / "metrics.csv")
    print("[patch] metrics rewritten")

    ind = read_csv(full / "industry_breadth.csv", dtype={"date": str})
    ind_f = read_csv(fresh / "industry_breadth.csv", dtype={"date": str})
    ind_f = ind_f[(ind_f["date"] >= GAP_START) & (ind_f["date"] <= GAP_END)]
    ind = pd.concat([ind[~ind["date"].isin(set(ind_f["date"]))], ind_f], ignore_index=True)
    write_csv(ind.sort_values(["date", "industry"]), full / "industry_breadth.csv")
    print(f"[patch] industry rows={len(ind)}")

    fic = read_csv(full / "factor_ic.csv", dtype={"date": str})
    fic_f = read_csv(fresh / "factor_ic.csv", dtype={"date": str})
    old = fic.set_index(["date", "factor"])
    new = fic_f.set_index(["date", "factor"])
    comb = new.combine_first(old.loc[new.index])
    new_ic = comb.reset_index()
    meta = _merge_factors(full, new_ic, pd.DataFrame())
    print(f"[patch] factors ic_through={meta.get('factor_ic_through')}")

    report = {
        "gap_days": len(gap),
        "breadth_2026-05-25": float(m.loc[m["date"] == "2026-05-25", "breadth10"].iloc[0]),
        "corr_2026-05-25": float(m.loc[m["date"] == "2026-05-25", "corr60_wp400"].iloc[0]),
        "factor_ic_through": meta.get("factor_ic_through"),
    }
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
