# -*- coding: utf-8 -*-
"""CSV 格式基线：UTF-8 无 BOM / LF / 6 位小数 / 空值空串。"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest

from wp.checks import assert_columns, check_text_file, sha256_file, write_csv


def test_write_csv_format(tmp_path) -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-10-16"]),
            "value": [1.23456789],
            "missing": [np.nan],
            "count": [3],
            "name": ["测试"],
        }
    )
    p = write_csv(df, tmp_path / "x.csv", columns=["date", "value", "missing", "count", "name"])
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    text = raw.decode("utf-8")
    assert text.splitlines()[0] == "date,value,missing,count,name"
    assert "1.234568" in text
    assert ",,3," in text or ",,3,测试" in text
    check_text_file(p)


def test_crlf_rejected(tmp_path) -> None:
    p = tmp_path / "bad.csv"
    p.write_bytes(b"a,b\r\n1,2\r\n")
    with pytest.raises(ValueError):
        check_text_file(p)


def test_bom_rejected(tmp_path) -> None:
    p = tmp_path / "bom.csv"
    p.write_bytes(b"\xef\xbb\xbfa\n1\n")
    with pytest.raises(ValueError):
        check_text_file(p)


def test_assert_columns() -> None:
    with pytest.raises(ValueError):
        assert_columns(pd.DataFrame({"a": [1]}), ["a", "b"])


def test_sha256(tmp_path) -> None:
    p = tmp_path / "x.txt"
    p.write_bytes(b"abc")
    assert sha256_file(p) == hashlib.sha256(b"abc").hexdigest()
