import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import UnoCSS from 'unocss/vite'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), UnoCSS()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 3500,
    rolldownOptions: {
      onLog(level, log, handler) {
        const code = typeof log === 'string' ? '' : log.code
        const message = typeof log === 'string' ? log : log.message
        const id = typeof log === 'string' ? '' : log.id
        if (
          code === 'INVALID_ANNOTATION' &&
          id?.includes('/@vueuse/core/') &&
          message.includes('#__PURE__')
        ) {
          return
        }
        handler(level, log)
      },
    },
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('/vue/') || id.includes('/pinia/') || id.includes('/vue-i18n/')) return 'vue'
          if (id.includes('/element-plus/') || id.includes('/@element-plus/icons-vue/')) return 'element'
          if (id.includes('/markdown-it/') || id.includes('/highlight.js/')) return 'markdown'
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
      ignored: ['**/node_modules/**', '**/logs/**', '**/.git/**', '**/dist/**', '**/frontend/.cache/**'],
    },
  },
})
