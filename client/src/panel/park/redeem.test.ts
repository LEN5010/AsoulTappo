import { describe, expect, it } from "vitest";
import { redeemMessage } from "./redeem";

describe("redeemMessage", () => {
  it("names each refusal of a code", () => {
    expect(redeemMessage("bad_code", "x")).toBe("兑换码不存在");
    expect(redeemMessage("code_expired", "x")).toBe("兑换码已过期");
    expect(redeemMessage("code_used_up", "x")).toBe("兑换码已领完");
    expect(redeemMessage("already_redeemed", "x")).toBe("已经兑换过了");
  });

  it("falls back to the server's message", () => {
    expect(redeemMessage("offline", "无法连接服务器")).toBe("无法连接服务器");
    expect(redeemMessage("stale", "")).toBe("兑换失败");
  });
});
