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
  exportWorkflow: (body) => req('POST', '/workflow/export', body),
  pushWorkflow: (body) => req('POST', '/workflow/push', body),
  workflowMeta: (id, body) => req('PUT', `/workflow/${id}/meta`, body),
  setCover: (id, body) => req('POST', `/workflow/${id}/cover`, body),
  clearCover: (id) => req('DELETE', `/workflow/${id}/cover`),
  tasks: (limit = 20) => req('GET', `/tasks?limit=${limit}`),
  task: (id) => req('GET', `/tasks/${id}`),
  createTask: (body) => req('POST', '/tasks', body),
  favorite: (id, favorite) => req('POST', `/tasks/${id}/favorite`, { favorite }),
  deleteOutput: (id, body) => req('POST', `/tasks/${id}/delete-output`, body),
  flows: () => req('GET', '/flows'),
  flow: (id) => req('GET', `/flows/${id}`),
  createFlow: (body) => req('POST', '/flows', body),
  updateFlow: (id, body) => req('PUT', `/flows/${id}`, body),
  deleteFlow: (id) => req('DELETE', `/flows/${id}`),
  runFlow: (id) => req('POST', `/flows/${id}/run`),
  flowRun: (ref) => req('GET', `/flows/runs/${ref}`),
  batches: (limit = 50) => req('GET', `/batches?limit=${limit}`),
  batch: (id) => req('GET', `/batches/${id}`),
  gate: (id) => req('GET', `/batches/${id}/gate`),
  create: (payload) => req('POST', '/batches', payload),
  approve: (batchId, assetId, approve) =>
    req('POST', `/batches/${batchId}/assets/${assetId}/approve`, { approve }),
  svg: (batchId, assetId, stage) =>
    req('GET', `/batches/${batchId}/assets/${assetId}/svg?stage=${stage}`),
}
