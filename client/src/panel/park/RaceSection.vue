<script setup lang="ts">
// 团子赛跑 (docs/design/amusement-park.md §6, protocol/PROTOCOL.md 团子赛跑). There is no push channel: while the
// page is shown the section asks GET /api/park/race (every 10 s while bets are open, soon around the start and the
// end), keeps the offset to the server's clock, and plays the race's move list from startsAt, so every client shows
// the same moment. The odds move with the coins staked until the start; a bet sends the odds the player saw and
// locks them, and when they have dropped meanwhile the slip shows the new ones to confirm. The countdown, the rules
// key and the host (the latest champion) go up in the park's coral band (band.ts).
// The page is the board (RaceTrack) with an infield that holds one thing at a time: the odds board (five runner keys,
// each with its odds and stakes for every kind) while bets are open or the race is void; the order's dice at the
// start; while it runs, the tuanzi whose turn it is beside the big die, over a small row of the order of play; the
// podium once it has finished. The odds board folds away as the race comes out, the tuanzi fly from their squares
// onto the podium at the finish, and the odds board rises again for the next race. The bet slip is the bottom bar,
// with my tickets when nothing is picked.
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import { manifest } from "../../manifest";
import { online } from "../../stores/player";
import { loadPark, parkTry } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import { ACHAO } from "../../ui/achao";
import Icon from "../../ui/Icon.vue";
import { EASE_OUT } from "../../ui/motion";
import { useBand } from "./band";
import RaceDie, { type Toss } from "./RaceDie.vue";
import RaceRules from "./RaceRules.vue";
import RaceTrack from "./RaceTrack.vue";
import TuanziToken from "./TuanziToken.vue";
import { COIN_SMALL } from "./coin";
import {
  hits, KIND_NAMES, OPEN_ROLL_MS, openingAt, playhead, staggered, stageOf, stepLength, stepPhases, stepStart,
  tuanziArt, type Race, type RaceAnswer, type RaceKind,
} from "./race";

// The bundled manifest always has the race; the server checks every number again.
const CFG = manifest.economy.park!.race!;
/** The members in manifest order: the lanes before a race's own are drawn. */
const MEMBERS = manifest.characters.map((c) => c.id);
const KINDS = CFG.kinds;
/** How often the odds are asked for while bets are open, ms. */
const BETTING_POLL = 10_000;
/** How often the race is asked for while it is about to start, ms. */
const STARTING_POLL = 350;
/** How long the last round's cue stays up, ms. */
const CUE_MS = 2600;
/** The faces of the order's die. */
const ORDER_FACES = [1, 2, 3, 4, 5, 6];
/** How long a win counts up beside the podium, ms. */
const COUNT_MS = 1200;
const fmt = (n: number) => Math.abs(n).toLocaleString("en-US");
const character = (m: string) => manifest.characters.find((c) => c.id === m);
const nameOf = (m: string) => character(m)?.name ?? m;
const colorOf = (m: string) => character(m)?.color ?? "var(--c-500)";
const x = (n: number | undefined) => (n === undefined ? "" : `×${n.toFixed(1)}`);

const data = ref<RaceAnswer | null>(null);
const loadError = ref("");
/** Server time minus local time, ms. */
const offset = ref(0);
const now = ref(Date.now());
const serverNow = computed(() => now.value + offset.value);

const race = computed(() => data.value?.race ?? null);
const last = computed(() => data.value?.last ?? null);
const phase = computed(() => race.value?.phase ?? null);
/** The race is still playing on screen (its moves are out, its end not reached). */
const playing = computed(() => {
  const r = race.value;
  return !!r?.moves && !!r.endsAt && serverNow.value < r.endsAt * 1000;
});
const finished = computed(() => {
  const r = race.value;
  return !!r?.ranking && !!r.endsAt && serverNow.value >= r.endsAt * 1000;
});

// ---------------------------------------------------------------- polling and the clock
let active = false;
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let clockTimer: ReturnType<typeof setInterval> | null = null;
let loading = false;
const hidden = () => typeof document !== "undefined" && document.visibilityState === "hidden";

/** When to ask next: every 10 s while bets are open, soon around the start and the end, slowly otherwise. */
function nextDelay(): number {
  const r = race.value;
  const t = serverNow.value;
  const until = (at: number) => at * 1000 - t + 300;
  if (!r || r.phase === "done" || r.phase === "void") return Math.max(1000, Math.min(5000, until(data.value?.nextAt ?? 0)));
  if (r.phase === "betting") return Math.max(1000, Math.min(BETTING_POLL, until(r.startsAt)));
  if (r.phase === "running" && r.endsAt && t < r.endsAt * 1000) return Math.max(1000, until(r.endsAt));
  // Starting: the server starts the race on its next tick; the opening's dice come with it.
  return r.phase === "starting" ? STARTING_POLL : 1000;
}

async function poll() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
  // A hidden window asks again once it shows (onVisible).
  if (!active || loading || hidden()) return;
  loading = true;
  const sent = Date.now();
  const reply = await parkTry<RaceAnswer>("GET", "/api/park/race");
  loading = false;
  if (reply.ok) {
    const got = Date.now();
    offset.value = reply.data.now * 1000 - (sent + got) / 2;
    data.value = reply.data;
    loadError.value = "";
  } else if (reply.error.status > 0) {
    loadError.value = reply.error.message;
  }
  if (active) pollTimer = setTimeout(poll, reply.ok ? nextDelay() : 5000);
}

function onVisible() {
  if (!hidden()) void poll();
}
function start() {
  if (active) return;
  active = true;
  void poll();
  clockTimer = setInterval(() => (now.value = Date.now()), 100);
  document.addEventListener("visibilitychange", onVisible);
}
function stop() {
  active = false;
  if (pollTimer) clearTimeout(pollTimer);
  if (clockTimer) clearInterval(clockTimer);
  pollTimer = null;
  clockTimer = null;
  document.removeEventListener("visibilitychange", onVisible);
}
onMounted(start);
onActivated(start);
onDeactivated(stop);
onBeforeUnmount(stop);

// ---------------------------------------------------------------- the countdown
function clock(sec: number): string {
  const s = Math.max(0, Math.ceil(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
const countdown = computed<{ label: string; time: string }>(() => {
  const r = race.value;
  const t = serverNow.value / 1000;
  if (r?.phase === "betting") return { label: "开跑", time: clock(r.startsAt - t) };
  if (r && (r.phase === "starting" || playing.value)) return { label: "比赛中", time: "" };
  return { label: "下一场", time: clock((data.value?.nextAt ?? t) - t) };
});
/** Winners come newest first. */
const champion = computed(() => data.value?.winners[0]?.member ?? "");
/** The rules sheet is open. */
const rules = ref(false);
useBand("race", () => ({
  ...(champion.value && tuanziArt(champion.value)
    ? { host: tuanziArt(champion.value), hostKind: "token" as const }
    : { host: ACHAO["观察"] }),
  timer: { label: countdown.value.label, time: countdown.value.time || undefined },
  info: { label: "规则", open: () => (rules.value = true) },
}));

// ---------------------------------------------------------------- the race under way
const head = computed(() => {
  const r = race.value;
  return r?.start && r.moves?.length ? playhead(r, serverNow.value) : null;
});
/** The opening (the dice for the order) while it plays. */
const opening = computed(() => (race.value && playing.value ? openingAt(race.value, serverNow.value) : null));
/** The order of play: the manifest's until the opening has settled it; none for a race from before the opening. */
const seats = computed<string[]>(() => {
  const r = race.value;
  if (r?.order && (!opening.value || opening.value.lined)) return r.order;
  return r?.order || !r?.moves ? MEMBERS : [];
});
/**
 * A member's die in the opening: the face it shows, keyed by the round it was last thrown in, so each throw remounts
 * it once; the throw while its round is in the air (staggered among those throwing), dimmed once its place is settled.
 */
function seatDie(m: string): { key: string; face: number; toss: Toss | null; out: boolean } | null {
  const o = opening.value;
  const rolls = race.value?.rolls;
  if (!o || !rolls || o.round < 0) return null;
  const k = o.rolling.indexOf(m);
  let thrown = o.round;
  while (thrown > 0 && !rolls[thrown].some((r) => r.m === m)) thrown--;
  if (k >= 0 && o.tumbling) {
    const face = rolls[o.round][k].face;
    const { delay, ms } = staggered(OPEN_ROLL_MS, k, o.rolling.length);
    const toss = reducedMotion.value ? null : { ms, delay, at: o.since, pool: ORDER_FACES, seed: MEMBERS.indexOf(m), height: 95 };
    return { key: `${m}${thrown}`, face, toss, out: false };
  }
  return { key: `${m}${thrown}`, face: o.faces[m] ?? 0, toss: null, out: k < 0 && !o.lined };
}
const seatDice = computed(() => Object.fromEntries(seats.value.map((m) => [m, seatDie(m)])));
/** Who stands in the middle: whose turn it is, the last to move between steps, the first to move before them. */
const hero = computed(() => {
  const r = race.value;
  const h = head.value;
  const moves = r?.moves ?? [];
  if (h && h.current >= 0) return moves[h.current].m;
  if (h && h.done > 0) return moves[h.done - 1].m;
  return r?.order?.[0] ?? "";
});
/** Whose turn it is in the step under way, and where the step is. */
const turn = computed(() => {
  const r = race.value;
  const h = head.value;
  if (!r?.moves || !h || h.current < 0) return null;
  return { m: r.moves[h.current].m, stage: stageOf(h.part) };
});
/**
 * The big die: blank until the first roll; while a mover is lit, the last face resting; then thrown once for the
 * step's roll (a new key remounts it), landing on the face. Hidden while the opening's own dice are out.
 */
const bigDie = computed<{ key: string; face: number; toss: Toss | null; rest: boolean } | null>(() => {
  const r = race.value;
  const h = head.value;
  if (opening.value || !r) return null;
  const moves = r.moves ?? [];
  const i = h ? (h.current >= 0 ? h.current : h.done - 1) : -1;
  const s = moves[i];
  const faceOf = (k: number) => moves[k]?.dice.at(-1) ?? moves[k]?.steps ?? 0;
  if (!h || !s) return { key: "blank", face: 0, toss: null, rest: true };
  const stage = h.current >= 0 ? stageOf(h.part) : "walk";
  if (stage === "lit") return { key: `${i}rest`, face: faceOf(i - 1), toss: null, rest: true };
  const len = stepLength(r, i);
  const p = stepPhases(len);
  const at = h.current >= 0 ? h.part * len - p.rollAt : p.rollLen;
  const toss = reducedMotion.value || at >= p.rollLen
    ? null
    : { ms: Math.round(p.rollLen), at, pool: CFG.dice, seed: i, height: 70 };
  return { key: `${i}roll`, face: faceOf(i), toss, rest: false };
});
/** The last round has just begun. */
const lastRound = computed(() => {
  const r = race.value;
  if (!r?.moves || r.slowFrom === undefined || r.slowFrom >= r.moves.length || !playing.value) return false;
  const at = serverNow.value - r.startsAt * 1000 - stepStart(r, r.slowFrom);
  return at >= 0 && at < CUE_MS;
});

// ---------------------------------------------------------------- the odds board
const betting = computed(() => phase.value === "betting" && serverNow.value < (race.value?.startsAt ?? 0) * 1000);
const staked = computed(() => race.value?.mine.reduce((n, b) => n + b.coins, 0) ?? 0);
const left = computed(() => Math.max(0, CFG.maxCoins - staked.value));
const oddsOf = (kind: RaceKind, m: string) => race.value?.odds[kind]?.[m];
const coinsOn = (kind: RaceKind, m: string) => race.value?.pool[kind]?.[m] ?? 0;
/**
 * How much of [kind]'s market [m]'s coins hold, 0 to 1: the stake's weight in the odds (race.py odds_tenths), where
 * the house's depth counts as coins spread evenly, so a first coin on a quiet race shows as the small move it is.
 */
function share(kind: RaceKind, m: string): number {
  const n = MEMBERS.length;
  const all = Object.values(race.value?.pool[kind] ?? {}).reduce((a, c) => a + c, 0);
  return (n * coinsOn(kind, m)) / (n * all + CFG.depth);
}

/** Odds that just moved: up or down, and a count so the cell replays its tick. */
const ticks = ref<Record<string, { dir: "up" | "down"; n: number }>>({});
let seen: { id: number; odds: Race["odds"] } | null = null;
let tickCount = 0;
watch(race, (r) => {
  if (r && seen?.id === r.id && r.phase === "betting") {
    for (const k of KINDS) {
      for (const m of MEMBERS) {
        const was = seen.odds[k]?.[m];
        const is = r.odds[k]?.[m];
        if (was === undefined || is === undefined || was === is) continue;
        const n = ++tickCount;
        ticks.value = { ...ticks.value, [`${k}${m}`]: { dir: is > was ? "up" : "down", n } };
        setTimeout(() => {
          if (ticks.value[`${k}${m}`]?.n !== n) return;
          const { [`${k}${m}`]: _, ...rest } = ticks.value;
          ticks.value = rest;
        }, 1800);
      }
    }
  }
  seen = r ? { id: r.id, odds: r.odds } : null;
});
const tickOf = (kind: RaceKind, m: string) => ticks.value[`${kind}${m}`];

// ---------------------------------------------------------------- bets
const pick = ref<{ kind: RaceKind; member: string } | null>(null);
const stake = ref(1);
const busy = ref(false);
const betError = ref("");
/** The odds of the pick dropped while the bet was on its way: what they were, to confirm at the new ones. */
const repriced = ref<{ kind: RaceKind; member: string; was: number } | null>(null);
const confirming = computed(() =>
  !!repriced.value && repriced.value.kind === pick.value?.kind && repriced.value.member === pick.value?.member,
);

watch(() => race.value?.id, () => {
  pick.value = null;
  betError.value = "";
});
watch(() => [pick.value?.member, pick.value?.kind], () => (repriced.value = null));
watch(left, (n) => (stake.value = Math.max(1, Math.min(stake.value, n))));

/** A runner key: picks that runner (keeping the kind picked last, the win at first), or lets go of it. */
function chooseRunner(member: string) {
  if (!betting.value) return;
  pick.value = pick.value?.member === member ? null : { kind: pick.value?.kind ?? "win", member };
  stake.value = Math.max(1, Math.min(stake.value, left.value));
  betError.value = "";
}
function chooseKind(kind: RaceKind) {
  if (!betting.value || !pick.value) return;
  pick.value = { ...pick.value, kind };
  betError.value = "";
}

async function place() {
  const r = race.value;
  const p = pick.value;
  if (!r || !p || busy.value || !left.value) return;
  const odds = oddsOf(p.kind, p.member);
  busy.value = true;
  betError.value = "";
  const reply = await parkTry<{ race: Race }>("POST", "/api/park/race/bet", {
    race: r.id, kind: p.kind, member: p.member, coins: stake.value, odds,
  });
  busy.value = false;
  if (reply.ok) {
    if (data.value) data.value = { ...data.value, race: reply.data.race };
    pick.value = null;
    void poll();
  } else if (reply.error.code === "odds_changed" && typeof reply.error.detail.odds === "number" && data.value?.race) {
    // The new odds go on the slip; the player presses again to take them.
    const cur = data.value.race;
    const fresh = reply.error.detail.odds;
    data.value = {
      ...data.value,
      race: { ...cur, odds: { ...cur.odds, [p.kind]: { ...cur.odds[p.kind], [p.member]: fresh } } },
    };
    repriced.value = { kind: p.kind, member: p.member, was: odds ?? fresh };
  } else betError.value = reply.error.message;
}

/** My coins on [m] in the race on the track. */
const mineOn = (m: string) => race.value?.mine.filter((b) => b.member === m).reduce((n, b) => n + b.coins, 0) ?? 0;
/**
 * My bets as tickets, one per selection: the odds each bet locked (most first; a range when there are more than
 * two), the coins in all, and whether it won once the race is run.
 */
const tickets = computed(() => {
  const r = race.value;
  const out: { key: string; kind: RaceKind; member: string; odds: number[]; coins: number; won: boolean }[] = [];
  for (const b of r?.mine ?? []) {
    const key = `${b.kind}${b.member}`;
    const t = out.find((o) => o.key === key);
    if (t) {
      t.coins += b.coins;
      if (!t.odds.includes(b.odds)) t.odds.push(b.odds);
    } else out.push({ key, kind: b.kind, member: b.member, odds: [b.odds], coins: b.coins, won: false });
  }
  for (const t of out) {
    t.odds.sort((a, b) => b - a);
    if (finished.value && r?.ranking) t.won = hits(t.kind, t.member, r.ranking);
  }
  return out;
});
const oddsList = (odds: number[]) =>
  odds.length > 2 ? `×${odds[0].toFixed(1)}–${odds[odds.length - 1].toFixed(1)}` : odds.map(x).join(" ");
/** Every bet of a ticket with its own odds, for its tooltip. */
const ticketTitle = (t: { kind: RaceKind; member: string }) =>
  (race.value?.mine ?? []).filter((b) => b.kind === t.kind && b.member === t.member)
    .map((b) => `${nameOf(b.member)} ${KIND_NAMES[b.kind]} ${x(b.odds)} · ${b.coins} 枚`).join("\n");
/** Why the bet key cannot be pressed, for its tooltip. With no runner picked the key is simply off. */
const betBlock = computed(() => (!online.value ? "未连接" : ""));

// ---------------------------------------------------------------- results
/** The race whose result is shown: this one once it has played, the one before while bets are open. */
const shown = computed<Race | null>(() => (finished.value ? race.value : betting.value ? last.value : null));
const result = computed(() => shown.value?.result ?? null);
// The park's balance and today's result follow a race the save had bets in.
watch(() => (race.value?.phase === "done" && race.value.mine.length ? race.value.id : null), (id) => {
  if (id) void loadPark();
});
/** The shards my bets won, counting up from 0 once the result is in; nothing shows for a race that won nothing. */
const won = computed(() => result.value?.won ?? 0);
const counted = ref(0);
let countFrame = 0;
watch(() => [shown.value?.id, won.value] as const, ([, to]) => {
  cancelAnimationFrame(countFrame);
  if (!to || reducedMotion.value) {
    counted.value = to;
    return;
  }
  const start = performance.now();
  counted.value = 0;
  const step = (t: number) => {
    const k = Math.min(1, (t - start) / COUNT_MS);
    counted.value = Math.round(to * (1 - (1 - k) ** 3));
    if (k < 1) countFrame = requestAnimationFrame(step);
  };
  countFrame = requestAnimationFrame(step);
}, { immediate: true });
onBeforeUnmount(() => cancelAnimationFrame(countFrame));

/** What the infield holds: the odds board, the race under way, or the podium. */
const infield = computed<"field" | "run" | "podium">(() => {
  if (finished.value) return "podium";
  if (betting.value || !race.value || race.value.phase === "void") return "field";
  return "run";
});
const ranking = computed(() => (finished.value ? race.value?.ranking ?? [] : []));
/** A place lights up when one of my bets on the tuanzi in it won. */
function lit(place: number): boolean {
  const r = race.value;
  const m = ranking.value[place];
  return !!r && !!m && r.mine.some((b) => b.member === m && hits(b.kind, b.member, ranking.value));
}
/** A place I had bets on, none of which won: it greys out. */
function missed(place: number): boolean {
  const m = ranking.value[place];
  return !!m && !!race.value?.mine.some((b) => b.member === m) && !lit(place);
}

// ---------------------------------------------------------------- between the phases
/*
 * The panes cross-fade (the board folds away, the race comes in; the podium fades, the board rises). At the finish
 * there is no fade: the panes swap at once and each tuanzi flies from its square on the board onto the podium
 * (FLIP), the steps rising under them. Without motion every change is a plain swap.
 */
const infieldEl = ref<HTMLElement | null>(null);
const cut = ref(reducedMotion.value);
let flipFrom: Map<string, DOMRect> | null = null;
watch(infield, (to, from) => {
  const flip = from === "run" && to === "podium";
  cut.value = reducedMotion.value || flip;
  flipFrom = null;
  if (!flip || reducedMotion.value || !infieldEl.value) return;
  flipFrom = new Map();
  const board = infieldEl.value.closest(".board");
  for (const el of board?.querySelectorAll<HTMLElement>(".tz[data-m]") ?? []) {
    const token = el.querySelector(".tuanzi-token");
    if (token) flipFrom.set(el.dataset.m!, token.getBoundingClientRect());
  }
  void nextTick(flyToPodium);
}, { flush: "pre" });

function flyToPodium() {
  const from = flipFrom;
  flipFrom = null;
  const root = infieldEl.value?.querySelector<HTMLElement>(".podium");
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
  });
}
</script>

<template>
  <section class="race" :class="{ calm: reducedMotion }" aria-label="团子赛跑">
    <p v-if="loadError" class="ui-error load-error" role="alert">{{ loadError }}</p>

    <RaceTrack class="lap" :race="race" :t="serverNow" :track="CFG.track" :members="MEMBERS" :cleared="infield === 'podium'">
      <div ref="infieldEl" class="panes">
        <Transition name="swap" :css="!cut">
          <!-- Bets open, a void race, or nothing loaded yet: the odds board. -->
          <div v-if="infield === 'field'" key="field" class="pane field-pane">
            <p v-if="race?.phase === 'void'" class="void" role="status">本场取消，驼币已退回</p>
            <div class="odds-board" role="group" aria-label="团子">
              <div class="legend who" :title="race ? `${race.bettors ?? 0} 人` : undefined">
                <Icon name="people" :size="16" /><b>{{ race?.bettors ?? 0 }}</b>
              </div>
              <span v-for="(k, r) in KINDS" :key="k" class="legend kind" :style="{ gridRow: r + 3 }">{{ KIND_NAMES[k] }}</span>
              <button
                v-for="m in MEMBERS" :key="m" type="button" class="ui-btn runner-key"
                :class="{ on: pick?.member === m }" :aria-pressed="pick?.member === m"
                :disabled="!betting || !online || !left" @click="chooseRunner(m)"
              >
                <TuanziToken class="face" :member="m" :size="48" :grey="race?.phase === 'void'" :style="{ gridRow: 1 }" />
                <span class="name" :style="{ gridRow: 2 }"><i class="bar" :style="{ background: colorOf(m) }"></i>{{ nameOf(m) }}</span>
                <span
                  v-for="(k, r) in KINDS" :key="`${k}${tickOf(k, m)?.n ?? 0}`" class="cell" :style="{ gridRow: r + 3 }"
                  :class="[tickOf(k, m)?.dir, { chosen: pick?.member === m && pick.kind === k }]"
                  :title="race ? `${coinsOn(k, m)} 枚` : undefined"
                >
                  <i class="fill" :style="{ width: `${share(k, m) * 100}%` }"></i>
                  <b>{{ x(oddsOf(k, m)) }}</b>
                  <small v-if="coinsOn(k, m)" class="coins"><img :src="COIN_SMALL" alt="" draggable="false" />{{ coinsOn(k, m) }}</small>
                  <svg v-if="tickOf(k, m)" class="arrow" viewBox="0 0 12 12" aria-hidden="true">
                    <path v-if="tickOf(k, m)!.dir === 'up'" d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" />
                    <path v-else d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" />
                  </svg>
                </span>
                <span v-if="mineOn(m)" class="mine"><img :src="COIN_SMALL" alt="" draggable="false" /><b>{{ mineOn(m) }}</b></span>
              </button>
            </div>
          </div>

          <!--
            Under way: the tuanzi whose turn it is beside the big die, over the order of play; in the opening the order
            alone, each with its own die. The last round's cue in the corner.
          -->
          <div v-else-if="infield === 'run'" key="run" class="pane run-pane">
            <div class="stage" :class="{ opening: !!opening }">
              <div class="hero" aria-hidden="true">
                <Transition name="hero" :css="!reducedMotion">
                  <span
                    v-if="hero && !opening" :key="hero" class="hero-tz"
                    :class="{ waiting: turn?.m === hero && turn.stage !== 'walk' }"
                  ><TuanziToken :member="hero" :size="72" /></span>
                </Transition>
                <div class="well">
                  <RaceDie
                    v-if="bigDie" :key="bigDie.key" class="big-die" :class="{ rest: bigDie.rest }" :face="bigDie.face"
                    :toss="bigDie.toss"
                  />
                </div>
              </div>
              <TransitionGroup v-if="seats.length" tag="ol" name="seat" class="order" aria-label="出场顺序">
                <li
                  v-for="m in seats" :key="m" class="seat"
                  :class="{ turn: turn?.m === m, waiting: turn?.m === m && turn.stage !== 'walk' }" :title="nameOf(m)"
                >
                  <span class="head"><TuanziToken :member="m" :size="48" /></span>
                  <RaceDie
                    v-if="seatDice[m]" :key="seatDice[m]!.key" class="mini-die" :class="{ out: seatDice[m]!.out }"
                    :face="seatDice[m]!.face" :toss="seatDice[m]!.toss"
                  />
                </li>
              </TransitionGroup>
            </div>
            <p v-if="lastRound" class="cue" role="status">最后一轮</p>
          </div>

          <!-- Finished: the podium, the last two on the floor beside it, and what my bets won. -->
          <div v-else key="podium" class="pane podium-pane">
            <div class="result">
              <ol class="podium" aria-label="本场名次">
                <li
                  v-for="(m, i) in ranking" :key="m" class="place" :class="[`p${i + 1}`, { lit: lit(i), missed: missed(i) }]"
                  :title="nameOf(m)"
                >
                  <TuanziToken :member="m" :size="i === 0 ? 72 : i < 3 ? 48 : 32" :grey="missed(i)" :data-m="m" />
                  <span class="step">{{ i + 1 }}</span>
                </li>
              </ol>
              <p v-if="won > 0" class="net" role="status" :aria-label="`+${fmt(won)}`">
                <Icon name="shard" :size="24" /><b>+{{ fmt(counted) }}</b>
              </p>
            </div>
          </div>
        </Transition>
      </div>
    </RaceTrack>

    <RaceRules v-if="rules" @close="rules = false" />

    <!-- The bet slip. -->
    <div class="park-actions slip">
      <template v-if="betting && pick && race">
        <span class="picked"><i class="bar" :style="{ background: colorOf(pick.member) }"></i>{{ nameOf(pick.member) }}</span>
        <span class="kinds" role="group" :aria-label="`${nameOf(pick.member)}的押法`">
          <button
            v-for="k in KINDS" :key="k" type="button" class="ui-btn kind-key"
            :class="{ on: pick.kind === k, repriced: confirming && pick.kind === k }" :aria-pressed="pick.kind === k"
            @click="chooseKind(k)"
          >
            <small>{{ KIND_NAMES[k] }}</small>
            <s v-if="confirming && pick.kind === k">{{ x(repriced!.was) }}</s>
            <b>{{ x(oddsOf(k, pick.member)) }}</b>
          </button>
        </span>
      </template>
      <template v-else>
        <span v-if="tickets.length" class="tickets" aria-label="我的押注">
          <span
            v-for="t in tickets" :key="t.key" class="ticket" :class="{ won: t.won }"
            :title="ticketTitle(t)"
          >
            <TuanziToken :member="t.member" :size="24" />
            <small>{{ KIND_NAMES[t.kind] }}</small><b>{{ oddsList(t.odds) }}</b>
            <span class="coin"><img :src="COIN_SMALL" alt="" draggable="false" />{{ t.coins }}</span>
          </span>
        </span>
        <span v-else-if="data?.winners.length" class="champs" aria-label="最近冠军">
          <span v-for="w in data.winners" :key="w.id" :title="nameOf(w.member)"><TuanziToken :member="w.member" :size="24" /></span>
        </span>
        <span v-if="betting && won > 0" class="last-net">
          <Icon name="shard" :size="14" />+{{ fmt(won) }}
        </span>
      </template>

      <div v-if="betting" class="park-actions-main">
        <span v-if="!left" class="full">本场已押满</span>
        <template v-else>
          <span v-if="pick" class="stepper">
            <button type="button" class="ui-btn small ghost" :disabled="stake <= 1" aria-label="少押一枚" @click="stake--">
              <Icon name="minus" :size="14" />
            </button>
            <b>{{ stake }}</b>
            <button type="button" class="ui-btn small ghost" :disabled="stake >= left" aria-label="多押一枚" @click="stake++">
              <Icon name="plus" :size="14" />
            </button>
          </span>
          <span v-else class="dots" :title="`本场还可押 ${left} 枚`">
            <i v-for="n in CFG.maxCoins" :key="n" :class="{ used: n > left }"></i>
          </span>
          <button
            type="button" class="ui-btn primary bet-key" :class="{ pulse: pick && !betBlock && !busy }"
            :disabled="busy || !pick || !!betBlock" :aria-busy="busy" :title="betBlock || undefined" @click="place"
          >
            <img class="coin" :src="COIN_SMALL" alt="" draggable="false" />
            <template v-if="confirming && pick">确认 {{ x(oddsOf(pick.kind, pick.member)) }}</template>
            <template v-else>押 {{ stake }} 枚</template>
          </button>
        </template>
      </div>
      <p v-if="betError" class="ui-error" role="alert">{{ betError }}</p>
    </div>
  </section>
</template>

<style scoped>
/* On the park's sheet, under the coral band: the lap fills the height, the slip is the bottom bar. */
.race {
  display: flex;
  flex-direction: column;
}
.load-error {
  margin: 14px 22px 0;
}
.lap {
  flex: 1 1 auto;
  min-height: 330px;
}

/* ---- the panes: one at a time fills the infield; one leaving lies over the next while it fades */
.panes {
  position: relative;
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.pane {
  flex: 1 1 auto;
  display: flex;
  min-height: 0;
}
.swap-leave-active {
  position: absolute;
  inset: 0;
  transition: opacity 260ms var(--ease-out), transform 260ms var(--ease-out);
}
.swap-enter-active {
  transition: opacity 420ms var(--ease-out) 120ms, transform 520ms var(--ease-out) 120ms;
}
/* The board folds away under the race and rises again for the next one; the rest fade. */
.swap-leave-to {
  opacity: 0;
}
.swap-leave-to.field-pane {
  transform: translateY(-14px) scale(0.96);
}
.swap-enter-from {
  opacity: 0;
}
.swap-enter-from.field-pane {
  transform: translateY(28px);
}

/* ---- the odds board: a legend column, then five runner keys whose rows line up with it */
.field-pane {
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}
.void {
  margin: 0;
  text-align: center;
  font: 800 var(--fs-number)/1.4 var(--font);
  color: var(--ink-2);
}
.odds-board {
  --face: 52px;
  --cell-h: 28px;
  display: grid;
  grid-template-columns: auto repeat(5, minmax(0, 1fr));
  grid-template-rows: auto auto repeat(3, var(--cell-h));
  column-gap: 8px;
  row-gap: 4px;
  width: 100%;
}
.legend {
  grid-column: 1;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
  white-space: nowrap;
}
.legend.kind {
  align-self: start;
  height: var(--cell-h);
}
/* How many have bet: over the kind names, level with the faces. */
.legend.who {
  grid-row: 1 / span 2;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  color: var(--ink-3);
}
.legend.who b {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}
.runner-key {
  grid-row: 1 / span 5;
  display: grid;
  grid-template-rows: subgrid;
  grid-template-columns: minmax(0, 1fr);
  justify-content: stretch;
  justify-items: stretch;
  align-items: center;
  min-width: 0;
  height: auto;
  padding: 8px 6px 8px;
  row-gap: 4px;
}
.runner-key .face {
  justify-self: center;
  --tuanzi-size: var(--face);
}
.name {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-width: 0;
  font: 800 var(--fs-strong)/1.2 var(--font);
  color: var(--ink);
  white-space: nowrap;
}
.bar {
  flex: none;
  width: 4px;
  height: 14px;
  border-radius: 2px;
}
/* One kind's odds on the runner: the number over a coral fill as wide as its share of that kind's coins. */
.cell {
  position: relative;
  align-self: start;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  height: var(--cell-h);
  border-radius: var(--radius-s);
  background: var(--c-100);
  overflow: hidden;
}
.runner-key.on .cell,
.runner-key:disabled .cell {
  background: var(--c-200);
}
.cell .fill {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: var(--c-300);
  transition: width var(--dur-stage) var(--ease-out);
}
.cell b {
  position: relative;
  font: 800 var(--fs-number)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
/* The coins on it, small at the cell's right end; only where the board has room. */
.cell .coins {
  position: absolute;
  right: 5px;
  display: inline-flex;
  align-items: center;
  gap: 1px;
  font: 700 var(--fs-caption)/1 var(--font-latin);
  color: var(--ink-3);
}
.cell .coins img {
  width: 10px;
  height: 10px;
  opacity: 0.8;
}
.cell.chosen {
  box-shadow: inset 0 0 0 2px var(--c-500);
}
/* An odds number that just moved: a short flare, coral and up, or grey and down. */
.cell .arrow {
  position: relative;
  width: 11px;
  height: 11px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.4;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.cell.up {
  color: var(--c-700);
  animation: tick 1.6s var(--ease-out) both;
}
.cell.down {
  color: var(--ink-3);
  animation: tick 1.6s var(--ease-out) both;
}
.cell.up b {
  color: var(--c-700);
}
@keyframes tick {
  0% { box-shadow: inset 0 0 0 2px currentColor; }
  70% { box-shadow: inset 0 0 0 2px currentColor; }
  100% { box-shadow: inset 0 0 0 0 transparent; }
}
.cell.up b,
.cell.down b {
  animation: tick-num 500ms var(--ease-pop) both;
}
.cell.down b {
  animation-name: tick-num-down;
}
@keyframes tick-num {
  from { transform: translateY(6px); opacity: 0.2; }
}
@keyframes tick-num-down {
  from { transform: translateY(-6px); opacity: 0.2; }
}
/* The coins I have on a runner: a coin stuck on the key's corner. */
.mine {
  position: absolute;
  top: -8px;
  right: -6px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 7px 2px 2px;
  border-radius: 999px;
  background: var(--surface);
  box-shadow: var(--shadow-key);
}
.mine img {
  width: 18px;
  height: 18px;
}
.mine b {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}

/*
 * ---- under way: the stage, the hero row (the tuanzi whose turn it is and the big die) over the order of play. The
 * pane is a size container: the seats follow its width, the hero row takes the height left.
 */
.run-pane {
  container: infield / size;
  position: relative;
  align-items: center;
  justify-content: center;
}
.stage {
  --seat: clamp(26px, min(7cqw, 24cqh), 48px);
  --face: calc(var(--seat) * 0.8);
  --mini: calc(var(--seat) * 0.72);
  --gap: clamp(6px, 4cqh, 14px);
  --hero: clamp(40px, 100cqh - var(--seat) - var(--gap) - 12px, 150px);
  --well: calc(var(--hero) * 0.78);
  /* How much larger the order stands in the opening (not in a very short infield). */
  --open-scale: 1.5;
  position: relative;
  display: grid;
  grid-template-rows: var(--hero) auto;
  justify-items: center;
  row-gap: var(--gap);
}
.hero {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: clamp(12px, 6cqw, 40px);
  transition: opacity 360ms var(--ease-out);
}
.stage.opening .hero {
  opacity: 0;
}
.hero-tz {
  display: block;
  width: var(--hero);
  height: var(--hero);
  line-height: 0;
  --tuanzi-size: var(--hero);
}
.hero-tz.waiting {
  filter: drop-shadow(0 0 3px var(--c-500)) drop-shadow(0 0 10px var(--c-500));
  animation: hero-glow 1s var(--ease-in-out) infinite alternate;
}
@keyframes hero-glow {
  from { filter: drop-shadow(0 0 1px var(--c-500)) drop-shadow(0 0 4px rgba(var(--c-500-rgb), 0.6)); }
}
.hero-enter-active {
  transition: opacity 260ms var(--ease-out), transform 360ms var(--ease-pop);
}
.hero-leave-active {
  position: absolute;
  transition: opacity 160ms var(--ease-out);
}
.hero-enter-from {
  opacity: 0;
  transform: translateY(12px) scale(0.8);
}
.hero-leave-to {
  opacity: 0;
}
/* The order of play: a small row of seats, first to move on the left; the one whose turn it is stands up, lit. */
.order {
  display: flex;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
  transition: translate 600ms var(--ease-out), scale 600ms var(--ease-out);
}
/* In the opening the seats carry their own dice (hung under them), come up to the middle and stand larger. */
.stage.opening .order {
  translate: 0 calc((var(--hero) + var(--gap) + 6px + var(--mini)) / -2);
  scale: var(--open-scale);
}
.seat {
  position: relative;
  width: var(--seat);
}
@container infield (max-height: 110px) {
  .stage {
    --open-scale: 1;
  }
}
.seat .head {
  display: grid;
  place-items: center;
  width: var(--seat);
  height: var(--seat);
  border-radius: 50%;
  background: var(--c-100);
  --tuanzi-size: var(--face);
  transition: translate 280ms var(--ease-pop), background 280ms var(--ease-out), box-shadow 280ms var(--ease-out);
}
.seat.turn .head {
  translate: 0 -5px;
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
/* A seat's die in the opening: thrown with the others (RaceDie), then dimmed once its place is settled. */
.mini-die {
  --s: var(--mini);
  position: absolute;
  top: calc(100% + 6px);
  left: 50%;
  margin-left: calc(var(--mini) / -2);
  transition: opacity 240ms var(--ease-out);
}
.mini-die.out {
  opacity: 0.4;
}
/* The big die: the one the steps roll, resting faded while the next mover is lit. */
.well {
  display: grid;
  place-items: center;
  width: var(--well);
  height: var(--well);
}
.big-die {
  --s: var(--well);
  transition: opacity 240ms var(--ease-out);
}
.big-die.rest {
  opacity: 0.75;
}
/* The last round: a small coral tag stamped in the infield's corner. */
.cue {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 2;
  margin: 0;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--c-500);
  box-shadow: var(--shadow-backlight);
  font: 800 var(--fs-label)/1.2 var(--font);
  color: var(--ink);
  white-space: nowrap;
  animation: cue 2.6s var(--ease-out) both;
}
@keyframes cue {
  0% { opacity: 0; transform: scale(1.6) rotate(-6deg); }
  14% { opacity: 1; transform: scale(0.94) rotate(-2deg); }
  22% { transform: scale(1) rotate(-2deg); }
  85% { opacity: 1; transform: scale(1) rotate(-2deg); }
  100% { opacity: 0; transform: scale(1) rotate(-2deg); }
}

/* ---- finished: the podium, then what my bets won; sized by the infield (a size container) */
.podium-pane {
  container: infield / size;
  align-items: center;
  justify-content: center;
}
.result {
  /* One unit of the podium: the infield's width or height, whichever is tighter. */
  --u: min(1cqw, 1.6cqh);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: clamp(10px, calc(var(--u) * 4), 36px);
}
.podium {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.place {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: clamp(40px, calc(var(--u) * 13), 84px);
  --tuanzi-size: clamp(30px, calc(var(--u) * 8), 48px);
}
/* Second on the left, the winner in the middle, third on the right; the last two stand on the floor beside. */
.place.p1 { order: 2; --tuanzi-size: clamp(40px, calc(var(--u) * 12), 72px); }
.place.p2 { order: 1; }
.place.p3 { order: 3; }
.place.p4,
.place.p5 {
  width: clamp(26px, calc(var(--u) * 7.5), 48px);
  --tuanzi-size: clamp(22px, calc(var(--u) * 5.5), 32px);
}
.place.p4 { order: 4; margin-left: clamp(4px, var(--u), 10px); }
.place.p5 { order: 5; }
.step {
  display: grid;
  place-items: center;
  width: 100%;
  height: 22px;
  border-radius: var(--radius-s) var(--radius-s) 0 0;
  background: var(--c-100);
  font: 800 var(--fs-heading)/1 var(--font-latin);
  color: var(--ink-3);
}
.p1 .step { height: clamp(30px, calc(var(--u) * 8.5), 52px); }
.p2 .step { height: clamp(22px, calc(var(--u) * 6), 36px); }
.p3 .step { height: clamp(18px, calc(var(--u) * 4.3), 26px); }
.p4 .step,
.p5 .step {
  height: 18px;
  font-size: var(--fs-number);
}
/* A place one of my winning bets is on; one I bet on that won nothing goes grey (the tuanzi too). */
.place.lit .step {
  background: var(--c-500);
  color: var(--ink);
}
.place.missed .step {
  color: var(--ink-3);
  opacity: 0.6;
}
.net {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 4px;
  color: var(--c-700);
}
.net b {
  font: 800 clamp(24px, calc(var(--u) * 7), 48px)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  animation: win-pop 600ms var(--ease-pop) both;
}
@keyframes win-pop {
  0% { transform: scale(0.6); opacity: 0; }
  100% { transform: none; opacity: 1; }
}

/* ---- the slip */
.picked {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 800 var(--fs-number)/1 var(--font);
  color: var(--ink);
}
.picked .bar {
  height: 16px;
}
.kinds {
  display: flex;
  gap: 8px;
}
.kind-key {
  gap: 5px;
  padding: 0 12px;
}
/* Latched on the slip's tonal strip: a step darker than the strip, so it still reads as down. */
.kind-key.on:not(:disabled) {
  --key-top: var(--c-300);
  --key-bottom: var(--c-300);
  --key-lip: var(--c-600);
}
.kind-key small {
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
.kind-key b {
  font: 800 var(--fs-number)/1 var(--font-latin);
}
/* The odds dropped on the way: the old ones struck out, the new ones flare once. */
.kind-key s {
  font: 700 var(--fs-label)/1 var(--font-latin);
  color: var(--ink-3);
}
.kind-key.repriced b {
  color: var(--c-800);
  animation: tick-num-down 500ms var(--ease-pop) both;
}
/* My bets: small paper tickets, the winners coral once the race is run. */
.tickets {
  display: flex;
  gap: 6px;
  mask-image: linear-gradient(90deg, #000 calc(100% - 18px), transparent);
  min-width: 0;
  max-width: 100%;
  overflow-x: auto;
  scrollbar-width: none;
  padding: 2px 2px 4px;
}
.ticket {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 9px 0 5px;
  box-sizing: border-box;
  border-radius: var(--radius-s);
  background: var(--surface);
  border-left: 3px dotted var(--c-300);
  box-shadow: 0 1px 2px rgba(var(--c-900-rgb), 0.12), 0 3px 6px -3px rgba(var(--c-900-rgb), 0.2);
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
.ticket.won {
  background: var(--c-500);
  border-left-color: #fff;
}
.ticket.won small,
.ticket.won .coin {
  color: var(--ink);
}
.champs {
  display: flex;
  align-items: center;
  gap: 4px;
}
.champs > span {
  line-height: 0;
}
.last-net {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--c-700);
}
.stepper {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.stepper b {
  min-width: 22px;
  text-align: center;
  font: 800 22px/1 var(--font-latin);
  color: var(--ink);
}
/* The coins still to bet on this race. */
.dots {
  display: inline-flex;
  gap: 5px;
}
.dots i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--c-500);
}
.dots i.used {
  background: var(--c-200);
}
.full {
  font: 700 var(--fs-body)/1 var(--font);
  color: var(--ink-2);
}
.bet-key {
  min-width: 112px;
}
.bet-key .coin {
  width: 18px;
  height: 18px;
}
.slip .ui-error {
  flex-basis: 100%;
  margin: 0;
}
/* The tickets scroll sideways rather than push the bet key onto a second line. */
.slip > .tickets {
  flex: 1 1 0;
  min-width: 0;
}

.calm .cell .fill {
  transition: none;
}
.calm .cell,
.calm .cell b,
.calm .kind-key.repriced b,
.calm .net b,
.calm .seat.waiting .head,
.calm .hero-tz.waiting {
  animation: none;
}
.calm .seat-move,
.calm .order,
.calm .seat .head,
.calm .hero,
.calm .mini-die,
.calm .big-die {
  transition: none;
}
/* Without motion the cue stands still for its time. */
.calm .cue {
  animation: none;
  transform: rotate(-2deg);
}

/* Tall panels: the board grows into the infield the race will need later. */
@container panel (min-height: 680px) and (min-width: 761px) {
  .odds-board {
    --face: 64px;
    --cell-h: 32px;
    row-gap: 6px;
  }
  .cell b {
    font-size: var(--fs-section);
  }
  .cell .coins {
    font-size: var(--fs-label);
  }
  .cell .coins img {
    width: 12px;
    height: 12px;
  }
}
@container panel (max-width: 760px) {
  .odds-board {
    --face: 40px;
    --cell-h: 22px;
    column-gap: 5px;
  }
  .runner-key {
    padding: 6px 3px;
  }
  .cell b {
    font-size: var(--fs-strong);
  }
  .cell .coins {
    display: none;
  }
  .legend {
    font-size: var(--fs-caption);
  }
}
/* Short panels: smaller faces, no names, a smaller podium (the race follows its infield: .run-pane). */
@container panel (max-height: 560px) {
  .lap {
    min-height: 250px;
  }
  .odds-board {
    --face: 28px;
    --cell-h: 18px;
    row-gap: 3px;
  }
  .runner-key {
    padding: 4px 3px;
    row-gap: 3px;
  }
  .runner-key .name {
    display: none;
  }
  .legend.who {
    grid-row: 1;
    flex-direction: row;
    gap: 3px;
  }
  .cell b {
    font-size: var(--fs-body);
  }
  .cell .coins {
    display: none;
  }
  .mine {
    top: -6px;
    right: -4px;
    padding-right: 5px;
  }
  .mine img {
    width: 14px;
    height: 14px;
  }
  .mine b {
    font-size: var(--fs-strong);
  }
}
/* Narrow panels: the kind keys stack their name over the odds, and the slip stays on one line. */
@container panel (max-width: 840px) {
  .kind-key {
    flex-direction: column;
    gap: 2px;
    min-width: 50px;
    padding: 0 8px;
  }
  .kind-key small {
    font-size: var(--fs-caption);
  }
  .kind-key b {
    font-size: var(--fs-strong);
  }
  .kind-key s {
    display: none;
  }
}
@container panel (max-width: 680px) {
  .picked {
    display: none;
  }
  .kinds {
    gap: 6px;
  }
  .stepper {
    gap: 2px;
  }
  .bet-key {
    min-width: 0;
    padding: 0 14px;
  }
  .dots {
    gap: 4px;
  }
  .dots i {
    width: 6px;
    height: 6px;
  }
  .ticket small {
    display: none;
  }
}
</style>
