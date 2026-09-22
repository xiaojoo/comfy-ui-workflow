import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The gate API is same-origin proxied so the app needs no CORS config and no
// baked-in backend URL; override the target with BACKEND_ORIGIN.
const backend = process.env.BACKEND_ORIGIN || 'http://127.0.0.1:8191'
const comfy = process.env.COMFY_ORIGIN || 'http://127.0.0.1:8188'

// The API prefixes collide with page routes: /tasks is both the queue endpoint and
// the recent-tasks screen, /models both the weight catalogue and its nav entry.
// A browser navigation asks for text/html and has to reach the router; fetch() asks
// for */* and has to reach the backend. Without this the nav items serve raw JSON.
const serveApp = (req) => (req.headers.accept || '').includes('text/html') ? '/index.html' : undefined

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5180,
    // /comfy/view serves the generated PNGs straight from the engine -- proxying
    // keeps the origin single so the app never learns ComfyUI's host.
    proxy: {
      ...Object.fromEntries(['/batches', '/health', '/tasks', '/models', '/templates', '/storage', '/flows', '/workflow', '/covers']
        .map((p) => [p, { target: backend, bypass: serveApp }])),
      '/comfy': { target: comfy, rewrite: (p) => p.replace(/^\/comfy/, '') },
    },
  },
})
