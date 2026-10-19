# -*- coding: utf-8 -*-
"""集中常量。任何口径/字段变化都改这里，并同步 docs/口径.md。"""
from __future__ import annotations

import os
from pathlib import Path

PIPELINE_VERSION = "0.1.0"

# ---- 路径 ----------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_DIR.parent
DEFAULT_DATA_DIR = Path(os.environ.get("WP_DATA_DIR", PROJECT_ROOT / "data_store"))

# ---- 池 ------------------------------------------------------------------
POOL_TOTAL_N = 400
POOL_CIRC_N = 1000
POOL_KINDS = ("total400", "circ1000")
MIN_LIST_DAYS = 60
# 停牌股在 daily_basic 无行：按个股向前找最近一次估值（最长回看自然日）
VALUATION_LOOKBACK_DAYS = 400
VALUATION_MAX_FILL = 300

# 剔除：北交所、科创板、B 股
EXCLUDE_SUFFIXES = (".BJ",)
EXCLUDE_PREFIXES = ("688", "689", "900", "200")

# ---- 行业 ----------------------------------------------------------------
INDUSTRY_SWITCH_DATE = "2021-12-13"  # SW2014(28) -> SW2021(31)
INDUSTRY_COVERAGE_MIN = 0.95

# ---- Tushare -------------------------------------------------------------
API_MIN_INTERVAL = 1.0 / 3.0  # 约 3 req/s
API_MAX_RETRIES = 3
API_BACKOFF = (1.0, 2.0, 4.0)
API_ROW_LIMIT = 6000

# ---- 格式 ----------------------------------------------------------------
FLOAT_FMT = ".6f"
DATE_FMT = "%Y-%m-%d"
CSV_ENCODING = "utf-8"
CSV_LINETERMINATOR = "\n"
VOLATILE_META_FIELDS = ("generated_at", "run_id", "duration_ms")

# ---- Tushare 字段快照（断言用；变更即失败，避免静默 schema 漂移） ----------
FIELDS = {
    "trade_cal": ["cal_date", "is_open"],
    "stock_basic": ["ts_code", "name", "market", "list_date", "delist_date"],
    "stock_st": ["ts_code", "name", "trade_date", "type"],
    "namechange": ["ts_code", "name", "start_date", "end_date", "change_reason"],
    "daily": ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "amount"],
    "daily_basic": ["ts_code", "trade_date", "turnover_rate", "pb", "total_mv", "circ_mv", "dv_ttm"],
    "moneyflow": ["ts_code", "trade_date", "buy_sm_amount", "sell_sm_amount"],
    "margin_detail": ["trade_date", "ts_code", "rzye", "rzmre"],
    "index_daily": ["ts_code", "trade_date", "close", "pre_close", "amount"],
    "index_classify": ["index_code", "industry_name", "level", "src"],
    "index_member": ["index_code", "con_code", "in_date", "out_date", "is_new"],
}

INDEX_CODES = {
    "csi300": "000300.SH",
    "csi500": "000905.SH",
    "csi1000": "000852.SH",
    "gz2000": "399303.SZ",
}

# ---- 监控阈值（与 notebook 对齐；前端也读这里生成 JSON） ------------------
THRESHOLDS = {
    "pb_spread": {"warn": 80, "danger": 90},
    "corr60": {"warn": 85, "danger": None},
    "ls_vol": {"warn": 90, "danger": None},
    "margin_pool_n": {"warn_below": 200},
}
