import { createSSRApp, h } from "vue";
import { renderToString } from "vue/server-renderer";
import { describe, expect, it, vi } from "vitest";
import { manifest } from "../../manifest";
import RaceTrack from "./RaceTrack.vue";
import alpacaRaces from "./raceAlpaca.fixture.json";
import mapRaces from "./raceMaps.fixture.json";
import { createBoardStepper, playhead, ROUND, stepCursor, stepStart, trackOf, tuanziArt, type Race } from "./race";
import { economy } from "../../stores/economy";

const { createHash } = await vi.importActual<{
  createHash(algorithm: "sha1"): { update(html: string): { digest(encoding: "hex"): string } };
}>("node:crypto");

const CFG = economy.value!.park!.race!;
const MEMBERS = manifest.characters.map((c) => c.id);

const render = (race: Race | null, t: number) =>
  renderToString(createSSRApp({ render: () => h(RaceTrack, { race, t, track: trackOf(race?.setup, CFG.track), members: MEMBERS }) }));

const count = (html: string, cls: string) => html.match(new RegExp(`class="[^"]*\\b${cls}\\b`, "g"))?.length ?? 0;

describe("race track", () => {
  it("has a dumpling picture for every member", () => {
    expect(MEMBERS).toHaveLength(5);
    for (const m of MEMBERS) expect(tuanziArt(m)).toMatch(/\.webp/);
  });

  it("draws every square and every dumpling before, during and after a race", async () => {
    const betting: Race = {
      id: 3600, phase: "betting", opensAt: 3600, startsAt: 6900, hash: "", setup: { boost: 6, trip: 11, portal: [13, 18], flip: 8 },
      odds: { win: {}, top2: {}, last: {} }, pool: {}, bettors: 0, mine: [],
    };
    const running: Race = {
      ...betting, phase: "running", leadMs: 4000, stepMs: 2400, slowFrom: 1, slowMs: 3600, endsAt: 6920,
      start: [...MEMBERS], moves: [{ m: MEMBERS[0], dice: [3], steps: 3, from: 0, to: 3 }], ranking: [...MEMBERS],
    };
    for (const [race, t] of [[null, 0], [betting, 6000_000], [running, 6905_000], [running, 6909_000], [running, 6930_000]] as const) {
      const html = await render(race, t);
      expect(count(html, "tile")).toBe(CFG.track);
      expect(count(html, "start")).toBe(1);
      expect(count(html, "tz")).toBe(MEMBERS.length);
      // Both portal ends carry the same marker; the flip square its own.
      if (race) {
        expect(count(html, "gate")).toBe(2);
        expect(count(html, "turn")).toBe(1);
        expect(count(html, "cap") + count(html, "pit")).toBe(2);
      }
    }
  });
});

const fixtureRaces = (mapRaces as unknown as Pick<Required<Race>, "setup" | "start" | "moves" | "ranking">[]).map((fixture) => {
  const running = {
    ...fixture, id: 3600, opensAt: 3600, startsAt: 6900, phase: "running" as const, hash: "",
    odds: { win: {}, top2: {}, last: {} }, pool: {}, mine: [], leadMs: 4000, stepMs: 2400,
    slowFrom: Math.floor((fixture.moves.length - 1) / ROUND) * ROUND, slowMs: 3600,
  };
  const endsAt = running.startsAt + Math.ceil(stepStart(running, running.moves.length) / 1000);
  const times: number[] = [];
  for (let t = running.startsAt * 1000 - 250; t <= endsAt * 1000 + 1000; t += 250) times.push(t);
  return { race: { ...running, endsAt }, times };
});

it.each(fixtureRaces)("renders every quarter second on $race.setup.map.name (#$race.moves.length)", async ({ race, times }) => {
  const frames: string[] = [];
  for (const t of times) frames.push(createHash("sha1").update(await render(race, t)).digest("hex"));
  expect(frames).toMatchSnapshot();
});

// Races with the order drawn every round and the alpaca (raceAlpaca.fixture.json), played from when the server starts
// them to a second past the end.
const alpacaFixture = (alpacaRaces as unknown as Race[]).map((r) => {
  const race = { ...r, opensAt: r.id, hash: "", odds: { win: {}, top2: {}, last: {} }, pool: {}, mine: [] } as Race;
  const times: number[] = [];
  for (let t = race.startsAt * 1000 - 250; t <= race.endsAt! * 1000 + 1000; t += 250) times.push(t);
  return { race, times };
});

it.each(alpacaFixture)("renders every quarter second with the alpaca on $race.setup.map.name (#$race.moves.length)", async ({ race, times }) => {
  const track = race.setup.map!.track;
  const board = createBoardStepper(false);
  const frames: string[] = [];
  let cars = 0;
  for (const t of times) {
    const html = await render(race, t);
    const h = playhead(race, t);
    const c = stepCursor(h);
    const b = board(race.start!, race.moves!, c.completed, c.partial, { race, driven: c.driven!, track });
    expect(count(html, "tz")).toBe(MEMBERS.length);
    expect(count(html, "midline")).toBe(1);
    // The car is on the board from its coming out on.
    const car = html.match(/class="(driving )?car"/g)?.length ?? 0;
    expect(car).toBe(b.car == null ? 0 : 1);
    cars += car;
    // Every dumpling stands where the steps and the drives so far put it, riders on the car's square.
    const where = new Map([...b.stacks].flatMap(([sq, ms]) => ms.map((m) => [m, sq] as const)));
    for (const [, m, title] of html.matchAll(/<div data-m="(\w+)" class="[^"]*\btz\b[^"]*"[^>]*title="([^"]*)"/g)) {
      const sq = where.get(m!) ?? 0;
      const said = title!.split(" · ")[1];
      if (said === "终点") expect(sq >= track || m === race.ranking![0]).toBe(true);
      else expect(said).toBe(sq ? `第 ${sq} 格` : "起点");
    }
    frames.push(createHash("sha1").update(html).digest("hex"));
  }
  expect(cars).toBeGreaterThan(0);
  expect(frames).toMatchSnapshot();
});
