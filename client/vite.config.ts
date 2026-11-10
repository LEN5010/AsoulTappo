import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import pkg from "./package.json" with { type: "json" };

// Tauri expects a fixed dev port (see src-tauri/tauri.conf.json).
// The page shows its version and compares it with the latest release. Tester builds
// (.github/workflows/debug-build.yml) override the app version and pass it in
// ASOULTAPPO_VERSION; every other build uses package.json.
export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  define: {
    __APP_VERSION__: JSON.stringify(loadEnv(mode, false, "ASOULTAPPO_VERSION").ASOULTAPPO_VERSION || pkg.version),
  },
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  build: { target: "es2022", chunkSizeWarningLimit: 1500 },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
}));
