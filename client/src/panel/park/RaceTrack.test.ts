import { createSSRApp, h } from "vue";
import { renderToString } from "vue/server-renderer";
import { describe, expect, it } from "vitest";
import { manifest } from "../../manifest";
import RaceTrack from "./RaceTrack.vue";
import { tuanziArt, type Race } from "./race";

const CFG = manifest.economy.park!.race!;
const MEMBERS = Object.keys(CFG.skills);

const render = (race: Race | null, t: number) =>
  renderToString(createSSRApp({ render: () => h(RaceTrack, { race, t, track: CFG.track, members: MEMBERS }) }));

const count = (html: string, cls: string) => html.match(new RegExp(`class="[^"]*\\b${cls}\\b`, "g"))?.length ?? 0;

describe("race track", () => {
  it("has a dumpling picture for every member", () => {
    for (const m of MEMBERS) expect(tuanziArt(m)).toMatch(/\.webp/);
  });

  it("draws every square and every dumpling before, during and after a race", async () => {
    const betting: Race = {
      id: 600, phase: "betting", opensAt: 600, startsAt: 1080, hash: "", setup: { moods: {}, boost: 6, trip: 11 },
      odds: { win: {}, top2: {}, last: {} }, pool: {}, mine: [],
    };
    const running: Race = {
      ...betting, phase: "running", leadMs: 3000, stepMs: 1000, endsAt: 1090, start: [...MEMBERS],
      moves: [{ m: MEMBERS[0], dice: [3], steps: 3, from: 0, to: 3, carry: MEMBERS.slice(1) }], ranking: [...MEMBERS].reverse(),
    };
    for (const [race, t] of [[null, 0], [betting, 700_000], [running, 1_083_500], [running, 1_100_000]] as const) {
      const html = await render(race, t);
      expect(count(html, "tile")).toBe(CFG.track + 1);
      expect(count(html, "tz")).toBe(MEMBERS.length);
      expect(html).toContain("终点");
    }
  });
});
