import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The gate API is same-origin proxied so the app needs no CORS config and no
// baked-in backend URL; override the target with BACKEND_ORIGIN.
const backend = process.env.BACKEND_ORIGIN || 'http://127.0.0.1:8191'
const comfy = process.env.COMFY_ORIGIN || 'http://127.0.0.1:8188'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5180,
    // /comfy/view serves the generated PNGs straight from the engine -- proxying
    // keeps the origin single so the app never learns ComfyUI's host.
    proxy: { '/batches': backend, '/health': backend, '/tasks': backend, '/models': backend,
             '/templates': backend, '/storage': backend,
             '/comfy': { target: comfy, rewrite: (p) => p.replace(/^\/comfy/, '') } },
  },
})
