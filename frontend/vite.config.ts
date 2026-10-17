import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Em desenvolvimento o Vite encaminha /api e /ws ao backend (porta 8000),
// então o código usa sempre URLs relativas — igual à produção com Nginx.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000' },
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
});
