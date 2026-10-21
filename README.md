# 微盘风险与监控（Web 重构版）

把原「微盘监控-小市值」notebook 的监控指标，重构为 **Tushare-only + GitHub Actions + 移动端静态站点**。

- 目标站点：<https://xavier2sy8827-cmyk.github.io/Micro-cap_Stock_Risk_Monitor/>
- 数据源：Tushare Pro（仅需 `TUSHARE_TOKEN`）
- 运行方式：本地一次性 INIT；Cloudflare Worker Cron 每交易日 17:00（北京时间）触发 GitHub Actions 增量更新；GitHub schedule 作兜底
- 站点形态：React + Vite + ECharts 静态站，手机优先；页面「更新数据」按钮通过 Cloudflare Worker 触发 daily（不暴露 GitHub token）

## 当前状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| M0 | 仓库骨架 + 最小站点 + Pages 部署链路 | 完成（Pages 已上线） |
| M1 | 数据骨架：Tushare 客户端、两个池、格式基线、CI | 完成（18 项单测通过、CI 绿） |
| M2 | 非因子指标 + 7 个监控页面 | 完成（全量） |
| M3 | 核心因子监控（IC / 多空 / 四态） | 完成（全量） |
| M4 | 全量 INIT（2016 起）+ data 分支 | 完成（2016-01-04 ~ 2026-10-20，2620 个交易日） |
| M5 | 每日 cron、接缝测试、手机验收 | 完成（Worker Cron 17:00/17:10 + GitHub schedule 兜底；页面按钮可用） |

## 目录

```
web/                     React + Vite + TypeScript 站点
pipeline/wp/             Python 数据管线
worker/                  Cloudflare Worker（页面按钮 + 17:00/17:10 Cron）
scripts/                 对拍与运维脚本
docs/                    口径、对拍、UI、更新按钮设计
.github/workflows/       deploy / ci / daily / backfill
```

数据不放在 `main`：`main` 只管代码，CSV 存在 orphan 分支 `data`，部署时 checkout `data` 再生成 JSON。

## 本地开发

```powershell
cd web
npm ci
npm run dev
```

数据 JSON 不入库。本地开发二选一：

- 把 `data` 分支 clone 到 `data_store`，在 `pipeline` 目录跑
  `python -m wp build-site --data-dir ../data_store --out ../web/public/data`
- 或直接把线上 `data/*.json` 下载到 `web/public/data/`。

## 部署与数据更新

- 推送到 `main` 触发 `.github/workflows/deploy.yml`：checkout `data` 分支 → `python -m wp build-site` → 构建 `web/` → 发布 Pages。
- **17:00 主定时**：Cloudflare Worker Cron（`09:00 UTC`）触发 `daily.yml`；`09:10 UTC` 重试。Cron 不依赖本地电脑开机。
- **17:00 兜底**：`.github/workflows/daily.yml` 的 `schedule` 仍保留；与 Worker 重复时由 `concurrency: wp-data` 串行化。
- **页面按钮**：右上角「更新数据」→ Cloudflare Worker `/refresh` → 同一个 `daily.yml`；token 只在 Worker secret。
- 需要重建全量历史时手动跑 `.github/workflows/backfill.yml`（输出起点 2016-01-04，预热起点 2015-09-01）。

首次使用需在仓库设置中完成（缺一不可）：

1. **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**
   （未启用时 `configure-pages` 会报 `Create Pages site failed: Resource not accessible by integration`，GITHUB_TOKEN 无权代建）
2. **Settings → Actions → General → Workflow permissions** 设为 `Read and write`
   （`daily` 任务需要向 `data` 分支提交）
3. **Settings → Secrets and variables → Actions** 添加 `TUSHARE_TOKEN`
4. **页面按钮 / 17:00 Worker Cron（可选）**：
   - `cd worker && wrangler deploy`
   - `wrangler secret put GITHUB_TOKEN`（fine-grained PAT，仅该仓库 Actions: Read and write）
   - 详见 [`worker/README.md`](worker/README.md) 与 [`docs/REFRESH_BUTTON.md`](docs/REFRESH_BUTTON.md)
   - 如需自定义端点，在 **Actions → Variables** 设置 `REFRESH_ENDPOINT`（默认已内置当前 Worker URL）

设置完成后，在 **Actions → deploy → Re-run jobs**，或向 `main` 推一个空提交触发重新部署。
站点地址：<https://xavier2sy8827-cmyk.github.io/Micro-cap_Stock_Risk_Monitor/>

## 数据口径（摘要）

- 池：总市值最小 400（`pool_total400`）用于宽度/拥挤度/qs/10 层/因子；流通市值最小 1000（`pool_circ1000`）**仅**用于两融主指标
- 两融主列：circ-1000；wp400 仅观察列
- ST：`stock_st` 按日；`namechange` 处理退市整理期
- 行业：SW2014（28）→ SW2021（31），`index_member` 区间重建
- 复权：`close/pre_close` 收益链，不引 `adj_factor`

详细口径与对拍记录见 [`docs/METHOD.md`](docs/METHOD.md)，页面规则见 [`docs/UI.md`](docs/UI.md)。

## 二期（不做）

IM 贴水、宏观/信用利差、估值页、盘中刷新、选股/持仓/组合。
