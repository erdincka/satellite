// Thin wrapper over the server API. Every call returns parsed JSON or throws.

async function call(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(text || `${response.status} ${response.statusText}`)
  }
  return response.status === 204 ? null : response.json()
}

export const api = {
  state: () => call('/api/state'),
  connections: () => call('/api/connections'),
  updateConnection: (side, body) =>
    call(`/api/connections/${side}`, { method: 'PUT', body: JSON.stringify(body) }),
  testConnection: (side, body) =>
    call(`/api/connections/${side}/test`, { method: 'POST', body: JSON.stringify(body) }),
  setRunning: (side, value) =>
    call(`/api/sites/${side}/run?value=${value}`, { method: 'POST' }),
  step: (side) => call(`/api/sites/${side}/step`, { method: 'POST' }),
  configure: (side) => call(`/api/sites/${side}/configure`, { method: 'POST' }),
  reset: (side) => call(`/api/sites/${side}/reset`, { method: 'POST' }),
  request: (key) => call(`/api/sites/EDGE/request/${encodeURIComponent(key)}`, { method: 'POST' }),
  ask: (side, key, question) =>
    call(`/api/assets/${side}/${encodeURIComponent(key)}/ask`,
         { method: 'POST', body: JSON.stringify({ question }) }),
  catalogue: (side) => call(`/api/catalogue/${side}`),
  getModel: () => call('/api/model'),
  setModel: (body) => call('/api/model', { method: 'PUT', body: JSON.stringify(body) }),
  setPace: (body) => call('/api/pace', { method: 'PUT', body: JSON.stringify(body) }),
  setLink: (body) => call('/api/link', { method: 'PUT', body: JSON.stringify(body) }),
  syncNow: () => call('/api/link/sync', { method: 'POST' }),
  mirrorNow: () => call('/api/link/mirror', { method: 'POST' }),
}

export const imageUrl = (side, key) =>
  `/api/assets/${side}/${encodeURIComponent(key)}/image`
