# -*- coding: utf-8 -*-
"""裁掉 INIT 的预热段（fetch_start < start），只保留输出起点之后的行。

新代码在 run_slice 内已自动裁剪；此脚本用于修复旧版本生成的 data 目录。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wp.checks import read_csv, write_csv  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--start", default="2016-01-04")
    args = ap.parse_args()
    d = Path(args.data_dir)

    for name, col in [
        ("metrics.csv", "date"),
        ("industry_breadth.csv", "date"),
        ("factor_ic.csv", "date"),
        ("factor_states.csv", "date"),
    ]:
        path = d / name
        if not path.exists():
            continue
        df = read_csv(path)
        before = len(df)
        df = df[df[col].astype(str).str[:10] >= args.start].reset_index(drop=True)
        write_csv(df, path)
        print(f"{name}: {before} -> {len(df)}")

    ev_path = d / "factor_events.csv"
    if ev_path.exists():
        ev = read_csv(ev_path)
        before = len(ev)
        ev = ev[ev["event_date"].astype(str).str[:10] >= args.start].reset_index(drop=True)
        write_csv(ev, ev_path)
        print(f"factor_events.csv: {before} -> {len(ev)}")

    meta_path = d / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["slice_start"] = args.start
        meta["days"] = len(read_csv(d / "metrics.csv"))
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"meta days={meta['days']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
