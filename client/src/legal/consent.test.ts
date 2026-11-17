import { beforeEach, describe, expect, it } from "vitest";
import { settings } from "../stores/settings";
import { APP_VERSION } from "../version";
import { TERMS_VERSION } from ".";
import { HOLD_MS, agree, agreed, holdLeft, termsCurrent } from "./consent";

describe("consent", () => {
  beforeEach(() => {
    settings.termsAgreed = "";
    settings.statementSeen = "";
  });

  it("takes both the current texts and this version's statement", () => {
    expect(agreed.value).toBe(false);
    settings.termsAgreed = TERMS_VERSION;
    expect([termsCurrent.value, agreed.value]).toEqual([true, false]);
    settings.statementSeen = APP_VERSION;
    expect(agreed.value).toBe(true);
  });

  it("asks again after an update, with the texts still agreed to", () => {
    agree();
    expect(agreed.value).toBe(true);
    settings.statementSeen = "0.0.1-older";
    expect([termsCurrent.value, agreed.value]).toEqual([true, false]);
  });

  it("asks for both again when the texts change", () => {
    agree();
    settings.termsAgreed = "2020-01-01";
    expect([termsCurrent.value, agreed.value]).toEqual([false, false]);
  });

  it("keeps the key locked until the dialog has been in view for the whole hold", () => {
    expect(HOLD_MS).toBe(3000);
    expect([0, 100, 1000, 1001, 2900, 2999].map(holdLeft)).toEqual([3, 3, 2, 2, 1, 1]);
    expect([3000, 9000].map(holdLeft)).toEqual([0, 0]);
  });
});
