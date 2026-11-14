// Tests run on the example economy (server/economy.example.json), never on the live numbers, which are not in the
// repository: expectations come from that file or from the store. Node has no local storage; a stand-in keeps the
// economy's entry only (src/stores/economy.ts reads it), so modules loaded again after vi.resetModules() find it too
// and nothing else changes. Tests that stub local storage themselves add it with withEconomy (./economy.ts).
import { watch } from "vue";
import { ECONOMY_KEY, exampleEconomy } from "./economy";

let entry: string | null = null;
(globalThis as { localStorage?: Pick<Storage, "getItem" | "setItem" | "removeItem"> }).localStorage ??= {
  getItem: (k) => (k === ECONOMY_KEY ? entry : null),
  setItem: (k, v) => { if (k === ECONOMY_KEY) entry = v; },
  removeItem: (k) => { if (k === ECONOMY_KEY) entry = null; },
};

const { settings } = await import("../stores/settings");
const { setEconomy } = await import("../stores/economy");
const load = () => setEconomy(exampleEconomy);
load();
// Tests that switch servers keep it.
watch(() => settings.serverUrl, load, { flush: "sync" });
