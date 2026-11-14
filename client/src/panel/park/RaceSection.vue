<script setup lang="ts">
// 团子赛跑 (docs/design/amusement-park.md §6, protocol/PROTOCOL.md 团子赛跑). There is no push channel: while the
// page is shown the section asks GET /api/park/race (every 10 s while bets are open, soon around the start and the
// end), keeps the offset to the server's clock, and plays the race's move list from startsAt, so every client shows
// the same moment. The odds move with the coins staked until the start; a bet sends the odds the player saw and
// locks them, and when they have dropped meanwhile the slip shows the new ones to confirm. The countdown, the rules
// key and the host (the latest champion) go up in the park's coral band (band.ts).
// The page is the board (RaceTrack) with a sheet of paper in the middle that holds one thing at a time: the five
// runners as keys, each with its odds to win (and my coins on it), while bets are open or the race is void; the
// order's dice at the start; while it runs, the field in its order of play, each under its own die in its colour, the
// five dice thrown together at the start of each round and the one whose turn it is raised; the podium once it has
// finished. The runners fold away as the race comes out, the tuanzi fly from
// their squares onto the podium at the finish, and the runners rise again for the next race. The bet slip is the
// bottom bar: a runner picked, its three kinds, the stake and the bet key; nothing picked, my tickets, or the last
// champion and what I won on that race.
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
import ParkCoin from "./ParkCoin.vue";
import TuanziToken from "./TuanziToken.vue";
import { COIN_SMALL } from "./coin";
import {
  DICE_TOSS, hits, KIND_NAMES, OPEN_ROLL_MS, openingAt, playhead, ROUND, roundAt, roundDice, roundsOf, staggered,
  stageOf, tuanziArt, type Race, type RaceAnswer, type RaceKind,
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
/** h:mm:ss, or m:ss under an hour: a day's race is most of a day away. */
function clock(sec: number): string {
  const s = Math.max(0, Math.ceil(sec));
  const pad = (n: number) => String(n).padStart(2, "0");
  const h = Math.floor(s / 3600);
  return h ? `${h}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}` : `${Math.floor(s / 60)}:${pad(s % 60)}`;
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
/** A member's colour, for its dice. */
const colorOf = (m: string) => character(m)?.color;

/** A seat's die: its face, keyed so each throw remounts it once; the throw while it is in the air. */
interface SeatDie { key: string; face: number; toss: Toss | null; out: boolean }
/**
 * A member's die in the opening: the face it shows, keyed by the round it was last thrown in; the throw while its
 * round is in the air (staggered among those throwing), dimmed once its place is settled.
 */
function openingDie(m: string): SeatDie | null {
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
    return { key: `${m}o${thrown}`, face, toss, out: false };
  }
  return { key: `${m}o${thrown}`, face: o.faces[m] ?? 0, toss: null, out: k < 0 && !o.lined };
}
/** The round whose dice are out, once the opening is over. */
const round = computed(() => (race.value?.moves && !opening.value ? roundAt(race.value, serverNow.value) : null));
/**
 * A member's die in a round: the five thrown together at the round's start (staggered, landing by DICE_TOSS of
 * rollMs), lying in the row after; dimmed once its move is done.
 */
function roundDie(m: string): SeatDie | null {
  const r = race.value;
  const ra = round.value;
  if (!r || !ra) return null;
  const dice = roundDice(r, ra.round);
  const k = dice.findIndex((d) => d.m === m);
  if (k < 0) return null;
  const len = (r.rollMs ?? 0) * DICE_TOSS;
  const { delay, ms } = staggered(len, k, dice.length);
  const toss = reducedMotion.value || ra.since >= len
    ? null
    : { ms, delay, at: ra.since, pool: CFG.dice, seed: ra.round * ROUND + k, height: 110 };
  const i = ra.round * ROUND + k;
  const done = !!head.value && i < (r.moves?.length ?? 0) && i < head.value.done && head.value.current !== i;
  return { key: `${m}r${ra.round}`, face: dice[k].face, toss, out: done };
}
const seatDice = computed(() =>
  Object.fromEntries(seats.value.map((m) => [m, opening.value ? openingDie(m) : roundDie(m)])),
);
/** Whose turn it is in the step under way, and where the step is. */
const turn = computed(() => {
  const r = race.value;
  const h = head.value;
  if (!r?.moves || !h || h.current < 0) return null;
  return { m: r.moves[h.current].m, stage: stageOf(h.part) };
});
/** The last round's dice have just been thrown. */
const lastRound = computed(() => {
  const r = race.value;
  const ra = round.value;
  if (!r || !ra || !playing.value || roundsOf(r) < 2 || ra.round !== roundsOf(r) - 1) return false;
  return ra.since < CUE_MS;
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
/** Why the bet key cannot be pressed, for its tooltip. */
const betBlock = computed(() => (!online.value ? "未连接" : ""));

// ---------------------------------------------------------------- results
/** The race whose result is shown: this one once it has played, the one before while bets are open. */
const shown = computed<Race | null>(() => (finished.value ? race.value : betting.value ? last.value : null));
const result = computed(() => shown.value?.result ?? null);
// The park's balance and today's result follow a race the save had bets in.
watch(() => (race.value?.phase === "done" && race.value.mine.length ? race.value.id : null), (id) => {
  if (id) void loadPark();
});
/** The coins my bets won, counting up from 0 once the result is in; nothing shows for a race that won nothing. */
const won = computed(() => result.value?.won ?? 0);
/** The champion of the race shown on the slip while bets are open: the last race's. */
const lastChampion = computed(() => last.value?.ranking?.[0] ?? data.value?.winners[0]?.member ?? "");
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
          <!-- Bets open, a void race, or nothing loaded yet: the five runners, each with its odds to win. -->
          <div v-if="infield === 'field'" key="field" class="pane field-pane" :class="{ off: race?.phase === 'void' }">
            <p v-if="race?.phase === 'void'" class="void" role="status">本场取消，驼币已退回</p>
            <div class="runners" role="group" aria-label="团子">
              <button
                v-for="m in MEMBERS" :key="m" type="button" class="ui-btn runner" :data-runner="m"
                :class="{ on: pick?.member === m }" :aria-pressed="pick?.member === m"
                :disabled="!betting || !online || !left" :title="nameOf(m)" @click="chooseRunner(m)"
              >
                <TuanziToken class="face" :member="m" :size="72" :grey="race?.phase === 'void'" />
                <span class="tag">
                  <span class="name">{{ nameOf(m) }}</span>
                  <span :key="`win${tickOf('win', m)?.n ?? 0}`" class="odds" :class="tickOf('win', m)?.dir">
                    <b>{{ x(oddsOf("win", m)) }}</b>
                    <svg v-if="tickOf('win', m)" class="arrow" viewBox="0 0 12 12" aria-hidden="true">
                      <path v-if="tickOf('win', m)!.dir === 'up'" d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" />
                      <path v-else d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" />
                    </svg>
                  </span>
                </span>
                <span v-if="mineOn(m)" class="mine"><img :src="COIN_SMALL" alt="" draggable="false" /><b>{{ mineOn(m) }}</b></span>
              </button>
            </div>
          </div>

          <!--
            Under way: the field in its order of play, each tuanzi under its own die in its colour; in the opening the
            dice for the order, then each round's five thrown together. The one whose turn it is stands up, its die
            raised; a die whose move is done fades. The last round's cue in the corner.
          -->
          <div v-else-if="infield === 'run'" key="run" class="pane run-pane">
            <TransitionGroup v-if="seats.length" tag="ol" name="seat" class="lineup" :class="{ opening: !!opening }" aria-label="出场顺序">
              <li
                v-for="m in seats" :key="m" class="seat"
                :class="{ turn: turn?.m === m, waiting: turn?.m === m && turn.stage !== 'walk' }" :title="nameOf(m)"
              >
                <span class="slot">
                  <RaceDie
                    v-if="seatDice[m]" :key="seatDice[m]!.key" class="seat-die" :class="{ out: seatDice[m]!.out }"
                    :face="seatDice[m]!.face" :toss="seatDice[m]!.toss" :color="colorOf(m)"
                  />
                </span>
                <span class="head"><TuanziToken :member="m" :size="48" /></span>
              </li>
            </TransitionGroup>
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
              <p v-if="won > 0" class="net" role="status" :aria-label="`+${fmt(won)} 驼币`">
                <ParkCoin class="net-coin" fill :tilt="false" /><b>+{{ fmt(counted) }}</b>
              </p>
            </div>
          </div>
        </Transition>
      </div>
    </RaceTrack>

    <RaceRules v-if="rules" @close="rules = false" />

    <!--
      The bet slip. A runner picked: its three kinds (odds, and a thin bar of the coins on each), the stake and the bet
      key. Nothing picked: my tickets on this race; with none while bets are open, the last champion and what my bets
      on that race won.
    -->
    <div class="park-actions slip">
      <template v-if="betting && pick && race">
        <span class="picked"><TuanziToken :member="pick.member" :size="32" />{{ nameOf(pick.member) }}</span>
        <span class="kinds" role="group" :aria-label="`${nameOf(pick.member)}的押法`">
          <button
            v-for="k in KINDS" :key="k" type="button" class="ui-btn kind-key"
            :class="{ on: pick.kind === k, repriced: confirming && pick.kind === k }" :aria-pressed="pick.kind === k"
            @click="chooseKind(k)"
          >
            <small>{{ KIND_NAMES[k] }}</small>
            <s v-if="confirming && pick.kind === k">{{ x(repriced!.was) }}</s>
            <span :key="`${k}${tickOf(k, pick.member)?.n ?? 0}`" class="odds" :class="tickOf(k, pick.member)?.dir">
              <b>{{ x(oddsOf(k, pick.member)) }}</b>
              <svg v-if="tickOf(k, pick.member)" class="arrow" viewBox="0 0 12 12" aria-hidden="true">
                <path v-if="tickOf(k, pick.member)!.dir === 'up'" d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" />
                <path v-else d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" />
              </svg>
            </span>
            <i class="pool" :title="`${coinsOn(k, pick.member)} 枚`"><i :style="{ width: `${share(k, pick.member) * 100}%` }"></i></i>
          </button>
        </span>
      </template>
      <span v-else-if="tickets.length" class="tickets" aria-label="我的押注">
        <span
          v-for="t in tickets" :key="t.key" class="ticket" :class="{ won: t.won }"
          :title="ticketTitle(t)"
        >
          <TuanziToken :member="t.member" :size="24" />
          <small>{{ KIND_NAMES[t.kind] }}</small><b>{{ oddsList(t.odds) }}</b>
          <span class="coin"><img :src="COIN_SMALL" alt="" draggable="false" />{{ t.coins }}</span>
        </span>
      </span>
      <span v-else-if="betting && lastChampion" class="last">
        <span class="champ" :title="nameOf(lastChampion)">
          <TuanziToken :member="lastChampion" :size="32" /><Icon class="champ-crown" name="crown" :size="14" />
        </span>
        <span v-if="won > 0" class="last-net" :aria-label="`+${fmt(won)} 驼币`"><ParkCoin :size="22" :tilt="false" />+{{ fmt(won) }}</span>
      </span>

      <div v-if="betting && (pick || !left)" class="park-actions-main">
        <span v-if="!left" class="full">本场已押满</span>
        <template v-else>
          <span class="stepper">
            <button type="button" class="ui-btn small ghost" :disabled="stake <= 1" aria-label="少押一枚" @click="stake--">
              <Icon name="minus" :size="14" />
            </button>
            <b>{{ stake }}</b>
            <button type="button" class="ui-btn small ghost" :disabled="stake >= left" aria-label="多押一枚" @click="stake++">
              <Icon name="plus" :size="14" />
            </button>
          </span>
          <button
            type="button" class="ui-btn primary bet-key" :class="{ pulse: !betBlock && !busy }"
            :disabled="busy || !!betBlock" :aria-busy="busy" :title="betBlock || undefined" @click="place"
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

/*
 * ---- bets open: five runner keys standing in a row on the paper, each a tuanzi over its name and its odds to win.
 * The pane is a size container: the keys follow the paper's width and height.
 */
.field-pane {
  container: infield / size;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
}
.void {
  margin: 0;
  text-align: center;
  font: 800 var(--fs-strong)/1.3 var(--font);
  color: var(--ink-2);
}
.runners {
  /* The tuanzi on a key: as large as the paper's height and a fifth of its width allow. */
  --face: clamp(26px, min(20cqw - 16px, 100cqh - 56px), 88px);
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: clamp(5px, 2cqw, 14px);
  width: min(100%, calc(5 * (var(--face) + 24px)));
}
/* A void race: its line over the runners, which give it the room. */
.field-pane.off .runners {
  --face: clamp(24px, min(20cqw - 16px, 100cqh - 80px), 88px);
}
.runner {
  flex-direction: column;
  gap: 0;
  min-width: 0;
  height: auto;
  padding: clamp(4px, 3cqh, 10px) 4px clamp(4px, 3cqh, 8px);
}
.runner .face {
  --tuanzi-size: var(--face);
  margin-bottom: 2px;
}
/* Under the tuanzi its name and odds to win: one line on a wide sheet, the name over the odds on a narrow one. */
.tag {
  display: flex;
  flex-direction: column;
  align-items: center;
}
@container infield (min-width: 400px) {
  .tag {
    flex-direction: row;
    align-items: baseline;
    gap: 4px;
  }
}
.runner .name {
  font: 700 var(--fs-label)/1.25 var(--font);
  color: var(--ink-2);
  white-space: nowrap;
}
.odds {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.odds b {
  font: 800 var(--fs-section)/1.05 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
/* Odds that just moved: an arrow beside them a moment, coral and up or grey and down, the number sliding in. */
.odds .arrow {
  width: 11px;
  height: 11px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.4;
  stroke-linecap: round;
  stroke-linejoin: round;
  animation: tick-arrow 1.6s var(--ease-out) both;
}
.odds.up {
  color: var(--c-700);
}
.odds.up b {
  color: var(--c-700);
  animation: tick-num 500ms var(--ease-pop) both;
}
.odds.down {
  color: var(--ink-3);
}
.odds.down b {
  animation: tick-num-down 500ms var(--ease-pop) both;
}
@keyframes tick-arrow {
  0%, 75% { opacity: 1; }
  100% { opacity: 0; }
}
@keyframes tick-num {
  from { transform: translateY(6px); opacity: 0.2; }
}
@keyframes tick-num-down {
  from { transform: translateY(-6px); opacity: 0.2; }
}
/* The runner picked: latched in coral. */
.runner.on:not(:disabled) {
  --key-top: var(--c-200);
  --key-bottom: var(--c-200);
  --key-lip: var(--c-500);
}
.runner.on .name {
  color: var(--ink);
}
.runner:disabled .face {
  opacity: 0.85;
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
@container infield (max-height: 84px) {
  .runner .name {
    display: none;
  }
}
@container infield (max-width: 360px) {
  .odds b {
    font-size: var(--fs-strong);
  }
  .runner .name {
    font-size: var(--fs-caption);
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

/*
 * ---- under way: the lineup, a row of seats in the order of play, first to move on the left: each a die in the
 * member's colour over its tuanzi. The pane is a size container: the seats follow its width and height.
 */
.run-pane {
  container: infield / size;
  position: relative;
  align-items: center;
  justify-content: center;
}
.lineup {
  /* A seat's width; its die and its tuanzi, as large as the pane's height leaves room for both. */
  --seat: clamp(30px, min(17cqw, 52cqh), 96px);
  --die-size: calc(var(--seat) * 0.62);
  --face: calc(var(--seat) * 0.66);
  display: flex;
  align-items: flex-end;
  gap: clamp(4px, 2.4cqw, 18px);
  margin: 0;
  padding: 0;
  list-style: none;
}
.seat {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: calc(var(--seat) * 0.12);
  width: var(--seat);
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
  height: calc(var(--seat) * 0.82);
  border-radius: 999px;
  background: var(--c-100);
  --tuanzi-size: var(--face);
  transition: translate 280ms var(--ease-pop), background 280ms var(--ease-out), box-shadow 280ms var(--ease-out);
}
.seat.turn .head {
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
  0% { opacity: 0; transform: scale(1.6); }
  14% { opacity: 1; transform: scale(0.94); }
  22% { transform: scale(1); }
  85% { opacity: 1; transform: scale(1); }
  100% { opacity: 0; transform: scale(1); }
}

/* ---- finished: the podium, then what my bets won; sized by the infield (a size container) */
.podium-pane {
  container: infield / size;
  align-items: center;
  justify-content: center;
}
.result {
  /* One unit of the podium: the infield's width or height, whichever is tighter. */
  --u: min(1.1cqw, 4cqh);
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
  width: clamp(34px, calc(var(--u) * 13), 84px);
  --tuanzi-size: clamp(24px, calc(var(--u) * 8), 48px);
}
/* Second on the left, the winner in the middle, third on the right; the last two stand on the floor beside. */
.place.p1 { order: 2; --tuanzi-size: clamp(34px, calc(var(--u) * 12), 72px); }
.place.p2 { order: 1; }
.place.p3 { order: 3; }
.place.p4,
.place.p5 {
  width: clamp(22px, calc(var(--u) * 7.5), 48px);
  --tuanzi-size: clamp(20px, calc(var(--u) * 5.5), 32px);
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
/* The coin as tall as the number. */
.net-coin {
  --size: clamp(22px, calc(var(--u) * 6.4), 44px);
}
.net b {
  font: 800 clamp(20px, calc(var(--u) * 7), 48px)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  animation: win-pop 600ms var(--ease-pop) both;
}
/* A narrow sheet: the podium and the win close up. */
@container infield (max-width: 320px) {
  .result {
    gap: 8px;
  }
  .podium {
    gap: 4px;
  }
  .net {
    gap: 3px;
  }
  .net-coin {
    --size: 20px;
  }
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
.kinds {
  display: flex;
  gap: 8px;
}
.kind-key {
  gap: 5px;
  padding: 0 12px;
  overflow: hidden;
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
.kind-key .odds b {
  font-size: var(--fs-number);
}
/* The odds dropped on the way: the old ones struck out, the new ones flare once. */
.kind-key s {
  font: 700 var(--fs-label)/1 var(--font-latin);
  color: var(--ink-3);
}
.kind-key.repriced .odds b {
  color: var(--c-700);
  animation: tick-num-down 500ms var(--ease-pop) both;
}
/* The coins on the kind: a thin bar along the key's foot, as long as their weight in the odds. */
.pool {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 4px;
  height: 3px;
  border-radius: 2px;
  background: rgba(var(--c-900-rgb), 0.08);
  overflow: hidden;
}
.pool > i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--c-600);
  transition: width var(--dur-stage) var(--ease-out);
}
/* The last race while bets are open: its champion crowned, and what my bets on it won. */
.last {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
.champ {
  position: relative;
  line-height: 0;
}
.champ-crown {
  position: absolute;
  left: 50%;
  top: -5px;
  translate: -50% 0;
  color: var(--c-600);
  filter: drop-shadow(0 1px 0 #fff) drop-shadow(0 -1px 0 #fff) drop-shadow(1px 0 0 #fff) drop-shadow(-1px 0 0 #fff);
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
  height: 30px;
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
/* A refused bet floats over the board's lower edge above the bet key, so the bar keeps its height and the board its
   size. */
.slip .ui-error {
  position: absolute;
  right: 22px;
  bottom: calc(100% + 8px);
  max-width: calc(100% - 44px);
  margin: 0;
  box-shadow: var(--shadow-paper);
}
/* The tickets scroll sideways rather than push the bet key onto a second line. */
.slip > .tickets {
  flex: 1 1 0;
  min-width: 0;
}

.calm .pool > i {
  transition: none;
}
.calm .odds .arrow,
.calm .odds b,
.calm .kind-key.repriced .odds b,
.calm .net b,
.calm .seat.waiting .head {
  animation: none;
}
.calm .seat-move,
.calm .seat .head,
.calm .seat-die {
  transition: none;
}
/* Without motion the cue stands still for its time. */
.calm .cue {
  animation: none;
}

@container panel (max-height: 560px) {
  .lap {
    min-height: 250px;
  }
}
/* Narrow panels: the kind keys stack their name over the odds, and the slip stays on one line. */
@container panel (max-width: 840px) {
  .kind-key {
    flex-direction: column;
    gap: 1px;
    min-width: 50px;
    padding: 0 8px 3px;
  }
  .kind-key small {
    font-size: var(--fs-caption);
  }
  .kind-key .odds b {
    font-size: var(--fs-strong);
  }
  .kind-key s {
    display: none;
  }
  .pool {
    bottom: 3px;
    height: 2px;
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
  .ticket small {
    display: none;
  }
}
</style>
