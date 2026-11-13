<script setup lang="ts">
// 每日夺宝 (docs/design/amusement-park.md §7, §11; docs/design/park-ui-rebuild.md §5.4): the prize board (the top
// prize on gold foil, then the second and the third), three number keys to pick a number, my stubs of the day, and in the bottom bar the last draw with its hash
// check and the buy keys. There is no push: while the page is open the state loads every POLL_MS, and every few
// seconds once the draw is due. The countdown and 阿草 go up in the park's coral band (band.ts).
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import { online, status } from "../../stores/player";
import { park, parkTry } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import { ACHAO } from "../../ui/achao";
import Icon from "../../ui/Icon.vue";
import { EASE_OUT } from "../../ui/motion";
import { useBand } from "./band";
import { COIN_SMALL } from "./coin";
import {
  cleanNumber, countdown, dayBefore, dropDigit, markDrawSeen, matchedDigits, nextDraw, NO_PICKS, pickedNumber,
  pickTarget, putDigit, seenDraw, shortDay, stepDigit, verifyDraw, type LotteryBuy, type LotteryState, type Picks,
} from "./lottery";
import TicketStub from "./TicketStub.vue";

const POLL_MS = 20000;
/** After the draw time, until the draw shows up. */
const DUE_POLL_MS = 4000;
/** A key pressed by typing stays down this long. */
const PRESS_MS = 140;
/** 机选 presses the keys this far apart, and shows the number bought this long before the keys go back. */
const RANDOM_STEP_MS = 60;
const RANDOM_HOLD_MS = 700;
/** How long a draw's first showing runs: balls dropping, digits lighting, stamps. */
const REVEAL_MS = 2200;
/** Wheel travel (px) per digit step. */
const WHEEL_STEP = 40;
const fmt = (n: number) => n.toLocaleString("en-US");

const state = ref<LotteryState | null>(null);
const loadError = ref("");
const now = ref(Date.now() / 1000);
const calm = computed(() => reducedMotion.value);
/** The page is shown: the clock runs and a new draw may play its reveal. */
const active = ref(false);
/** The pop-up open over the bottom bar. */
const pop = ref<"" | "proof" | "past">("");

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
  active.value = true;
  window.addEventListener("keydown", onPageKey, true);
  if (timer) return;
  now.value = Date.now() / 1000;
  void load();
  timer = setInterval(tick, 1000);
}
function stop() {
  active.value = false;
  window.removeEventListener("keydown", onPageKey, true);
  if (timer) clearInterval(timer);
  timer = null;
  pop.value = "";
  endReveal();
}
// The page is kept alive: mounting (the park may open while the page is shown) and coming back both start the clock.
onMounted(start);
onActivated(start);
onDeactivated(stop);
onBeforeUnmount(() => {
  stop();
  clearTimeout(holdTimer);
  pressTimers.forEach(clearTimeout);
});
// Another save: its numbers.
watch(() => status.value?.player, (player, was) => {
  if (player === was) return;
  state.value = null;
  fresh.value = [];
  picks.value = NO_PICKS;
  at.value = null;
  shown.value = null;
  pop.value = "";
  endReveal();
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

// ---- buying
const coins = computed(() => park.value?.coins ?? status.value?.park?.coins ?? 0);
const busy = ref<"pick" | "random" | "">("");
const buyError = ref("");
/** Indexes of the tickets just bought, for their drop from the keys. */
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

// ---- the number keys: a digit or blank each; a key clicked is the one the next digit changes
const picks = ref<Picks>(NO_PICKS);
const at = ref<number | null>(null);
/** The number just bought at random, shown on the keys for a moment over what was picked. */
const shown = ref<Picks | null>(null);
const pressed = ref([false, false, false]);
/** The hidden field under the keys has the keyboard. */
const typing = ref(false);
const field = ref<HTMLInputElement>();
const keysEl = ref<HTMLElement>();
const stubsEl = ref<HTMLElement>();

const typed = computed(() => pickedNumber(picks.value) ?? "");
const faces = computed(() => shown.value ?? picks.value);
/** Keys stay pressable while coins are short: picking is free, only 下注 waits. */
const keysOff = computed(() => !online.value || !state.value?.open || state.value.left === 0);
/** Where the caret shows: the key the next typed digit goes to. */
const target = computed(() => (typing.value && !keysOff.value && !shown.value ? pickTarget(picks.value, at.value) : null));
const pickReady = computed(() => typed.value.length === 3 && blocked(1) === null);
const note = computed(() => buyError.value || blocked(1) || "");

const pressTimers: ReturnType<typeof setTimeout>[] = [];
function press(i: number) {
  if (calm.value) return;
  pressed.value = pressed.value.map((p, j) => p || j === i);
  clearTimeout(pressTimers[i]);
  pressTimers[i] = setTimeout(() => (pressed.value = pressed.value.map((p, j) => p && j !== i)), PRESS_MS);
}
function put(d: string) {
  const r = putDigit(picks.value, at.value, d);
  if (r.key === null) return;
  picks.value = r.picks;
  at.value = null;
  press(r.key);
}
/** Typed or pasted digits go onto the keys; the field itself stays empty. */
function onType(e: Event) {
  const input = e.target as HTMLInputElement;
  if (!keysOff.value && !shown.value) for (const d of cleanNumber(input.value)) put(d);
  input.value = "";
}
function onKey(e: KeyboardEvent) {
  if (e.isComposing) return;
  const busyKeys = keysOff.value || !!shown.value;
  if (e.key === "Enter") {
    buyPicked();
  } else if (e.key === "Escape") {
    // Lets go of a picked key before the panel's own Escape closes the panel.
    if (at.value !== null) {
      at.value = null;
      e.stopPropagation();
    }
  } else if (busyKeys) {
    return;
  } else if (e.key === "Backspace" || e.key === "Delete") {
    e.preventDefault();
    picks.value = dropDigit(picks.value, at.value);
    at.value = null;
  } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    e.preventDefault();
    const from = at.value ?? pickTarget(picks.value, null) ?? 2;
    at.value = Math.min(2, Math.max(0, from + (e.key === "ArrowLeft" ? -1 : 1)));
  } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    e.preventDefault();
    step(at.value ?? pickTarget(picks.value, null) ?? 2, e.key === "ArrowUp" ? 1 : -1);
  }
}
/**
 * Keys typed anywhere on the shown page while picking is open go to the number keys, ahead of the panel's digit page
 * shortcuts (a window listener in the bubble phase). Editable fields keep their keys (the hidden field has its own
 * handler), a focused tab keeps its arrows and a focused key its Enter; with picking closed everything passes through.
 */
function onPageKey(e: KeyboardEvent) {
  const s = state.value;
  if (!s || s.drawn || keysOff.value || e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return;
  if (document.querySelector("[data-overlay]")) return;
  const el = document.activeElement;
  const focused = (sel: string) => !!el?.closest?.(sel);
  if (focused("input, textarea, select, [contenteditable]")) return;
  const digit = /^[0-9]$/.test(e.key);
  const arrow = e.key.startsWith("Arrow");
  if (!digit && !arrow && e.key !== "Backspace" && e.key !== "Enter") return;
  if (arrow && focused("[role=tab]")) return;
  if (e.key === "Enter" && focused("button, a, [role=button]")) return;
  e.stopImmediatePropagation();
  e.preventDefault();
  if (!digit) onKey(e);
  else if (!shown.value) put(e.key);
}
function step(i: number, by: 1 | -1) {
  const next: [string, string, string] = [...picks.value];
  next[i] = stepDigit(next[i]!, by);
  picks.value = next;
}
function pickKey(i: number) {
  if (keysOff.value || shown.value) return;
  at.value = at.value === i ? null : i;
  field.value?.focus({ preventScroll: true });
}
let wheel = { key: -1, sum: 0 };
function onWheel(i: number, e: WheelEvent) {
  if (keysOff.value || shown.value) return;
  if (wheel.key !== i) wheel = { key: i, sum: 0 };
  wheel.sum += e.deltaY;
  if (Math.abs(wheel.sum) < WHEEL_STEP && Math.abs(e.deltaY) < WHEEL_STEP) return;
  step(i, wheel.sum < 0 ? 1 : -1);
  wheel.sum = 0;
}

let holdTimer: ReturnType<typeof setTimeout> | undefined;
/** 机选: the keys go down one after another, each taking a digit of the number bought, then go back. */
function showBought(number: string) {
  if (calm.value) return;
  clearTimeout(holdTimer);
  const base = picks.value;
  [0, 1, 2].forEach((i) => setTimeout(() => {
    const next: [string, string, string] = [...(shown.value ?? base)];
    next[i] = number[i] ?? "";
    shown.value = next;
    press(i);
  }, i * RANDOM_STEP_MS));
  holdTimer = setTimeout(() => (shown.value = null), 2 * RANDOM_STEP_MS + RANDOM_HOLD_MS);
}
/** The stubs just bought fall from the keys into their places. */
function dropFresh(delay: number) {
  const keys = keysEl.value?.getBoundingClientRect();
  if (calm.value || !keys || !stubsEl.value) return;
  const x = keys.left + keys.width / 2;
  const y = keys.top + keys.height / 2;
  stubsEl.value.querySelectorAll<HTMLElement>(".cell.fresh .ticket-stub").forEach((el, k) => {
    const to = el.getBoundingClientRect();
    const move = `translate(${x - (to.left + to.width / 2)}px, ${y - (to.top + to.height / 2)}px) scale(1.2)`;
    el.animate(
      [{ transform: move, opacity: 0 }, { opacity: 1, offset: 0.2 }, { transform: "none", opacity: 1 }],
      { duration: 480, delay: delay + k * 70, easing: EASE_OUT, fill: "backwards" },
    );
  });
}

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
  if (kind === "pick") {
    picks.value = NO_PICKS;
    at.value = null;
  } else {
    showBought(r.data.bought[r.data.bought.length - 1] ?? "");
  }
  await nextTick();
  dropFresh(kind === "random" ? 3 * RANDOM_STEP_MS : 0);
}
function buyPicked() {
  if (pickReady.value) void buy({ numbers: [typed.value] }, "pick");
}
function buyRandom(n: number) {
  if (blocked(n) === null) void buy({ random: n }, "random");
}
// A reason from the server holds until the state it was about changes.
watch(() => [state.value?.left, state.value?.open, coins.value, online.value], () => { if (!busy.value) buyError.value = ""; });
// Picking stops with the sales: no key held, no caret.
watch(keysOff, (off) => { if (off) at.value = null; });

// ---- the prize board: top, second and third, each with the trailing digits it takes
const tiers = computed(() => {
  const s = state.value;
  if (!s) return [];
  return [
    { id: "top", name: s.drawn ? "明日头奖" : "头奖", hit: 3, amount: s.prize.top, each: false },
    { id: "second", name: "二等", hit: 2, amount: s.prize.second, each: false },
    { id: "third", name: "三等", hit: 1, amount: s.prize.third, each: true },
  ] as const;
});

// ---- the last draw
const last = computed(() => state.value?.last ?? null);
const winning = computed(() => (last.value ? last.value.number.split("") : []));
/** Today is drawn: the stubs on the table are the ones of the last draw, with their results. */
const drawnHere = computed(() => !!last.value && last.value.day === state.value?.day);
const lastName = computed(() => {
  const d = last.value?.day ?? "";
  const today = state.value?.day ?? "";
  return d === today ? "今日" : d === dayBefore(today) ? "昨日" : shortDay(d);
});
/**
 * The last draw's stubs, with their results, are on the table: today once it is drawn, and the day after it until the
 * first number of that day is bought, so a draw seen the next morning lights up the stubs it was played with.
 */
const lastOnTable = computed(() => {
  const s = state.value;
  const d = last.value;
  if (!s || !d) return false;
  return drawnHere.value || (!!d.mine.length && !s.tickets.length && d.day === dayBefore(s.day));
});
/** My stubs: today's, or the last draw's with what each matched. */
const table = computed(() => {
  const s = state.value;
  if (!s) return [];
  if (lastOnTable.value) return last.value!.mine;
  return s.tickets.map((number) => ({ number, tier: null, prize: 0 }));
});
/** The day of the stubs on the table, so a stub of one day is never reused for another. */
const tableDay = computed(() => (lastOnTable.value ? last.value!.day : state.value?.day ?? ""));
/** Free places, while there is still a draw to buy for and today's stubs are on the table. */
const slots = computed(() => (state.value && !lastOnTable.value ? Math.max(0, state.value.daily - table.value.length) : 0));

/** The earlier days of the history; the last draw has its own block. */
const older = computed(() => (state.value?.history ?? []).filter((h) => h.day !== last.value?.day));
/** The last draw's stubs when they are not on the table (today's stubs are): they go behind 往期. */
const lastAside = computed(() => (!lastOnTable.value && last.value?.mine.length ? last.value : null));
const hasPast = computed(() => !!lastAside.value || older.value.length > 0);

const verified = ref<boolean | null>(null);
// Checked again only when the draw itself changes, not on every reload of the same one.
watch(() => (last.value ? [last.value.day, last.value.number, last.value.salt, last.value.hash].join("|") : ""), async (key) => {
  verified.value = null;
  if (pop.value === "proof") pop.value = "";
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

// ---- the first showing of a draw: balls drop right to left, my matching digits light up the same way
const reveal = ref("");
let revealTimer: ReturnType<typeof setTimeout> | undefined;
function endReveal() {
  clearTimeout(revealTimer);
  reveal.value = "";
}
watch(() => [active.value, last.value?.day ?? ""] as const, ([on, day]) => {
  if (!on || !day || seenDraw() === day) return;
  markDrawSeen(day);
  if (calm.value) return;
  reveal.value = day;
  clearTimeout(revealTimer);
  revealTimer = setTimeout(() => (reveal.value = ""), REVEAL_MS);
}, { immediate: true });

// ---- the bar's two pop-ups (pop, above): the proof of the draw, and the earlier days
const barEl = ref<HTMLElement>();
function toggle(p: "proof" | "past") {
  pop.value = pop.value === p ? "" : p;
}
function onOutside(e: PointerEvent) {
  if (!barEl.value?.contains(e.target as Node)) pop.value = "";
}
watch(pop, (open) => {
  if (open) document.addEventListener("pointerdown", onOutside, true);
  else document.removeEventListener("pointerdown", onOutside, true);
});
onBeforeUnmount(() => document.removeEventListener("pointerdown", onOutside, true));
function onBarKey(e: KeyboardEvent) {
  if (e.key === "Escape" && pop.value) {
    pop.value = "";
    e.stopPropagation();
  }
}
</script>

<template>
  <section class="lottery" :class="{ calm, reveal: !!reveal }" aria-label="每日夺宝">
    <div class="stage" :class="{ empty: !state }">
      <p v-if="loadError" class="ui-error" role="alert">{{ loadError }}</p>

      <template v-if="state">
        <!-- The prize board: three steps down from the top prize; the dots are the trailing digits a number must match. -->
        <ol class="prizes">
          <li
            v-for="t in tiers" :key="t.id" class="tier" :class="t.id"
            :aria-label="`${t.name} ${fmt(t.amount)}${t.each ? ' /注' : ''}`"
          >
            <span class="tier-head" aria-hidden="true">
              <span class="tier-name">{{ t.name }}</span>
              <span class="match"><i v-for="d in 3" :key="d" :class="{ on: d > 3 - t.hit }"></i></span>
            </span>
            <b class="amount" aria-hidden="true">
              <Icon name="shard" :size="t.id === 'top' ? 26 : 16" />{{ fmt(t.amount) }}<small v-if="t.each">/注</small>
            </b>
          </li>
        </ol>

        <!-- The keys take clicks and the wheel; the keyboard goes to the hidden field under them. -->
        <div v-if="!state.drawn" ref="keysEl" class="keys">
          <button
            v-for="(d, i) in faces" :key="i" type="button" class="ui-btn numkey" tabindex="-1" aria-hidden="true"
            :class="{ on: at === i, down: pressed[i], target: target === i }" :disabled="keysOff"
            @mousedown.prevent @click="pickKey(i)" @wheel.prevent="onWheel(i, $event)"
          >
            <span v-if="d" :key="d" class="face">{{ d }}</span>
            <i v-else-if="target !== i" class="blank"></i>
            <i v-if="target === i" class="caret"></i>
          </button>
          <input
            ref="field" class="field" type="text" inputmode="numeric" autocomplete="off" aria-label="号码"
            :disabled="keysOff" @input="onType" @keydown="onKey" @focus="typing = true" @blur="typing = false; at = null"
          />
        </div>

        <ol ref="stubsEl" class="stubs" :class="{ drawn: lastOnTable }" aria-label="我的号码">
          <li
            v-for="(t, i) in table" :key="`${tableDay}-${i}`" class="cell"
            :class="{ fresh: fresh.includes(i) }"
          >
            <TicketStub>
              <span
                v-for="(c, j) in digits(t.number, t.tier)" :key="j" class="digit" :class="{ on: c.hit }"
                :style="{ '--k': 2 - j }"
              >{{ c.d }}</span>
            </TicketStub>
            <b v-if="t.prize" class="stamp" :class="{ top: t.tier === 'top' }">+{{ fmt(t.prize) }}</b>
          </li>
          <li v-for="i in slots" :key="`slot-${i}`" class="cell slot" aria-hidden="true"></li>
        </ol>
      </template>
    </div>

    <div v-if="state" ref="barEl" class="park-actions" @keydown="onBarKey">
      <div v-if="last" class="last">
        <span class="when">{{ lastName }}</span>
        <span class="balls" :aria-label="`开奖号码 ${last.number}`">
          <i v-for="(d, i) in winning" :key="i" :style="{ '--i': i }">{{ d }}</i>
        </span>
        <button
          v-if="verified !== null" type="button" class="ui-btn ghost small proof-key" :class="{ bad: !verified }"
          :title="verified ? '已校验' : '校验不符'" :aria-expanded="pop === 'proof'" @click="toggle('proof')"
        >
          <Icon :name="verified ? 'check' : 'info'" :size="14" /><span>{{ verified ? "已校验" : "校验不符" }}</span>
        </button>
        <span class="result" :class="{ won: last.won > 0 }">
          <template v-if="last.won > 0"><Icon name="shard" :size="16" />+{{ fmt(last.won) }}</template>
          <template v-else-if="last.mine.length">未中奖</template>
        </span>
      </div>
      <button
        v-if="hasPast" type="button" class="ui-btn ghost small" :aria-expanded="pop === 'past'" @click="toggle('past')"
      >往期</button>

      <dl v-if="pop === 'proof' && last" class="pop proof">
        <div><dt>哈希</dt><dd>{{ last.hash }}</dd></div>
        <div><dt>随机串</dt><dd>{{ last.salt }}</dd></div>
      </dl>
      <div v-if="pop === 'past'" class="pop past ui-scroll">
        <div v-if="lastAside" class="past-day">
          <p class="past-head">
            <span>{{ shortDay(lastAside.day) }}</span>
            <b>{{ lastAside.number }}</b>
            <span class="won" :class="{ on: lastAside.won > 0 }">{{ lastAside.won > 0 ? `+${fmt(lastAside.won)}` : "未中奖" }}</span>
          </p>
          <ul class="past-stubs">
            <li v-for="(t, i) in lastAside.mine" :key="i">
              <TicketStub size="s">
                <span v-for="(c, j) in digits(t.number, t.tier)" :key="j" class="digit" :class="{ on: c.hit }">{{ c.d }}</span>
              </TicketStub>
            </li>
          </ul>
        </div>
        <ul v-if="older.length" class="history">
          <li v-for="h in older" :key="h.day">
            <span>{{ shortDay(h.day) }}</span>
            <b>{{ h.number }}</b>
            <span class="won" :class="{ on: h.won > 0 }">{{ h.won > 0 ? `+${fmt(h.won)}` : "未中奖" }}</span>
          </li>
        </ul>
      </div>

      <div v-if="!state.drawn" class="park-actions-main">
        <p class="note" :class="{ warn: !!buyError }" role="status">{{ note }}</p>
        <button type="button" class="ui-btn" :disabled="blocked(1) !== null" :aria-busy="busy === 'random'" @click="buyRandom(1)">机选</button>
        <button
          v-if="state.left > 1" type="button" class="ui-btn"
          :disabled="blocked(state.left) !== null" @click="buyRandom(state.left)"
        >机选 {{ state.left }} 注</button>
        <button
          type="button" class="ui-btn primary" :class="{ pulse: pickReady }" :disabled="!pickReady"
          :aria-busy="busy === 'pick'" @click="buyPicked"
        >
          <img class="coin" :src="COIN_SMALL" alt="" draggable="false" />下注
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* Fills the park's white body; the bottom bar (.park-actions) is the last child, so the root has no side padding. */
.lottery {
  display: flex;
  flex-direction: column;
}
.stage {
  flex: 1 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 24px;
  padding: 22px 22px 26px;
}
/* Nothing loaded: the error is the sheet's first line. */
.stage.empty {
  justify-content: flex-start;
}
.stage > .ui-error {
  align-self: stretch;
  margin: 0;
}

/*
 * ---- the prize board: three plaques stepping down, gold foil for the top prize, then coral, then the paper tint.
 * Plaques are read, not pressed: no edge under them. The dots are the trailing digits a number must match.
 */
.prizes {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.tier {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 6px;
  box-sizing: border-box;
  border-radius: var(--radius-m);
  color: var(--ink);
}
.tier.top {
  height: 96px;
  padding: 12px 24px 14px 20px;
  background: var(--grad-gold);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6), inset 0 -2px 0 rgba(var(--c-900-rgb), 0.14);
}
.tier.second {
  height: 76px;
  padding: 10px 16px 12px 14px;
  background: var(--c-300);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5);
}
.tier.third {
  height: 62px;
  padding: 8px 14px 10px 12px;
  background: var(--c-100);
}
.tier-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.tier-name {
  font: 800 var(--fs-label)/1 var(--font);
  white-space: nowrap;
}
.tier.top .tier-name {
  font-size: var(--fs-body);
}
.match {
  display: inline-flex;
  gap: 3px;
}
.match i {
  width: 7px;
  height: 7px;
  box-sizing: border-box;
  border-radius: 50%;
  border: 1.5px solid rgba(var(--c-900-rgb), 0.35);
}
.match i.on {
  border: 0;
  background: var(--ink);
}
.amount {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font: 800 22px/1 var(--font-latin);
  white-space: nowrap;
}
.tier.top .amount {
  gap: 4px;
  font-size: 48px;
}
.tier.second .amount {
  font-size: 28px;
}
.tier:not(.top) .amount svg {
  color: var(--c-700);
}
.amount small {
  margin-left: 3px;
  font: 600 var(--fs-caption) var(--font);
  color: var(--ink-2);
}

/* ---- the number keys: three tall keycaps; typing presses them */
/* On a tonal tray: white keys need a step of the ramp under them to read as keys. */
.keys {
  position: relative;
  display: flex;
  gap: 14px;
  padding: 14px 16px 18px;
  border-radius: var(--radius-l);
  background: var(--c-100);
}
.numkey {
  --key-lip-h: 4px;
  width: 88px;
  height: 112px;
  padding: 0;
  border-radius: var(--radius-l);
}
.numkey.down:not(:disabled) {
  --key-y: 4px;
  --key-lip-h: 0px;
  transition-duration: var(--dur-press);
  transition-timing-function: ease-out;
}
/* Latched (the key being changed): a step deeper than the tray it sits on. */
.numkey.on:not(:disabled) {
  --key-top: var(--c-200);
  --key-bottom: var(--c-200);
  --key-lip: var(--c-300);
}
/* Disabled keys stay a shade off the tray. */
.numkey:disabled {
  --key-top: var(--c-50);
  --key-bottom: var(--c-50);
}
.numkey:disabled .face {
  color: var(--ink-3);
}
/* The field to read the keyboard: there, focusable, never seen. */
.field {
  position: absolute;
  left: 50%;
  bottom: 0;
  width: 1px;
  height: 1px;
  padding: 0;
  border: 0;
  opacity: 0;
  pointer-events: none;
}
.face {
  font: 800 72px/1 var(--font-latin);
  color: var(--ink);
  animation: face-in 200ms var(--ease-pop) both;
}
@keyframes face-in {
  from { transform: translateY(-10px) scale(0.8); opacity: 0; }
}
/* A blank key: a short line where its digit goes. */
.blank {
  width: 28px;
  height: 4px;
  margin-top: 46px;
  border-radius: 2px;
  background: var(--c-200);
}
.caret {
  position: absolute;
  left: 50%;
  top: 28px;
  width: 3px;
  height: 52px;
  margin-left: -1.5px;
  border-radius: 2px;
  background: var(--c-500);
  animation: caret 1.1s steps(1) infinite;
}
@keyframes caret {
  50% { opacity: 0; }
}
.calm .face,
.calm .caret {
  animation: none;
}

/* ---- my stubs: 2 rows of 5; a place still free is a dashed outline */
.stubs {
  display: grid;
  grid-template-columns: repeat(5, 96px);
  gap: 14px 16px;
  justify-content: center;
  margin: 0;
  padding: 0;
  list-style: none;
}
.cell {
  position: relative;
  display: flex;
  height: 56px;
}
.cell :deep(.ticket-stub),
.cell :deep(.paper) {
  width: 100%;
}
.slot {
  box-sizing: border-box;
  border: 2px dashed var(--c-200);
  border-radius: var(--radius-s);
}
.digit {
  display: inline-block;
}
/* Drawn: what matched is coral, the rest steps back. */
.drawn .digit {
  color: var(--ink-3);
}
.drawn .digit.on,
.past-stubs .digit.on {
  color: var(--c-700);
}
.stamp {
  position: absolute;
  top: -11px;
  right: -9px;
  padding: 3px 6px 2px;
  border: 2px solid var(--c-600);
  border-radius: var(--radius-s);
  background: var(--surface);
  font: 800 17px/1 var(--font-latin);
  color: var(--c-700);
  rotate: -9deg;
  white-space: nowrap;
}
.stamp.top {
  border-color: color-mix(in oklab, var(--gold) 78%, var(--c-700));
  background: var(--grad-gold);
  color: var(--ink);
}

/* ---- the bottom bar: the last draw on the left, the buy keys on the right */
.last {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.when {
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.balls {
  display: inline-flex;
  gap: 5px;
}
/* Lottery balls: coral spheres with a soft light at the upper left. */
.balls i {
  display: inline-grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: radial-gradient(circle at 34% 28%, var(--c-300), var(--c-500) 52%, var(--c-600));
  box-shadow: inset 0 -2px 3px rgba(var(--c-900-rgb), 0.18);
  font: 800 26px/1 var(--font-latin);
  font-style: normal;
  color: #fff;
}
.proof-key {
  gap: 3px;
  padding: 0 8px;
  color: var(--ink-3);
}
.proof-key.bad,
.proof-key.bad:hover:not(:disabled),
.proof-key.bad[aria-expanded="true"]:not(:disabled) {
  color: var(--bad);
}
.result {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.result.won {
  font: 800 var(--fs-title)/1 var(--font-latin);
  color: var(--c-700);
}
.note {
  min-width: 0;
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
  white-space: nowrap;
}
.note:empty {
  display: none;
}
.note.warn {
  color: var(--c-700);
}
.coin {
  width: 18px;
  height: 18px;
}

/* Pop-ups rise from the bar over the page. */
.pop {
  position: absolute;
  left: 16px;
  bottom: calc(100% + 8px);
  z-index: 3;
  max-width: min(460px, calc(100% - 32px));
  max-height: 240px;
  margin: 0;
  padding: 14px 16px;
  box-sizing: border-box;
  overflow-y: auto;
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: var(--shadow-paper), 0 10px 28px -12px rgba(var(--c-900-rgb), 0.3);
}
.proof {
  display: flex;
  flex-direction: column;
  gap: 6px;
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
.past {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 360px;
}
.past-day {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 12px 12px;
  border-radius: var(--radius-s);
  background: var(--c-100);
}
.past-head,
.history li {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.past-head b,
.history b {
  font: 800 var(--fs-number)/1 var(--font-latin);
  letter-spacing: 0.08em;
  color: var(--ink-2);
}
.past-head .won,
.history .won {
  margin-left: auto;
}
.past-head .won.on,
.history .won.on {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--c-700);
}
.past-stubs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.past-stubs .digit {
  color: var(--ink-3);
}
.history {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0 2px;
  list-style: none;
}

/* ---- the first showing of a draw: balls drop in from right to left, then my digits light the same way */
.reveal .balls i {
  animation: ball-in 460ms var(--ease-pop) both;
  animation-delay: calc((2 - var(--i)) * 320ms);
}
@keyframes ball-in {
  from { transform: translate(14px, -46px); opacity: 0; }
  40% { opacity: 1; }
}
.reveal .drawn .digit.on {
  animation: digit-lit 360ms var(--ease-out) both;
  animation-delay: calc(var(--k) * 320ms + 300ms);
}
@keyframes digit-lit {
  from { color: var(--ink-3); }
  45% { transform: translateY(-4px) scale(1.18); }
  to { color: var(--c-700); }
}
.reveal .stamp,
.reveal .result.won {
  animation: stamp-in 360ms var(--ease-pop) 1300ms both;
}
@keyframes stamp-in {
  from { transform: scale(1.7); opacity: 0; }
}

@container panel (max-width: 760px) {
  .stage {
    gap: 20px;
  }
  .tier.top {
    height: 84px;
    padding: 10px 18px 12px 16px;
  }
  .tier.top .amount {
    font-size: 40px;
  }
  .tier.second {
    height: 68px;
  }
  .tier.second .amount {
    font-size: 24px;
  }
  .numkey {
    width: 64px;
    height: 84px;
    border-radius: var(--radius-m);
  }
  .face {
    font-size: 54px;
  }
  .blank {
    width: 22px;
    margin-top: 34px;
  }
  .caret {
    top: 20px;
    height: 40px;
  }
  .stubs {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    max-width: 560px;
  }
  .stubs {
    gap: 12px;
  }
  .cell {
    width: 88px;
  }
  .keys {
    gap: 10px;
    padding: 10px 12px 14px;
  }
  .when {
    display: none;
  }
}

/* Short panel: the top prize and the keys side by side, the stubs under them; the body scrolls, the bar stays. */
@container panel (max-height: 560px) {
  .stage {
    flex-direction: row;
    flex-wrap: wrap;
    align-content: flex-start;
    gap: 16px 24px;
    padding: 16px 16px 18px;
  }
  /* The board turns into three rows: name and dots on the left, the amount on the right. */
  .prizes {
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
  }
  .tier.top,
  .tier.second,
  .tier.third {
    height: auto;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    padding: 6px 12px;
  }
  .tier.top .amount {
    font-size: 30px;
  }
  .tier.second .amount {
    font-size: 22px;
  }
  .tier.third .amount {
    font-size: 18px;
  }
  .stubs,
  .stage > .ui-error {
    flex: 1 0 100%;
  }
  .balls i {
    width: 32px;
    height: 32px;
    font-size: 21px;
  }
  .proof-key > span {
    display: none;
  }
  .result.won {
    font-size: var(--fs-heading);
  }
}
</style>
