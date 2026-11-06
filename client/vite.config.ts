import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import pkg from "./package.json" with { type: "json" };

// Tauri expects a fixed dev port (see src-tauri/tauri.conf.json).
export default defineConfig({
  plugins: [vue()],
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  build: { target: "es2022", chunkSizeWarningLimit: 1500 },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
