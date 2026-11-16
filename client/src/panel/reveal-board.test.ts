import { describe, expect, it } from "vitest";
import { manifest } from "../manifest";
import { entriesOf, memberTone } from "./reveal-board";

describe("memberTone", () => {
  it("fills a skin's reveal with its member's colour", () => {
    const tone = memberTone("乃琳");
    expect(tone["--tone-fill"]).toContain("#4F63C9");
    expect(tone["--tone-glow"]).toBe("rgba(79, 99, 201, 0.72)");
    expect(tone["--tone-ink"]).toBe("#fff");
  });
  it("writes in dark ink on the light member colours", () => {
    expect(memberTone("嘉然")["--tone-ink"]).toBe("var(--ink)");
    expect(memberTone("贝拉")["--tone-ink"]).toBe("var(--ink)");
  });
  it("leaves an unknown skin to the default tone", () => {
    expect(memberTone("nobody")).toEqual({});
  });
});

describe("entriesOf", () => {
  const card = manifest.cards.find((c) => c.holo)!;
  const drop = (over: object) => ({ item: `card:${card.id}`, rarity: "common" as const, tier: "normal" as const, new: false, count: 1, shards: 20, ...over });

  it("lifts a first holo version into the spotlight under its own label, on the holo band", () => {
    const [e] = entriesOf([drop({ holo: true, new: true, cardNew: false, shards: 0 })]);
    expect(e!.holo).toBe(true);
    expect(e!.spot).toBe(true);
    expect(e!.kind).toBe("镭射款");
    expect(e!.tone).toBe("tone-holo");
  });

  it("shows a repeat holo version marked but without the spotlight, and a plain draw as before", () => {
    const [again, plain] = entriesOf([drop({ holo: true, new: false, cardNew: false }), drop({})]);
    expect(again!.holo).toBe(true);
    expect(again!.spot).toBe(false);
    expect(plain!.holo).toBe(false);
    expect(plain!.kind).not.toBe("镭射款");
    expect(plain!.tone).toBe("tone-common");
    expect(again!.key).not.toBe(plain!.key);
  });
});
