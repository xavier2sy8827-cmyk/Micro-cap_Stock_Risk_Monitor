# 微盘风险与监控（Web 重构版）

把原「微盘监控-小市值」notebook 的监控指标，重构为 **Tushare-only + GitHub Actions + 移动端静态站点**。

- 目标站点：<https://xavier2sy8827-cmyk.github.io/Micro-cap_Stock_Risk_Monitor/>
- 数据源：Tushare Pro（仅需 `TUSHARE_TOKEN`）
- 运行方式：本地一次性 INIT；GitHub Actions 每交易日 17:00（北京时间）增量更新
- 站点形态：纯静态（React + Vite + ECharts），手机优先，无后端

## 当前状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| M0 | 仓库骨架 + 最小站点 + Pages 部署链路 | 完成（Pages 已上线） |
| M1 | 数据骨架：Tushare 客户端、两个池、格式基线、CI | 完成（18 项单测通过、CI 绿） |
| M2 | 非因子指标 + 7 个监控页面 | 完成（近端 2 年切片；全量等 M4） |
| M3 | 核心因子监控（IC / 多空 / 四态） | 完成（全量） |
| M4 | 全量 INIT（2016 起）+ data 分支 | 完成（2016-01-04 ~ 2026-10-19，2619 个交易日） |
| M5 | 每日 cron、接缝测试、手机验收 | 完成（daily 已跑通；cron 已排程 17:00） |

## 目录

```
web/                     React + Vite + TypeScript 站点
pipeline/wp/             Python 数据管线（M1 起填充）
scripts/                 对拍与运维脚本
docs/                    口径、对拍、二期说明
.github/workflows/       deploy / ci / daily / backfill
```

数据不放在 `main`：`main` 只管代码，CSV 存在 orphan 分支 `data`，部署时 checkout `data` 再生成 JSON。

## 本地开发

```powershell
cd web
npm ci
npm run dev
```

## 部署与数据更新

- 推送到 `main`（或 `data`）触发 `.github/workflows/deploy.yml`：checkout `data` 分支 → `python -m wp build-site` → 构建 `web/` → 发布 Pages。
- 每个交易日 17:00（北京时间）`.github/workflows/daily.yml` 增量更新最近窗口，提交到 `data` 分支后自动部署。
- 需要重建全量历史时手动跑 `.github/workflows/backfill.yml`（输出起点 2016-01-04，预热起点 2015-09-01）。

首次使用需在仓库设置中完成（缺一不可）：

1. **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**
   （未启用时 `configure-pages` 会报 `Create Pages site failed: Resource not accessible by integration`，GITHUB_TOKEN 无权代建）
2. **Settings → Actions → General → Workflow permissions** 设为 `Read and write`
   （`daily` 任务需要向 `data` 分支提交）
3. **Settings → Secrets and variables → Actions** 添加 `TUSHARE_TOKEN`

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
