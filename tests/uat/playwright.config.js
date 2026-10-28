const { defineConfig } = require("@playwright/test");
const path = require("path");

module.exports = defineConfig({
  testDir: ".",
  testMatch: "app.spec.js",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["line"], ["json", { outputFile: "../../.uat/playwright-results/results.json" }]],
  outputDir: "../../.uat/playwright-results/artifacts",
  webServer: {
    command: '".venv\\Scripts\\python.exe" manage.py runserver 127.0.0.1:8010 --noreload --settings=config.uat_settings --no-color',
    cwd: path.resolve(__dirname, "../.."),
    url: "http://127.0.0.1:8010/login/",
    reuseExistingServer: true,
    timeout: 30_000
  },
  use: {
    baseURL: process.env.UAT_BASE_URL || "http://127.0.0.1:8010",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure"
  }
});
