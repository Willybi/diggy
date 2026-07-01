import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { visualizer } from 'rollup-plugin-visualizer'

export default defineConfig({
  plugins: [
    vue(),
    // Activer avec : ANALYZE=true npm run build
    process.env.ANALYZE && visualizer({ open: true, gzipSize: true }),
  ].filter(Boolean),
  test: {
    environment: 'jsdom',
    globals: true,
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://api:8000',
        changeOrigin: true,
      },
    },
  },
})
