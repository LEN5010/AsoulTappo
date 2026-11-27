// Races run by the order drawn every round and the alpaca (race.py run with setup.shuffle and setup.alpaca), as the
// server prepares and shows them (raceAlpaca.fixture.json; server/tests/gen_race_alpaca_fixture.py writes it and
// tests/test_race_alpaca.py checks it is what the rules give).
import { describe, expect, it } from "vitest";
import { manifest } from "../../manifest";
import {
  ALPACA, createBoardStepper, createStackStepper, driveTimes, ENTER_CUT, glideAt, glideWhen, leaders, leadersBefore,
  orderAt, orderDiceAt, pickupsOf, playhead, playLength, playStep, rankOf, rollStart, roundAt, roundDice, roundsOf,
  ROUND, stepCursor, stepStart, timelineOf, turnsOf, type Playhead, type Race,
} from "./race";
import fixture from "./raceAlpaca.fixture.json";

const MEMBERS = manifest.characters.map((c) => c.id);
/** Who rolls first for an order: the members in manifest order, the alpaca after them. */
const rollsBefore = (a: string, b: string) => (a === ALPACA ? MEMBERS.length : MEMBERS.indexOf(a)) - (b === ALPACA ? MEMBERS.length : MEMBERS.indexOf(b));

/** Played from startsAt as the view gives it; the betting fields a race needs and nobody reads here. */
const races = (fixture as unknown as Race[]).map((r) => ({
  ...r, opensAt: r.id, hash: "", odds: { win: {}, top2: {}, last: {} }, pool: {}, mine: [],
}) as Race);
const TAIL_MS = 4000;
const trackOfRace = (r: Race) => r.setup.map!.track;
const runOf = (r: Race, driven: number) => ({ race: r, driven, track: trackOfRace(r) });

/**
 * The board at [h] worked out from nothing: the steps and the car's changes in time order, each drive taking those on
 * the squares it passes, bottom to top from where it stops, which must be what the server says it took.
 */
function referenceBoard(r: Race, h: Playhead) {
  const tl = timelineOf(r)!;
  const c = stepCursor(h);
  const st = new Map<number, string[]>([[0, [...r.start!]]]);
  const track = trackOfRace(r);
  let car: number | null = null;
  let i = 0;
  let j = 0;
  for (;;) {
    const e = tl.cars[j];
    if (e && j < (c.driven ?? 0) && e.before <= i) {
      const d = r.drives![e.k];
      if (e.kind === "enter") car = track;
      else if (e.kind === "glide") {
        expect(car).toBe(d.from);
        const took: string[] = [];
        for (let sq = d.to; sq <= d.from; sq++) {
          took.push(...(st.get(sq) ?? []));
          st.delete(sq);
        }
        if (took.length) st.set(d.to, took);
        expect(took).toEqual(d.take ?? []);
        car = d.to;
      } else {
        if (e.kind === "back") expect(car).toBe(d.back);
        car = track;
      }
      j++;
    } else if (i < c.completed) {
      playStep(st, r.moves![i], true);
      i++;
    } else break;
  }
  if (c.partial >= 0) playStep(st, r.moves![c.partial], false);
  return { stacks: [...st], car };
}

/** Every 250 ms from just before the start to a second past the end. */
const timesOf = (r: Race) => {
  const out: number[] = [];
  for (let t = r.startsAt * 1000 - 250; t <= r.endsAt! * 1000 + 1000; t += 250) out.push(t);
  return out;
};

describe.each(races.map((race) => ({ race, name: `${race.setup.map!.name} (#${race.moves!.length})` })))("$name", ({ race }) => {
  const tl = timelineOf(race)!;

  it("plays its beats one after another to the end, as long as the server says", () => {
    expect(tl).not.toBeNull();
    let at = race.leadMs!;
    for (const b of tl.beats) {
      expect(b.at).toBeCloseTo(at, 6);
      at = b.at + b.len;
    }
    expect(tl.end + TAIL_MS).toBeCloseTo(playLength(race), 0);
    // Every step, every drive and every round's dice once, in the round the orders put them.
    expect(tl.steps).toHaveLength(race.moves!.length);
    expect(tl.beats.filter((b) => b.kind === "drive").map((b) => b.i)).toEqual(race.drives!.map((_, k) => k));
    expect(tl.rolls).toHaveLength(roundsOf(race));
    for (const b of tl.beats.filter((x) => x.kind === "drive")) expect(race.drives![b.i]!.r).toBe(b.r);
    for (let r = 0; r < roundsOf(race); r++) {
      expect(rollStart(race, r)).toBeLessThan(stepStart(race, r * ROUND));
      if (r + 1 < roundsOf(race)) expect(stepStart(race, r * ROUND + ROUND - 1)).toBeLessThan(rollStart(race, r + 1));
    }
    // The alpaca comes out right after the step that brought it, and drives from the next round on.
    const enter = tl.beats.find((b) => b.kind === "enter")!;
    const brought = tl.beats[tl.steps[race.enter!]!]!;
    expect(enter.at).toBeCloseTo(brought.at + brought.len, 6);
    expect(enter.len).toBe(race.enterMs);
    expect(tl.cars[0]).toMatchObject({ kind: "enter", at: enter.at + race.enterMs! * ENTER_CUT });
    expect(race.drives![0]!.r).toBeGreaterThan(Math.floor(race.enter! / ROUND));
  });

  it("knows where it is at any moment", () => {
    let last: Playhead | null = null;
    for (const t of timesOf(race)) {
      const h = playhead(race, t);
      if (last) {
        expect(h.done).toBeGreaterThanOrEqual(last.done);
        expect(h.driven!).toBeGreaterThanOrEqual(last.driven!);
      }
      // A drive and a step are never under way together.
      if (h.drive) expect(h.current).toBe(-1);
      last = h;
    }
    expect(last).toEqual({ done: race.moves!.length, current: -1, part: 0, driven: tl.cars.length });
    // In a drive's beat: its turn, how far in.
    const d = tl.beats.find((b) => b.kind === "drive")!;
    expect(playhead(race, race.startsAt * 1000 + d.at + 10)).toMatchObject({ current: -1, drive: { k: d.i, ms: 10 } });
    // The round on show follows the round's dice, even where the alpaca drives first.
    for (let r = 0; r < roundsOf(race); r++) expect(roundAt(race, race.startsAt * 1000 + rollStart(race, r) + 1)?.round).toBe(r);
  });

  it("steps and scrubs the board with the alpaca's turns in between", () => {
    const times = timesOf(race);
    const shuffled = [...times];
    let seed = 7;
    for (let i = shuffled.length - 1; i > 0; i--) {
      seed = (Math.imul(1664525, seed) + 1013904223) >>> 0;
      const j = Math.floor((seed / 2 ** 32) * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j]!, shuffled[i]!];
    }
    const board = createBoardStepper();
    const standings = createStackStepper();
    for (const t of [...times, ...shuffled]) {
      const h = playhead(race, t);
      const c = stepCursor(h);
      const got = board(race.start!, race.moves!, c.completed, c.partial, runOf(race, c.driven!));
      const want = referenceBoard(race, h);
      expect([...got.stacks]).toEqual(want.stacks);
      expect(got.car).toBe(want.car);
      expect([...standings(race.start!, race.moves!, c.completed, c.partial, runOf(race, c.driven!))]).toEqual(want.stacks);
    }
    // Played to the end, the board ranks as the server did.
    const end = playhead(race, race.endsAt! * 1000);
    const c = stepCursor(end);
    expect(rankOf(board(race.start!, race.moves!, c.completed, c.partial, runOf(race, c.driven!)).stacks)).toEqual(race.ranking);
  });

  it("deals each round's dice in its order, the alpaca's among them", () => {
    for (let r = 0; r < roundsOf(race); r++) {
      const turns = turnsOf(race, r);
      expect(turns.map((x) => x.m)).toEqual(race.orders![r]);
      expect(roundDice(race, r)).toEqual(turns.map(({ m, face }) => ({ m, face })));
      for (const x of turns) {
        if (x.step !== undefined) expect(race.moves![x.step]!.m).toBe(x.m);
        if (x.drive !== undefined) expect(race.drives![x.drive]!.face).toBe(x.face);
        if (x.m === ALPACA) expect(x.step).toBeUndefined();
      }
    }
    // The last round's turns after the winning move are its rest.
    const last = turnsOf(race, roundsOf(race) - 1);
    expect(last.filter((x) => x.step === undefined && x.drive === undefined)).toEqual(race.rest);
    // The order on show changes at each round's change of order; while its dice for the order are out the order
    // before stays, the alpaca's seat at its end when it rolls for a place the first time.
    for (let r = 1; r < roundsOf(race); r++) {
      const at = race.startsAt * 1000 + rollStart(race, r);
      const before = race.orders![r - 1]!;
      const joining = race.orders![r]!.includes(ALPACA) && !before.includes(ALPACA);
      const dice = race.orderRolls![r]!.length * race.orderRollMs!;
      expect(orderAt(race, at - race.shuffleMs! - dice - 1)).toEqual(before);
      expect(orderAt(race, at - race.shuffleMs! - 1)).toEqual(joining ? [...before, ALPACA] : before);
      expect(orderAt(race, at - race.shuffleMs! + 1)).toEqual(race.orders![r]);
    }
  });

  it("throws each round's dice for its order as the opening's, then lines the field up in it", () => {
    const step = race.orderRollMs!;
    const beats = tl.beats.filter((b) => b.kind === "order");
    expect(beats.map((b) => b.r)).toEqual(Array.from({ length: roundsOf(race) - 1 }, (_, k) => k + 1));
    for (const b of beats) {
      const rolls = race.orderRolls![b.r]!;
      const order = race.orders![b.r]!;
      expect(b.len).toBe(rolls.length * step);
      // Everyone taking turns rolls first, the members in their order and the alpaca after them.
      expect(rolls[0]!.map((x) => x.m)).toEqual([...order].sort(rollsBefore));
      const t0 = race.startsAt * 1000 + b.at;
      rolls.forEach((got, k) => {
        const flying = orderDiceAt(race, playhead(race, t0 + k * step + 10));
        expect(flying).toMatchObject({ r: b.r, round: k, rolling: got.map((x) => x.m), tumbling: true, lined: false });
        const landed = orderDiceAt(race, playhead(race, t0 + k * step + step * 0.6))!;
        expect(landed.tumbling).toBe(false);
        for (const x of got) expect(landed.faces[x.m]).toBe(x.face);
      });
      // Lined up while the order changes, each showing its first face: high to low along the order.
      const lined = orderDiceAt(race, playhead(race, t0 + b.len + 1))!;
      expect(lined).toMatchObject({ r: b.r, lined: true, tumbling: false });
      const firsts = order.map((m) => lined.faces[m]!);
      expect(firsts).toEqual([...firsts].sort((x, y) => y - x));
      // Then the round's own dice.
      expect(orderDiceAt(race, playhead(race, race.startsAt * 1000 + rollStart(race, b.r) + 1))).toBeNull();
    }
    expect(orderDiceAt(race, playhead(race, race.startsAt * 1000 + stepStart(race, 0) + 1))).toBeNull();
  });

  it("names the leader before and after each step with the alpaca's turns in between", () => {
    const before = leadersBefore(race.start!, race.moves!, { race, track: trackOfRace(race) });
    const after = leaders(race.start!, race.moves!, { race, track: trackOfRace(race) });
    const board = createBoardStepper(false);
    race.moves!.forEach((_, i) => {
      const n = tl.cars.filter((e) => e.before <= i).length;
      expect(before[i]).toBe(rankOf(board(race.start!, race.moves!, i, -1, runOf(race, n)).stacks)[0]);
      expect(after[i]).toBe(rankOf(board(race.start!, race.moves!, i + 1, -1, runOf(race, n)).stacks)[0]);
    });
    expect(after[after.length - 1]).toBe(race.ranking![0]);
  });

  it("lists whom each drive picks up, square by square as it reaches them", () => {
    const picks = pickupsOf(race, trackOfRace(race));
    expect(picks).toHaveLength(race.drives!.length);
    race.drives!.forEach((d, k) => {
      expect([...picks[k]!].reverse().flatMap((x) => x.stack)).toEqual(d.take ?? []);
      for (const x of picks[k]!) expect(x.sq <= d.from && x.sq >= d.to).toBe(true);
      expect(picks[k]!.map((x) => x.sq)).toEqual([...picks[k]!.map((x) => x.sq)].sort((a, b) => b - a));
    });
  });

  it("times every drive within its length, slower in the last round", () => {
    race.drives!.forEach((d, k) => {
      const p = driveTimes(race, k);
      expect(p.homeAt + p.homeLen).toBeLessThanOrEqual(p.len);
      expect(p.glideAt).toBeGreaterThan(0);
      expect(p.backLen > 0).toBe(d.back !== undefined);
      expect(p.takeLen > 0).toBe(!!d.take?.length);
      expect(p.homeLen > 0).toBe(!!d.home);
      const slow = d.r >= Math.floor(race.slowFrom! / ROUND);
      const squares = Math.abs(d.from - d.to);
      expect(p.glideLen).toBeCloseTo(squares * race.drivePace!.sq * (slow ? race.slowMs! / race.stepMs! : 1), 6);
    });
  });

  it("records every quarter second", () => {
    const board = createBoardStepper();
    const frames = timesOf(race).map((t) => {
      const h = playhead(race, t);
      const c = stepCursor(h);
      const b = board(race.start!, race.moves!, c.completed, c.partial, runOf(race, c.driven!));
      return JSON.stringify({
        stacks: [...b.stacks], hops: b.hops, car: b.car, carKey: b.carKey, current: h.current,
        drive: h.drive?.k ?? null, order: h.order?.r ?? null, shuffle: h.shuffle?.r ?? null, enter: h.enter !== undefined,
      });
    });
    expect(frames).toMatchSnapshot();
  });
});

describe("the car's way", () => {
  it("starts and stops smoothly and runs evenly between", () => {
    expect(glideAt(0)).toBe(0);
    expect(glideAt(1)).toBe(1);
    let last = 0;
    for (let u = 0.01; u <= 1; u += 0.01) {
      const p = glideAt(u);
      expect(p).toBeGreaterThan(last);
      expect(glideWhen(p)).toBeCloseTo(u, 9);
      last = p;
    }
    // Even in the middle: equal times, equal ways.
    expect(glideAt(0.6) - glideAt(0.5)).toBeCloseTo(glideAt(0.4) - glideAt(0.3), 9);
  });
});

it("a race from before the dice for each order only changes places", () => {
  const r = { ...races[0]!, orderRolls: undefined, orderRollMs: undefined } as Race;
  const tl = timelineOf(r)!;
  expect(tl.beats.some((b) => b.kind === "order")).toBe(false);
  const s = tl.beats.find((b) => b.kind === "shuffle")!;
  expect(orderDiceAt(r, playhead(r, r.startsAt * 1000 + s.at + 1))).toBeNull();
  expect(orderAt(r, r.startsAt * 1000 + s.at + 1)).toEqual(r.orders![s.r]);
});

it("a race by the rules before them plays as it always did", () => {
  const r = { ...races[0]!, orders: undefined, drives: undefined, enter: undefined };
  expect(timelineOf(r as Race)).toBeNull();
  expect(Object.keys(playhead(r as Race, r.startsAt * 1000 + 1))).toEqual(["done", "current", "part"]);
});
