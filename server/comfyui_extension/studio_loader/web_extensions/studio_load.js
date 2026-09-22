// Open a workflow on this canvas when the local comfy-ui-workflow app asks for one.
//
// The app writes the file into this server's own `workflows/studio/` through ComfyUI's
// userdata API, then posts its path here -- so the fetch below is same-origin and nothing
// in ComfyUI needs a CORS exception. Without this file the feature degrades by one click:
// the workflow still appears in the Workflow menu, it just is not loaded by itself.
//
// Needs an engine restart to be served: ComfyUI registers /extensions/<name> routes at
// startup (server.py:1247), not per request.
(() => {
  // Only the local desk app. Any page that can load a workflow could also replace whatever
  // is on this canvas, so the door stays on localhost rather than opening for every origin.
  const allowed = (o) => /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(o)

  const wait = (ms) => new Promise((r) => setTimeout(r, ms))

  async function app() {
    for (let i = 0; i < 200; i++) {
      const a = window.comfyAPI && window.comfyAPI.app && window.comfyAPI.app.app
      if (a && a.loadGraphData) return a
      await wait(100)
    }
    return null
  }

  async function run(a, path, source, origin) {
    // A message posted from this same window arrives with source === null, so the reply has
    // to fall back to this window; the desk app's own tab always arrives as a real source.
    const say = (type, extra) => {
      const target = source || window
      try {
        target.postMessage(Object.assign({ type, path }, extra), origin || location.origin)
      } catch { /* the opener may already be gone */ }
    }
    let wf
    try {
      const r = await fetch(`/userdata/${encodeURIComponent(path)}`)
      if (!r.ok) return say('studio:failed', { error: `HTTP ${r.status}` })
      wf = await r.json()
    } catch (e) {
      return say('studio:failed', { error: String(e && e.message || e) })
    }
    if (!wf || !Array.isArray(wf.nodes)) return say('studio:failed', { error: '不是工作流文件' })
    // The menu's own "Open" does this too: a half-loaded graph from a failed load reads as
    // a broken file rather than as the error it is.
    a.graph.clear()
    try {
      await a.loadGraphData(wf)
    } catch (e) {
      return say('studio:failed', { error: String(e && e.message || e) })
    }
    a.graph.setDirtyCanvas(true, true)
    say('studio:loaded', { nodes: a.graph._nodes.length })
  }

  let queue = []
  window.addEventListener('message', (e) => {
    const d = e.data || {}
    if (d.type !== 'studio:load' || !allowed(e.origin)) return
    queue.push({ path: d.path, source: e.source, origin: e.origin })
  })

  app().then((a) => {
    if (!a) return
    setInterval(() => {
      const job = queue.shift()
      if (job) run(a, job.path, job.source, job.origin)
    }, 120)
  })
})()
