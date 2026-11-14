// The example economy for tests (server/economy.example.json) and the local-storage entry the economy store reads, for
// tests that stub local storage themselves.
import example from "../../../server/economy.example.json";
import { toHttpBase } from "../net/protocol";
import type { Economy } from "../stores/economy";

export const ECONOMY_KEY = "asoultappo.economy.v1";
const { antiCheat: _server, _note: _about, ...data } = example;
export const exampleEconomy = data as unknown as Economy;
/** The default server of src/stores/settings.ts. */
const DEFAULT_SERVER = "https://len5010.top/tappo";

export const economyEntry = (serverUrl = DEFAULT_SERVER) =>
  JSON.stringify({ server: toHttpBase(serverUrl), at: Date.now(), data: exampleEconomy });

/** A stubbed getItem that also has the example economy for [serverUrl]. */
export const withEconomy = (get: (k: string) => string | null, serverUrl?: string) =>
  (k: string) => (k === ECONOMY_KEY ? economyEntry(serverUrl) : get(k));
