// Tests of the standalone edition (src/edition.ts): the same code with __STANDALONE__ true. Built on its own rather
// than merged with vite.config.ts, whose include and setup files are the online edition's.
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import pkg from "./package.json" with { type: "json" };

export default defineConfig({
  plugins: [vue()],
  define: { __APP_VERSION__: JSON.stringify(pkg.version), __STANDALONE__: "true" },
  test: {
    environment: "node", include: ["src/**/*.standalone.test.ts"],
    setupFiles: ["src/test/network.setup.ts", "src/test/standalone.setup.ts"],
  },
});
