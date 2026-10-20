import { defineConfig } from "@playwright/test";

export default defineConfig({
  timeout: 90_000,
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8765",
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "uv run python scripts/e2e_server.py",
    cwd: "..",
    url: "http://127.0.0.1:8765/health",
    reuseExistingServer: false,
    env: {
      LOOTSPLIT_BACKUP_ENABLED: "false",
      LOOTSPLIT_BACKUP_PATH: "",
      LOOTSPLIT_BANK_WEBSITE: "",
      LOOTSPLIT_BANK_LOGIN: "",
      LOOTSPLIT_BANK_PASSWORD: "",
      LOOTSPLIT_BANK_LOGIN_FILE: "",
      LOOTSPLIT_BANK_PASSWORD_FILE: "",
      LOOTSPLIT_E2E_TOKEN: "e2e-key-local-fake-more-than-thirty-two-characters",
    },
  },
});
