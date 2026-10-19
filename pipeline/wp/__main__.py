# -*- coding: utf-8 -*-
"""命令行入口：python -m wp ..."""
from __future__ import annotations

import argparse
import json
from datetime import date

from wp import config as C
from wp.build_site import build as build_site
from wp.pipeline import run_slice
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


def cmd_slice(args: argparse.Namespace) -> int:
    meta = run_slice(
        start=args.start,
        end=args.end,
        fetch_start=args.fetch_start,
        data_dir=args.data_dir,
        include_margin=not args.no_margin,
        include_moneyflow=not args.no_moneyflow,
    )
    print(json.dumps({"rows": meta.get("days"), "through": meta.get("data_through")}, ensure_ascii=False))
    return 0


def cmd_build_site(args: argparse.Namespace) -> int:
    meta = build_site(args.data_dir, args.out)
    print(json.dumps({"data_through": meta.get("data_through"), "out": args.out}, ensure_ascii=False))
    return 0


def cmd_daily(args: argparse.Namespace) -> int:
    from wp.daily import run_daily

    out = run_daily(args.data_dir, day=args.date, window=args.window)
    print(json.dumps(out, ensure_ascii=False))
    return 0


def cmd_manifest(args: argparse.Namespace) -> int:
    from wp.manifest import make_manifest

    man = make_manifest(args.data_dir, args.start, args.end)
    print(json.dumps({"outputs": len(man["outputs"]), "code_commit": man["code_commit"]}, ensure_ascii=False))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from wp.manifest import verify

    rep = verify(args.data_dir, args.start, args.end)
    print(json.dumps(rep, ensure_ascii=False))
    return 0 if rep["ok"] else 2


def cmd_rebuild_pb(args: argparse.Namespace) -> int:
    from wp.rebuild_pb import rebuild

    print(json.dumps(rebuild(args.data_dir), ensure_ascii=False))
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

    p_slice = sub.add_parser("slice", help="计算一段区间的指标并写 data 目录")
    p_slice.add_argument("--start", required=True)
    p_slice.add_argument("--end", required=True)
    p_slice.add_argument("--fetch-start", default=None, help="取数起点（默认=start）")
    p_slice.add_argument("--data-dir", default=str(C.DEFAULT_DATA_DIR))
    p_slice.add_argument("--no-margin", action="store_true", help="跳过两融（省时间）")
    p_slice.add_argument("--no-moneyflow", action="store_true", help="跳过资金流（F5 将为 NaN）")
    p_slice.set_defaults(func=cmd_slice)

    p_site = sub.add_parser("build-site", help="metrics.csv -> 前端 JSON")
    p_site.add_argument("--data-dir", default=str(C.DEFAULT_DATA_DIR))
    p_site.add_argument("--out", default=str(C.PROJECT_ROOT / "web" / "public" / "data"))
    p_site.set_defaults(func=cmd_build_site)

    p_daily = sub.add_parser("daily", help="每日增量：只重算最近窗口并合并历史")
    p_daily.add_argument("--data-dir", default=str(C.DEFAULT_DATA_DIR))
    p_daily.add_argument("--date", default=None, help="交易日 YYYY-MM-DD；默认最近开市日")
    p_daily.add_argument("--window", type=int, default=100, help="取数窗口（交易日）")
    p_daily.set_defaults(func=cmd_daily)

    p_man = sub.add_parser("manifest", help="生成 init_manifest.json")
    p_man.add_argument("--data-dir", default=str(C.DEFAULT_DATA_DIR))
    p_man.add_argument("--start", default="2016-01-04")
    p_man.add_argument("--end", required=True)
    p_man.set_defaults(func=cmd_manifest)

    p_ver = sub.add_parser("verify", help="覆盖/不变量检查")
    p_ver.add_argument("--data-dir", default=str(C.DEFAULT_DATA_DIR))
    p_ver.add_argument("--start", default="2016-01-04")
    p_ver.add_argument("--end", required=True)
    p_ver.set_defaults(func=cmd_verify)

    p_pb = sub.add_parser("rebuild-pb", help="只重算 pb_spread 历史（修复样本口径）")
    p_pb.add_argument("--data-dir", default=str(C.DEFAULT_DATA_DIR))
    p_pb.set_defaults(func=cmd_rebuild_pb)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
