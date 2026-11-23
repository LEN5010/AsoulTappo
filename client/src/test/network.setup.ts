// Tests never reach a server. The stores' default server is the official one, and a request still on its way when a
// test puts its stubs back would go there (GET /api/me with a new token makes a save), its answer landing in a later
// test. fetch and WebSocket refuse here, and a file whose tests got to them fails. A test that needs a server stubs
// them itself; vi.unstubAllGlobals() puts these back.
import { afterAll } from "vitest";

const reached: string[] = [];

function refuse(what: string): TypeError {
  reached.push(what);
  return new TypeError(`no network in tests: ${what}`);
}

globalThis.fetch = (input, init) => Promise.reject(
  refuse(`${init?.method ?? "GET"} ${input instanceof Request ? input.url : String(input)}`),
);
globalThis.WebSocket = class {
  constructor(url: string | URL) {
    throw refuse(`WebSocket ${String(url)}`);
  }
} as unknown as typeof WebSocket;

afterAll(() => {
  if (reached.length) throw new Error(`tests reached for the network: ${reached.join(", ")}`);
});
