import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import UnoCSS from 'unocss/vite'
import { fileURLToPath, URL } from 'node:url'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), UnoCSS()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    // Tests do not assert stylesheet rules; disabling CSS cuts jsdom parse cost.
    css: false,
    // DOM-heavy Ant Design suites thrash under high parallelism; keep a moderate worker cap.
    fileParallelism: true,
    maxWorkers: 4,
    testTimeout: 8_000,
    hookTimeout: 8_000,
    pool: 'forks',
  },

  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 3500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('/react/') || id.includes('/react-dom/')) return 'react'
          if (id.includes('/@tanstack/')) return 'tanstack'
          if (id.includes('/@ant-design/x-markdown/')) return 'x-markdown'
          if (id.includes('/antd/') || id.includes('/@ant-design/icons/')) return 'antd'
          if (id.includes('/echarts/') || id.includes('/echarts-for-react/')) return 'echarts'
          if (id.includes('/i18next/') || id.includes('/react-i18next/')) return 'i18n'
          return 'vendor'
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      '/schedules': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
    watch: {
      ignored: ['**/node_modules/**', '**/logs/**', '**/.logs/**', '**/.git/**', '**/dist/**', '**/frontend/.cache/**'],
    },
  },
})
