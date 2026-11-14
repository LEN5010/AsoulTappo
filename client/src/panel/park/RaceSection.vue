<script setup lang="ts">
// 团子赛跑 (docs/design/amusement-park.md §6, protocol/PROTOCOL.md 团子赛跑). There is no push channel: while the
// page is shown the section asks GET /api/park/race (every 10 s while bets are open, soon around the start and the
// end), keeps the offset to the server's clock, and plays the race's move list from startsAt, so every client shows
// the same moment. The odds move with the coins staked until the start; a bet sends the odds the player saw and
// locks them, and when they have dropped meanwhile the slip shows the new ones to confirm. The countdown, the rules
// key and the host (the latest champion) go up in the park's coral band (band.ts).
// The page is the lap (RaceTrack) with an infield that follows the phase: the odds board (five runner keys, each
// with its odds and stakes for every kind) while bets are open or the race is void; the live standings while it
// runs; the podium once it has finished. The bet slip is the bottom bar, with my tickets when nothing is picked.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import { manifest } from "../../manifest";
import { online } from "../../stores/player";
import { loadPark, parkTry } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import { ACHAO } from "../../ui/achao";
import Icon from "../../ui/Icon.vue";
import { useBand } from "./band";
import RaceRules from "./RaceRules.vue";
import RaceTrack from "./RaceTrack.vue";
import TuanziToken from "./TuanziToken.vue";
import { COIN_SMALL } from "./coin";
import {
  HOP_AT, hits, KIND_NAMES, leaders, playhead, rankOf, stacksAt, stepStart, tuanziArt,
  type Race, type RaceAnswer, type RaceKind,
} from "./race";

// The bundled manifest always has the race; the server checks every number again.
const CFG = manifest.economy.park!.race!;
/** The members in manifest order: the lanes before a race's own are drawn. */
const MEMBERS = manifest.characters.map((c) => c.id);
const KINDS = CFG.kinds;
/** How often the odds are asked for while bets are open, ms. */
const BETTING_POLL = 10_000;
/** How long the last round's cue stays up, ms. */
const CUE_MS = 2600;
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
  return 1000;
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
/** The field first to last as it stands on the track now. */
const standing = computed<string[]>(() => {
  const r = race.value;
  if (!r?.start || !r.moves || !head.value) return r?.start ?? MEMBERS;
  return rankOf(stacksAt(r.start, r.moves, head.value));
});
const leadAfter = computed(() => {
  const r = race.value;
  return r?.start && r.moves?.length ? leaders(r.start, r.moves) : [];
});
/** The step that just changed the leader, while it plays: the first slot flashes once for it. */
const leadFlash = computed(() => {
  const h = head.value;
  const r = race.value;
  if (!h || !r?.start || h.current < 0 || h.part < HOP_AT) return "";
  const before = h.current ? leadAfter.value[h.current - 1] : r.start[0];
  return standing.value[0] !== before ? `${r.id}-${h.current}` : "";
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
const signed = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${fmt(n)}`;

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
</script>

<template>
  <section class="race" :class="{ calm: reducedMotion }" aria-label="团子赛跑">
    <p v-if="loadError" class="ui-error load-error" role="alert">{{ loadError }}</p>

    <RaceTrack class="lap" :class="`in-${infield}`" :race="race" :t="serverNow" :track="CFG.track" :members="MEMBERS"
      :cleared="infield === 'podium'"
    >
      <!-- Bets open, a void race, or nothing loaded yet: the odds board. -->
      <template v-if="infield === 'field'">
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
      </template>

      <!-- Under way: the standings, swapping as they overtake; the last round's cue. -->
      <template v-else-if="infield === 'run'">
        <div class="standings" aria-label="名次">
          <ol class="plates" aria-hidden="true">
            <li v-for="n in MEMBERS.length" :key="n" :class="{ first: n === 1 }">
              <span v-if="n === 1 && leadFlash" :key="leadFlash" class="flash"></span>
              <b>{{ n }}</b>
            </li>
          </ol>
          <TransitionGroup tag="ol" name="rank" class="field">
            <li v-for="m in standing" :key="m" :title="nameOf(m)">
              <TuanziToken :member="m" :size="48" />
              <span v-if="mineOn(m)" class="mine"><img :src="COIN_SMALL" alt="" draggable="false" /><b>{{ mineOn(m) }}</b></span>
            </li>
          </TransitionGroup>
        </div>
        <p v-if="lastRound" class="cue" role="status">最后一轮</p>
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

/* ---- the odds board: a legend column, then five runner keys whose rows line up with it */
.lap.in-field :deep(.infield) {
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

/* ---- under way: five places, the tuanzi sliding between them as they overtake */
.lap.in-run :deep(.infield) {
  justify-content: flex-start;
  align-items: center;
  gap: 10px;
  padding-top: 4px;
}
.standings {
  --slot: 72px;
  --tuanzi-size: 52px;
  display: grid;
}
.standings > ol {
  grid-area: 1 / 1;
  display: grid;
  grid-template-columns: repeat(5, var(--slot));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.plates li {
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  height: calc(var(--tuanzi-size) + 22px);
  padding-bottom: 3px;
  box-sizing: border-box;
  border-radius: var(--radius-m);
  background: var(--c-100);
}
.plates li.first {
  background: var(--c-300);
}
.plates b {
  position: relative;
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink-3);
}
.plates .first b {
  color: var(--ink);
}
/* The lead just changed hands: the first place lights up once. */
.flash {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  animation: lead-flash 1.1s var(--ease-out) both;
}
@keyframes lead-flash {
  0% { box-shadow: 0 0 0 0 rgba(var(--c-500-rgb), 0.9); background: var(--c-500); }
  100% { box-shadow: 0 0 0 12px rgba(var(--c-500-rgb), 0); background: transparent; }
}
.field li {
  position: relative;
  display: flex;
  justify-content: center;
  padding-top: 2px;
  line-height: 0;
}
.field .mine {
  top: -6px;
  right: -2px;
  padding-right: 5px;
}
.field .mine img {
  width: 14px;
  height: 14px;
}
.field .mine b {
  font-size: var(--fs-strong);
}
.rank-move {
  transition: transform 640ms var(--ease-in-out);
}
/* The last round: a coral tag stamped onto the infield. */
.cue {
  margin: 0;
  padding: 6px 16px;
  border-radius: 999px;
  background: var(--c-500);
  box-shadow: var(--shadow-backlight);
  font: 800 var(--fs-section)/1.2 var(--font);
  color: var(--ink);
  animation: cue 2.6s var(--ease-out) both;
}
@keyframes cue {
  0% { opacity: 0; transform: scale(1.6) rotate(-6deg); }
  14% { opacity: 1; transform: scale(0.94) rotate(-2deg); }
  22% { transform: scale(1) rotate(-2deg); }
  85% { opacity: 1; transform: scale(1) rotate(-2deg); }
  100% { opacity: 0; transform: scale(1) rotate(-2deg); }
}

/* ---- finished: the podium, then my net */
.lap.in-podium :deep(.infield) {
  justify-content: center;
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
.calm .flash,
.calm .kind-key.repriced b,
.calm .place .tuanzi-token,
.calm .net.up b {
  animation: none;
}
.calm .rank-move {
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
  .standings {
    --slot: 52px;
    --tuanzi-size: 38px;
  }
  .standings > ol {
    gap: 6px;
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
/* Short panels: smaller faces, no names, smaller standings and podium; the cue beside the standings. */
@container panel (max-height: 560px) {
  .lap {
    min-height: 250px;
  }
  .lap.in-run :deep(.infield) {
    flex-direction: row;
    justify-content: center;
    align-items: flex-start;
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
  .standings {
    --slot: 44px;
    --tuanzi-size: 30px;
  }
  .standings > ol {
    gap: 5px;
  }
  .plates li {
    height: calc(var(--tuanzi-size) + 18px);
  }
  .plates b {
    font-size: var(--fs-strong);
  }
  .cue {
    padding: 3px 12px;
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
