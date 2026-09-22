import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  server: {
    hmr: process.env.VITE_TEST === 'true' ? false : undefined,
    watch: process.env.VITE_TEST === 'true' ? { ignored: ['**/*'] } : undefined,
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(
      ['/api', '/media', '/health'].map((p) => [
        p,
        { target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: false },
      ]),
    ),
  },
})
