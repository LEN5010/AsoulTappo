import type { Plugin } from "vite";
export const PACKS_DIR: string;
export const PACK_KINDS: string[];
export function listFiles(dir: string): string[];
export function copyPacks(outDir: string): void;
export function tempDir(): string;
export function bundlePacks(): Plugin;
