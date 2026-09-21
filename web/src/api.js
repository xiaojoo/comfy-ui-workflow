async function req(method, url, body) {
  const r = await fetch(url, {
    method,
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const text = await r.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = null }
  if (!r.ok) {
    const detail = data?.detail ?? data?.message ?? text.slice(0, 300)
    const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    err.status = r.status
    throw err
  }
  return data
}

export const api = {
  health: () => req('GET', '/health'),
  models: () => req('GET', '/models'),
  templates: () => req('GET', '/templates'),
  tasks: (limit = 20) => req('GET', `/tasks?limit=${limit}`),
  task: (id) => req('GET', `/tasks/${id}`),
  createTask: (body) => req('POST', '/tasks', body),
  favorite: (id, favorite) => req('POST', `/tasks/${id}/favorite`, { favorite }),
  batches: (limit = 50) => req('GET', `/batches?limit=${limit}`),
  batch: (id) => req('GET', `/batches/${id}`),
  gate: (id) => req('GET', `/batches/${id}/gate`),
  create: (payload) => req('POST', '/batches', payload),
  approve: (batchId, assetId, approve) =>
    req('POST', `/batches/${batchId}/assets/${assetId}/approve`, { approve }),
  svg: (batchId, assetId, stage) =>
    req('GET', `/batches/${batchId}/assets/${assetId}/svg?stage=${stage}`),
}
