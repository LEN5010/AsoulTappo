<script setup lang="ts">
// 每日夺宝 (docs/design/amusement-park.md §7, §11): the next top prize and the countdown to the draw, my numbers of
// the day, picking one by hand or buying random ones, and the last draw with my result and its hash check. There is
// no push: while the page is open the state loads every POLL_MS, and every few seconds once the draw is due. The
// countdown and 阿草 go up in the park's coral band (band.ts).
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import { online, status } from "../../stores/player";
import { park, parkTry } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import { ACHAO } from "../../ui/achao";
import Icon from "../../ui/Icon.vue";
import { useBand } from "./band";
import { COIN_SMALL } from "./coin";
import {
  cleanNumber, countdown, matchedDigits, nextDraw, shortDay, verifyDraw, type LotteryBuy, type LotteryState,
} from "./lottery";

const POLL_MS = 20000;
/** After the draw time, until the draw shows up. */
const DUE_POLL_MS = 4000;
const fmt = (n: number) => n.toLocaleString("en-US");

const state = ref<LotteryState | null>(null);
const loadError = ref("");
const now = ref(Date.now() / 1000);
const calm = computed(() => reducedMotion.value);

let loading = false;
let loadedAt = 0;
async function load() {
  if (loading) return;
  loading = true;
  loadedAt = Date.now();
  const player = status.value?.player;
  try {
    const r = await parkTry<LotteryState>("GET", "/api/park/lottery");
    if (player !== status.value?.player) return;
    if (r.ok) {
      state.value = r.data;
      loadError.value = "";
    } else if (!state.value && r.error.status > 0) {
      loadError.value = r.error.message;
    }
  } finally {
    loading = false;
  }
}

// ---- the clock: the countdown, and loading again on time
let timer: ReturnType<typeof setInterval> | null = null;
function tick() {
  now.value = Date.now() / 1000;
  const s = state.value;
  const due = !!s && !s.drawn && now.value >= s.drawAt;
  if (Date.now() - loadedAt >= (due ? DUE_POLL_MS : POLL_MS)) void load();
}
function start() {
  if (timer) return;
  now.value = Date.now() / 1000;
  void load();
  timer = setInterval(tick, 1000);
}
function stop() {
  if (timer) clearInterval(timer);
  timer = null;
}
// The page is kept alive: mounting (the park may open while the page is shown) and coming back both start the clock.
onMounted(start);
onActivated(start);
onDeactivated(stop);
onBeforeUnmount(stop);
// Another save: its numbers.
watch(() => status.value?.player, (player, was) => {
  if (player === was) return;
  state.value = null;
  fresh.value = [];
  if (timer) void load();
});

// ---- the next draw
const drawTime = computed(() => (state.value ? nextDraw(state.value) : 0));
const left = computed(() => countdown(drawTime.value, now.value));
const waiting = computed(() => !!state.value && !state.value.drawn && now.value >= state.value.drawAt);
useBand("lottery", () => {
  const s = state.value;
  const label = waiting.value ? "开奖中" : s?.drawn ? "明日 22:00 开奖" : "22:00 开奖";
  return { host: ACHAO["观察"], timer: s ? { label, time: waiting.value ? undefined : left.value } : undefined };
});

// ---- my numbers and buying
const coins = computed(() => park.value?.coins ?? status.value?.park?.coins ?? 0);
const typed = ref("");
const busy = ref<"pick" | "random" | "">("");
const buyError = ref("");
/** Indexes of the tickets just bought, for their entrance. */
const fresh = ref<number[]>([]);

/** Why [n] tickets cannot be bought now: a short reason, "" when none is worth showing, null when they can. */
function blocked(n: number): string | null {
  if (!online.value) return "未连接";
  const s = state.value;
  if (!s || busy.value) return "";
  if (!s.open) return "已停售";
  if (s.left === 0) return "今日已买满";
  if (n > s.left) return "";
  if (coins.value < n) return "驼币不足";
  return null;
}
const pickReady = computed(() => typed.value.length === 3 && blocked(1) === null);
const note = computed(() => buyError.value || blocked(1) || "");

async function buy(body: { numbers?: string[]; random?: number }, kind: "pick" | "random") {
  busy.value = kind;
  buyError.value = "";
  const r = await parkTry<LotteryBuy>("POST", "/api/park/lottery", body);
  busy.value = "";
  if (!r.ok) {
    buyError.value = r.error.message;
    return;
  }
  const s = r.data.lottery;
  state.value = s;
  const from = s.tickets.length - r.data.bought.length;
  fresh.value = r.data.bought.map((_, i) => from + i);
  if (kind === "pick") typed.value = "";
}
function buyPicked() {
  if (pickReady.value) void buy({ numbers: [typed.value] }, "pick");
}
function buyRandom(n: number) {
  if (blocked(n) === null) void buy({ random: n }, "random");
}
function onType(e: Event) {
  const input = e.target as HTMLInputElement;
  typed.value = cleanNumber(input.value);
  input.value = typed.value;
}
// A reason from the server holds until the state it was about changes.
watch(() => [state.value?.left, state.value?.open, coins.value, online.value], () => { if (!busy.value) buyError.value = ""; });

const slots = computed(() => {
  const s = state.value;
  return s ? Math.max(0, s.daily - s.tickets.length) : 0;
});

// ---- the last draw
const last = computed(() => state.value?.last ?? null);
const winning = computed(() => (last.value ? last.value.number.split("") : []));
/** The earlier days of the history; the last draw has its own block. */
const older = computed(() => (state.value?.history ?? []).filter((h) => h.day !== last.value?.day));
const verified = ref<boolean | null>(null);
const showProof = ref(false);
// Checked again only when the draw itself changes, not on every reload of the same one.
watch(() => (last.value ? [last.value.day, last.value.number, last.value.salt, last.value.hash].join("|") : ""), async (key) => {
  verified.value = null;
  showProof.value = false;
  const d = last.value;
  if (!d) return;
  const ok = await verifyDraw(d.number, d.salt, d.hash);
  if (last.value?.day === d.day && key) verified.value = ok;
}, { immediate: true });

/** A ticket's digits, each marked when it is one of the trailing digits that matched. */
function digits(number: string, tier: Parameters<typeof matchedDigits>[0]) {
  const hit = matchedDigits(tier);
  return number.split("").map((d, i) => ({ d, hit: i >= 3 - hit }));
}
</script>

<template>
  <section class="lottery" :class="{ calm }" aria-label="每日夺宝">
    <p v-if="loadError" class="ui-error" role="alert">{{ loadError }}</p>

    <template v-if="state">
      <div class="prizes">
        <div class="top">
          <span>{{ state.drawn ? "明日头奖" : "头奖" }}</span>
          <b><Icon name="shard" :size="22" />{{ fmt(state.prize.top) }}</b>
        </div>
        <dl class="minor">
          <div><dt>二等</dt><dd><Icon name="shard" :size="12" />{{ fmt(state.prize.second) }}</dd></div>
          <div><dt>三等</dt><dd><Icon name="shard" :size="12" />{{ fmt(state.prize.third) }}<small>/注</small></dd></div>
        </dl>
      </div>

      <div class="mine">
        <p class="sub">我的号码 <small>{{ state.tickets.length }} / {{ state.daily }}</small></p>
        <ul class="tickets">
          <li v-for="(n, i) in state.tickets" :key="`${state.day}-${i}`" class="ticket" :class="{ fresh: fresh.includes(i) }">{{ n }}</li>
          <li v-for="i in slots" :key="`slot-${i}`" class="ticket slot" aria-hidden="true"></li>
        </ul>
      </div>

      <div v-if="!state.drawn" class="pick">
        <input
          class="ui-input digits" type="text" inputmode="numeric" maxlength="3" placeholder="000" aria-label="号码"
          :value="typed" :disabled="!state.open" @input="onType" @keydown.enter="buyPicked"
        />
        <button type="button" class="ui-btn primary" :disabled="!pickReady" :aria-busy="busy === 'pick'" @click="buyPicked">
          <img class="coin" :src="COIN_SMALL" alt="" draggable="false" />下注
        </button>
        <button type="button" class="ui-btn" :disabled="blocked(1) !== null" :aria-busy="busy === 'random'" @click="buyRandom(1)">机选</button>
        <button
          v-if="state.left > 1" type="button" class="ui-btn"
          :disabled="blocked(state.left) !== null" @click="buyRandom(state.left)"
        >机选 {{ state.left }} 注</button>
        <p class="note" :class="{ warn: !!buyError }" role="status">{{ note }}</p>
      </div>

      <div v-if="last" class="last">
        <div class="draw">
          <span class="day">{{ shortDay(last.day) }}</span>
          <span class="balls" :aria-label="`开奖号码 ${last.number}`">
            <i v-for="(d, i) in winning" :key="i">{{ d }}</i>
          </span>
          <button
            v-if="verified !== null" type="button" class="proof-key" :class="{ bad: !verified }"
            :aria-expanded="showProof" @click="showProof = !showProof"
          >
            <Icon :name="verified ? 'check' : 'info'" :size="12" />{{ verified ? "已校验" : "校验不符" }}
          </button>
          <span class="result" :class="{ won: last.won > 0 }">
            <template v-if="last.won > 0"><Icon name="shard" :size="14" />+{{ fmt(last.won) }}</template>
            <template v-else-if="last.mine.length">未中奖</template>
          </span>
        </div>
        <dl v-if="showProof" class="proof">
          <div><dt>哈希</dt><dd>{{ last.hash }}</dd></div>
          <div><dt>随机串</dt><dd>{{ last.salt }}</dd></div>
        </dl>
        <ul v-if="last.mine.length" class="tickets past">
          <li v-for="(t, i) in last.mine" :key="i" class="ticket" :class="{ hit: t.tier }">
            <span v-for="(c, j) in digits(t.number, t.tier)" :key="j" :class="{ on: c.hit }">{{ c.d }}</span>
            <small v-if="t.prize">+{{ fmt(t.prize) }}</small>
          </li>
        </ul>
        <ul v-if="older.length" class="history">
          <li v-for="h in older" :key="h.day">
            <span>{{ shortDay(h.day) }}</span>
            <b>{{ h.number }}</b>
            <span class="won" :class="{ on: h.won > 0 }">{{ h.won > 0 ? `+${fmt(h.won)}` : "未中奖" }}</span>
          </li>
        </ul>
      </div>
    </template>
  </section>
</template>

<style scoped>
/* On the park's sheet, under the coral band; groups inside it are tonal bands, not boxes. */
.lottery {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 22px 20px;
}
.lottery > .ui-error {
  margin: 0;
}

/* ---- prizes: the top one is the number to see */
.prizes {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 10px 28px;
}
.top {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.top span {
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.top b {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font: 800 40px/1 var(--font-latin);
  color: var(--ink);
}
.top svg {
  color: var(--c-600);
}
.minor {
  display: flex;
  gap: 20px;
  margin: 0 0 4px;
}
.minor > div {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.minor dt {
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.minor dd {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin: 0;
  font: 700 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}
.minor dd svg {
  color: var(--c-600);
}
.minor small {
  margin-left: 2px;
  font: 600 var(--fs-caption) var(--font);
  color: var(--ink-3);
}

/* ---- my numbers: ticket stubs on a tonal band, empty places dashed */
.mine {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sub {
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.sub small {
  margin-left: 4px;
  font: 700 var(--fs-strong)/1 var(--font-latin);
  color: var(--c-700);
}
.tickets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.ticket {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 1px;
  min-width: 52px;
  height: 34px;
  padding: 0 8px;
  box-sizing: border-box;
  border-radius: var(--radius-s);
  background: var(--c-100);
  font: 800 20px/1 var(--font-latin);
  letter-spacing: 0.08em;
  color: var(--ink);
}
.ticket.slot {
  background: transparent;
  outline: 1.5px dashed var(--c-300);
  outline-offset: -1.5px;
}
.ticket.fresh {
  animation: ticket-in 420ms var(--ease-out) both;
}
.calm .ticket.fresh {
  animation: none;
}
@keyframes ticket-in {
  0% { opacity: 0; transform: translateY(6px) scale(0.86); }
  60% { opacity: 1; transform: translateY(-2px) scale(1.04); }
  100% { transform: none; }
}

/* ---- picking */
.pick {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.digits {
  width: 84px;
  background: var(--c-100);
  box-shadow: none;
  font: 800 22px/1 var(--font-latin);
  letter-spacing: 0.2em;
  text-align: center;
}
.coin {
  width: 16px;
  height: 16px;
  margin-right: 4px;
}
.note {
  flex: 1;
  min-width: 80px;
  min-height: 16px;
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
  text-align: right;
}
.note.warn {
  color: var(--c-700);
}

/* ---- the last draw */
.last {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border-radius: var(--radius-m);
  background: var(--c-50);
}
.draw {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
}
.day {
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.balls {
  display: inline-flex;
  gap: 5px;
}
.balls i {
  display: inline-grid;
  place-items: center;
  width: 32px;
  height: 38px;
  border-radius: var(--radius-s);
  background: linear-gradient(180deg, var(--c-400), var(--c-500));
  font: 800 28px/1 var(--font-latin);
  font-style: normal;
  color: #fff;
}
/* The check stays quiet: a small key without a lip, opening the hash and salt. */
.proof-key {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 22px;
  padding: 0 6px;
  border: 0;
  border-radius: var(--radius-s);
  background: transparent;
  font: 700 var(--fs-caption) var(--font);
  color: var(--ink-3);
  cursor: pointer;
}
.proof-key:hover,
.proof-key[aria-expanded="true"] {
  background: var(--c-100);
}
.proof-key.bad {
  color: var(--bad);
}
.result {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: auto;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.result.won {
  font: 800 var(--fs-heading)/1 var(--font-latin);
  color: var(--c-700);
}
.proof {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
}
.proof > div {
  display: flex;
  gap: 8px;
  min-width: 0;
}
.proof dt {
  flex: none;
  width: 40px;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-3);
}
.proof dd {
  min-width: 0;
  margin: 0;
  font: 500 var(--fs-caption)/1.4 ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  color: var(--ink-2);
  overflow-wrap: anywhere;
  user-select: text;
}
.tickets.past .ticket {
  height: 30px;
  font-size: 17px;
  background: var(--surface);
  color: var(--ink-3);
}
.tickets.past .ticket.hit {
  color: var(--ink-2);
}
.tickets.past .on {
  color: var(--c-700);
}
.tickets.past small {
  margin-left: 6px;
  font: 800 var(--fs-label)/1 var(--font-latin);
  letter-spacing: 0;
  color: var(--c-700);
}
.history {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.history li {
  display: flex;
  align-items: baseline;
  gap: 12px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.history b {
  font: 800 var(--fs-number)/1 var(--font-latin);
  letter-spacing: 0.08em;
  color: var(--ink-2);
}
.history .won {
  margin-left: auto;
}
.history .won.on {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--c-700);
}

@container panel (max-width: 760px) {
  .top b {
    font-size: 34px;
  }
}
</style>
