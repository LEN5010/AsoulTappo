import type { Plugin } from "vite";
export const PACKS_DIR: string;
export const PACK_KINDS: string[];
export function listFiles(dir: string): string[];
export function copyPacks(outDir: string): void;
export function tempDir(): string;
type BundleFile =
  | { type: "chunk"; fileName: string; code: string }
  | { type: "asset"; fileName: string; source: string | Uint8Array; originalFileNames: string[] };
export function dropOnlineFiles(bundle: Record<string, BundleFile>): void;
export function dropOnline(): Plugin;
export function bundlePacks(): Plugin;
