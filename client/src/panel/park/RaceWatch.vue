<script setup lang="ts">
// Watching a race (protocol/PROTOCOL.md 团子赛跑): the page of the race's own window (RaceApp.vue; the browser preview
// floats it over the desk page, pet/RaceFrame.vue). The race page only takes bets and lists the past races; this is
// where a race is seen. It follows the live race (raceFeed.ts) or, with [replay], plays that finished race again on a
// clock of its own (race.ts replayTime), at 1× or 2×.
// The bar on top moves the window and says what is on: the map, live or a replay, the round. Under it the board
// (RaceTrack) fills the stage; beside it the field in the order it stands, each with its skill, its die's faces, how
// far along it is and my coins on it, and under those my bets. The strip under the board is the order of play, each
// tuanzi under its die: the opening's dice, then each round's five thrown together, the one whose turn it is raised.
// Between races the board shows the next race's map with the time to its start; at the finish the tuanzi fly from
// their squares onto a podium over the board.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { manifest } from "../../manifest";
import { economy } from "../../stores/economy";
import { parkTry } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import { EASE_OUT } from "../../ui/motion";
import ParkCoin from "./ParkCoin.vue";
import RaceDie, { type Toss } from "./RaceDie.vue";
import RaceTrack from "./RaceTrack.vue";
import TuanziToken from "./TuanziToken.vue";
import { COIN_SMALL } from "./coin";
import { shortDay } from "./lottery";
import {
  chinaDay, cutOf, DICE_TOSS, FORM_NAMES, hits, KIND_NAMES, leaders, momentOf, OPEN_ROLL_MS, openingAt, playhead,
  playLength, rankOf, replayAt, replayTime, ROUND, roundAt, roundDice, roundsOf, SKILL_NAMES, skillText, spots,
  stacksAt, staggered, stageOf, stepStart, trackOf, type Race, type ReplayClock,
} from "./race";
import { isFinished, isPlaying, raceClock, useRaceFeed } from "./raceFeed";

/** [replay]: the finished race to play, 0 for the live one. */
const props = defineProps<{ replay?: number }>();
const emit = defineEmits<{ close: []; drag: [e: PointerEvent] }>();

const CFG = computed(() => economy.value?.park?.race);
/** The members in manifest order: the lanes before a race's own are drawn. */
const MEMBERS = manifest.characters.map((c) => c.id);
/** How long the last round's cue stays up, ms. */
const CUE_MS = 2600;
/** The faces of the order's die. */
const ORDER_FACES = [1, 2, 3, 4, 5, 6];
const fmt = (n: number) => Math.abs(n).toLocaleString("en-US");
const character = (m: string) => manifest.characters.find((c) => c.id === m);
const nameOf = (m: string) => character(m)?.name ?? m;
const colorOf = (m: string) => character(m)?.color;
const x = (n: number) => `×${n.toFixed(1)}`;

const replaying = ref(!!props.replay);
const feed = useRaceFeed({ scheduleOnly: () => replaying.value });
const { now, serverNow, race, loadError } = feed;
onMounted(feed.start);
onBeforeUnmount(feed.stop);

// ---------------------------------------------------------------- the race on the board
/** A finished race played again: the race, its day, clock, and seek count used to reset move animations. */
const played = ref<{ race: Race; day: string; clock: ReplayClock; n: number } | null>(null);
const playRate = ref<1 | 2>(1);
const paused = ref(false);
const boardPeek = ref(false);
const replayError = ref("");
let replayLoad = 0;
/** Asks for race [id] and plays it from its start; 0 goes back to the live race. */
async function load(id: number) {
  const request = ++replayLoad;
  clearScrub();
  replaying.value = !!id;
  replayError.value = "";
  paused.value = false;
  boardPeek.value = false;
  if (!id) {
    played.value = null;
    return;
  }
  const have = [race.value, feed.last.value].find((r) => r?.id === id && r.phase === "done" && r.moves?.length);
  let r = have ?? null;
  if (!r) {
    const reply = await parkTry<{ race: Race }>("GET", `/api/park/race/replay/${id}`);
    if (request !== replayLoad) return;
    if (!reply.ok) {
      replayError.value = reply.error.message;
      replaying.value = !!played.value;
      return;
    }
    r = reply.data.race;
  }
  played.value = {
    race: r, day: chinaDay(r.startsAt), clock: replayAt(r, 0, Date.now(), playRate.value), n: (played.value?.n ?? 0) + 1,
  };
}

/** The race on the board and its time: the replay's while one plays, else the live race at the server's time. */
const scrubAt = ref<number | null>(null);
const scrubbing = computed(() => scrubAt.value !== null);
const stage = computed(() => played.value?.race ?? race.value);
const stageNow = computed(() => {
  const p = played.value;
  if (!p) return serverNow.value;
  return scrubAt.value === null ? replayTime(p.race, p.clock, now.value) : p.race.startsAt * 1000 + scrubAt.value;
});
/** Playback rate for animations & dice throws (never 0, even while paused). */
const speed = computed(() => (played.value ? playRate.value : 1));
const playing = computed(() => isPlaying(stage.value, stageNow.value));
const finished = computed(() => isFinished(stage.value, stageNow.value));
const track = computed(() => trackOf(stage.value?.setup, CFG.value?.track ?? 24));
const trackKey = computed(() => (played.value ? `r${played.value.race.id}` : `live${race.value?.id ?? 0}`));

watch(finished, (done) => {
  if (done) {
    if (!scrubbing.value) paused.value = false;
  }
  else boardPeek.value = false;
});
watch(() => stage.value?.id, () => {
  boardPeek.value = false;
});

/** Moves the replay to [from] ms into the race (0: from the start, the end: its result). */
function seek(from: number) {
  const p = played.value;
  if (!p) return;
  boardPeek.value = false;
  const end = playLength(p.race);
  const clamped = Math.max(0, Math.min(end, from));
  if (clamped >= end) paused.value = false;
  const effSpeed = paused.value && clamped < end ? 0 : playRate.value;
  played.value = { ...p, clock: replayAt(p.race, clamped, Date.now(), effSpeed), n: p.n + 1 };
}
/** Plays the replay at [k]×, on from where it is. */
function setSpeed(k: 1 | 2) {
  playRate.value = k;
  const p = played.value;
  if (!p) return;
  const at = replayTime(p.race, p.clock, Date.now()) - p.race.startsAt * 1000;
  played.value = { ...p, clock: replayAt(p.race, at, Date.now(), paused.value ? 0 : k) };
}
function togglePause() {
  const p = played.value;
  if (!p || finished.value) return;
  const at = replayTime(p.race, p.clock, Date.now()) - p.race.startsAt * 1000;
  paused.value = !paused.value;
  played.value = { ...p, clock: replayAt(p.race, at, Date.now(), paused.value ? 0 : playRate.value) };
}
function stepSeek(dir: -1 | 1) {
  const p = played.value;
  const moves = p?.race.moves;
  if (!p || !moves?.length) return;
  const at = replayTime(p.race, p.clock, Date.now()) - p.race.startsAt * 1000;
  if (dir > 0) {
    const nextIdx = moves.findIndex((_, i) => stepStart(p.race, i) > at + 80);
    seek(nextIdx >= 0 ? stepStart(p.race, nextIdx) : playLength(p.race));
  } else {
    let prevIdx = -1;
    for (let i = moves.length - 1; i >= 0; i--) {
      if (stepStart(p.race, i) < at - 280) {
        prevIdx = i;
        break;
      }
    }
    seek(prevIdx >= 0 ? stepStart(p.race, prevIdx) : 0);
  }
}
const canReplayStage = computed(() => finished.value && !!stage.value?.moves?.length);
function replayStage() {
  boardPeek.value = false;
  paused.value = false;
  if (played.value) seek(0);
  else if (stage.value) void load(stage.value.id);
}
const toEnd = () => played.value && seek(playLength(played.value.race));
const progress = computed(() => {
  const p = played.value;
  return p ? Math.min(1, (stageNow.value - p.race.startsAt * 1000) / Math.max(1, playLength(p.race))) : 0;
});
/** Key moments along the replay timeline (skills, portals, flips and lead changes) for quick visual scrubbing. */
const replayMarks = computed(() => {
  const r = played.value?.race;
  if (!r?.start || !r.moves?.length) return [];
  const total = playLength(r);
  if (total <= 0) return [];
  const lead = leaders(r.start, r.moves);
  const out: { at: number; pct: number; label: string; kind: "skill" | "lead" | "special" }[] = [];
  r.moves.forEach((s, i) => {
    const at = stepStart(r, i);
    const pct = Math.min(97, Math.max(3, (at / total) * 100));
    const rNo = Math.floor(i / ROUND) + 1;
    const cut = cutOf(r, i);
    const m = momentOf(s, i ? lead[i - 1] : r.start![0], lead[i]);
    if (cut) {
      const sk = r.setup.skills?.[cut.m];
      out.push({ at, pct, kind: "skill", label: `第 ${rNo} 轮 · ${nameOf(cut.m)} ${sk ? SKILL_NAMES[sk.id] ?? "" : ""}`.trim() });
    } else if (s.square === "portal" || s.square === "flip") {
      out.push({ at, pct, kind: "special", label: `第 ${rNo} 轮 · ${nameOf(s.m)} ${s.square === "portal" ? "传送门" : "翻转"}` });
    } else if (m?.kind === "lead") {
      out.push({ at, pct, kind: "lead", label: `第 ${rNo} 轮 · ${nameOf(m.m)} 领先` });
    }
  });
  // Keep markers spaced enough to read cleanly on the bar.
  return out.filter((mk, idx, arr) => idx === 0 || mk.pct - arr[idx - 1]!.pct >= 4.5);
});
let scrub: { pointerId: number; left: number; width: number; x: number; length: number } | null = null;
let scrubFrame = 0;
function previewScrub() {
  scrubFrame = 0;
  if (!scrub) return;
  const u = Math.max(0, Math.min(1, (scrub.x - scrub.left) / scrub.width));
  scrubAt.value = u * scrub.length;
}
function clearScrub() {
  cancelAnimationFrame(scrubFrame);
  scrubFrame = 0;
  scrub = null;
  scrubAt.value = null;
}
function onProgressDown(e: PointerEvent) {
  if (e.button !== 0 || scrub || !played.value) return;
  const target = e.currentTarget as HTMLElement;
  const { left, width } = target.getBoundingClientRect();
  if (!width) return;
  e.stopPropagation();
  e.preventDefault();
  target.setPointerCapture?.(e.pointerId);
  scrub = { pointerId: e.pointerId, left, width, x: e.clientX, length: playLength(played.value.race) };
  boardPeek.value = false;
  previewScrub();
}
function onProgressMove(e: PointerEvent) {
  if (!scrub || scrub.pointerId !== e.pointerId) return;
  scrub.x = e.clientX;
  if (!scrubFrame) scrubFrame = requestAnimationFrame(previewScrub);
}
function onProgressEnd(e: PointerEvent) {
  if (!scrub || scrub.pointerId !== e.pointerId) return;
  if (e.type === "pointerup") scrub.x = e.clientX;
  cancelAnimationFrame(scrubFrame);
  previewScrub();
  const at = scrubAt.value;
  clearScrub();
  if (at !== null) seek(at);
}
watch(() => props.replay ?? 0, load, { immediate: true });
onBeforeUnmount(() => { replayLoad++; clearScrub(); });
/** The live race is under way while a replay plays: a key goes to it. */
const liveOn = computed(() => !!played.value && feed.live.value);

/** What is over the board: nothing while a race runs or while inspecting the final board, the wait, or the podium. */
const view = computed<"run" | "wait" | "podium" | "board">(() => {
  if (finished.value) return boardPeek.value ? "board" : "podium";
  if (played.value || playing.value || stage.value?.phase === "starting") return "run";
  return "wait";
});
const wait = computed(() => {
  const r = race.value;
  const t = serverNow.value / 1000;
  if (r?.phase === "void") return { label: "本场取消", time: "" };
  if (r?.phase === "betting") return { label: "下注中", time: raceClock(r.startsAt - t) };
  const next = feed.data.value?.nextAt;
  return next ? { label: "下一场", time: raceClock(next - t) } : null;
});

// ---------------------------------------------------------------- the field as it stands
const head = computed(() => {
  const r = stage.value;
  return r?.start && r.moves?.length ? playhead(r, stageNow.value) : null;
});
const stacks = computed(() => {
  const r = stage.value;
  return r?.start && r.moves && head.value ? stacksAt(r.start, r.moves, head.value) : null;
});
/*
 * The lists below move their rows when the order changes (TransitionGroup). A list that draws again while its rows
 * are on the way starts their move afresh from where they are, so what the lists read must stand still between the
 * clock's ticks: the values that follow the clock are turned into text first, which only changes when they do.
 */
/** First to last (the ranking once it is in, the board's order while it runs, the lanes before), and each one's square. */
const standing = computed(() => {
  const r = stage.value;
  const order = finished.value && r?.ranking ? r.ranking : stacks.value ? rankOf(stacks.value) : r?.start ?? MEMBERS;
  const squares: Record<string, number> = {};
  if (stacks.value) for (const [m, s] of Object.entries(spots(stacks.value))) squares[m] = s.square;
  return JSON.stringify({ order, squares, led: !!stacks.value });
});
const field = computed(() => JSON.parse(standing.value) as { order: string[]; squares: Record<string, number>; led: boolean });
const order = computed(() => field.value.order);
const squares = computed(() => field.value.squares);
/** How far along [m] is, 0 to 1, and its square readout on the side card. */
const along = (m: string) => (finished.value && order.value[0] === m ? 1 : Math.min(1, (squares.value[m] ?? 0) / track.value));
function sqLabel(m: string): string {
  const sq = squares.value[m] ?? 0;
  if ((finished.value && order.value[0] === m) || sq >= track.value) return "终";
  return `${sq}/${track.value}`;
}
const skillOf = (m: string) => stage.value?.setup.skills?.[m];
/** A member's skill, or its form on races from before skills: the name and what it does. */
function traitOf(m: string): { name: string; text: string } | null {
  const skill = skillOf(m);
  if (skill) return { name: SKILL_NAMES[skill.id] ?? skill.id, text: skillText(skill) };
  const form = stage.value?.setup.forms?.[m];
  return form ? { name: FORM_NAMES[form] ?? form, text: "" } : null;
}
const diceOf = (m: string) => stage.value?.setup.dice?.[m] ?? CFG.value?.dice ?? [];
const mineOn = (m: string) => stage.value?.mine.filter((b) => b.member === m).reduce((n, b) => n + b.coins, 0) ?? 0;
const backedMembers = computed(() => [...new Set((stage.value?.mine ?? []).map((b) => b.member))]);

// ---------------------------------------------------------------- the order of play and its dice
/** The opening (the dice for the order) while it plays. */
const opening = computed(() => (stage.value && playing.value ? openingAt(stage.value, stageNow.value) : null));
/** The order of play: the manifest's until the opening has settled it; none for a race from before the opening. */
const seats = computed<string[]>(() => {
  const r = stage.value;
  if (r?.order && (!opening.value || opening.value.lined)) return r.order;
  return r?.order || !r?.moves ? MEMBERS : [];
});
/** A seat's die: its face, keyed so each throw remounts it once; the throw while it is in the air. */
interface SeatDie { key: string; face: number; toss: Toss | null; out: boolean }
/**
 * A member's die in the opening: the face it shows, keyed by the round it was last thrown in; the throw while its
 * round is in the air (staggered among those throwing), dimmed once its place is settled.
 */
function openingDie(m: string): SeatDie | null {
  const o = opening.value;
  const rolls = stage.value?.rolls;
  if (!o || !rolls || o.round < 0) return null;
  const k = o.rolling.indexOf(m);
  let thrown = o.round;
  while (thrown > 0 && !rolls[thrown].some((r) => r.m === m)) thrown--;
  if (k >= 0 && o.tumbling) {
    const face = rolls[o.round][k].face;
    const { delay, ms } = staggered(OPEN_ROLL_MS, k, o.rolling.length);
    const toss = reducedMotion.value || scrubbing.value
      ? null : { ms, delay, at: o.since, pool: ORDER_FACES, seed: MEMBERS.indexOf(m), height: 95 };
    return { key: `${m}o${thrown}`, face, toss, out: false };
  }
  return { key: `${m}o${thrown}`, face: o.faces[m] ?? 0, toss: null, out: k < 0 && !o.lined };
}
/** The round whose dice are out, once the opening is over. */
const round = computed(() => (stage.value?.moves && playing.value && !opening.value ? roundAt(stage.value, stageNow.value) : null));
/**
 * A member's die in a round: the five thrown together at the round's start (staggered, landing by DICE_TOSS of
 * rollMs), lying in the row after; dimmed once its move is done.
 */
function roundDie(m: string): SeatDie | null {
  const r = stage.value;
  const ra = round.value;
  if (!r || !ra) return null;
  const dice = roundDice(r, ra.round);
  const k = dice.findIndex((d) => d.m === m);
  if (k < 0) return null;
  const len = (r.rollMs ?? 0) * DICE_TOSS;
  const { delay, ms } = staggered(len, k, dice.length);
  const toss = reducedMotion.value || scrubbing.value || ra.since >= len
    ? null
    : { ms, delay, at: ra.since, pool: diceOf(m), seed: ra.round * ROUND + k, height: 110 };
  const i = ra.round * ROUND + k;
  const done = !!head.value && i < (r.moves?.length ?? 0) && i < head.value.done && head.value.current !== i;
  return { key: `${m}r${ra.round}`, face: dice[k].face, toss, out: done };
}
/** The throws in the air, by member: read as a die comes up and not followed, since they change with every tick. */
const tosses: { now: Record<string, Toss | null> } = { now: {} };
const diceText = computed(() => {
  const air: Record<string, Toss | null> = {};
  const shown = seats.value.map((m) => {
    const d = opening.value ? openingDie(m) : roundDie(m);
    air[m] = d?.toss ?? null;
    return d ? { m, key: d.key, face: d.face, out: d.out, air: !!d.toss } : { m };
  });
  tosses.now = air;
  return JSON.stringify(shown);
});
/** A seat's die as the row shows it; `air`: its throw is in `tosses`. */
const seatDice = computed(() =>
  Object.fromEntries((JSON.parse(diceText.value) as { m: string; key?: string; face?: number; out?: boolean; air?: boolean }[])
    .map((d) => [d.m, d.key ? d : null])),
);
/** Whose turn it is in the step under way, and whether it still waits for its die. */
const mover = computed(() => {
  const r = stage.value;
  const h = head.value;
  return r?.moves && h && h.current >= 0 ? r.moves[h.current].m : "";
});
const moverWaits = computed(() => !!mover.value && !!head.value && stageOf(head.value.part) !== "walk");
/** The last round is under way, and its opening cue. */
const inFinalRound = computed(() => {
  const r = stage.value;
  const ra = round.value;
  return !!r && !!ra && roundsOf(r) >= 2 && ra.round === roundsOf(r) - 1;
});
const lastRound = computed(() => inFinalRound.value && (round.value?.since ?? Infinity) < CUE_MS);
/** Five turn-rhythm pips inside the current round: which seats have moved, and whose turn is active. */
const roundPips = computed<("done" | "now" | "todo")[]>(() => {
  const r = stage.value;
  const ra = round.value;
  const h = head.value;
  if (!r?.moves || !ra || !h) return [];
  const base = ra.round * ROUND;
  return Array.from({ length: ROUND }, (_, k) => {
    const idx = base + k;
    if (h.current === idx) return "now";
    if (idx < h.done && idx < r.moves!.length) return "done";
    return "todo";
  });
});
/** What the bar says is on: in replays includes total rounds (already settled); in live avoids spoiling the end round. */
const status = computed(() => {
  if (finished.value) return view.value === "board" ? "终局赛道" : "本场名次";
  if (opening.value) return "掷骰定序";
  if (round.value && stage.value) {
    const cur = round.value.round + 1;
    if (played.value) return `第 ${cur}/${roundsOf(stage.value)} 轮`;
    return inFinalRound.value ? `第 ${cur} 轮 · 冲线` : `第 ${cur} 轮`;
  }
  return "";
});

// ---------------------------------------------------------------- my bets and the result
/** My bets on the race on the board, one a selection: the coins in all, and whether it won once the race is run. */
const tickets = computed(() => {
  const r = stage.value;
  const out: { key: string; kind: string; member: string; odds: number[]; coins: number; won: boolean }[] = [];
  for (const b of r?.mine ?? []) {
    const key = `${b.kind}${b.member}`;
    const t = out.find((o) => o.key === key);
    if (t) {
      t.coins += b.coins;
      if (!t.odds.includes(b.odds)) t.odds.push(b.odds);
    } else out.push({ key, kind: KIND_NAMES[b.kind], member: b.member, odds: [b.odds], coins: b.coins, won: finished.value && !!r?.ranking && hits(b.kind, b.member, r.ranking) });
  }
  for (const t of out) t.odds.sort((a, b) => b - a);
  return out;
});
const oddsList = (odds: number[]) =>
  (odds.length > 2 ? `×${odds[0].toFixed(1)}–${odds[odds.length - 1].toFixed(1)}` : odds.map(x).join(" "));
const ranking = computed(() => (finished.value ? stage.value?.ranking ?? [] : []));
/** A place lights up when one of my bets on the tuanzi in it won; one I bet on that won nothing greys out. */
function lit(place: number): boolean {
  const m = ranking.value[place];
  return !!m && !!stage.value?.mine.some((b) => b.member === m && hits(b.kind, b.member, ranking.value));
}
const missed = (place: number) => !!stage.value?.mine.some((b) => b.member === ranking.value[place]) && !lit(place);
const won = computed(() => (finished.value ? stage.value?.result?.won ?? 0 : 0));

// ---------------------------------------------------------------- the finish
/*
 * At the finish each tuanzi flies from its square on the board onto the podium (FLIP), the steps rising under them.
 * Without motion the podium is simply there.
 */
const stageEl = ref<HTMLElement | null>(null);
let flipFrom: Map<string, DOMRect> | null = null;
watch(view, (to, from) => {
  flipFrom = null;
  if ((from !== "run" && from !== "board") || to !== "podium" || reducedMotion.value || scrubbing.value || !stageEl.value) return;
  flipFrom = new Map();
  for (const el of stageEl.value.querySelectorAll<HTMLElement>(".tz[data-m]")) {
    const token = el.querySelector(".tuanzi-token");
    if (token) flipFrom.set(el.dataset.m!, token.getBoundingClientRect());
  }
  void nextTick(flyToPodium);
}, { flush: "pre" });

function flyToPodium() {
  const from = flipFrom;
  flipFrom = null;
  const root = stageEl.value?.querySelector<HTMLElement>(".podium");
  if (!from || !root) return;
  root.querySelectorAll<HTMLElement>(".place").forEach((place, i) => {
    const token = place.querySelector<HTMLElement>("[data-m]");
    const was = token && from.get(token.dataset.m!);
    if (token && was) {
      const to = token.getBoundingClientRect();
      if (to.width) {
        const move = `translate(${was.left - to.left}px, ${was.top - to.top}px) scale(${was.width / to.width})`;
        token.animate([{ transform: move, transformOrigin: "0 0" }, { transform: "none", transformOrigin: "0 0" }],
          { duration: 720, delay: i * 70, easing: EASE_OUT, fill: "backwards" });
      }
    }
    place.querySelector<HTMLElement>(".step")?.animate(
      [{ transform: "scaleY(0)", transformOrigin: "50% 100%" }, { transform: "none", transformOrigin: "50% 100%" }],
      { duration: 520, delay: 160 + i * 70, easing: EASE_OUT, fill: "backwards" },
    );
    place.querySelector<HTMLElement>(".podium-crown")?.animate(
      [{ opacity: 0, transform: "scale(0.35) translateY(8px)" }, { opacity: 1, transform: "none" }],
      { duration: 420, delay: 520, easing: EASE_OUT, fill: "backwards" },
    );
  });
}

function onBarDown(e: PointerEvent) {
  if (e.button === 0 && !(e.target as HTMLElement).closest("button, [data-no-bar-drag]")) emit("drag", e);
}
// Escape closes it, and only it; replay & post-race board shortcuts stay local to the watch window.
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    e.stopPropagation();
    emit("close");
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
  if (finished.value && (e.key === "b" || e.key === "B") && !e.repeat) {
    e.preventDefault();
    e.stopPropagation();
    boardPeek.value = !boardPeek.value;
    return;
  }
  if (!played.value) return;
  if (e.key === " " && !e.repeat && !(e.target as HTMLElement | null)?.closest("button")) {
    e.preventDefault();
    e.stopPropagation();
    if (finished.value) replayStage();
    else togglePause();
  } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    e.preventDefault();
    e.stopPropagation();
    stepSeek(e.key === "ArrowLeft" ? -1 : 1);
  }
}
onMounted(() => window.addEventListener("keydown", onKey, true));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey, true));
</script>

<template>
  <section class="watch" :class="{ calm: reducedMotion }" aria-label="团子赛跑">
    <div class="sheet">
    <header class="bar" @pointerdown="onBarDown">
      <h1>团子赛跑</h1>
      <span v-if="stage?.setup.map" class="map">{{ stage.setup.map.name }}</span>
      <span v-if="played" class="mode"><Icon name="play" :size="12" />回放 {{ shortDay(played.day) }}</span>
      <span v-else-if="view === 'run'" class="mode live"><i class="dot" aria-hidden="true"></i>直播</span>
      <span v-if="status" class="round" :class="{ final: inFinalRound && view === 'run' }">
        <span>{{ status }}</span>
        <span v-if="roundPips.length && view === 'run'" class="round-pips" aria-hidden="true">
          <i v-for="(p, pi) in roundPips" :key="pi" :class="p"></i>
        </span>
      </span>
      <span class="grow"></span>
      <template v-if="played">
        <div
          class="progress-wrap" data-no-bar-drag role="slider" aria-label="回放进度"
          :aria-valuemin="0" :aria-valuemax="100" :aria-valuenow="Math.round(progress * 100)"
          @pointerdown="onProgressDown" @pointermove="onProgressMove" @pointerup="onProgressEnd"
          @pointercancel="onProgressEnd" @lostpointercapture="onProgressEnd"
        >
          <i class="progress" aria-hidden="true"><i :style="{ width: `${progress * 100}%` }"></i></i>
          <i
            v-for="(mk, mi) in replayMarks" :key="mi" class="mark" :class="mk.kind"
            :style="{ left: `${mk.pct}%` }" :title="mk.label"
          ></i>
        </div>
        <button
          v-if="!finished" type="button" class="ui-btn small ghost icon-key"
          :aria-label="paused ? '继续' : '暂停'" :title="paused ? '继续' : '暂停'" @click="togglePause"
        >
          <Icon :name="paused ? 'play' : 'pause'" :size="15" />
        </button>
        <button
          type="button" class="ui-btn small ghost speed-key" :class="{ on: playRate === 2 }" :aria-pressed="playRate === 2"
          @click="setSpeed(playRate === 2 ? 1 : 2)"
        >2×</button>
        <button v-if="!finished" type="button" class="ui-btn small ghost icon-key" aria-label="跳到结果" title="跳到结果" @click="toEnd">
          <Icon name="skip" :size="16" />
        </button>
        <button v-else type="button" class="ui-btn small ghost icon-key" aria-label="再看一遍" title="再看一遍" @click="replayStage">
          <Icon name="refresh" :size="16" />
        </button>
        <button v-if="liveOn" type="button" class="ui-btn small live-key" @click="load(0)">
          <i class="dot" aria-hidden="true"></i>直播
        </button>
      </template>
      <template v-else-if="finished">
        <button
          type="button" class="ui-btn small ghost bar-toggle" :aria-pressed="boardPeek"
          @click="boardPeek = !boardPeek"
        >
          <Icon :name="boardPeek ? 'crown' : 'grid'" :size="14" /><span>{{ boardPeek ? "领奖台" : "查看终局" }}</span>
        </button>
        <button v-if="canReplayStage" type="button" class="ui-btn small ghost bar-toggle" @click="replayStage">
          <Icon name="refresh" :size="14" /><span>回放</span>
        </button>
      </template>
      <button type="button" class="ui-btn small ghost icon-key" aria-label="关闭" @click="emit('close')"><Icon name="close" :size="16" /></button>
    </header>

    <div ref="stageEl" class="stage">
      <RaceTrack
        :key="trackKey" class="lap" :class="{ behind: view === 'podium' }" :race="stage" :t="stageNow" :rate="speed"
        :paused="paused" :seek="played?.n" :scrubbing="scrubbing" :backed="backedMembers" :track="track" :members="MEMBERS"
        :caption="stage?.setup.map?.name" :cleared="view === 'podium'"
      />
      <p v-if="loadError || replayError" class="ui-error note" role="alert">{{ replayError || loadError }}</p>
      <Transition name="card">
        <div v-if="view === 'wait' && wait" class="card wait" role="status">
          <small>{{ wait.label }}</small>
          <b v-if="wait.time">{{ wait.time }}</b>
        </div>
        <div v-else-if="view === 'podium'" class="card result">
          <ol class="podium" aria-label="本场名次">
            <li
              v-for="(m, i) in ranking" :key="m" class="place" :class="[`p${i + 1}`, { lit: lit(i), missed: missed(i) }]"
              :title="`${i + 1}. ${nameOf(m)}`"
            >
              <span class="figure">
                <Icon v-if="i === 0" class="podium-crown" name="crown" :size="24" />
                <TuanziToken :member="m" :size="i === 0 ? 72 : i < 3 ? 48 : 32" :grey="missed(i)" :data-m="m" />
              </span>
              <span class="step">{{ i + 1 }}</span>
            </li>
          </ol>
          <p v-if="won > 0" class="net" role="status" :aria-label="`+${fmt(won)} 驼币`">
            <ParkCoin class="net-coin" fill :tilt="false" /><b>+{{ fmt(won) }}</b>
          </p>
          <p v-if="!played && wait?.time" class="next">{{ wait.label }} <b>{{ wait.time }}</b></p>
          <div class="result-actions">
            <button type="button" class="ui-btn small" @click="boardPeek = true">
              <Icon name="grid" :size="14" /><span>查看终局</span>
            </button>
            <button v-if="canReplayStage" type="button" class="ui-btn small primary" @click="replayStage">
              <Icon name="refresh" :size="14" /><span>{{ played ? "再看一遍" : "回放本场" }}</span>
            </button>
          </div>
        </div>
      </Transition>
    </div>

    <aside class="side">
      <TransitionGroup tag="ol" name="rank" class="field" aria-label="名次">
        <li v-for="(m, i) in order" :key="m" class="runner" :class="{ turn: mover === m, first: i === 0 && field.led }">
          <b class="no">{{ i + 1 }}</b>
          <TuanziToken class="face" :member="m" :size="48" />
          <span class="who">
            <span class="line">
              <i class="hue" :style="{ background: colorOf(m) }" aria-hidden="true"></i>
              <span class="name">{{ nameOf(m) }}</span>
              <span v-if="traitOf(m)" class="trait" :title="traitOf(m)!.text || undefined">{{ traitOf(m)!.name }}</span>
            </span>
            <span v-if="skillOf(m)" class="does">{{ traitOf(m)!.text }}</span>
            <span class="along-row">
              <i class="along" aria-hidden="true"><i :style="{ width: `${along(m) * 100}%` }"></i></i>
              <small v-if="field.led || finished" class="sq-num">{{ sqLabel(m) }}</small>
            </span>
          </span>
          <span class="tail">
            <span class="form" :aria-label="`骰子 ${diceOf(m).join(' ')}`">
              <RaceDie v-for="(f, k) in diceOf(m)" :key="k" :face="f" :color="colorOf(m)" />
            </span>
            <span v-if="mineOn(m)" class="mine"><img :src="COIN_SMALL" alt="" draggable="false" />{{ mineOn(m) }}</span>
          </span>
        </li>
      </TransitionGroup>
      <ul v-if="tickets.length" class="tickets" aria-label="我的押注">
        <li v-for="t in tickets" :key="t.key" class="ticket" :class="{ won: t.won }">
          <span class="ticket-paper">
            <i class="perf" aria-hidden="true"></i>
            <TuanziToken :member="t.member" :size="24" />
            <small>{{ t.kind }}</small><b>{{ oddsList(t.odds) }}</b>
            <span class="coin"><img :src="COIN_SMALL" alt="" draggable="false" />{{ t.coins }}</span>
          </span>
        </li>
      </ul>
    </aside>

    <footer class="deck">
      <TransitionGroup v-if="seats.length && view === 'run'" tag="ol" name="seat" class="lineup" aria-label="出场顺序">
        <li
          v-for="m in seats" :key="m" class="seat"
          :class="{ turn: mover === m, waiting: mover === m && moverWaits, done: !!seatDice[m]?.out }" :title="nameOf(m)"
        >
          <span class="slot">
            <RaceDie
              v-if="seatDice[m]" :key="`${seatDice[m]!.key}-${played?.n ?? 0}-${scrubbing}`" class="seat-die" :class="{ out: seatDice[m]!.out }"
              :face="seatDice[m]!.face!" :toss="seatDice[m]!.air ? tosses.now[m] : null" :color="colorOf(m)"
              :paused="paused" :rate="speed"
            />
          </span>
          <span class="head"><TuanziToken :member="m" :size="48" /></span>
        </li>
      </TransitionGroup>
      <div v-else-if="view === 'board'" class="board-dock" role="toolbar" aria-label="终局查看">
        <span class="dock-label">终局赛道</span>
        <button type="button" class="ui-btn small" @click="boardPeek = false">
          <Icon name="crown" :size="14" /><span>领奖台</span>
        </button>
        <button v-if="canReplayStage" type="button" class="ui-btn small primary" @click="replayStage">
          <Icon name="refresh" :size="14" /><span>{{ played ? "再看一遍" : "回放本场" }}</span>
        </button>
      </div>
      <p v-if="lastRound" class="cue" role="status">最后一轮</p>
    </footer>
    </div>
  </section>
</template>

<style scoped>
/*
 * The window's face: the bar across the top, the board's stage with the order of play under it, the field down the
 * right. It fills its box (the window, or the preview's frame) and is the size container the parts follow.
 */
.watch {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border-radius: var(--radius-l);
  background: var(--c-50);
  font-family: var(--font);
  color: var(--ink);
  container: watch / size;
}
.sheet {
  display: grid;
  grid-template: "bar bar" 46px "stage side" minmax(0, 1fr) "deck side" 104px / minmax(0, 1fr) 286px;
  height: 100%;
}

/* ---- the bar: coral, the window's handle */
.bar {
  grid-area: bar;
  position: relative;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 8px 0 18px;
  background: var(--grad-sky);
  box-shadow: 0 1px 0 rgba(var(--c-900-rgb), 0.12);
  user-select: none;
}
.bar h1 {
  flex: none;
  margin: 0;
  font: 800 var(--fs-section)/1 var(--font);
  letter-spacing: 0.04em;
  white-space: nowrap;
  color: var(--ink);
}
.map,
.mode,
.round {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font: 800 var(--fs-label)/1 var(--font);
  white-space: nowrap;
}
.map {
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(var(--c-900-rgb), 0.12);
}
.mode {
  background: rgba(255, 255, 255, 0.52);
  color: var(--ink);
}
.mode.live {
  background: var(--c-800);
  color: #fff;
  box-shadow: 0 1px 3px rgba(var(--c-900-rgb), 0.22);
}
.round {
  gap: 7px;
  background: rgba(255, 255, 255, 0.48);
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.round.final {
  background: var(--surface);
  color: var(--c-800);
  box-shadow: 0 1px 3px rgba(var(--c-900-rgb), 0.16);
}
.round-pips {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.round-pips i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(var(--c-900-rgb), 0.2);
  transition: transform var(--dur-fast) var(--ease-out), background var(--dur-fast);
}
.round-pips i.done {
  background: var(--c-700);
}
.round-pips i.now {
  width: 7px;
  height: 7px;
  background: var(--ink);
  box-shadow: 0 0 0 1.5px var(--surface);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  animation: beat 1.2s var(--ease-out) infinite;
}
@keyframes beat {
  50% { opacity: 0.25; }
}
.grow {
  flex: 1 1 auto;
}
.progress-wrap {
  position: relative;
  flex: 0 1 236px;
  min-width: 64px;
  height: 24px;
  display: flex;
  align-items: center;
  cursor: pointer;
  touch-action: none;
}
.progress {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: rgba(var(--c-900-rgb), 0.18);
  box-shadow: inset 0 1px 1px rgba(var(--c-900-rgb), 0.15);
  overflow: hidden;
  transition: height var(--dur-fast);
}
.progress-wrap:hover .progress {
  height: 8px;
}
.progress > i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--surface);
}
.mark {
  position: absolute;
  top: 50%;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  translate: -50% -50%;
  background: rgba(255, 255, 255, 0.85);
  box-shadow: 0 0 0 1px rgba(var(--c-900-rgb), 0.28);
  transition: transform var(--dur-fast) var(--ease-out);
}
.mark.skill {
  width: 6px;
  height: 6px;
  background: var(--c-800);
  box-shadow: 0 0 0 1.5px var(--surface);
}
.mark.lead {
  background: var(--gold-soft);
  box-shadow: 0 0 0 1px var(--gold);
}
.progress-wrap:hover .mark {
  transform: scale(1.2);
}
.icon-key {
  width: 30px;
  padding: 0;
}
.bar-toggle {
  gap: 5px;
  padding: 0 10px;
}
.speed-key {
  min-width: 40px;
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.speed-key.on:not(:disabled) {
  --key-top: var(--surface);
  --key-bottom: var(--surface);
}
.live-key {
  gap: 6px;
  color: var(--c-800);
}
.live-key .dot {
  background: var(--c-700);
}

/* ---- the stage: the board as large as it fits, what is between races on a card over it */
.stage {
  grid-area: stage;
  position: relative;
  min-width: 0;
  min-height: 0;
  padding: 10px 18px 0;
  display: flex;
}
.lap {
  flex: 1 1 auto;
  transition: opacity var(--dur-slow) var(--ease-out), filter var(--dur-slow) var(--ease-out);
}
.lap.behind {
  opacity: 0.42;
  filter: saturate(0.82);
}
.calm .lap {
  transition: none;
}
.note {
  position: absolute;
  left: 50%;
  top: 14px;
  z-index: 6;
  margin: 0;
  translate: -50% 0;
  box-shadow: var(--shadow-paper);
}
.card {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 6;
  translate: -50% -50%;
  max-width: calc(100% - 24px);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper), 0 20px 48px -14px rgba(var(--c-900-rgb), 0.42);
}
.card-enter-active {
  transition: opacity 320ms var(--ease-out), scale 320ms var(--ease-pop);
}
.card-leave-active {
  transition: opacity 200ms var(--ease-in);
}
.card-enter-from {
  opacity: 0;
  scale: 0.9;
}
.card-leave-to {
  opacity: 0;
}
.wait {
  gap: 8px;
  min-width: 176px;
  padding: 16px 30px 20px;
}
.wait small {
  padding: 4px 11px;
  border-radius: 999px;
  background: var(--c-100);
  font: 800 var(--fs-label)/1.1 var(--font);
  color: var(--c-700);
}
.wait b {
  font: 800 46px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}

/* ---- finished: the podium (1st step in gold and crowned), the last two beside it, and what my bets won */
.result {
  gap: 12px;
  padding: 32px 34px 18px;
}
.podium {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.place {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 92px;
  --tuanzi-size: 64px;
}
.figure {
  position: relative;
  line-height: 0;
}
.podium-crown {
  position: absolute;
  z-index: 2;
  left: 50%;
  top: -12px;
  translate: -50% 0;
  color: var(--gold);
  filter:
    drop-shadow(0 1.4px 0 #fff) drop-shadow(0 -1.4px 0 #fff)
    drop-shadow(1.4px 0 0 #fff) drop-shadow(-1.4px 0 0 #fff)
    drop-shadow(0 2px 3px rgba(var(--c-900-rgb), 0.3));
}
.podium-crown :deep(path) {
  fill: var(--gold-soft);
}
/* Second on the left, the winner in the middle, third on the right; the last two stand on the floor beside. */
.place.p1 { order: 2; --tuanzi-size: 96px; width: 114px; }
.place.p2 { order: 1; }
.place.p3 { order: 3; }
.place.p4,
.place.p5 {
  width: 56px;
  --tuanzi-size: 40px;
}
.place.p4 { order: 4; margin-left: 12px; }
.place.p5 { order: 5; }
.step {
  display: grid;
  place-items: center;
  width: 100%;
  height: 18px;
  border-radius: var(--radius-s) var(--radius-s) 0 0;
  background: color-mix(in oklab, var(--c-100) 65%, var(--surface));
  font: 800 var(--fs-heading)/1 var(--font-latin);
  color: var(--ink-3);
}
/* 1st place: the legendary gold step. */
.p1 .step {
  height: 66px;
  font-size: 30px;
  background: var(--grad-gold);
  color: var(--ink);
  box-shadow:
    inset 0 1.5px 0 rgba(255, 255, 255, 0.72),
    inset 0 0 0 1.5px var(--gold);
}
.p2 .step {
  height: 44px;
  background: var(--c-200);
  color: var(--ink-2);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
}
.p3 .step {
  height: 30px;
  background: var(--c-100);
  color: var(--ink-2);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
}
.p4 .step,
.p5 .step {
  font-size: var(--fs-number);
}
.place.lit:not(.p1) .step {
  background: var(--c-500);
  color: var(--ink);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45), 0 0 14px rgba(var(--c-500-rgb), 0.5);
}
.place.p1.lit .step {
  box-shadow:
    inset 0 1.5px 0 rgba(255, 255, 255, 0.8),
    0 0 0 2px var(--gold),
    0 0 20px rgba(var(--gold-rgb), 0.65);
}
.place.missed .step {
  opacity: 0.6;
}
.net {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: var(--c-700);
}
.net-coin {
  --size: 36px;
}
.net b {
  font: 800 40px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  animation: win-pop 600ms var(--ease-pop) both;
}
@keyframes win-pop {
  0% { transform: scale(0.6); opacity: 0; }
}
.next {
  margin: 0;
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
.next b {
  font: 800 var(--fs-number)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.result-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}
.result-actions .ui-btn {
  gap: 5px;
}

/* ---- the field down the right: a sheet of paper, first on top */
.side {
  grid-area: side;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  padding: 12px 12px 12px 0;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.runner {
  position: relative;
  display: grid;
  grid-template-columns: 18px 44px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-height: 62px;
  padding: 6px 10px 6px 8px;
  box-sizing: border-box;
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
  transition: background 240ms var(--ease-out), box-shadow 240ms var(--ease-out);
}
.rank-move {
  transition: transform 520ms var(--ease-in-out);
}
/* Whose turn it is: the row latched in coral. */
.runner.turn {
  background: var(--c-200);
  box-shadow: 0 0 0 2px var(--c-500), var(--shadow-paper);
}
.no {
  text-align: center;
  font: 800 var(--fs-heading)/1 var(--font-latin);
  color: var(--ink-3);
}
.runner.first .no {
  color: var(--gold);
  text-shadow: 0 1px 0 rgba(var(--c-900-rgb), 0.14);
}
.runner .face {
  --tuanzi-size: 44px;
}
.who {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.line {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}
.hue {
  flex: none;
  width: 4px;
  height: 13px;
  border-radius: 2px;
}
.name {
  font: 800 var(--fs-body)/1.1 var(--font);
  color: var(--ink);
  white-space: nowrap;
}
.trait {
  flex: none;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--c-500);
  font: 800 var(--fs-caption)/1.1 var(--font);
  color: var(--ink);
  white-space: nowrap;
}
.does {
  overflow: hidden;
  font: 700 var(--fs-caption)/1.1 var(--font);
  color: var(--ink-2);
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* How far along: a crisp bar paired with the runner's exact square count, gold for the 1st-place leader. */
.along-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.along {
  flex: 1 1 0;
  display: block;
  height: 4px;
  border-radius: 2px;
  background: var(--c-100);
  overflow: hidden;
}
.along > i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--c-400), var(--c-500));
  transition: width 480ms var(--ease-out);
}
.runner.first .along > i {
  background: var(--grad-gold);
}
.sq-num {
  flex: none;
  min-width: 28px;
  text-align: right;
  font: 800 11px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-3);
}
.runner.first .sq-num {
  color: var(--c-700);
}
.tail {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
}
/* Three faces to a row: a six-sided die takes two rows, not the words' room. */
.form {
  display: grid;
  grid-template-columns: repeat(3, auto);
  gap: 2px;
}
.form .race-die {
  --s: 12px;
  --die-shadow: none;
}
.mine {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.mine img {
  width: 15px;
  height: 15px;
}
/* My bets: notched paper stubs under the field, the winners coral once the race is run. */
.tickets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 2px 1px;
  list-style: none;
  overflow: hidden;
}
.ticket {
  display: inline-flex;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.14)) drop-shadow(0 2px 4px rgba(var(--c-900-rgb), 0.12));
}
.ticket-paper {
  --x: 8px;
  --bite: 3.2px;
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 9px 0 13px;
  box-sizing: border-box;
  border-radius: var(--radius-s);
  background: var(--surface);
  -webkit-mask:
    radial-gradient(circle at var(--x) 0, transparent var(--bite), #000 calc(var(--bite) + 0.5px)),
    radial-gradient(circle at var(--x) 100%, transparent var(--bite), #000 calc(var(--bite) + 0.5px));
  -webkit-mask-composite: source-in;
  mask:
    radial-gradient(circle at var(--x) 0, transparent var(--bite), #000 calc(var(--bite) + 0.5px)),
    radial-gradient(circle at var(--x) 100%, transparent var(--bite), #000 calc(var(--bite) + 0.5px));
  mask-composite: intersect;
}
.ticket .perf {
  position: absolute;
  top: 5px;
  bottom: 5px;
  left: var(--x);
  width: 3px;
  margin-left: -1.5px;
  background: radial-gradient(circle, var(--c-400) 1.1px, transparent 1.5px) 50% 0 / 3px 5px repeat-y;
}
.ticket small {
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
.ticket b {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}
.ticket .coin {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  margin-left: 2px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink-2);
}
.ticket .coin img {
  width: 14px;
  height: 14px;
}
.ticket.won .ticket-paper {
  background: var(--c-500);
}
.ticket.won .perf {
  background: radial-gradient(circle, #fff 1.1px, transparent 1.5px) 50% 0 / 3px 5px repeat-y;
}
.ticket.won small,
.ticket.won .coin {
  color: var(--ink);
}

/*
 * ---- under the board: the lineup dock, five seats in left-to-right turn order, each a die over its tuanzi.
 */
.deck {
  grid-area: deck;
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0 18px 9px;
}
.lineup {
  --seat: 54px;
  --die-size: calc(var(--seat) * 0.62);
  --face: calc(var(--seat) * 0.66);
  display: flex;
  align-items: flex-end;
  gap: 20px;
  margin: 0;
  padding: 6px 20px 7px;
  list-style: none;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.seat {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: calc(var(--seat) * 0.1);
  width: var(--seat);
}
/* Directional chevron between seats showing left-to-right play order. */
.seat + .seat::before {
  content: "";
  position: absolute;
  left: -13px;
  bottom: calc(var(--seat) * 0.36);
  width: 5px;
  height: 5px;
  border-top: 2px solid var(--c-300);
  border-right: 2px solid var(--c-300);
  rotate: 45deg;
  pointer-events: none;
}
/* The die rests on the seat's top; it rises when its tuanzi's turn comes, and fades once that move is done. */
.slot {
  display: grid;
  place-items: end center;
  width: var(--die-size);
  height: var(--die-size);
}
.seat-die {
  --s: var(--die-size);
  transition: opacity 280ms var(--ease-out), translate 280ms var(--ease-pop), scale 280ms var(--ease-pop);
}
.seat-die.out {
  opacity: 0.35;
}
.seat.turn .seat-die {
  translate: 0 calc(var(--seat) * -0.16);
  scale: 1.08;
  filter: drop-shadow(0 0 calc(var(--seat) * 0.08) rgba(var(--c-500-rgb), 0.9));
}
.seat .head {
  display: grid;
  place-items: center;
  width: var(--seat);
  height: calc(var(--seat) * 0.8);
  border-radius: 999px;
  background: var(--c-100);
  --tuanzi-size: var(--face);
  transition:
    translate 280ms var(--ease-pop),
    opacity 280ms var(--ease-out),
    background 280ms var(--ease-out),
    box-shadow 280ms var(--ease-out);
}
.seat.done .head {
  opacity: 0.56;
}
.seat.turn .head {
  opacity: 1;
  translate: 0 -4px;
  background: var(--c-500);
  box-shadow: var(--shadow-backlight);
}
.seat.waiting .head {
  animation: seat-glow 1s var(--ease-in-out) infinite alternate;
}
@keyframes seat-glow {
  from { box-shadow: 0 0 0 0 rgba(var(--c-500-rgb), 0.6); }
  to { box-shadow: 0 0 0 7px rgba(var(--c-500-rgb), 0); }
}
.seat-move {
  transition: transform 640ms var(--ease-in-out);
}
/* Post-race final board dock: sits in the deck strip below the board so no tile is ever obscured. */
.board-dock {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  padding: 6px 10px 6px 14px;
  border-radius: 999px;
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.dock-label {
  font: 800 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
  white-space: nowrap;
}
.board-dock .ui-btn {
  gap: 5px;
}
/* The last round: a crisp coral badge stamped cleanly at the deck's upper right. */
.cue {
  position: absolute;
  z-index: 3;
  right: 22px;
  top: 2px;
  margin: 0;
  padding: 4px 12px;
  border-radius: 999px;
  background: var(--c-500);
  box-shadow: 0 0 0 2px var(--surface), var(--shadow-backlight);
  font: 800 var(--fs-body)/1.2 var(--font);
  color: var(--ink);
  white-space: nowrap;
  animation: cue 2.6s var(--ease-out) both;
}
@keyframes cue {
  0% { opacity: 0; transform: scale(1.6); }
  14% { opacity: 1; transform: scale(0.94); }
  22% { transform: scale(1); }
  85% { opacity: 1; transform: scale(1); }
  100% { opacity: 0; transform: scale(1); }
}

.calm .dot,
.calm .net b,
.calm .cue,
.calm .seat.waiting .head {
  animation: none;
}
.calm .rank-move,
.calm .seat-move,
.calm .seat .head,
.calm .seat-die,
.calm .along > i,
.calm .round-pips i,
.calm .progress,
.calm .mark,
.calm .scrim-enter-active,
.calm .scrim-leave-active,
.calm .card-enter-active,
.calm .card-leave-active {
  transition: none;
}

/* A low window: the deck and the rows close up. */
@container watch (max-height: 640px) {
  .sheet {
    grid-template-rows: 46px minmax(0, 1fr) 88px;
  }
  .lineup {
    --seat: 44px;
    gap: 16px;
    padding: 4px 16px 5px;
  }
  .seat + .seat::before {
    left: -11px;
  }
  .board-dock {
    margin-bottom: 4px;
  }
  .result {
    gap: 9px;
    padding: 24px 28px 14px;
  }
  .runner {
    min-height: 54px;
  }
  .does {
    display: none;
  }
}
@container watch (max-width: 940px) {
  .sheet {
    grid-template-columns: minmax(0, 1fr) 236px;
  }
  .form,
  .round-pips {
    display: none;
  }
}
</style>
