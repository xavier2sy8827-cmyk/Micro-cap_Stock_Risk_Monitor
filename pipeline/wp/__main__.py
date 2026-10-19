# -*- coding: utf-8 -*-
"""命令行入口：python -m wp ..."""
from __future__ import annotations

import argparse
import json
from datetime import date

from wp import config as C
from wp.ts_client import TsClient
from wp.universe import build_pool


def _latest_trade_day(client: TsClient) -> str:
    today = date.today().strftime("%Y%m%d")
    days = client.trade_days(f"{today[:4]}0101", today)
    if not days:
        raise SystemExit("无法获取交易日历")
    return days[-1]


def cmd_pools(args: argparse.Namespace) -> int:
    client = TsClient(min_interval=60.0 / max(args.rpm, 1))
    day = args.date or _latest_trade_day(client)
    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    out = []
    for kind in kinds:
        res = build_pool(client, day, kind)
        mv_col = "total_mv" if kind == "total400" else "circ_mv"
        head = res.df.head(args.show)[["rank_in_pool", "ts_code", "name", mv_col]]
        tail = res.df.tail(args.show)[["rank_in_pool", "ts_code", "name", mv_col]]
        out.append(
            {
                "kind": kind,
                "trade_date": res.trade_date,
                "prev_trade_date": res.prev_trade_date,
                "n": len(res.df),
                "min_mv_yi": round(float(res.df[mv_col].min()) / 1e4, 4),
                "max_mv_yi": round(float(res.df[mv_col].max()) / 1e4, 4),
                "st_source": res.st_info.source,
                "st_degraded": res.st_info.degraded,
                "name_mismatch": res.name_mismatch,
                "suspended_filled": res.suspended_filled,
            }
        )
        print(f"== {kind} @ {res.trade_date} (prev {res.prev_trade_date}) n={len(res.df)} ==")
        print(
            f"  ST source={res.st_info.source} degraded={res.st_info.degraded} "
            f"mismatch={res.name_mismatch} suspended_filled={res.suspended_filled}"
        )
        print("  head:")
        print(head.to_string(index=False))
        print("  tail:")
        print(tail.to_string(index=False))
    print("calls:", json.dumps(client.stats(), ensure_ascii=False))
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wp", description="微盘监控数据管线")
    parser.add_argument("--version", action="version", version=C.PIPELINE_VERSION)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pools = sub.add_parser("pools", help="构建并打印两个池")
    p_pools.add_argument("--date", default=None, help="交易日 YYYY-MM-DD；默认最近开市日")
    p_pools.add_argument("--kinds", default="total400,circ1000")
    p_pools.add_argument("--show", type=int, default=5)
    p_pools.add_argument("--rpm", type=float, default=180.0, help="每分钟调用上限")
    p_pools.add_argument("--json", action="store_true")
    p_pools.set_defaults(func=cmd_pools)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
