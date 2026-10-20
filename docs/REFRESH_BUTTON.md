# 页面「更新数据」按钮 · 方案设计（v0.3）

> 目标：在 GitHub Pages 静态站点上点一个按钮，即可触发一次 `daily` 工作流，跑完自动刷新页面；不要求用户登录 GitHub，也不把 GitHub token 放进前端。
> 状态：**GLM-5.3 外审 PASS（2026-10-20）**，可进入实现。

## 1. 背景与问题

- 站点是纯静态 GitHub Pages，数据更新依赖 `.github/workflows/daily.yml` 的 `schedule`（`0 9 * * *` UTC = 17:00 北京时间）。
- GitHub 的 `schedule` 是 best-effort：本仓库实际出现过 17:00 的任务延迟到次日 00:16 才执行（约 7 小时）。
- 当前绕过办法是登录 GitHub，在 Actions 里手动 `Run workflow`；用户希望在页面上完成。
- 参考站 `joseph2young.github.io` 的「刷新行情」只是前端调用腾讯公开行情接口刷新当前涨跌幅，**不触发数据管线**，不能直接照搬。

## 2. 目标与非目标

### 目标

1. 页面顶部提供 `更新数据` 按钮，点击后触发一次 `daily.yml`。
2. 触发成功后页面轮询数据版本，`data_through` 前进时自动重载 JSON，并提示新日期。
3. 浏览器端**不出现** GitHub PAT；token 只存在服务端（Cloudflare Worker secret）。
4. 触发接口有基本的防滥用：来源限制、频率限制、可选口令。
5. 失败可诊断：token 失效、权限不足、已有任务在跑、超时、部署失败都有明确文案。
6. 没有配置 Worker 时，按钮自动隐藏或降级为“刷新已发布数据”，站点仍可用。

### 非目标

- 不做盘中行情刷新（参考站那种 15 分钟行情轮询不在本期）。
- 不替代 GitHub Actions，不把计算搬到 Worker/浏览器。
- 不保证“秒级”更新；一次完整 daily + deploy 目前约 5–15 分钟。
- 不解决 GitHub `schedule` 本身的延迟；按钮是手动兜底。

## 3. 总体架构

```
┌─────────────┐   1. POST /refresh     ┌──────────────────┐
│  浏览器      │ ─────────────────────▶ │ Cloudflare Worker │
│  (Pages)    │                        │  secret: GH_TOKEN │
│             │ ◀───────────────────── │  KV: rate limit   │
└─────────────┘   2. 202 {dispatched_at} └────────┬─────────┘
      │                                         │ 3. workflow_dispatch
      │                                         ▼
      │                                ┌──────────────────┐
      │                                │ GitHub Actions    │
      │                                │ daily.yml         │
      │                                └────────┬─────────┘
      │                                         │ 4. commit data 分支
      │                                         ▼
      │                                ┌──────────────────┐
      │                                │ deploy.yml       │
      │                                │ 生成 JSON/Pages   │
      │                                └────────┬─────────┘
      │ 5. 轮询 meta.json?ts=...                │
      └─────────────────────────────────────────┘
                    发现 data_through 变化 → 重载全部 JSON
```

### 组件职责

| 组件 | 职责 |
|---|---|
| 页面按钮 | 发起触发、展示状态、轮询、重载数据；不持有 token |
| Cloudflare Worker | 校验来源/口令/频率；调用 GitHub `workflow_dispatch`；返回运行状态 |
| GitHub Actions `daily` | 真正的数据更新：Tushare → data 分支 |
| GitHub Actions `deploy` | data 分支 → JSON → Pages |
| `data/meta.json` | 页面轮询的版本探针（`data_through` / `generated_at`） |

## 4. 前端设计

### 4.1 按钮位置与状态

位置：顶栏 `主题` 左侧，移动端不换行；触控高度 ≥ 40px。

状态机：

| 状态 | 文案 | 行为 |
|---|---|---|
| idle | `更新数据` | 可点击 |
| triggering | `触发中…` | 禁用 |
| running | `更新中 12s` | 禁用；轮询 |
| success | `已更新 10-20 18:42` | 3 秒后回 idle |
| unchanged | `已是最新 10-20` | 3 秒后回 idle |
| error | `触发失败，点此重试` | 可点击；toast 显示原因 |

页面同时显示 `数据截至 YYYY-MM-DD`（顶栏已有）和 `上次更新 HH:MM`（页脚构建时间）。

### 4.2 触发流程（前端伪代码）

```ts
const endpoint = import.meta.env.VITE_REFRESH_ENDPOINT // 未配置则隐藏按钮

async function refreshData() {
  setState('triggering')
  // before 必须来自 /status，不能来自 Pages meta（可能被 CDN 缓存成旧值）
  const before = await getStatus()

  const res = await fetch(`${endpoint}/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(key ? { 'X-Refresh-Key': key } : {}) },
    body: JSON.stringify({ ref: 'main' }),
  })
  const attachedRun = res.status === 409
  if (!res.ok && !attachedRun) return fail(await parseError(res))
  const payload = await res.json().catch(() => ({}))
  const dispatchedAt = payload.dispatched_at ?? new Date().toISOString()
  const graceUntil = Date.now() + 60_000
  let sawActive = attachedRun

  setState('running')
  const deadline = Date.now() + 20 * 60 * 1000
  while (Date.now() < deadline) {
    await sleep(5000)
    let st
    try {
      st = await getStatus()
    } catch {
      continue // 单次网络抖动不终止轮询
    }
    // 只认 dispatch 之后创建的 run，避免把上一次 completed run 当成本次结果
    const isNewRun = !!st.run?.created_at && st.run.created_at >= dispatchedAt
    if (st.active) {
      sawActive = true
      continue
    }
    // 409 接手的是更早创建的 run：用 active→inactive 转变判定，不再比对 dispatched_at
    if (attachedRun && !isNewRun) {
      if (!sawActive || st.run?.status !== 'completed') continue
      if (st.last_data_through && st.last_data_through > before.last_data_through) {
        await reloadUntilCaughtUp(st.last_data_through, before.last_data_through)
        return success(st.last_data_through)
      }
      return unchanged(before.last_data_through)
    }
    if (!isNewRun) {
      if (Date.now() < graceUntil) continue
      continue // 新 run 还没出现，继续等到超时
    }
    if (st.run.conclusion === 'failure' || st.run.conclusion === 'cancelled') {
      return fail(`更新失败：${st.run.html_url}`)
    }
    if (st.last_data_through && st.last_data_through > before.last_data_through) {
      await reloadUntilCaughtUp(st.last_data_through, before.last_data_through)
      return success(st.last_data_through)
    }
    // 必须是本次新 run 正常结束且数据未变，才是真的“已是最新”
    if (st.run.status === 'completed') return unchanged(before.last_data_through)
  }
  fail('更新超时，请查看 Actions 日志')
}
```

关键点：

- **成功判据**是 Worker `/status` 的 `last_data_through`，不是页面 meta。
- **只认本次 dispatch 之后的 run**：`/refresh` 返回 `dispatched_at`，`/status` 返回 run 的 `created_at`；旧 completed run 不会被误判。`dispatched_at` 同时写入 KV（`last_dispatch`），`/status` 可回传。
- 60 秒宽限期只是保险；即使新 run 创建很慢，也不会误显示“已是最新”，只会继续轮询到超时。
- 单次 `/status` 失败 `continue`，不中断轮询。
- 非交易日 / 当天已跑过：**本次新 run** 正常结束且日期未变 → `unchanged`。
- 409（已有 run）不是错误：不比对 `dispatched_at`，改用 `active → inactive` 转变判定；该 run 结束且数据未变 → `unchanged`，数据前进 → 成功。
- 日期比较用 `>`（`YYYY-MM-DD` 字符串可比较），避免“日期不变仅 generated_at 变”误判。
- 页面隐藏时暂停轮询，恢复时先拉一次 `/status` 再继续。
- 20 分钟超时合理（daily 5–25 分钟 + deploy）；超时文案附 Actions 链接。

### 4.3 GitHub Pages 缓存与权威信号

GitHub Pages 前端是 Fastly，`?ts=` 只能绕过浏览器缓存，**不保证绕过 CDN 的约 10 分钟缓存**；因此：

- “run 完成 → 页面 10 秒内看到新数据”不能作为硬验收。
- Worker `/status` 的 `last_data_through`（从 `raw.githubusercontent.com` 读 data 分支 meta）是权威信号；`raw` 的缓存更短，且 Worker 可以在请求上加 `Cache-Control: no-cache`。
- 页面在权威信号变化后按 `?v=<data_through>` 重载 JSON；若 Pages 仍返回旧 JSON，则每 15 秒重试，最多 10 分钟，并显示“服务端已更新，CDN 同步中”。
- 验收改为：**服务端数据更新后，页面最终能在 ≤10 分钟内自动显示新数据**；具体 CDN 行为在实现阶段用 curl 实测一次并记录。

### 4.4 失败文案

| 情况 | 文案 |
|---|---|
| 401/403 | 服务端授权失效，请检查 Worker 的 GitHub token |
| 409 | 已有更新任务在跑，已进入等待（不是错误） |
| 429 | 触发太频繁，请 X 分钟后再试 |
| 5xx | 更新服务暂不可用 |
| 超时 | 更新超时，请查看 Actions 日志（附链接） |
| 非交易日/数据未变 | 已是最新（daily 无新数据，属正常） |
| run 失败 | 更新失败，查看 Actions 日志（附链接） |

## 5. Worker 设计

### 5.1 运行环境

- Cloudflare Workers（免费额度足够：每天几次请求）。
- 依赖：`@cloudflare/workers-types`；无需数据库，频率限制用 **KV**（或 Durable Object，见 5.5）。
- 变量：

| 名称 | 类型 | 示例 |
|---|---|---|
| `GITHUB_TOKEN` | secret | fine-grained PAT |
| `OWNER` | var | `xavier2sy8827-cmyk` |
| `REPO` | var | `Micro-cap_Stock_Risk_Monitor` |
| `WORKFLOW` | var | `daily.yml` |
| `REF` | var | `main` |
| `ALLOWED_ORIGIN` | var | `https://xavier2sy8827-cmyk.github.io` |
| `REFRESH_KEY` | secret（可选） | 随机口令 |
| `RATE_KV` | KV binding | 频率限制 |

### 5.2 GitHub token 权限

使用 **fine-grained PAT**，只授权该仓库：

- `Actions: Read and write`（触发 workflow、查询 run 状态）
- `Contents: Read`（可选，读仓库元信息）
- 不勾选 `Contents: Write`、不勾选 `Administration`、不勾选其他仓库。
- 有效期建议 90 天；到期前轮换；Worker secret 更新即可，页面无感。

### 5.3 接口

#### `POST /refresh`

请求：

```http
Origin: https://xavier2sy8827-cmyk.github.io
Content-Type: application/json
X-Refresh-Key: <可选口令>

{"ref":"main"}
```

处理：

1. CORS 校验 `Origin`（不等于 `ALLOWED_ORIGIN` 直接 403；注意 Origin 可被非浏览器伪造，只是第一道门槛）。
2. 若配置 `REFRESH_KEY`，常量时间比较 `X-Refresh-Key`，不匹配 401。
3. 频率限制：
   - 全局：`RATE_KV` key `global`，10 分钟内只允许 1 次；
   - 可选 per-IP：`ip:<CF-Connecting-IP>`，30 分钟 3 次。
   - 超过返回 429，带 `Retry-After`。
4. 查询是否已有活跃 run：
   - `GET /repos/{owner}/{repo}/actions/workflows/{workflow}/runs?status=in_progress&per_page=1`
   - `GET ...?status=queued&per_page=1`
   - 有则返回 409 + `run_url`，不重复触发。
5. 调 `POST /repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches`，body `{"ref": REF}`。
6. 触发成功后把 `dispatched_at` 写入 KV `last_dispatch`（TTL 1 天），返回 202：

```json
{"ok":true,"status":"dispatched","ref":"main","dispatched_at":"2026-10-20T13:05:00Z"}
```

> GitHub 的 dispatch 接口不返回 run_id；页面用 `/status` 的 `last_data_through` 与 run `created_at >= dispatched_at` 判定本次结果，不依赖 run_id。

#### `GET /status`

返回 Worker 视角的状态，便于页面显示“正在跑”：

```json
{
  "ok": true,
  "active": false,
  "dispatched_at": "2026-10-20T13:05:00Z",
  "run": {
    "status": "completed",
    "conclusion": "success",
    "created_at": "2026-10-20T13:05:20Z",
    "html_url": "https://github.com/.../actions/runs/..."
  },
  "last_data_through": "2026-10-20",
  "last_generated_at": "2026-10-20 21:05:00"
}
```

实现：

- 查询 workflow 最近一次 run：`GET /actions/workflows/{workflow}/runs?per_page=1`，取 `status/conclusion/created_at/html_url`。
- 读 KV `last_dispatch` 作为 `dispatched_at`；没有则 `null`。
- 读 `https://raw.githubusercontent.com/{owner}/{repo}/data/meta.json`，取 `data_through/generated_at`；使用 `cf: { cacheTtl: 30 }`（不要同时依赖 `Cache-Control` 头）。
- `active = status in ('queued','in_progress','waiting','requested')`。
- 页面把 `last_data_through` 作为“服务端是否已更新”的权威信号，并且只接受 `run.created_at >= dispatched_at` 的 run。

#### `OPTIONS /refresh`

返回 CORS preflight：

```
Access-Control-Allow-Origin: https://xavier2sy8827-cmyk.github.io
Access-Control-Allow-Methods: POST, GET, OPTIONS
Access-Control-Allow-Headers: Content-Type, X-Refresh-Key
Access-Control-Max-Age: 86400
```

### 5.4 核心 Worker 伪代码

```ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url)
    const origin = req.headers.get('Origin') ?? ''
    if (req.method === 'OPTIONS') return cors(new Response(null, { status: 204 }), env)
    if (origin !== env.ALLOWED_ORIGIN) return cors(json({ error: 'origin' }, 403), env)

    // 先按 path 路由，再校验 method；/status 允许 GET
    if (url.pathname === '/status' && req.method === 'GET') {
      return cors(json(await status(env)), env)
    }
    if (url.pathname !== '/refresh' || req.method !== 'POST') {
      return cors(json({ error: 'not_found' }, 404), env)
    }

    const key = req.headers.get('X-Refresh-Key') ?? ''
    if (env.REFRESH_KEY && !timingSafeEqual(key, env.REFRESH_KEY)) {
      return cors(json({ error: 'key' }, 401), env)
    }
    if (!(await allow(env))) return cors(json({ error: 'rate' }, 429, { 'Retry-After': '600' }), env)

    const active = await latestRun(env)
    if (active && ['queued', 'in_progress', 'waiting', 'requested'].includes(active.status)) {
      return cors(json({ error: 'running', run_url: active.html_url }, 409), env)
    }

    const res = await gh(env, `/repos/${env.OWNER}/${env.REPO}/actions/workflows/${env.WORKFLOW}/dispatches`, {
      method: 'POST',
      body: JSON.stringify({ ref: env.REF }),
    })
    if (!res.ok) return cors(json({ error: 'github', status: res.status }, 502), env)
    const dispatchedAt = new Date().toISOString()
    await env.RATE_KV.put('last_dispatch', dispatchedAt, { expirationTtl: 86400 })
    return cors(json({ ok: true, status: 'dispatched', ref: env.REF, dispatched_at: dispatchedAt }, 202), env)
  },
}

async function status(env: Env) {
  const run = await latestRun(env)
  const meta = await fetch(
    `https://raw.githubusercontent.com/${env.OWNER}/${env.REPO}/data/meta.json?ts=${Date.now()}`,
    { cf: { cacheTtl: 30 } },
  ).then((r) => (r.ok ? r.json() : {})).catch(() => ({}))
  return {
    ok: true,
    active: !!run && ['queued', 'in_progress', 'waiting', 'requested'].includes(run.status),
    dispatched_at: (await env.RATE_KV.get('last_dispatch')) ?? null,
    run: run
      ? { status: run.status, conclusion: run.conclusion, created_at: run.created_at, html_url: run.html_url }
      : null,
    last_data_through: meta.data_through ?? null,
    last_generated_at: meta.generated_at ?? null,
  }
}
```

> `latestRun` 只查 `per_page=1`；dispatch 后 GitHub 异步创建 run，短时间内可能仍返回**上一次 completed run**。页面必须用 `run.created_at >= dispatched_at` 过滤，并在 60 秒宽限期内忽略旧 completed run；宽限期后仍未看到新 run 则继续轮询到超时，不能误判「已是最新」。

### 5.5 频率限制实现选择

| 方案 | 优点 | 缺点 |
|---|---|---|
| KV + 时间戳 | 简单、免费 | 最终一致，极端并发可能穿透 |
| Durable Object | 强一致、可做锁 | 多一点代码/绑定 |
| GitHub 活跃 run 检查 | 天然防重复 | 不能防高频空触发 |

建议：**KV 全局 10 分钟 + GitHub 活跃 run 检查** 作为 v1；若发现被刷再加 Durable Object。

## 6. 安全设计

1. **Token 不落前端**：只在 Worker secret；前端 bundle 不含任何 `ghp_`/`github_pat_`。
2. **最小权限**：fine-grained PAT 只给该仓库 Actions 读写；不用 classic PAT，不给 repo 全权。
3. **来源限制**：CORS 只允许 Pages 域名；明确说明它不能替代鉴权（非浏览器可伪造）。
4. **口令（可选）**：`REFRESH_KEY` 第一次点击时弹窗输入，存 `localStorage`；Worker 常量时间比较。作用是防误点和简单滥用，不是强认证。
5. **频率限制**：全局 10 分钟 1 次；可选 per-IP。
6. **不记录敏感信息**：Worker 日志不打印 token/Authorization；错误只返回状态码。
7. **审计**：GitHub Actions 页面本身保留每次 `workflow_dispatch` 的 actor/时间；Worker 可加 `console.log` 记录 IP 哈希与时间（可选）。
8. **轮换**：PAT 过期/泄露时，更新 Worker secret 即可；页面无 token。
9. **拒绝危险操作**：Worker 只允许固定 `WORKFLOW/REF`，不接受用户传 owner/repo/workflow，避免被当成通用 GitHub 代理。

## 7. 失败模式与恢复

| 失败 | 页面表现 | 恢复 |
|---|---|---|
| Worker token 过期 | 401 文案 | 更新 secret |
| PAT 权限不足 | 403/502 | 补 Actions: write |
| 已有 run | 409 + 链接 | 等待，页面继续轮询 |
| Actions 排队久 | running 状态 | 20 分钟超时提示 + Actions 链接 |
| daily 失败 | `/status` 显示 failed | 页面附 run 链接；重试或看日志 |
| deploy 失败 | data 已更新但页面旧 | `/status.last_data_through` 已前进，页面显示“CDN 同步中”；重跑 deploy |
| 非交易日 | `已是最新` | 正常 |
| CORS 配错 | 浏览器控制台 CORS | 检查 ALLOWED_ORIGIN |
| Pages CDN 缓存 | 页面 JSON 仍旧 | 以 `/status` 为权威，按 `?v=` 重试 ≤10 分钟 |

## 8. 部署步骤（实现阶段）

1. 创建 fine-grained PAT（仅该仓库，Actions: write）。
2. `wrangler init wp-refresh`，创建 KV namespace `RATE_KV`。
3. `wrangler secret put GITHUB_TOKEN`；可选 `REFRESH_KEY`。
4. `wrangler.toml` 配置 `OWNER/REPO/WORKFLOW/REF/ALLOWED_ORIGIN` 与 KV binding。
5. `wrangler deploy`，得到 `https://wp-refresh.<account>.workers.dev`。
6. 前端 `.env.production` 设置 `VITE_REFRESH_ENDPOINT`；重新 build/deploy。
7. 用 curl 验证：
   - 正常触发 202
   - 10 分钟内第二次 429
   - 错误 Origin 403
   - 错误口令 401
   - 触发后 Actions 出现 `workflow_dispatch` run，data 分支更新，`/status.last_data_through` 前进
8. 运维：
   - PAT 到期前 7 天提醒（Worker 定时自检或 GitHub PAT 到期邮件）；
   - `wrangler rollback` 可回到上一版 Worker；
   - 移除前端 `VITE_REFRESH_ENDPOINT` 并重新 build 即回退到“无按钮”状态。

## 9. 验收标准

- [ ] 页面点击「更新数据」后，GitHub Actions 出现一次 `workflow_dispatch` 的 daily run。
- [ ] `GET /status` 在 run 完成后返回新的 `last_data_through`；页面以该字段判定成功，不依赖 Pages meta。
- [ ] 服务端数据更新后，页面最终在 **≤10 分钟**内自动显示新数据（`?v=` 重载 + 15s 重试）；实现阶段用 curl 实测 Pages 对 query string 的缓存行为并记录。
- [ ] 非交易日 / 当天 cron 已跑过时，run 正常结束且日期未变，页面显示「已是最新」而不是超时。
- [ ] 已有 run 时点击，Worker 返回 409，页面进入 running 轮询而不是报错。
- [ ] run 失败/取消时，页面显示失败并附 Actions run 链接。
- [ ] 浏览器 Network/JS bundle 中搜不到 GitHub token；Worker 响应头不含 token/内部路径。
- [ ] 10 分钟内重复点击被 429 拦截，页面提示剩余时间。
- [ ] 非允许 Origin 的请求被 403。
- [ ] 配置口令时，错误口令 401，正确口令可触发。
- [ ] Worker 异常/未配置时，按钮隐藏或降级，页面其他功能不受影响。
- [ ] dispatch 后 GitHub 尚未创建新 run、`/status` 仍返回上一次 completed run 时，页面不会误显示「已是最新」，会继续等待新 run（`run.created_at >= dispatched_at`）。
- [ ] 两个标签页同时点击不会产生两个并行 daily（concurrency 组 + 活跃 run 检查），两个页面都能各自看到状态。
- [ ] cron 正在跑时点击，返回 409 并进入轮询。
- [ ] PAT 失效（401/403）时 Worker 有日志/告警，页面文案可操作，不是静默失败。
- [ ] 回滚演练：`wrangler rollback` 回上一版 Worker；移除 `VITE_REFRESH_ENDPOINT` 重新构建后按钮消失、站点正常。
- [ ] 移动端 390px 下按钮不挤压标题/主题按钮。

## 10. 备选方案与取舍

| 方案 | 结论 |
|---|---|
| 前端直接放 PAT 调 GitHub API | ❌ 拒绝：token 公开，任何人可触发/滥用 |
| 页面只做 `location.reload()` / cache-bust | ✅ 方案 1，成本最低，但不能触发 Action |
| GitHub Issue 评论触发 bot | ❌ 复杂，需要额外 bot 常驻 |
| 外部 cron（cron-job.org）调 dispatch | ✅ 可做定时兜底，但没有页面按钮 |
| Cloudflare Worker + 页面按钮 | ✅ 本方案：安全、低成本、体验接近参考站 |
| 自建服务器 | ❌ 为一周几次触发维护服务器不划算 |

## 11. 开放问题（待用户/外审拍板）

1. 是否需要 `REFRESH_KEY` 口令？建议要，防误触和简单滥用。
2. 频率限制：全局 10 分钟 1 次是否合适？还是 5 分钟？
3. 是否同时加一个「刷新已发布数据」按钮（不触发 Action），用于只是绕过缓存？
4. Worker 用 Cloudflare 还是用户已有服务器/其他 serverless？
5. 是否需要在页面上显示最近一次 run 的日志链接（GitHub Actions URL）？
