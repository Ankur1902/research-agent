import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "tests",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
  },
  timeout: 120000,
  workers: 1,
});
