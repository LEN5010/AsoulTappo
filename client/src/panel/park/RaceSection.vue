<script setup lang="ts">
// 团子赛跑 (docs/design/amusement-park.md §6, protocol/PROTOCOL.md 团子赛跑). There is no push channel: while the
// page is open the section asks GET /api/park/race every few seconds, keeps the offset to the server's clock, and
// plays the race's move list from startsAt, so every client shows the same moment. Bets are taken while the race's
// phase is betting; a race's result is its net over every selection. The countdown, the rules key and the host
// (the latest champion) go up in the park's coral band (band.ts).
// The page is the lap (RaceTrack) with an infield that follows the phase: the five runner keys while bets are open
// (or the race is void), their heads and the commentary while it runs, the podium once it has finished. The bet
// slip is the bottom bar.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import { manifest } from "../../manifest";
import { online } from "../../stores/player";
import { loadPark, parkTry } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import { ACHAO } from "../../ui/achao";
import Icon from "../../ui/Icon.vue";
import { useBand } from "./band";
import ParkSheet from "./ParkSheet.vue";
import RaceTrack from "./RaceTrack.vue";
import TuanziToken from "./TuanziToken.vue";
import { COIN_SMALL } from "./coin";
import {
  hits, KIND_NAMES, MOOD_NAMES, moodLine, playhead, SKILL_NAMES, skillLine, tuanziArt,
  type Race, type RaceAnswer, type RaceKind,
} from "./race";

// The bundled manifest always has the race; the server checks every number again.
const CFG = manifest.economy.park!.race!;
const MEMBERS = Object.keys(CFG.skills);
const KINDS = CFG.kinds;
const fmt = (n: number) => Math.abs(n).toLocaleString("en-US");
const character = (m: string) => manifest.characters.find((c) => c.id === m);
const nameOf = (m: string) => character(m)?.name ?? m;
const colorOf = (m: string) => character(m)?.color ?? "var(--c-500)";

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

/** When to ask next: soon around the start and the end, slowly otherwise. */
function nextDelay(): number {
  const r = race.value;
  const t = serverNow.value;
  const until = (at: number) => at * 1000 - t + 300;
  if (!r || r.phase === "done" || r.phase === "void") return Math.max(1000, Math.min(5000, until(data.value?.nextAt ?? 0)));
  if (r.phase === "betting") return Math.max(1000, Math.min(4000, until(r.startsAt)));
  if (r.phase === "running" && r.endsAt && t < r.endsAt * 1000) return Math.max(1000, until(r.endsAt));
  return 1000;
}

async function poll() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
  if (!active || loading) return;
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

function start() {
  if (active) return;
  active = true;
  void poll();
  clockTimer = setInterval(() => (now.value = Date.now()), 100);
}
function stop() {
  active = false;
  if (pollTimer) clearTimeout(pollTimer);
  if (clockTimer) clearInterval(clockTimer);
  pollTimer = null;
  clockTimer = null;
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
/** The rules table (skills and moods) is open. */
const rules = ref(false);
useBand("race", () => ({
  ...(champion.value && tuanziArt(champion.value)
    ? { host: tuanziArt(champion.value), hostKind: "token" as const }
    : { host: ACHAO["观察"] }),
  timer: { label: countdown.value.label, time: countdown.value.time || undefined },
  info: { label: "规则", open: () => (rules.value = true) },
}));

// ---------------------------------------------------------------- what is happening on the track
const ADD_NAMES: Record<string, string> = { snack: "加餐", dash: "冲刺", catchup: "追赶" };
const ticker = computed(() => {
  const r = race.value;
  if (!r?.moves || !playing.value) return "";
  const head = playhead(r, serverNow.value);
  if (head.current < 0) return head.done ? "" : "各就各位";
  const s = r.moves[head.current];
  const parts = [nameOf(s.m)];
  if (s.dice.length) parts.push(`掷出 ${s.dice.join(" → ")}`);
  for (const [tag, n] of s.add ?? []) {
    if (tag === "mood") {
      if (n) parts.push(`${MOOD_NAMES[r.setup.moods[s.m]] ?? ""} ${n > 0 ? "+" : "−"}${Math.abs(n)}`);
    } else parts.push(`${ADD_NAMES[tag] ?? tag} +${n}`);
  }
  if (s.carry?.length) parts.push(`带上${s.carry.map(nameOf).join("、")}`);
  if (s.square) parts.push(s.square === "boost" ? "加速" : "绊脚");
  if (s.snack) parts.push("吃到零食");
  return parts.join(" · ");
});

// ---------------------------------------------------------------- bets
const betting = computed(() => phase.value === "betting" && serverNow.value < (race.value?.startsAt ?? 0) * 1000);
const staked = computed(() => race.value?.mine.reduce((n, b) => n + b.coins, 0) ?? 0);
const left = computed(() => Math.max(0, CFG.maxCoins - staked.value));
const pick = ref<{ kind: RaceKind; member: string } | null>(null);
const stake = ref(1);
const busy = ref(false);
const betError = ref("");

watch(() => race.value?.id, () => {
  pick.value = null;
  betError.value = "";
});
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
  busy.value = true;
  betError.value = "";
  const reply = await parkTry<{ race: Race }>("POST", "/api/park/race/bet", {
    race: r.id, kind: p.kind, member: p.member, coins: stake.value,
  });
  busy.value = false;
  if (reply.ok) {
    if (data.value) data.value = { ...data.value, race: reply.data.race };
    pick.value = null;
  } else betError.value = reply.error.message;
}

const poolTotal = computed(() => Object.values(race.value?.pool ?? {}).reduce((n, p) => n + p.coins, 0));
/** This runner's share of the coins bet on the race, 0 to 1. */
const share = (m: string) => (poolTotal.value ? (race.value?.pool[m]?.coins ?? 0) / poolTotal.value : 0);
const poolTitle = (m: string) => `${race.value?.pool[m]?.coins ?? 0} 枚 · ${race.value?.pool[m]?.bettors ?? 0} 人`;
/** My bets on [m] in the race on the track: the coins in all, and each bet for the badge's tooltip. */
function mineOn(m: string): { coins: number; title: string } {
  const bets = race.value?.mine.filter((b) => b.member === m) ?? [];
  return {
    coins: bets.reduce((n, b) => n + b.coins, 0),
    title: bets.map((b) => `${KIND_NAMES[b.kind]} ×${b.odds.toFixed(1)} · ${b.coins} 枚`).join("\n"),
  };
}
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
const odds = (r: Race, kind: RaceKind, m: string) => r.odds[kind]?.[m];
const signed = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${fmt(n)}`;

/** What the infield holds: the runner keys, the race under way, or the podium. */
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
</script>

<template>
  <section class="race" :class="{ calm: reducedMotion }" aria-label="团子赛跑">
    <p v-if="loadError" class="ui-error load-error" role="alert">{{ loadError }}</p>

    <RaceTrack class="lap" :class="`in-${infield}`" :race="race" :t="serverNow" :track="CFG.track" :members="MEMBERS">
      <!-- Bets open, a void race, or nothing loaded yet: the five runner keys. -->
      <template v-if="infield === 'field'">
        <p v-if="race?.phase === 'void'" class="void" role="status">本场取消，驼币已退回</p>
        <div class="runners" role="group" aria-label="团子">
          <button
            v-for="m in MEMBERS" :key="m" type="button" class="ui-btn runner-key"
            :class="{ on: pick?.member === m }" :aria-pressed="pick?.member === m"
            :disabled="!betting || !online || !left" :title="race ? poolTitle(m) : undefined" @click="chooseRunner(m)"
          >
            <TuanziToken class="face" :member="m" :size="72" :grey="race?.phase === 'void'" />
            <span class="name"><i class="bar" :style="{ background: colorOf(m) }"></i>{{ nameOf(m) }}</span>
            <span class="tags">
              <b
                v-if="race" class="mood" :class="race.setup.moods[m]" role="img"
                :title="MOOD_NAMES[race.setup.moods[m]]" :aria-label="MOOD_NAMES[race.setup.moods[m]]"
              ><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" /></svg></b>
              <small class="skill">{{ SKILL_NAMES[CFG.skills[m].kind] }}</small>
            </span>
            <span v-if="race" class="pool" aria-hidden="true"><i :style="{ width: `${share(m) * 100}%` }"></i></span>
            <span v-if="mineOn(m).coins" class="mine" :title="mineOn(m).title">
              <img :src="COIN_SMALL" alt="" draggable="false" /><b>{{ mineOn(m).coins }}</b>
            </span>
          </button>
        </div>
      </template>

      <!-- Under way: the field as small heads, and what just happened. -->
      <template v-else-if="infield === 'run'">
        <ul class="heads" aria-label="团子">
          <li v-for="m in MEMBERS" :key="m" :title="nameOf(m)">
            <TuanziToken :member="m" :size="32" />
            <span v-if="mineOn(m).coins" class="mine" :title="mineOn(m).title">
              <img :src="COIN_SMALL" alt="" draggable="false" /><b>{{ mineOn(m).coins }}</b>
            </span>
          </li>
        </ul>
        <p class="ticker" aria-hidden="true">{{ ticker }}</p>
      </template>

      <!-- Finished: the podium, the last two on the floor beside it, and my net. -->
      <div v-else class="result">
        <ol class="podium" aria-label="本场名次">
          <li
            v-for="(m, i) in ranking" :key="m" class="place" :class="[`p${i + 1}`, { lit: lit(i) }]"
            :title="nameOf(m)" :style="{ '--i': i }"
          >
            <TuanziToken :member="m" :size="i === 0 ? 72 : i < 3 ? 48 : 32" />
            <span class="step">{{ i + 1 }}</span>
          </li>
        </ol>
        <p v-if="result" class="net" :class="{ up: result.net > 0 }" role="status">
          <Icon name="shard" :size="24" /><b>{{ signed(result.net) }}</b>
        </p>
      </div>
    </RaceTrack>

    <!-- The rules: each tuanzi with its skill, each mood with its chip as on the runner keys. -->
    <ParkSheet v-if="rules" title="赛跑规则" @close="rules = false">
      <div class="rules park-sheet-columns">
        <section>
          <h4 class="park-sheet-head">技能</h4>
          <ul class="park-sheet-list single">
            <li v-for="m in MEMBERS" :key="m" class="park-sheet-row">
              <span class="park-sheet-lead bare"><TuanziToken :member="m" :size="48" /></span>
              <span class="park-sheet-main">
                <b><i class="park-sheet-bar" :style="{ background: colorOf(m) }"></i>{{ nameOf(m) }}<em>{{ SKILL_NAMES[CFG.skills[m].kind] }}</em></b>
                <small>{{ skillLine(CFG.skills[m]) }}</small>
              </span>
            </li>
          </ul>
        </section>
        <section>
          <h4 class="park-sheet-head">状态</h4>
          <ul class="park-sheet-list single">
            <li v-for="md in CFG.moods" :key="md.id" class="park-sheet-row">
              <span class="park-sheet-lead bare">
                <b class="mood" :class="md.id" aria-hidden="true"><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" /></svg></b>
              </span>
              <span class="park-sheet-main">
                <b>{{ MOOD_NAMES[md.id] }}</b>
                <small v-if="moodLine(md)">{{ moodLine(md) }}</small>
              </span>
            </li>
          </ul>
        </section>
      </div>
    </ParkSheet>

    <!-- The bet slip. -->
    <div class="park-actions slip">
      <template v-if="betting && pick && race">
        <span class="picked"><i class="bar" :style="{ background: colorOf(pick.member) }"></i>{{ nameOf(pick.member) }}</span>
        <span class="kinds" role="group" :aria-label="`${nameOf(pick.member)}的押法`">
          <button
            v-for="k in KINDS" :key="k" type="button" class="ui-btn kind-key"
            :class="{ on: pick.kind === k }" :aria-pressed="pick.kind === k" @click="chooseKind(k)"
          >
            <small>{{ KIND_NAMES[k] }}</small><b>×{{ odds(race, k, pick.member)?.toFixed(1) }}</b>
          </button>
        </span>
      </template>
      <template v-else>
        <span v-if="data?.winners.length" class="champs" aria-label="最近冠军">
          <span v-for="w in data.winners" :key="w.id" :title="nameOf(w.member)"><TuanziToken :member="w.member" :size="24" /></span>
        </span>
        <span v-if="betting && result" class="last-net" :class="{ up: result.net > 0 }">
          <Icon name="shard" :size="14" />{{ signed(result.net) }}
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
            <img class="coin" :src="COIN_SMALL" alt="" draggable="false" />押 {{ stake }} 枚
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

/* ---- the runner keys */
.lap :deep(.infield) {
  justify-content: center;
  gap: 12px;
}
.void {
  margin: 0;
  text-align: center;
  font: 800 var(--fs-number)/1.4 var(--font);
  color: var(--ink-2);
}
.runners {
  --tuanzi-size: 72px;
  display: flex;
  gap: 10px;
  width: 100%;
}
.runner-key {
  flex: 1 1 0;
  min-width: 0;
  height: auto;
  flex-direction: column;
  gap: 4px;
  padding: 10px 6px 16px;
}
.runner-key .face {
  margin-bottom: 2px;
}
.name {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font: 800 var(--fs-strong)/1.2 var(--font);
  color: var(--ink);
}
.bar {
  flex: none;
  width: 4px;
  height: 14px;
  border-radius: 2px;
}
.tags {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-width: 0;
}
.skill {
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
/*
 * Today's mood as an arrow, from straight up (hot) through level (normal) to straight down (slacking); the tag goes
 * from solid coral down to grey. The name is in the tooltip and the rules table.
 */
.mood {
  display: inline-grid;
  place-items: center;
  width: 26px;
  height: 18px;
  border-radius: 999px;
  color: var(--ink);
  background: var(--c-100);
}
.mood svg {
  width: 12px;
  height: 12px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.mood.excited svg {
  rotate: 45deg;
}
.mood.normal svg {
  rotate: 90deg;
}
.mood.sleepy svg {
  rotate: 135deg;
}
.mood.slacking svg {
  rotate: 180deg;
}
.mood.hot {
  background: var(--c-500);
}
.mood.excited {
  background: var(--c-300);
}
.mood.sleepy,
.mood.slacking {
  /* Grey: the ink's rose-grey thinned on paper. */
  background: color-mix(in oklab, var(--ink-3) 18%, var(--surface));
  color: var(--ink-2);
}
.runner-key.on .mood.normal,
.runner-key:disabled .mood.normal {
  background: var(--c-200);
}
.runner-key:disabled .mood {
  opacity: 0.7;
}
/* This runner's share of the coins bet, along the key's bottom. */
.pool {
  position: absolute;
  left: 10px;
  right: 10px;
  bottom: 7px;
  height: 4px;
  border-radius: 2px;
  background: var(--c-100);
  overflow: hidden;
}
.runner-key.on .pool,
.runner-key:disabled .pool {
  background: var(--c-200);
}
.pool i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--c-500);
  transition: width var(--dur-stage) var(--ease-out);
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

/* ---- under way: small heads and the commentary */
.lap.in-run :deep(.infield) {
  justify-content: flex-start;
  gap: 14px;
  padding-top: 6px;
}
.heads {
  display: flex;
  justify-content: center;
  gap: 18px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.heads li {
  position: relative;
  line-height: 0;
}
.heads .mine {
  top: -6px;
  right: -14px;
  padding-right: 5px;
}
.heads .mine img {
  width: 14px;
  height: 14px;
}
.heads .mine b {
  font-size: var(--fs-strong);
}
.ticker {
  min-height: 28px;
  margin: 0;
  font: 800 var(--fs-heading)/1.4 var(--font);
  color: var(--ink);
  text-align: center;
}

/* ---- finished: the podium, then my net */
.lap.in-podium :deep(.infield) {
  justify-content: flex-start;
  padding-top: 8px;
  /* Clear of the stack on the finish square, at the infield's bottom left. */
  padding-left: calc(var(--cell) * 1.1);
}
.result {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 36px;
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
  width: 84px;
}
/* Second on the left, the winner in the middle, third on the right; the last two stand on the floor beside. */
.place.p1 { order: 2; }
.place.p2 { order: 1; }
.place.p3 { order: 3; }
.place.p4 { order: 4; width: 48px; margin-left: 10px; }
.place.p5 { order: 5; width: 48px; }
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
.p1 .step { height: 52px; }
.p2 .step { height: 36px; }
.p3 .step { height: 26px; }
.p4 .step,
.p5 .step {
  height: 18px;
  font-size: var(--fs-number);
}
/* A place one of my winning bets is on. */
.place.lit .step {
  background: var(--c-500);
  color: var(--ink);
}
.place .tuanzi-token {
  animation: land var(--dur-slow) var(--ease-pop) both;
  animation-delay: calc((4 - var(--i)) * 90ms);
}
@keyframes land {
  from { translate: 0 -24px; opacity: 0; }
}
.net {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 4px;
  color: var(--ink-2);
}
.net b {
  font: 800 48px/1 var(--font-latin);
}
.net.up {
  color: var(--c-700);
}
.net.up b {
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
  color: var(--ink-2);
}
.last-net.up {
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

/* ---- the rules (park-sheet.css): the tuanzi fills its lead, the mood chip a size up from the runner keys' */
.rules .park-sheet-lead {
  --tuanzi-size: calc(var(--lead) - 6px);
}
.rules .mood {
  width: 36px;
  height: 24px;
}
.rules .mood svg {
  width: 15px;
  height: 15px;
}
/* The rows are --c-100: the level chip goes a step deeper, as on a latched runner key. */
.rules .mood.normal {
  background: var(--c-200);
}

.calm .pool i {
  transition: none;
}
.calm .place .tuanzi-token,
.calm .net.up b {
  animation: none;
}

@container panel (max-width: 760px) {
  .runners {
    --tuanzi-size: 56px;
    gap: 8px;
  }
  .runner-key .skill {
    display: none;
  }
  .result {
    gap: 18px;
  }
  .place {
    width: 60px;
  }
  .place.p1 {
    --tuanzi-size: 56px;
  }
  .place.p4,
  .place.p5 {
    width: 36px;
  }
  .net b {
    font-size: 36px;
  }
}
/* Short panels: one row of head keys, a smaller podium. */
@container panel (max-height: 560px) {
  .lap {
    min-height: 250px;
  }
  .runners {
    --tuanzi-size: 40px;
    gap: 6px;
  }
  .runner-key {
    gap: 3px;
    padding: 6px 4px 12px;
  }
  .runner-key .name,
  .runner-key .skill {
    display: none;
  }
  .runner-key .face {
    margin: 0;
  }
  .pool {
    bottom: 5px;
    height: 3px;
  }
  .ticker {
    font-size: var(--fs-number);
  }
  .net b {
    font-size: 36px;
  }
  .p1 .step { height: 36px; }
  .p2 .step { height: 26px; }
  .p3 .step { height: 18px; }
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
  .result {
    gap: 12px;
  }
  .podium {
    gap: 4px;
  }
  .place {
    width: 46px;
    --tuanzi-size: 36px;
  }
  .place.p1 {
    --tuanzi-size: 48px;
  }
  .place.p4,
  .place.p5 {
    width: 30px;
    --tuanzi-size: 24px;
  }
  .place.p4 {
    margin-left: 4px;
  }
  .step {
    font-size: var(--fs-number);
  }
  .net {
    gap: 3px;
  }
  .net svg {
    width: 18px;
    height: 18px;
  }
  .net b {
    font-size: 28px;
  }
}
</style>
