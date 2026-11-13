<script setup lang="ts">
// 团子赛跑 (docs/design/amusement-park.md §6, protocol/PROTOCOL.md 团子赛跑). There is no push channel: while the
// page is open the section asks GET /api/park/race every few seconds, keeps the offset to the server's clock, and
// plays the race's move list from startsAt, so every client shows the same moment. Bets are taken while the race's
// phase is betting; a race's result is its net over every selection.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import { manifest } from "../../manifest";
import { online } from "../../stores/player";
import { loadPark, parkTry } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import RaceTrack from "./RaceTrack.vue";
import { COIN_SMALL } from "./coin";
import {
  hits, KIND_NAMES, MOOD_NAMES, moodLine, playhead, SKILL_NAMES, skillLine,
  type Race, type RaceAnswer, type RaceKind,
} from "./race";

// The bundled manifest always has the race; the server checks every number again.
const CFG = manifest.economy.park!.race!;
const MEMBERS = Object.keys(CFG.skills);
const KINDS = CFG.kinds;
const fmt = (n: number) => Math.abs(n).toLocaleString("en-US");
const ART = import.meta.glob<string>("../../assets/park/tuanzi/*.webp", { eager: true, query: "?url", import: "default" });
const art = (m: string) => Object.entries(ART).find(([path]) => path.endsWith(`/${m}.webp`))?.[1] ?? "";
const character = (m: string) => manifest.characters.find((c) => c.id === m);
const nameOf = (m: string) => character(m)?.name ?? m;
const colorOf = (m: string) => character(m)?.color ?? "var(--c-500)";
const moodOf = (id: string) => CFG.moods.find((m) => m.id === id);

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

function choose(kind: RaceKind, member: string) {
  if (!betting.value) return;
  const same = pick.value?.kind === kind && pick.value.member === member;
  pick.value = same ? null : { kind, member };
  stake.value = Math.max(1, Math.min(stake.value, left.value));
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

const poolMax = computed(() => Math.max(1, ...Object.values(race.value?.pool ?? {}).map((p) => p.coins)));

// ---------------------------------------------------------------- results
/** The race whose result is shown: this one once it has played, the one before while bets are open. */
const shown = computed<Race | null>(() => (finished.value ? race.value : betting.value ? last.value : null));
const result = computed(() => shown.value?.result ?? null);
// The park's balance and today's result follow a race the save had bets in.
watch(() => (race.value?.phase === "done" && race.value.mine.length ? race.value.id : null), (id) => {
  if (id) void loadPark();
});
const odds = (r: Race, kind: RaceKind, m: string) => r.odds[kind]?.[m];
</script>

<template>
  <section class="race" :class="{ calm: reducedMotion }" aria-label="团子赛跑">
    <header class="head">
      <div class="title">
        <span class="ui-eyebrow" aria-hidden="true">RACE</span>
        <h3>团子赛跑</h3>
      </div>
      <p class="count" role="timer">
        <span>{{ countdown.label }}</span>
        <b v-if="countdown.time">{{ countdown.time }}</b>
      </p>
    </header>

    <p v-if="loadError" class="ui-error" role="alert">{{ loadError }}</p>

    <RaceTrack :race="race" :t="serverNow" :track="CFG.track" :members="MEMBERS" />
    <p class="ticker" aria-hidden="true">{{ ticker }}</p>
    <p v-if="race?.phase === 'void'" class="void">本场取消，驼币已退回</p>

    <!-- The field: skill, today's mood, the three odds, and what has been bet. -->
    <ul class="field">
      <li v-for="m in MEMBERS" :key="m" class="runner" :class="{ won: finished && race?.ranking?.[0] === m }">
        <span class="who">
          <img v-if="art(m)" class="face" :src="art(m)" alt="" draggable="false" />
          <i class="tag" :style="{ background: colorOf(m) }"></i>
          <b>{{ nameOf(m) }}</b>
        </span>
        <span class="skill">
          <b>{{ SKILL_NAMES[CFG.skills[m].kind] }}</b>
          <small>{{ skillLine(CFG.skills[m]) }}</small>
        </span>
        <span v-if="race" class="mood" :class="race.setup.moods[m]">
          <b>{{ MOOD_NAMES[race.setup.moods[m]] }}</b>
          <small>{{ moodLine(moodOf(race.setup.moods[m])) }}</small>
        </span>
        <span v-if="race" class="odds" role="group" :aria-label="`${nameOf(m)}的赔率`">
          <button
            v-for="k in KINDS" :key="k" type="button" class="ui-btn small pick"
            :class="{ on: pick?.kind === k && pick.member === m, hit: finished && race.ranking && hits(k, m, race.ranking) }"
            :disabled="!betting || !online || !left" @click="choose(k, m)"
          >
            <small>{{ KIND_NAMES[k] }}</small>×{{ odds(race, k, m)?.toFixed(1) }}
          </button>
        </span>
        <span v-if="race" class="pool">
          <span class="bar"><i :style="{ width: `${((race.pool[m]?.coins ?? 0) / poolMax) * 100}%`, background: colorOf(m) }"></i></span>
          <small>{{ race.pool[m]?.coins ?? 0 }} 枚 · {{ race.pool[m]?.bettors ?? 0 }} 人</small>
        </span>
      </li>
    </ul>

    <div v-if="betting" class="stake">
      <template v-if="pick">
        <span class="picked">{{ nameOf(pick.member) }} {{ KIND_NAMES[pick.kind] }} ×{{ odds(race!, pick.kind, pick.member)?.toFixed(1) }}</span>
        <span class="stepper">
          <button type="button" class="ui-btn small ghost" :disabled="stake <= 1" aria-label="少押一枚" @click="stake--">
            <Icon name="minus" :size="14" />
          </button>
          <b>{{ stake }}</b>
          <button type="button" class="ui-btn small ghost" :disabled="stake >= left" aria-label="多押一枚" @click="stake++">
            <Icon name="plus" :size="14" />
          </button>
        </span>
        <button type="button" class="ui-btn primary" :disabled="busy || !online || !left" :aria-busy="busy" @click="place">
          <img class="coin" :src="COIN_SMALL" alt="" draggable="false" />押 {{ stake }} 枚
        </button>
      </template>
      <span class="left">本场还可押 {{ left }} 枚</span>
      <p v-if="betError" class="ui-error" role="alert">{{ betError }}</p>
    </div>

    <ul v-if="race?.mine.length" class="mine" aria-label="我的押注">
      <li v-for="b in race.mine" :key="`${b.kind}-${b.member}`" :class="{ hit: finished && race.ranking && hits(b.kind, b.member, race.ranking) }">
        <i class="tag" :style="{ background: colorOf(b.member) }"></i>
        {{ nameOf(b.member) }} {{ KIND_NAMES[b.kind] }} ×{{ b.odds.toFixed(1) }} · {{ b.coins }} 枚
      </li>
    </ul>

    <div v-if="shown?.ranking" class="result">
      <ol class="ranking" :aria-label="shown === race ? '本场名次' : '上一场名次'">
        <li v-for="(m, i) in shown.ranking" :key="m">
          <span class="rank" :style="{ background: colorOf(m) }">{{ i + 1 }}</span>{{ nameOf(m) }}
        </li>
      </ol>
      <p v-if="result" class="net" :class="{ up: result.net > 0, down: result.net < 0 }" role="status">
        <Icon name="shard" :size="16" />
        <b>{{ result.net > 0 ? "+" : result.net < 0 ? "−" : "" }}{{ fmt(result.net) }}</b>
      </p>
    </div>

    <p v-if="data?.winners.length" class="winners">
      <span>最近冠军</span>
      <span v-for="w in data.winners" :key="w.id" class="winner" :title="nameOf(w.member)">
        <img v-if="art(w.member)" :src="art(w.member)" alt="" draggable="false" />
        <i v-else class="tag" :style="{ background: colorOf(w.member) }"></i>
      </span>
    </p>
  </section>
</template>

<style scoped>
/* One sheet of paper, like the other park sections. */
.race {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 22px 20px;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}
.title h3 {
  margin: 6px 0 0;
  font: 800 var(--fs-heading)/1 var(--font);
  color: var(--ink);
}
.count {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.count b {
  font: 800 28px/1 var(--font-latin);
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.ticker {
  min-height: 18px;
  margin: -4px 0 0;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink-2);
  text-align: center;
}
.void {
  margin: 0;
  text-align: center;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--c-700);
}

/* ---- the field */
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.runner {
  display: grid;
  grid-template-columns: 88px minmax(96px, 1fr) minmax(84px, 0.8fr) auto minmax(90px, 0.9fr);
  align-items: center;
  gap: 10px 14px;
  padding: 6px 10px;
  border-radius: var(--radius-m);
}
.runner:nth-child(odd) {
  background: var(--c-50);
}
.runner.won {
  background: var(--c-100);
}
.who {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-strong);
  color: var(--ink);
}
.face {
  width: 34px;
  height: 34px;
  object-fit: contain;
  filter: var(--sticker);
}
.tag {
  flex: none;
  width: 4px;
  height: 16px;
  border-radius: 2px;
}
.skill,
.mood {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  font-size: var(--fs-body);
  color: var(--ink);
}
.skill small,
.mood small {
  font-size: var(--fs-caption);
  font-weight: 500;
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mood.hot b,
.mood.excited b {
  color: var(--c-700);
}
.mood.sleepy b,
.mood.slacking b {
  color: var(--ink-3);
}
.odds {
  display: flex;
  gap: 6px;
}
.pick {
  flex-direction: column;
  gap: 1px;
  height: 40px;
  min-width: 58px;
  padding: 0 8px;
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.pick small {
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-2);
}
.pick.hit {
  box-shadow: inset 0 0 0 2px var(--c-500);
}
.pool {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pool .bar {
  height: 6px;
  border-radius: 3px;
  background: var(--c-100);
  overflow: hidden;
}
.pool .bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  transition: width var(--dur-stage) var(--ease-out);
}
.pool small {
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-3);
  white-space: nowrap;
}

/* ---- the stake */
.stake {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 14px;
  padding: 10px 14px;
  border-radius: var(--radius-m);
  background: var(--c-100);
}
.picked {
  font-size: var(--fs-strong);
  font-weight: 800;
  color: var(--ink);
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
.stake .coin {
  width: 18px;
  height: 18px;
}
.left {
  margin-left: auto;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.stake .ui-error {
  flex-basis: 100%;
  margin: 0;
}

.mine {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink-2);
}
.mine li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.mine li.hit {
  color: var(--c-700);
}

/* ---- results */
.result {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 20px;
}
.ranking {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink);
}
.ranking li {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.rank {
  display: inline-grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border-radius: 5px;
  font: 800 var(--fs-label)/1 var(--font-latin);
  color: #fff;
}
.net {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0 0 0 auto;
  color: var(--ink-2);
}
.net b {
  font: 800 30px/1 var(--font-latin);
}
.net.up {
  color: var(--c-700);
}
.net.up b {
  animation: win-pop 600ms var(--ease-pop) both;
}
.calm .net.up b {
  animation: none;
}
@keyframes win-pop {
  0% { transform: scale(0.6); opacity: 0; }
  100% { transform: none; opacity: 1; }
}

.winners {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.winner img {
  width: 26px;
  height: 26px;
  object-fit: contain;
  filter: var(--sticker);
}

@container panel (max-width: 760px) {
  .runner {
    grid-template-columns: 80px 1fr 1fr;
  }
  .odds,
  .pool {
    grid-column: span 3;
  }
  .odds .pick {
    flex: 1;
  }
}
</style>
