import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: resolve(tmpdir(), `paperwise-playwright-${process.pid}`),
  reporter: "line",
  fullyParallel: false,
  workers: 1,
  webServer: [
    {
      command: ".\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18000",
      cwd: resolve("../backend"),
      url: "http://127.0.0.1:18000/api/health",
      reuseExistingServer: false,
      env: {
        ...process.env,
        PAPERWISE_DATA_DIR: resolve(tmpdir(), `paperwise-e2e-${process.pid}`),
        PAPERWISE_FRONTEND_ORIGIN: "http://127.0.0.1:15173",
      },
    },
    {
      command: "npm.cmd run dev -- --host 127.0.0.1 --port 15173",
      cwd: resolve("."),
      url: "http://127.0.0.1:15173",
      reuseExistingServer: false,
      env: {
        ...process.env,
        VITE_API_BASE_URL: "http://127.0.0.1:18000/api",
      },
    },
  ],
  use: {
    baseURL: "http://127.0.0.1:15173",
    headless: true,
  },
});
