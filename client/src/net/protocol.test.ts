import { describe, expect, it } from "vitest";
import { toHttpBase, toWsUrl } from "./protocol";

describe("url helpers", () => {
  it("maps http(s) to ws(s) and appends /ws", () => {
    expect(toWsUrl("http://localhost:8000")).toBe("ws://localhost:8000/ws");
    expect(toWsUrl("https://tappo.example.com/")).toBe("wss://tappo.example.com/ws");
    expect(toWsUrl("https://example.com/base/")).toBe("wss://example.com/base/ws");
  });
  it("rejects garbage", () => {
    expect(() => toWsUrl("not a url")).toThrow();
  });
  it("trims trailing slashes for http base", () => {
    expect(toHttpBase(" http://x:1/// ")).toBe("http://x:1");
  });
});
