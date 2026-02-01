import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './', // Required for Electron
  server: {
    host: '127.0.0.1',
    port: 3001,
    strictPort: false,
    // Optimize for faster startup
    hmr: {
      overlay: false // Disable error overlay for faster startup
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
  // Optimize dependencies for faster startup
  optimizeDeps: {
    include: ['react', 'react-dom', 'axios']
  }
})

