// The standalone edition has no server to fetch `pack:` files from (src/manifest.ts resolveAsset): the build copies
// them from assets-packs at the repository root into the output under packs/. Only vite.config.ts uses this, and only
// for the standalone edition, so the online build's output does not grow. Plain JavaScript: the type check has no
// Node types.
import { cpSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PACKS_DIR = fileURLToPath(new URL("../assets-packs", import.meta.url));
/** Every kind the bundled manifest refers to with `pack:`. */
export const PACK_KINDS = ["cards", "holo", "plates", "themes"];

/** @returns {import("vite").Plugin} */
export function bundlePacks() {
  let outDir = "";
  return {
    name: "asoultappo-standalone-packs",
    apply: "build",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    writeBundle() {
      for (const kind of PACK_KINDS) {
        const from = resolve(PACKS_DIR, kind);
        if (!existsSync(from)) throw new Error(`standalone build: ${from} is missing`);
        cpSync(from, resolve(outDir, "packs", kind), { recursive: true });
      }
    },
  };
}
