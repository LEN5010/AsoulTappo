import { expect, it } from "vitest";
import { accountLoginTrusted, trustedOrigin } from "./trust";

it("trusts only the official origin in release builds", () => {
  expect(trustedOrigin("https://len5010.top/tappo", false)).toBe(true);
  expect(trustedOrigin("https://len5010.top/dynamics/api/", false)).toBe(true);
  expect(trustedOrigin("http://len5010.top/tappo", false)).toBe(false);
  expect(trustedOrigin("https://len5010.top:8443/tappo", false)).toBe(false);
  expect(trustedOrigin("https://len5010.top.evil.com/tappo", false)).toBe(false);
  expect(trustedOrigin("https://evil.com/?u=https://len5010.top", false)).toBe(false);
  expect(trustedOrigin("https://len5010.top@evil.com/", false)).toBe(false);
  expect(trustedOrigin("http://localhost:8000", false)).toBe(false);
  expect(trustedOrigin("len5010.top", false)).toBe(false);
  expect(trustedOrigin("", false)).toBe(false);
  expect(trustedOrigin(null, false)).toBe(false);
});

it("dev builds also trust local http servers on any port", () => {
  expect(trustedOrigin("http://localhost:8000", true)).toBe(true);
  expect(trustedOrigin("http://127.0.0.1:9", true)).toBe(true);
  expect(trustedOrigin("http://localhost.evil.com", true)).toBe(false);
  expect(trustedOrigin("http://192.168.1.2:8000", true)).toBe(false);
});

it("needs both the room server and the account service to be trusted", () => {
  expect(accountLoginTrusted("https://len5010.top/tappo", "https://len5010.top/dynamics/api", false)).toBe(true);
  expect(accountLoginTrusted("https://len5010.top/tappo", "https://evil.com/api", false)).toBe(false);
  expect(accountLoginTrusted("https://evil.com", "https://len5010.top/dynamics/api", false)).toBe(false);
  expect(accountLoginTrusted("https://len5010.top/tappo", null, false)).toBe(false);
});
