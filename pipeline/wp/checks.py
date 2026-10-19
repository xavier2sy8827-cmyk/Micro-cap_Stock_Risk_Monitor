# -*- coding: utf-8 -*-
"""格式与校验工具：CSV 统一为 UTF-8 无 BOM / LF / 6 位小数。"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from wp import config as C


class SchemaError(ValueError):
    """返回字段与预期不一致。"""


def assert_columns(df: pd.DataFrame, expected: Iterable[str], name: str = "dataframe") -> None:
    expected = list(expected)
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise SchemaError(f"{name} 缺少字段 {missing}；实际字段: {list(df.columns)}")


def _fmt_float(v: object) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return format(float(v), C.FLOAT_FMT)


def write_csv(
    df: pd.DataFrame,
    path: str | Path,
    columns: Iterable[str] | None = None,
) -> Path:
    """稳定格式写 CSV：固定列序、浮点 6 位、空值空串、LF、无 BOM。"""
    out = df.copy()
    if columns is not None:
        cols = list(columns)
        assert_columns(out, cols, name=str(path))
        out = out[cols]

    for col in out.columns:
        s = out[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            out[col] = s.dt.strftime(C.DATE_FMT)
        elif pd.api.types.is_float_dtype(s):
            out[col] = s.map(_fmt_float)
        elif pd.api.types.is_integer_dtype(s):
            out[col] = s.map(lambda v: "" if pd.isna(v) else str(int(v)))
        else:
            out[col] = s.map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(
        target,
        index=False,
        lineterminator=C.CSV_LINETERMINATOR,
        encoding=C.CSV_ENCODING,
    )
    check_text_file(target)
    return target


def read_csv(path: str | Path, **kwargs) -> pd.DataFrame:
    return pd.read_csv(path, encoding=C.CSV_ENCODING, **kwargs)


def check_text_file(path: str | Path) -> None:
    """拒绝 CRLF 与 BOM（防止 Windows 本地与 Ubuntu 产生接缝差异）。"""
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path} 含 UTF-8 BOM")
    if b"\r\n" in raw:
        raise ValueError(f"{path} 含 CRLF")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_blank(value: object) -> bool:
    return value is None or (isinstance(value, float) and np.isnan(value)) or value == ""
