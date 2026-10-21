// 页面「更新数据」按钮的 Cloudflare Worker。
// 只做三件事：CORS/口令/限流校验、触发 GitHub Actions、返回 run 与 data 分支版本。

interface Env {
  GITHUB_TOKEN: string
  REPO: string
  OWNER: string
  WORKFLOW: string
  REF: string
  ALLOWED_ORIGIN: string
  REFRESH_KEY?: string
  RATE_KV: KVNamespace
}

const ACTIVE = new Set(['queued', 'in_progress', 'waiting', 'requested'])
const RATE_MS = 10 * 60 * 1000
const TTL = { expirationTtl: 86400 }

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  })
}

function cors(res: Response, env: Env): Response {
  const h = new Headers(res.headers)
  h.set('Access-Control-Allow-Origin', env.ALLOWED_ORIGIN)
  h.set('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
  h.set('Access-Control-Allow-Headers', 'Content-Type, X-Refresh-Key')
  h.set('Access-Control-Max-Age', '86400')
  h.set('Vary', 'Origin')
  h.set('X-Content-Type-Options', 'nosniff')
  return new Response(res.body, { status: res.status, headers: h })
}

function equal(a: string, b: string): boolean {
  if (a.length !== b.length) return false
  let out = 0
  for (let i = 0; i < a.length; i += 1) out |= a.charCodeAt(i) ^ b.charCodeAt(i)
  return out === 0
}

function ghHeaders(env: Env): HeadersInit {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'wp-refresh-worker',
  }
}

async function gh(env: Env, path: string, init?: RequestInit): Promise<Response> {
  return fetch(`https://api.github.com${path}`, {
    ...init,
    headers: { ...ghHeaders(env), ...(init?.headers ?? {}) },
  })
}

async function latestRun(env: Env): Promise<any | null> {
  const r = await gh(
    env,
    `/repos/${env.OWNER}/${env.REPO}/actions/workflows/${env.WORKFLOW}/runs?per_page=1`,
  )
  if (!r.ok) return null
  const data = (await r.json()) as { workflow_runs?: any[] }
  return data.workflow_runs?.[0] ?? null
}

async function readDataMeta(env: Env): Promise<Record<string, unknown>> {
  try {
    const r = await fetch(
      `https://raw.githubusercontent.com/${env.OWNER}/${env.REPO}/data/meta.json?ts=${Date.now()}`,
      { cf: { cacheTtl: 30 } } as RequestInit,
    )
    if (!r.ok) return {}
    return (await r.json()) as Record<string, unknown>
  } catch {
    return {}
  }
}

async function status(env: Env): Promise<Record<string, unknown>> {
  const run = await latestRun(env)
  const meta = await readDataMeta(env)
  const dispatchedAt = await env.RATE_KV.get('last_dispatch')
  return {
    ok: true,
    active: !!run && ACTIVE.has(String(run.status)),
    dispatched_at: dispatchedAt,
    run: run
      ? {
          status: run.status,
          conclusion: run.conclusion,
          created_at: run.created_at,
          html_url: run.html_url,
        }
      : null,
    last_data_through: meta.data_through ?? null,
    last_generated_at: meta.generated_at ?? null,
  }
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url)
    const origin = req.headers.get('Origin') ?? ''

    if (req.method === 'OPTIONS') {
      return cors(new Response(null, { status: 204 }), env)
    }
    if (origin !== env.ALLOWED_ORIGIN) {
      return cors(json({ error: 'origin' }, 403), env)
    }

    if (url.pathname === '/status' && req.method === 'GET') {
      return cors(json(await status(env)), env)
    }
    if (url.pathname !== '/refresh' || req.method !== 'POST') {
      return cors(json({ error: 'not_found' }, 404), env)
    }

    if (env.REFRESH_KEY && !equal(req.headers.get('X-Refresh-Key') ?? '', env.REFRESH_KEY)) {
      return cors(json({ error: 'key' }, 401), env)
    }

    const now = Date.now()
    const last = await env.RATE_KV.get('last_refresh')
    if (last && now - Number(last) < RATE_MS) {
      const retry = Math.ceil((RATE_MS - (now - Number(last))) / 1000)
      return cors(json({ error: 'rate', retry_after: retry }, 429), env)
    }

    const run = await latestRun(env)
    if (run && ACTIVE.has(String(run.status))) {
      return cors(json({ error: 'running', run_url: run.html_url }, 409), env)
    }

    // 先占位，避免并发请求同时 dispatch；失败再删除。
    await env.RATE_KV.put('last_refresh', String(now), TTL)
    const res = await gh(
      env,
      `/repos/${env.OWNER}/${env.REPO}/actions/workflows/${env.WORKFLOW}/dispatches`,
      { method: 'POST', body: JSON.stringify({ ref: env.REF }) },
    )
    if (!res.ok) {
      await env.RATE_KV.delete('last_refresh')
      return cors(json({ error: 'github', status: res.status }, 502), env)
    }

    const dispatchedAt = new Date().toISOString()
    await env.RATE_KV.put('last_dispatch', dispatchedAt, TTL)
    return cors(json({ ok: true, status: 'dispatched', ref: env.REF, dispatched_at: dispatchedAt }, 202), env)
  },
}
