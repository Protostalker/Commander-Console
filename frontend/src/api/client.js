/**
 * API client for commander-console connector.
 *
 * All requests go to /api/* — in production these are proxied by nginx to
 * the connector container. In dev mode Vite proxies them to localhost:8100.
 */

const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch {
      // ignore parse error
    }
    throw new Error(detail)
  }

  // 204 No Content
  if (res.status === 204) return null
  return res.json()
}

/** GET /api/status — connection health */
export function fetchStatus() {
  return request('/status')
}

/** GET /api/prices — cached prices */
export function fetchPrices() {
  return request('/prices')
}

/** GET /api/prices/live — force-fetch from Commander */
export function fetchPricesLive() {
  return request('/prices/live')
}

/**
 * POST /api/prices — update prices in Commander DB
 * @param {Array<{id, name, cash?, credit?}>} grades
 * @param {boolean} pushImmediately
 */
export function updatePrices(grades, pushImmediately = false) {
  return request('/prices', {
    method: 'POST',
    body: JSON.stringify({ grades, push_immediately: pushImmediately }),
  })
}

/** POST /api/prices/push — push pending prices to dispensers */
export function pushPrices() {
  return request('/prices/push', { method: 'POST' })
}

/**
 * POST /api/prices/update-and-push — atomic update + push
 * @param {Array<{id, name, cash?, credit?}>} grades
 */
export function updateAndPush(grades) {
  return request('/prices/update-and-push', {
    method: 'POST',
    body: JSON.stringify({ grades, push_immediately: true }),
  })
}

/** GET /api/prices/history */
export function fetchHistory(limit = 50, offset = 0) {
  return request(`/prices/history?limit=${limit}&offset=${offset}`)
}

/**
 * GET /api/totals — fuel sales totals by period
 * @param {1|2|3|4} period — 1=Shift, 2=Day, 3=Month, 4=Year
 */
export function fetchTotals(period = 2) {
  return request(`/totals?period=${period}`)
}
