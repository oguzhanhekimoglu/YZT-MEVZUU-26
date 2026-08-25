import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e-backend", outputDir: "test-results/backend", timeout: 30_000,
  fullyParallel: false, workers: 1, reporter: "list",
  use: { baseURL: "http://127.0.0.1:4173/goruntule/", locale: "tr-TR", colorScheme: "dark", trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: { command: "npm run build:backend && npm run serve:e2e", url: "http://127.0.0.1:4173/goruntule/", reuseExistingServer: false, timeout: 120_000 },
  projects: [{ name: "backend-chromium", use: { browserName: "chromium" } }],
});
