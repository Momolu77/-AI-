import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60000,
  expect: { timeout: 10000 },
  workers: 1,
  fullyParallel: false,
  outputDir: '../artifacts/playwright',
  reporter: [
    ['list'],
    ['html', { outputFolder: '../artifacts/playwright-report', open: 'never' }],
    ['junit', { outputFile: '../artifacts/e2e-results.xml' }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:5174',
    channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge',
    headless: true,
    viewport: { width: 1500, height: 960 },
    permissions: ['clipboard-read', 'clipboard-write'],
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: '..\\.venv\\Scripts\\python.exe ..\\scripts\\e2e_server.py',
      url: 'http://127.0.0.1:8001/health',
      timeout: 60000,
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort',
      url: 'http://127.0.0.1:5174',
      timeout: 60000,
      reuseExistingServer: false,
      env: { VITE_API_TARGET: 'http://127.0.0.1:8001', VITE_TEST: 'true' },
    },
  ],
})
