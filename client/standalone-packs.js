// The standalone edition has no server to fetch `pack:` files from (src/manifest.ts resolveAsset): the build copies
// them from assets-packs at the repository root into the output under packs/. Only vite.config.ts uses the plugin,
// and only for the standalone edition, so the online build's output does not grow. Plain JavaScript: the type check
// has no Node types (standalone-packs.d.ts declares what is used from TypeScript).
import { cpSync, existsSync, mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const PACKS_DIR = fileURLToPath(new URL("../assets-packs", import.meta.url));
/** Every kind the bundled manifest refers to with `pack:`. */
export const PACK_KINDS = ["cards", "holo", "plates", "themes"];

/** Every file under [dir], as paths relative to it with forward slashes, sorted. */
export function listFiles(dir) {
  return readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((e) => e.isFile())
    .map((e) => relative(dir, join(e.parentPath ?? e.path, e.name)).split("\\").join("/"))
    .sort();
}

/** Copies every kind into [outDir]/packs and checks that each arrived whole. */
export function copyPacks(outDir) {
  for (const kind of PACK_KINDS) {
    const from = resolve(PACKS_DIR, kind);
    if (!existsSync(from)) throw new Error(`standalone build: ${from} is missing`);
    const to = resolve(outDir, "packs", kind);
    cpSync(from, to, { recursive: true });
    if (listFiles(to).join("\n") !== listFiles(from).join("\n")) throw new Error(`standalone build: ${to} is incomplete`);
  }
}

/** A fresh empty directory for the tests. */
export const tempDir = () => mkdtempSync(join(tmpdir(), "asoultappo-packs-"));

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
      copyPacks(outDir);
    },
  };
}
