import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Built straight into the place the API server serves static files from.
  build: { outDir: '../backend/static', emptyOutDir: true },
  server: {
    // `npm run dev` proxies to the API server so the UI can be developed with hot
    // reload against a real backend.
    proxy: {
      '/api': 'http://localhost:8080',
      '/ws': { target: 'ws://localhost:8080', ws: true },
    },
  },
})
