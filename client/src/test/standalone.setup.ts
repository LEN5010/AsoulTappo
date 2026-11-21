// The standalone edition's tests (vitest.standalone.config.ts). Node has no local storage; an in-memory one stands in,
// so the stores keep what they write as they do in the app. No economy is loaded: the standalone edition has none.
const store = new Map<string, string>();
(globalThis as { localStorage?: Pick<Storage, "getItem" | "setItem" | "removeItem" | "clear"> }).localStorage ??= {
  getItem: (k) => store.get(k) ?? null,
  setItem: (k, v) => { store.set(k, String(v)); },
  removeItem: (k) => { store.delete(k); },
  clear: () => store.clear(),
};
