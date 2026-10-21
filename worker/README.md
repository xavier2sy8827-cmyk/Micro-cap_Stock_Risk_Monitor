# 页面「更新数据」按钮的 Cloudflare Worker

Cloudflare Worker：接收页面按钮的 `POST /refresh`，用服务端 secret 的 GitHub PAT 触发 `daily.yml`；`GET /status` 返回最近一次 run 和 data 分支的 `data_through`。

## 首次部署

```powershell
cd worker
wrangler login          # 只需一次
wrangler secret put GITHUB_TOKEN   # 粘贴 fine-grained PAT（Actions: Read and write），输入不回显
wrangler deploy
```

部署输出会给出：

```
https://wp-refresh.<你的 workers.dev 子域名>.workers.dev
```

把这个 URL 配到仓库的 **Settings → Secrets and variables → Actions → Variables**：

- `REFRESH_ENDPOINT` = 上面的 Worker URL

之后重新跑一次 deploy 工作流，页面右上角会出现「更新数据」按钮。

## 可选口令

如需防误点，再加一个 secret：

```powershell
wrangler secret put REFRESH_KEY
```

配置后页面首次点击会提示输入口令，存在浏览器 localStorage。

## 验证

```powershell
curl.exe -s -o status.json -w "HTTP=%{http_code}`n" `
  -H "Origin: https://xavier2sy8827-cmyk.github.io" `
  "https://wp-refresh.<你的子域名>.workers.dev/status"

Get-Content status.json
```

`/refresh` 的 CORS 只允许 Pages Origin；GitHub token 只存在 Worker secret，不进入前端。

## 回滚

```powershell
wrangler rollback
```

或重新部署上一版代码。
