# -*- coding: utf-8 -*-
"""盘后涨停情绪监控：复用现有 Slice 行情与 total400 池，独立落盘、独立展示。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from wp import config as C
from wp import series as S
from wp.checks import read_csv, write_csv
from wp.dataset import Slice, _effective_names, load_slice
from wp.ts_client import TsClient, to_dash

UNIVERSES = ("main", "wp400", "gem")
UNIVERSE_NAMES = {"main": "主板", "wp400": "微盘400", "gem": "创业板"}
SUMMARY_FILENAME = "limit_sentiment_summary.md"
METRICS_FILENAME = "limit_sentiment.csv"
EVENTS_FILENAME = "limit_sentiment_events.csv"
EVENT_COLUMNS = [
    "date", "ts_code", "universes", "streak", "prev_streak", "is_limit_up", "is_failed_proxy",
    "is_limit_down", "is_broken", "was_limit_up", "is_one_word", "open_ret", "close_ret",
]

_VALUE_COLUMNS = [
    "max_height", "max_height_n", "max_height_non_one_word", "width_1", "width_2", "width_3",
    "width_4", "width_5p", "limit_up_n", "promote_1_2", "promote_1_2_num", "promote_1_2_den",
    "promote_2_3", "promote_2_3_num", "promote_2_3_den", "promote_3p", "promote_3p_num",
    "promote_3p_den", "broken_open_mean", "broken_open_median", "broken_close_mean",
    "broken_close_median", "broken_first_close_mean", "broken_multi_close_mean", "broken_loss_pct",
    "broken_n", "broken_return_n", "prev_limit_open_mean", "prev_limit_open_median",
    "prev_limit_close_mean", "prev_limit_close_median", "prev_limit_red_pct", "prev_limit_n",
    "prev_limit_suspended_n", "failed_rate", "failed_n", "touch_n", "limit_down_n",
]


def _wide(frames: dict[str, pd.DataFrame], value: str, days: list[str], columns: pd.Index) -> pd.DataFrame:
    valid = [df for df in frames.values() if df is not None and not df.empty]
    if not valid:
        return pd.DataFrame(np.nan, index=pd.to_datetime(days), columns=columns)
    raw = pd.concat(valid, ignore_index=True)
    return S.reindex_days(S.pivot(raw, value), days).reindex(columns=columns)


def _price_eq(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    valid = left.notna() & right.notna()
    close = np.isclose(left.to_numpy(dtype=float), right.to_numpy(dtype=float), rtol=0.0, atol=0.001)
    return pd.DataFrame(close & valid.to_numpy(), index=left.index, columns=left.columns)


def _limit_streak(limit_up: pd.DataFrame) -> pd.DataFrame:
    flags = limit_up.to_numpy(dtype=bool)
    out = np.zeros(flags.shape, dtype=int)
    for i in range(len(flags)):
        if i:
            out[i] = np.where(flags[i], out[i - 1] + 1, 0)
        else:
            out[i] = np.where(flags[i], 1, 0)
    return pd.DataFrame(out, index=limit_up.index, columns=limit_up.columns)


def _ratio(num: int, den: int) -> float:
    return float(num * 100.0 / den) if den else np.nan


def _return_stats(values: pd.Series, prefix: str, row: dict) -> None:
    values = pd.to_numeric(values, errors="coerce").dropna()
    row[f"{prefix}_mean"] = float(values.mean()) if len(values) else np.nan
    row[f"{prefix}_median"] = float(values.median()) if len(values) else np.nan


def _namechange_frames(client: TsClient, days: list[str]) -> pd.DataFrame:
    start_year = int(days[0][:4])
    end_year = int(days[-1][:4])
    frames = [
        client.namechange(f"{year}0101", f"{year}1231")
        for year in range(start_year - 1, end_year + 1)
    ]
    frames = [df for df in frames if df is not None and not df.empty]
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame(columns=C.FIELDS["namechange"])


def _build_universes(
    sl: Slice,
    up_limit: pd.DataFrame,
    st_frames: dict[str, pd.DataFrame],
    namechange: pd.DataFrame,
) -> dict[str, dict[str, list[str]]]:
    sb = sl.stock_basic.drop_duplicates("ts_code", keep="last").set_index("ts_code")
    list_dt = pd.to_datetime(sb["list_date"], format="%Y%m%d", errors="coerce")
    delist_dt = pd.to_datetime(sb["delist_date"], format="%Y%m%d", errors="coerce")
    out: dict[str, dict[str, list[str]]] = {key: {} for key in UNIVERSES}
    for day, dt in zip(sl.days, up_limit.index):
        st_df = st_frames.get(day)
        st_set = set(st_df["ts_code"].astype(str)) if st_df is not None and not st_df.empty else set()
        _, delisting = _effective_names(namechange, day)
        for key in UNIVERSES:
            if key == "wp400":
                candidates = list(sl.pools_total.get(day, []))
            else:
                market = "主板" if key == "main" else "创业板"
                candidates = sb.index[sb["market"].eq(market)].tolist()
            codes = []
            for code in candidates:
                if code not in sl.close.columns:
                    continue
                if key != "wp400":
                    if code in st_set or code in delisting:
                        continue
                    if str(code).endswith(C.EXCLUDE_SUFFIXES) or str(code).startswith(C.EXCLUDE_PREFIXES):
                        continue
                    if pd.isna(list_dt.get(code)) or list_dt[code] > dt - pd.Timedelta(days=C.MIN_LIST_DAYS):
                        continue
                    if pd.notna(delist_dt.get(code)) and delist_dt[code] <= dt:
                        continue
                    limit = up_limit.at[dt, code]
                    if pd.isna(limit) or limit <= 0:
                        continue
                codes.append(code)
            out[key][day] = codes
    return out


def compute_limit_sentiment(
    sl: Slice,
    limit_frames: dict[str, pd.DataFrame],
    st_frames: dict[str, pd.DataFrame],
    namechange: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """纯计算：收益率字段均为百分数，无候选时分母和比例记 NaN。"""
    days = sl.days
    columns = sl.close.columns
    up_limit = _wide(limit_frames, "up_limit", days, columns)
    down_limit = _wide(limit_frames, "down_limit", days, columns)
    limit_up = _price_eq(sl.close, up_limit)
    touched = _price_eq(sl.high, up_limit)
    limit_down = _price_eq(sl.close, down_limit)
    one_word = (
        limit_up
        & _price_eq(sl.open, up_limit)
        & _price_eq(sl.high, up_limit)
        & _price_eq(sl.low, up_limit)
    )
    streak = _limit_streak(limit_up)
    open_ret = (sl.open / sl.pre_close - 1.0) * 100.0
    close_ret = (sl.close / sl.pre_close - 1.0) * 100.0
    universes = _build_universes(sl, up_limit, st_frames, namechange)
    available = {day for day, df in limit_frames.items() if df is not None and not df.empty}

    metric_rows: list[dict] = []
    event_rows: list[dict] = []
    for i, (day, dt) in enumerate(zip(days, up_limit.index)):
        prev = days[i - 1] if i else None
        day_available = day in available
        prev_available = prev in available if prev else False
        current_membership: dict[str, list[str]] = {}
        previous_limit: set[str] = set()
        broken_all: set[str] = set()
        for universe in UNIVERSES:
            codes = universes[universe].get(day, [])
            current_membership[universe] = codes
            prev_codes = universes[universe].get(prev, []) if prev else []
            prev_up = []
            # 前一交易日按交易日序列取值，不能用自然日减一。
            if prev and prev_available:
                prev_dt = up_limit.index[i - 1]
                prev_up = [c for c in prev_codes if bool(limit_up.at[prev_dt, c])]
            previous_limit.update(prev_up)
            row = {"date": to_dash(day), "universe": universe}
            row.update({col: np.nan for col in _VALUE_COLUMNS})
            pool_ready = universe != "wp400" or len(sl.pools_total.get(day, [])) == C.POOL_TOTAL_N
            if day_available and pool_ready:
                up_codes = [c for c in codes if bool(limit_up.at[dt, c])]
                touch_codes = [c for c in codes if bool(touched.at[dt, c])]
                failed_codes = [c for c in touch_codes if c not in set(up_codes)]
                heights = [int(streak.at[dt, c]) for c in up_codes]
                max_height = max(heights, default=0)
                non_one = [int(streak.at[dt, c]) for c in up_codes if not bool(one_word.at[dt, c])]
                broken = [c for c in prev_up if not bool(limit_up.at[dt, c])]
                broken_all.update(broken)
                row.update(
                    {
                        "max_height": max_height,
                        "max_height_n": heights.count(max_height) if max_height else 0,
                        "max_height_non_one_word": max(non_one, default=0),
                        "width_1": heights.count(1),
                        "width_2": heights.count(2),
                        "width_3": heights.count(3),
                        "width_4": heights.count(4),
                        "width_5p": sum(h >= 5 for h in heights),
                        "limit_up_n": len(up_codes),
                        "failed_rate": _ratio(len(failed_codes), len(touch_codes)),
                        "failed_n": len(failed_codes),
                        "touch_n": len(touch_codes),
                        "limit_down_n": sum(bool(limit_down.at[dt, c]) for c in codes),
                    }
                )
                if prev and prev_available:
                    row.update(
                        {
                            "broken_n": len(broken),
                            "broken_return_n": int(close_ret.loc[dt, broken].notna().sum()) if broken else 0,
                            "prev_limit_n": len(prev_up),
                            "prev_limit_suspended_n": int(sl.close.loc[dt, prev_up].isna().sum()) if prev_up else 0,
                        }
                    )
                for prefix, mask in (
                    ("promote_1_2", 1),
                    ("promote_2_3", 2),
                    ("promote_3p", 3),
                ):
                    if prev and prev_available:
                        prev_dt = up_limit.index[i - 1]
                        if prefix == "promote_3p":
                            cohort = [c for c in prev_up if int(streak.at[prev_dt, c]) >= 3]
                        else:
                            cohort = [c for c in prev_up if int(streak.at[prev_dt, c]) == mask]
                        num = sum(bool(limit_up.at[dt, c]) for c in cohort)
                        row[f"{prefix}_num"] = num
                        row[f"{prefix}_den"] = len(cohort)
                        row[prefix] = _ratio(num, len(cohort))
                _return_stats(open_ret.loc[dt, broken], "broken_open", row)
                _return_stats(close_ret.loc[dt, broken], "broken_close", row)
                if prev and prev_available:
                    prev_dt = up_limit.index[i - 1]
                    first_broken = [c for c in broken if int(streak.at[prev_dt, c]) == 1]
                    multi_broken = [c for c in broken if int(streak.at[prev_dt, c]) >= 2]
                    row["broken_first_close_mean"] = (
                        float(pd.to_numeric(close_ret.loc[dt, first_broken], errors="coerce").dropna().mean())
                        if first_broken else np.nan
                    )
                    row["broken_multi_close_mean"] = (
                        float(pd.to_numeric(close_ret.loc[dt, multi_broken], errors="coerce").dropna().mean())
                        if multi_broken else np.nan
                    )
                broken_close = pd.to_numeric(close_ret.loc[dt, broken], errors="coerce").dropna()
                row["broken_loss_pct"] = float((broken_close < 0).mean() * 100.0) if len(broken_close) else np.nan
                _return_stats(open_ret.loc[dt, prev_up], "prev_limit_open", row)
                _return_stats(close_ret.loc[dt, prev_up], "prev_limit_close", row)
                prev_close = pd.to_numeric(close_ret.loc[dt, prev_up], errors="coerce").dropna()
                row["prev_limit_red_pct"] = float((prev_close > 0).mean() * 100.0) if len(prev_close) else np.nan
            metric_rows.append(row)

        relevant = set().union(*(set(current_membership[u]) for u in UNIVERSES)) | previous_limit
        if day_available:
            event_codes = {
                c for c in relevant
                if bool(limit_up.at[dt, c]) or bool(touched.at[dt, c])
                or bool(limit_down.at[dt, c]) or c in broken_all
            }
            membership = {c: [u for u in UNIVERSES if c in current_membership[u]] for c in event_codes}
            for code in sorted(event_codes):
                event_rows.append(
                    {
                        "date": to_dash(day),
                        "ts_code": code,
                        "universes": "|".join(membership[code]),
                        "streak": int(streak.at[dt, code]),
                        "prev_streak": (
                            int(streak.at[up_limit.index[i - 1], code])
                            if prev and code in previous_limit else 0
                        ),
                        "is_limit_up": bool(limit_up.at[dt, code]),
                        "is_failed_proxy": bool(touched.at[dt, code] and not limit_up.at[dt, code]),
                        "is_limit_down": bool(limit_down.at[dt, code]),
                        "is_broken": code in broken_all,
                        "was_limit_up": code in previous_limit,
                        "is_one_word": bool(one_word.at[dt, code]),
                        "open_ret": open_ret.at[dt, code],
                        "close_ret": close_ret.at[dt, code],
                    }
                )
    return pd.DataFrame(metric_rows), pd.DataFrame(event_rows, columns=EVENT_COLUMNS)


def _merge_metrics(hist: pd.DataFrame, new: pd.DataFrame, run_day: str | None = None) -> pd.DataFrame:
    """历史行 append-only；只有本次运行日允许被重跑替换，防止窗口首日重写旧 cohort。"""
    if hist is not None and not hist.empty:
        hist = hist.copy()
        hist["date"] = pd.to_datetime(hist["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        if run_day is not None:
            hist = hist[hist["date"].ne(to_dash(run_day))]
    frames = [df for df in (hist, new) if df is not None and not df.empty]
    if not frames:
        return new.copy()
    both = pd.concat(frames, ignore_index=True)
    both["date"] = pd.to_datetime(both["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    both = both.dropna(subset=["date", "universe"])
    both = both.drop_duplicates(["date", "universe"], keep="first").sort_values(["universe", "date"])
    both["max_height_pct"] = np.nan
    for universe in UNIVERSES:
        mask = both["universe"].eq(universe)
        both.loc[mask, "max_height_pct"] = S.rolling_pct_last(
            both.loc[mask, "max_height"].astype(float), 250, 120
        ).to_numpy()
    return both.sort_values(["date", "universe"]).reset_index(drop=True)


def _merge_events(hist: pd.DataFrame, new: pd.DataFrame, run_day: str | None = None) -> pd.DataFrame:
    if hist is not None and not hist.empty:
        hist = hist.copy()
        hist["date"] = pd.to_datetime(hist["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        if run_day is not None:
            hist = hist[hist["date"].ne(to_dash(run_day))]
    frames = [df for df in (hist, new) if df is not None and not df.empty]
    if not frames:
        return new.copy()
    both = pd.concat(frames, ignore_index=True)
    both["date"] = pd.to_datetime(both["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return (
        both.dropna(subset=["date", "ts_code"])
        .drop_duplicates(["date", "ts_code"], keep="first")
        .sort_values(["date", "ts_code"])
        .reset_index(drop=True)
    )


def _number(value: object) -> str:
    return "—" if pd.isna(value) else str(int(round(float(value))))


def _pct(value: object, digits: int = 1, signed: bool = False) -> str:
    if pd.isna(value):
        return "—"
    return f"{float(value):+.{digits}f}%" if signed else f"{float(value):.{digits}f}%"


def _height(row: pd.Series) -> str:
    return f"{_number(row['max_height'])}板（{_pct(row['max_height_pct'])}）"


def _promotions(row: pd.Series) -> str:
    return " / ".join(_pct(row[key]) for key in ("promote_1_2", "promote_2_3", "promote_3p"))


def render_summary(metrics: pd.DataFrame, day: str, aux_status: str, aux_counts: dict[str, int]) -> str:
    latest = metrics[metrics["date"].eq(to_dash(day))]
    lines = [
        "## 涨停情绪监控",
        "",
        f"**{to_dash(day)}｜盘后数据｜核心：完整｜辅助：{aux_status}｜现有池：{to_dash(day)}**",
        "",
        "| 市场 | 最高板（250日分位） | 宽度：1/2/3/4/5+ | 晋级率：1→2 / 2→3 / 3+ | 断板收益：均值/中位 | 昨停溢价：开盘/收盘 | 炸板率 | 跌停数 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for universe in UNIVERSES:
        rows = latest[latest["universe"].eq(universe)]
        if rows.empty:
            continue
        row = rows.iloc[-1]
        width = "/".join(_number(row[f"width_{key}"]) for key in ("1", "2", "3", "4", "5p"))
        broken = f"{_pct(row['broken_close_mean'], 2, True)}/{_pct(row['broken_close_median'], 2, True)}"
        premium = f"{_pct(row['prev_limit_open_mean'], 2, True)}/{_pct(row['prev_limit_close_mean'], 2, True)}"
        lines.append(
            f"| {UNIVERSE_NAMES[universe]} | {_height(row)} | {width} | {_promotions(row)} "
            f"| {broken} | {premium} | {_pct(row['failed_rate'])} | {_number(row['limit_down_n'])} |"
        )
    lines.extend(["", "<details><summary>样本与数据说明</summary>", ""])
    for universe in UNIVERSES:
        rows = latest[latest["universe"].eq(universe)]
        if rows.empty:
            continue
        row = rows.iloc[-1]
        samples = []
        for key, label in (("promote_1_2", "1→2"), ("promote_2_3", "2→3"), ("promote_3p", "3+")):
            samples.append(f"{label} {_number(row[f'{key}_num'])}/{_number(row[f'{key}_den'])}")
        lines.append(
            f"- {UNIVERSE_NAMES[universe]}：涨停 {_number(row['limit_up_n'])} 只；"
            f"断板样本 {_number(row['broken_return_n'])}/{_number(row['broken_n'])}；晋级 " + "，".join(samples)
        )
    if aux_counts:
        aux_text = "/".join(str(aux_counts[k]) if k in aux_counts else "—" for k in ("U", "Z", "D"))
        lines.append(f"- Tushare 榜单核对：U/Z/D = {aux_text}")
    lines.extend(["", "炸板率为日线“触及涨停但未封收”的代理口径。", "仅展示盘后事实，不构成离场建议。", "", "</details>", ""])
    return "\n".join(lines)


def _write_summary(data_dir: Path, text: str) -> None:
    (data_dir / SUMMARY_FILENAME).write_text(text, encoding="utf-8", newline="\n")


def write_limit_sentiment_failure(data_dir: str | Path, day: str, error: Exception, token: str = "") -> None:
    target = Path(data_dir)
    target.mkdir(parents=True, exist_ok=True)
    message = str(error).replace("\n", " ")
    if token:
        message = message.replace(token, "[REDACTED]")
    message = message[:500]
    text = (
        "## 涨停情绪监控\n\n"
        f"**{to_dash(day)}｜盘后数据｜核心：失败｜现有池：{to_dash(day)}**\n\n"
        f"本次监控未生成结果：{type(error).__name__}: {message}\n\n"
        "原有监控与数据更新不受影响。\n"
    )
    _write_summary(target, text)


def update_limit_sentiment(
    client: TsClient,
    sl: Slice,
    data_dir: str | Path,
    replace_existing: bool = False,
    output_start: str | None = None,
) -> dict:
    target = Path(data_dir)
    target.mkdir(parents=True, exist_ok=True)
    day = sl.days[-1]
    limit_frames = client.fetch_many(sl.days, client.stk_limit)
    if limit_frames.get(day) is None or limit_frames[day].empty:
        raise ValueError(f"{to_dash(day)} 涨跌停价未落库")
    st_frames = {d: client.stock_st(d) for d in sl.days}
    namechange = _namechange_frames(client, sl.days)
    metrics_new, events_new = compute_limit_sentiment(sl, limit_frames, st_frames, namechange)
    if output_start is not None:
        output_start = to_dash(output_start)
        metrics_new = metrics_new[metrics_new["date"] >= output_start].copy()
        events_new = events_new[events_new["date"] >= output_start].copy()

    metric_path = target / METRICS_FILENAME
    event_path = target / EVENTS_FILENAME
    hist_metrics = read_csv(metric_path, dtype={"date": str}) if metric_path.exists() else pd.DataFrame()
    hist_events = read_csv(event_path, dtype={"date": str}) if event_path.exists() else pd.DataFrame()
    if replace_existing:
        # 仅显式全历史回填允许替换重叠日期，消除首次短窗口的预热截断。
        metric_dates = set(metrics_new["date"].astype(str)) if "date" in metrics_new else set()
        event_dates = set(events_new["date"].astype(str)) if "date" in events_new else set()
        if not hist_metrics.empty:
            hist_metrics = hist_metrics[~hist_metrics["date"].astype(str).isin(metric_dates)]
        if not hist_events.empty:
            hist_events = hist_events[~hist_events["date"].astype(str).isin(event_dates)]
    metrics = _merge_metrics(hist_metrics, metrics_new, run_day=day)
    events = _merge_events(hist_events, events_new, run_day=day).reindex(columns=EVENT_COLUMNS)
    write_csv(metrics, metric_path)
    write_csv(events, event_path, columns=EVENT_COLUMNS)

    aux_counts: dict[str, int] = {}
    aux_status = "完整"
    for kind in ("U", "Z", "D"):
        try:
            aux_counts[kind] = len(client.limit_list_d(day, kind))
        except Exception as exc:  # noqa: BLE001 - 辅助接口不得影响核心结果
            aux_status = "缺失"
            print(f"[limit-sentiment] 辅助榜单 {kind} 不可用: {type(exc).__name__}: {str(exc)[:160]}")
    _write_summary(target, render_summary(metrics, day, aux_status, aux_counts))
    return {"status": "ok", "date": to_dash(day), "rows": len(metrics_new), "aux_status": aux_status}


def backfill_limit_sentiment(
    start: str,
    end: str,
    fetch_start: str,
    data_dir: str | Path,
) -> dict:
    """手动全历史回填：复用同一 Slice/现有池，不改原 backfill 指标与调度。"""
    client = TsClient(log=print)
    sl = load_slice(
        client,
        start=start,
        end=end,
        fetch_start=fetch_start,
        include_margin=False,
        include_moneyflow=False,
    )
    return update_limit_sentiment(
        client, sl, data_dir, replace_existing=True, output_start=start
    )
