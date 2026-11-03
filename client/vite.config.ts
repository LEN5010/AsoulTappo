import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

// Tauri expects a fixed dev port (see src-tauri/tauri.conf.json).
export default defineConfig({
  plugins: [vue()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  build: { target: "es2022", chunkSizeWarningLimit: 1500 },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
