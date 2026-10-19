import { defineConfig } from '@playwright/test';

// Por padrão sobe o servidor falso (porta 8000) e o Vite (porta 5173).
// Contra o sistema real (docker compose up): E2E_BASE_URL=https://localhost E2E_NO_SERVER=1 npm run e2e
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:5173';

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: { baseURL, ignoreHTTPSErrors: true, trace: 'retain-on-failure' },
  webServer: process.env.E2E_NO_SERVER
    ? undefined
    : [
        {
          command: 'node dev/mock-server.mjs',
          url: 'http://localhost:8000/api/health',
          reuseExistingServer: true,
          env: { INVITE_TIMEOUT_S: '30', RECONNECT_GRACE_S: '30' },
        },
        {
          command: 'npm run dev -- --port 5173 --strictPort',
          url: 'http://localhost:5173',
          reuseExistingServer: true,
        },
      ],
});
