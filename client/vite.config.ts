import { loadEnv } from "vite";
import { configDefaults, defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import pkg from "./package.json" with { type: "json" };
import { bundlePacks, dropOnline } from "./standalone-packs.js";

// Tauri expects a fixed dev port (see src-tauri/tauri.conf.json).
// The page shows its version and compares it with the latest release. Tester builds
// (.github/workflows/debug-build.yml) override the app version and pass it in
// ASOULTAPPO_VERSION; every other build uses package.json.
// The standalone edition (src/edition.ts) is built with `--mode standalone` (npm run build:standalone, which works the
// same on Windows) or with ASOULTAPPO_EDITION=standalone.
export default defineConfig(({ mode }) => {
  const standalone = mode === "standalone" || loadEnv(mode, false, "ASOULTAPPO_EDITION").ASOULTAPPO_EDITION === "standalone";
  return {
    plugins: [vue(), ...(standalone ? [bundlePacks(), dropOnline()] : [])],
    define: {
      __APP_VERSION__: JSON.stringify(loadEnv(mode, false, "ASOULTAPPO_VERSION").ASOULTAPPO_VERSION || pkg.version),
      __STANDALONE__: JSON.stringify(standalone),
    },
    clearScreen: false,
    server: { port: 1420, strictPort: true },
    // Two pages: the desk and panel share index.html, the capture window has its own (src/capture.ts).
    build: { target: "es2022", assetsInlineLimit: 0, chunkSizeWarningLimit: 1500, rollupOptions: { input: ["index.html", "capture.html"] } },
    // The standalone edition's tests run with their own config (vitest.standalone.config.ts).
    test: {
      environment: "node", include: ["src/**/*.test.ts"], exclude: [...configDefaults.exclude, "src/**/*.standalone.test.ts"],
      setupFiles: ["src/test/network.setup.ts", "src/test/economy.setup.ts"],
    },
  };
});
