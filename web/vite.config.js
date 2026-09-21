import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The gate API is same-origin proxied so the app needs no CORS config and no
// baked-in backend URL; override the target with BACKEND_ORIGIN.
const backend = process.env.BACKEND_ORIGIN || 'http://127.0.0.1:8191'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5180,
    proxy: { '/batches': backend, '/health': backend },
  },
})
