# -*- coding: utf-8 -*-
"""Tushare Pro 客户端：限速、重试、字段断言、调用统计。

铁律：所有取数只经这里，禁止研究/指标代码直接 `ts.pro_api`。
"""
from __future__ import annotations

import os
import time
from collections import Counter
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable

import pandas as pd

from wp import config as C
from wp.checks import assert_columns


class TsError(RuntimeError):
    """Tushare 调用失败。"""


class TsPermissionError(TsError):
    """权限/积分不足：不重试，直接失败。"""


class TsParamError(TsError):
    """参数错误：不重试，直接失败。"""


_PERMISSION_HINTS = ("没有接口", "没有权限", "权限", "积分", "无权", "not authorized", "permission")
_PARAM_HINTS = ("参数", "不存在", "invalid", "无效")


def to_compact(value: str | date_cls | datetime) -> str:
    """统一成 YYYYMMDD。"""
    if isinstance(value, (date_cls, datetime)):
        return value.strftime("%Y%m%d")
    s = str(value).strip()[:10]
    if len(s) == 8 and s.isdigit():
        return s
    if len(s) >= 10 and s[4] in "-/" and s[7] in "-/":
        return s[:4] + s[5:7] + s[8:10]
    raise ValueError(f"无法识别的日期: {value!r}")


def to_dash(value: str | date_cls | datetime) -> str:
    """统一成 YYYY-MM-DD。"""
    s = to_compact(value)
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


class TsClient:
    """薄封装：`query(api, **params)` + 限速 + 重试 + 统计。"""

    def __init__(
        self,
        token: str | None = None,
        min_interval: float | None = None,
        max_retries: int | None = None,
        log: Callable[..., None] | None = None,
    ) -> None:
        self.token = token or os.environ.get("TUSHARE_TOKEN", "")
        if not self.token:
            raise TsError("TUSHARE_TOKEN 未设置")
        self.min_interval = C.API_MIN_INTERVAL if min_interval is None else min_interval
        self.max_retries = C.API_MAX_RETRIES if max_retries is None else max_retries
        self._pro = None
        self._last_call = 0.0
        self._counts: Counter[str] = Counter()
        self._attempts: Counter[str] = Counter()
        self._cache: dict[tuple[Any, ...], pd.DataFrame] = {}
        self._log = log or (lambda *a, **k: None)

    # ------------------------------------------------------------------ 基础
    @property
    def pro(self):
        if self._pro is None:
            import tushare as ts

            self._pro = ts.pro_api(self.token)
        return self._pro

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def call(self, api: str, **params: Any) -> pd.DataFrame:
        """调用一个接口；仅对瞬时错误重试。"""
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            self._attempts[api] += 1
            try:
                df = self.pro.query(api, **params)
                self._counts[api] += 1
                if df is None:
                    return pd.DataFrame()
                return df
            except Exception as exc:  # noqa: BLE001 - 需要按消息分类
                msg = str(exc)
                if any(h in msg for h in _PERMISSION_HINTS):
                    raise TsPermissionError(f"{api} 权限/积分不足: {msg}") from exc
                if any(h in msg for h in _PARAM_HINTS):
                    raise TsParamError(f"{api} 参数错误: {msg}") from exc
                last = exc
                self._log(f"[ts] {api} 第 {attempt + 1} 次失败: {msg[:160]}")
                if attempt < self.max_retries:
                    time.sleep(C.API_BACKOFF[min(attempt, len(C.API_BACKOFF) - 1)])
        raise TsError(f"{api} 重试 {self.max_retries} 次后仍失败: {last}")

    def df(
        self,
        api: str,
        expected: Iterable[str] | None = None,
        **params: Any,
    ) -> pd.DataFrame:
        out = self.call(api, **params)
        if out is None or out.empty:
            # 空结果是合法返回（非交易日/无该股行情），由调用方决定如何处理
            return pd.DataFrame() if out is None else out
        if expected:
            assert_columns(out, list(expected), name=api)
        return out

    def stats(self) -> dict[str, Any]:
        return {"calls": dict(self._counts), "attempts": dict(self._attempts), "total": sum(self._counts.values())}

    def reset_stats(self) -> None:
        self._counts.clear()
        self._attempts.clear()

    def _cached(self, key: tuple[Any, ...], loader: Callable[[], pd.DataFrame]) -> pd.DataFrame:
        """同一次运行内复用（池/行业/元数据会被多次调用）。"""
        if key not in self._cache:
            self._cache[key] = loader()
        return self._cache[key]

    def clear_cache(self) -> None:
        self._cache.clear()

    # ------------------------------------------------------------------ 日历
    def trade_days(self, start: str, end: str) -> list[str]:
        key = ("trade_days", to_compact(start), to_compact(end))

        def load() -> pd.DataFrame:
            return self.df(
                "trade_cal",
                C.FIELDS["trade_cal"],
                exchange="SSE",
                start_date=to_compact(start),
                end_date=to_compact(end),
                fields=",".join(C.FIELDS["trade_cal"]),
            )

        df = self._cached(key, load)
        if df.empty:
            return []
        open_df = df[df["is_open"] == 1]
        return sorted(str(x) for x in open_df["cal_date"])

    def prev_trade_day(self, day: str) -> str:
        d = to_compact(day)
        start = (datetime.strptime(d, "%Y%m%d") - timedelta(days=40)).strftime("%Y%m%d")
        days = [x for x in self.trade_days(start, d) if x < d]
        if not days:
            raise TsError(f"{to_dash(day)} 之前找不到交易日")
        return days[-1]

    def next_trade_day(self, day: str) -> str:
        d = to_compact(day)
        end = (datetime.strptime(d, "%Y%m%d") + timedelta(days=40)).strftime("%Y%m%d")
        days = [x for x in self.trade_days(d, end) if x > d]
        if not days:
            raise TsError(f"{to_dash(day)} 之后找不到交易日")
        return days[0]

    # ------------------------------------------------------------------ 元数据
    def stock_basic(self) -> pd.DataFrame:
        return self._cached(("stock_basic",), self._load_stock_basic)

    def _load_stock_basic(self) -> pd.DataFrame:
        frames = []
        for status in ("L", "D", "P"):
            frames.append(
                self.df(
                    "stock_basic",
                    C.FIELDS["stock_basic"],
                    exchange="",
                    list_status=status,
                    fields=",".join(C.FIELDS["stock_basic"]),
                )
            )
        df = pd.concat([x for x in frames if not x.empty], ignore_index=True)
        if df.empty:
            return df
        return df.drop_duplicates(subset=["ts_code"], keep="last").reset_index(drop=True)

    def stock_st(self, day: str) -> pd.DataFrame:
        key = ("stock_st", to_compact(day))

        def load() -> pd.DataFrame:
            return self.df(
                "stock_st",
                C.FIELDS["stock_st"],
                trade_date=to_compact(day),
                fields=",".join(C.FIELDS["stock_st"]),
            )

        return self._cached(key, load)

    def namechange(self, start: str, end: str) -> pd.DataFrame:
        key = ("namechange", to_compact(start), to_compact(end))

        def load() -> pd.DataFrame:
            return self.df(
                "namechange",
                C.FIELDS["namechange"],
                start_date=to_compact(start),
                end_date=to_compact(end),
                fields=",".join(C.FIELDS["namechange"]),
            )

        return self._cached(key, load)

    # ------------------------------------------------------------------ 日频
    def daily(self, day: str) -> pd.DataFrame:
        key = ("daily", to_compact(day))
        return self._cached(
            key,
            lambda: self.df(
                "daily", C.FIELDS["daily"], trade_date=to_compact(day),
                fields=",".join(C.FIELDS["daily"]),
            ),
        )

    def daily_basic(self, day: str) -> pd.DataFrame:
        key = ("daily_basic", to_compact(day))
        return self._cached(
            key,
            lambda: self.df(
                "daily_basic", C.FIELDS["daily_basic"], trade_date=to_compact(day),
                fields=",".join(C.FIELDS["daily_basic"]),
            ),
        )

    def moneyflow(self, day: str) -> pd.DataFrame:
        key = ("moneyflow", to_compact(day))
        return self._cached(
            key,
            lambda: self.df(
                "moneyflow", C.FIELDS["moneyflow"], trade_date=to_compact(day),
                fields=",".join(C.FIELDS["moneyflow"]),
            ),
        )

    def margin_detail(self, day: str) -> pd.DataFrame:
        key = ("margin_detail", to_compact(day))
        return self._cached(
            key,
            lambda: self.df(
                "margin_detail", C.FIELDS["margin_detail"], trade_date=to_compact(day),
                fields=",".join(C.FIELDS["margin_detail"]),
            ),
        )

    def daily_basic_history(self, ts_code: str, start: str, end: str) -> pd.DataFrame:
        """按个股取 daily_basic 区间（用于停牌股的最近估值）。"""
        key = ("daily_basic_history", ts_code, to_compact(start), to_compact(end))

        def load() -> pd.DataFrame:
            return self.df(
                "daily_basic",
                C.FIELDS["daily_basic"],
                ts_code=ts_code,
                start_date=to_compact(start),
                end_date=to_compact(end),
                fields=",".join(C.FIELDS["daily_basic"]),
            )

        return self._cached(key, load)

    def index_daily(self, ts_code: str, start: str, end: str) -> pd.DataFrame:
        key = ("index_daily", ts_code, to_compact(start), to_compact(end))

        def load() -> pd.DataFrame:
            return self.df(
                "index_daily",
                C.FIELDS["index_daily"],
                ts_code=ts_code,
                start_date=to_compact(start),
                end_date=to_compact(end),
                fields=",".join(C.FIELDS["index_daily"]),
            )

        return self._cached(key, load)

    # ------------------------------------------------------------------ 行业
    def index_classify(self, level: str = "L1", src: str = "SW2021") -> pd.DataFrame:
        return self.df(
            "index_classify", C.FIELDS["index_classify"], level=level, src=src,
            fields=",".join(C.FIELDS["index_classify"]),
        )

    def index_member(self, index_code: str) -> pd.DataFrame:
        return self.df(
            "index_member", C.FIELDS["index_member"], index_code=index_code,
            fields=",".join(C.FIELDS["index_member"]),
        )
