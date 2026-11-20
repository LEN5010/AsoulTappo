import { describe, expect, it } from "vitest";
import {
  CARDS, GUIDE_TEXT, GUIDE_V, cleanGuide, deskCard, guideDue, guideLeft, lineLength, mergeGuide, startGuide, withDone,
  type Card, type DeskFacts, type Guide,
} from "./guide";
import { loadSettings } from "./stores/settings";
import { TERMS_VERSION } from "./legal";

const STRIP = ["count", "draw", "menu", "grip"];

function desk(over: Partial<DeskFacts> = {}): DeskFacts {
  return { agreed: true, busy: false, panelBusy: false, panelVisible: false, tapped: true, targets: new Set(STRIP), ...over };
}
const started = (...done: Card[]): Guide => done.reduce(withDone, startGuide());
const storage = (value: unknown) => ({ getItem: () => JSON.stringify(value) });

describe("guide progress in the settings", () => {
  it("starts for a save from 1.2.5, which has no guide yet", () => {
    // Terms current, the statement of the version before: the 1.2.6 statement comes first.
    for (const termsAgreed of [TERMS_VERSION, "2026-11-01"]) {
      const s = loadSettings(storage({ termsAgreed, statementSeen: "1.2.5", scale: 1 }));
      expect(s.guide).toEqual({ v: 0, done: [] });
      expect(guideDue(s.guide)).toBe(true);
      expect(s.termsAgreed).toBe(termsAgreed);
    }
  });

  it("keeps a started guide and drops what it does not know", () => {
    const s = loadSettings(storage({ guide: { v: GUIDE_V, done: ["tap", "tap", "nope", "bag", 3], off: true } }));
    expect(s.guide).toEqual({ v: GUIDE_V, done: ["tap"] });
    expect(guideDue(s.guide)).toBe(false);
  });

  it("never shares the default object between loads", () => {
    const a = loadSettings(storage({ guide: "broken" }));
    const b = loadSettings(storage({ guide: null }));
    expect(a.guide).not.toBe(b.guide);
    expect(cleanGuide([1, 2])).toEqual({ v: 0, done: [] });
  });

  it("keeps every line to twelve characters", () => {
    for (const c of CARDS) expect(lineLength(GUIDE_TEXT[c]), c).toBeLessThanOrEqual(12);
  });
});

describe("the first run of a fresh install", () => {
  const g = started();

  it("waits for the terms, the panel's opening queue and the first input", () => {
    expect(deskCard(startGuide(), desk({ agreed: false }))).toBeNull();
    expect(deskCard(g, desk({ panelVisible: true, panelBusy: true }))).toBeNull();
    expect(deskCard(g, desk({ tapped: false }))).toBeNull();
    expect(deskCard(cleanGuide(undefined), desk())).toBeNull();
  });

  it("goes tap and draw, then panel and handle once the panel is closed", () => {
    expect(deskCard(g, desk({ panelVisible: true }))).toBe("tap");
    expect(deskCard(started("tap"), desk({ panelVisible: true }))).toBe("draw");
    // The panel stays open: the panel's step waits for it to close.
    expect(deskCard(started("tap", "draw"), desk({ panelVisible: true }))).toBeNull();
    expect(deskCard(started("tap", "draw"), desk())).toBe("panel");
    expect(deskCard(started("tap", "draw", "panel"), desk())).toBe("grip");
    expect(deskCard(started(...CARDS), desk())).toBeNull();
  });

  it("waits while something else holds the spot over the pet", () => {
    expect(deskCard(g, desk({ busy: true }))).toBeNull();
  });
});

describe("an upgrader from 1.2.5", () => {
  it("gets the panel step only after the tap step, though the statement kept the panel open", () => {
    // The first input has not come yet and the panel is closed: nothing jumps ahead of the first step.
    expect(deskCard(started(), desk({ tapped: false }))).toBeNull();
    expect(deskCard(started(), desk())).toBe("tap");
  });

  it("with no draws: the draw step waits for the key, the later steps go on, and it comes once there are draws", () => {
    const noDraw = new Set(["count", "menu", "grip"]);
    expect(deskCard(started("tap"), desk({ targets: noDraw }))).toBe("panel");
    expect(deskCard(started("tap", "panel"), desk({ targets: noDraw }))).toBe("grip");
    expect(deskCard(started("tap", "panel", "grip"), desk({ targets: noDraw }))).toBeNull();
    expect(deskCard(started("tap", "panel", "grip"), desk())).toBe("draw");
  });

  it("with the name plate in the strip's place: only the handle is there", () => {
    expect(deskCard(started(), desk({ targets: new Set(["grip"]) }))).toBe("grip");
  });

  it("with the pet docked: no strip, so no card until it is back", () => {
    expect(deskCard(started(), desk({ targets: new Set() }))).toBeNull();
    expect(deskCard(started(), desk())).toBe("tap");
  });

  it("macOS without the permission: no input, so no card", () => {
    expect(deskCard(started(), desk({ tapped: false, busy: true }))).toBeNull();
    expect(deskCard(started(), desk({ tapped: false }))).toBeNull();
  });
});

describe("progress from another window", () => {
  it("keeps what either answered", () => {
    const local: Guide = { v: 1, done: ["tap", "draw"] };
    const incoming: Guide = { v: 1, done: ["tap", "grip"] };
    expect(mergeGuide(local, incoming)).toEqual({ v: 1, done: ["tap", "draw", "grip"] });
    expect(mergeGuide(incoming, local)).toEqual({ v: 1, done: ["tap", "grip", "draw"] });
  });

  it("lets a guide started again for a newer version replace the older one", () => {
    const old: Guide = { v: 1, done: ["tap"] };
    const fresh: Guide = { v: 2, done: [] };
    expect(mergeGuide(old, fresh)).toEqual(fresh);
    expect(mergeGuide(fresh, old)).toEqual(fresh);
  });

  it("tells whether cards are left: none once the four steps are answered", () => {
    expect(guideLeft(started())).toBe(true);
    expect(guideLeft(started("tap", "draw", "panel"))).toBe(true);
    expect(guideLeft(started("tap", "draw", "panel", "grip"))).toBe(false);
  });
});
