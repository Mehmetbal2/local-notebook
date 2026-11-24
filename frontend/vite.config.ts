import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  server: {
    proxy: {
      // xfwd adds X-Forwarded-For, so the backend (which trusts it only from this
      // machine) sees each user's own address, e.g. for the sign-in attempt limit.
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8081',
        changeOrigin: true,
        xfwd: true,
      },
      '/health': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8081',
        changeOrigin: true,
        xfwd: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Emit .js instead of .mjs so servers without an .mjs MIME mapping still serve them
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        // Large libraries get their own long-lived chunks: the project page no longer ships
        // as a single 1.1 MB file, and a release that only changes app code leaves these cached.
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('pdfjs-dist')) return 'vendor-pdfjs'
          if (id.includes('katex')) return 'vendor-katex'
          if (id.includes('marked') || id.includes('diff-match-patch')) return 'vendor-text'
          if (/node_modules\/(@vue|vue|vue-router|vue-i18n|@intlify)\//.test(id)) return 'vendor-vue'
          return 'vendor'
        },
      }
    }
  }
})
