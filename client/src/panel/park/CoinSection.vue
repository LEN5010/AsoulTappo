<script setup lang="ts">
// The coin page of the park (docs/design/amusement-park.md §2, §4, §8.3, §10; docs/design/park-ui-rebuild.md §5.1):
// the big coin and the coins held, three tall keys that buy more, the stamp card with its badges, and the redeem
// code in the bottom bar. Bought coins fly from the key into the big coin; a card of stamps paid out as a coin
// flashes, clears, and sends its coin the same way.
import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from "vue";
import { manifest } from "../../manifest";
import { online, shards, status } from "../../stores/player";
import { buyCoins, park, parkError } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import { ACHAO } from "../../ui/achao";
import Icon from "../../ui/Icon.vue";
import { EASE_OUT } from "../../ui/motion";
import { useBand } from "./band";
import { BADGE_ART, COIN_SMALL } from "./coin";
import CoinStack from "./CoinStack.vue";
import ParkCoin from "./ParkCoin.vue";
import RedeemForm from "./RedeemForm.vue";
import Stamp from "./Stamp.vue";

const emit = defineEmits<{ bought: [count: number] }>();
useBand("coin", () => ({ host: ACHAO["招商"] }));

// The bundled manifest always has the park; the server checks every number again.
const CFG = manifest.economy.park!.coin;
const PACKS: { n: number; pile: 1 | 3 | 5 }[] = [{ n: 1, pile: 1 }, { n: 5, pile: 3 }, { n: 10, pile: 5 }];
const BADGES = ["铜驼", "银驼", "金驼"];
const PER = CFG.stampsPerCoin;
const fmt = (n: number) => n.toLocaleString("en-US");

const state = computed(() => park.value);
const coins = computed(() => state.value?.coins ?? status.value?.park?.coins ?? 0);
const badge = computed(() => Math.min(BADGES.length, state.value?.badge ?? 0));
const stampsTotal = computed(() => state.value?.stampsTotal ?? 0);

/** Today's result: shards won in the park less shards spent on coins. */
const net = computed(() => (state.value ? state.value.today.won - state.value.today.spent : 0));
const netText = computed(() => (net.value > 0 ? `+${fmt(net.value)}` : net.value < 0 ? `−${fmt(-net.value)}` : "0"));
const netTip = computed(() =>
  state.value ? `今日花费 ${fmt(state.value.today.spent)}，今日赢得 ${fmt(state.value.today.won)}` : undefined,
);

const busy = ref(0);
const buyError = ref("");

/** Why [n] coins cannot be bought now: a short reason, "" for a state that needs none (loading, busy), null when they can. */
function blocked(n: number): string | null {
  if (!online.value) return "未连接";
  const s = state.value;
  if (!s || busy.value) return "";
  if (shards.value < n * CFG.price) return "碎片不足";
  return null;
}
/** A key is out of reach (not just waiting on a request): disabled and grey. */
const outOfReach = (n: number) => !busy.value && blocked(n) !== null;
/** The disabled key's tooltip: its reason. */
const keyTip = (n: number) => (outOfReach(n) ? blocked(n) || undefined : undefined);
/** The 1-coin key is the coral primary while it can be pressed, and stays so while its own request runs. */
const live1 = computed(() => !outOfReach(1));
/** The one line under the keys: why buying is blocked. Empty while it is not. */
const note = computed(() => buyError.value || (busy.value ? "" : blocked(1)) || "");

async function buy(n: number, ev: MouseEvent) {
  if (blocked(n) !== null) return;
  const key = ev.currentTarget as HTMLElement;
  busy.value = n;
  buyError.value = "";
  hold++;
  let ok = false;
  try {
    ok = await buyCoins(n);
  } finally {
    // Busy covers the request only: the keys work again while the coins are still flying.
    busy.value = 0;
  }
  if (!ok) {
    buyError.value = parkError.value?.message ?? "";
    release();
    return;
  }
  emit("bought", n);
  try {
    await flyIn(key.querySelector<HTMLElement>(".coin-stack") ?? key, n);
  } finally {
    release();
  }
}
// A reason from the server holds until the state it was about changes.
watch(() => [state.value?.coins, shards.value, online.value], () => { if (!busy.value) buyError.value = ""; });

// ---------------------------------------------------------------- the balance shown, and the motion into it
const sky = ref<HTMLElement>();
const heroCoin = ref<HTMLElement>();
const spinner = ref<HTMLElement>();
const card = ref<HTMLElement>();

const ROLL_MS = 400;
const FLIGHT_MS = 560;
const WAVE_MS = 170;
const FLASH_MS = 420;
const CLEAR_MS = 180;

/** The balance on the page: it waits for coins in flight, then rolls to the held count. */
const shown = ref(coins.value);
let hold = 0;
let rollFrame = 0;
let active = false;
const ghosts = new Set<Animation>();

function roll(to: number) {
  cancelAnimationFrame(rollFrame);
  if (reducedMotion.value || !active || shown.value === to) {
    shown.value = to;
    return;
  }
  const base = shown.value;
  const start = performance.now();
  const step = (now: number) => {
    const t = Math.min(1, (now - start) / ROLL_MS);
    shown.value = Math.round(base + (to - base) * (1 - (1 - t) ** 3));
    if (t < 1) rollFrame = requestAnimationFrame(step);
  };
  rollFrame = requestAnimationFrame(step);
}
/**
 * Ends one hold; the last one lets the balance roll, and the big coin turns when it went up or [landed] (a coin
 * from the stamp card can land while the coin it was paid for is spent in the same answer).
 */
function release(landed = false) {
  hold = Math.max(0, hold - 1);
  if (hold || pendingWrap) return;
  const up = coins.value > shown.value;
  roll(coins.value);
  if (up || landed) turn();
}

const wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const centre = (el: Element, base: DOMRect) => {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2 - base.left, y: r.top + r.height / 2 - base.top };
};

/** One small coin on an arc from [from] into the big coin. Resolves when it lands (at once without motion). */
function flyOne(from: Element, delay: number, jitter: number): Promise<void> {
  const layer = sky.value;
  const target = heroCoin.value;
  if (!layer || !target || reducedMotion.value || !active) return Promise.resolve();
  const base = layer.getBoundingClientRect();
  const a = centre(from, base);
  const b = centre(target, base);
  const size = 40;
  const ghost = new Image();
  ghost.src = COIN_SMALL;
  ghost.alt = "";
  Object.assign(ghost.style, {
    position: "absolute",
    left: `${-size / 2}px`,
    top: `${-size / 2}px`,
    width: `${size}px`,
    height: `${size}px`,
    opacity: "0",
    filter: "drop-shadow(0 2px 2px rgba(var(--c-900-rgb), 0.3))",
  });
  layer.append(ghost);
  const peak = Math.min(a.y, b.y) - 70;
  const mid = { x: (a.x + b.x) / 2 + jitter, y: peak };
  const anim = ghost.animate(
    [
      { transform: `translate(${a.x}px, ${a.y}px) scale(0.8)`, opacity: 1 },
      { transform: `translate(${mid.x}px, ${mid.y}px) scale(1.15) rotate(-20deg)`, opacity: 1, offset: 0.5 },
      { transform: `translate(${b.x}px, ${b.y}px) scale(0.8) rotate(-40deg)`, opacity: 1, offset: 0.85 },
      { transform: `translate(${b.x}px, ${b.y}px) scale(0.5) rotate(-40deg)`, opacity: 0 },
    ],
    { duration: FLIGHT_MS, delay, easing: "cubic-bezier(0.45, 0, 0.55, 1)", fill: "backwards" },
  );
  ghosts.add(anim);
  return anim.finished.catch(() => {}).then(() => {
    ghosts.delete(anim);
    ghost.remove();
    bump();
  });
}
/** Coins from a buy key: one coin, or three waves for 5 and 10. */
function flyIn(from: Element, n: number): Promise<void> {
  const waves = n === 1 ? [1] : n === 5 ? [2, 2, 1] : [3, 3, 4];
  const flights: Promise<void>[] = [];
  waves.forEach((count, w) => {
    for (let i = 0; i < count; i++) flights.push(flyOne(from, w * WAVE_MS + i * 45, (i - (count - 1) / 2) * 36));
  });
  return Promise.all(flights).then(() => {});
}

/** The big coin gives a little as a coin lands in it. */
function bump() {
  if (reducedMotion.value || !spinner.value) return;
  spinner.value.animate([{ scale: "1" }, { scale: "1.06" }, { scale: "1" }], { duration: 180, easing: EASE_OUT });
}
/** Half a turn about its upright axis, settling face up: edge-on at the halfway mark, so the face never flips. */
function turn() {
  if (reducedMotion.value || !spinner.value) return;
  spinner.value.animate(
    [
      { transform: "perspective(600px) rotateY(0deg)" },
      { transform: "perspective(600px) rotateY(90deg)", offset: 0.4 },
      { transform: "perspective(600px) rotateY(-90deg)", offset: 0.4 },
      { transform: "perspective(600px) rotateY(14deg)", offset: 0.82 },
      { transform: "perspective(600px) rotateY(0deg)" },
    ],
    { duration: 640, easing: "ease-out" },
  );
}

// ---------------------------------------------------------------- the stamp card
/** All 30 slots inked for a moment when a card of stamps has just turned into a coin, then cleared. */
const wrapping = ref<"" | "flash" | "clear">("");
const inked = computed(() => (wrapping.value ? PER : state.value?.stamps ?? 0));
/** A full card seen while the page was hidden plays when it is shown again. */
let pendingWrap = false;

async function playWrap() {
  pendingWrap = false;
  if (reducedMotion.value || !active) {
    roll(coins.value);
    return;
  }
  hold++;
  try {
    wrapping.value = "flash";
    await wait(FLASH_MS);
    wrapping.value = "clear";
    await wait(CLEAR_MS);
    wrapping.value = "";
    if (card.value) await flyOne(card.value.querySelector(".stamps") ?? card.value, 0, -40);
  } finally {
    wrapping.value = "";
    release(active);
  }
}

// The balance follows the coins held, unless coins are on their way in. Stamps passing a multiple of the card
// size mean a coin was paid out for them, on the same save (signing in can switch to a save with more stamps).
watch(() => [coins.value, state.value?.stampsTotal, status.value?.player] as const, ([held, total, player], [, was, before]) => {
  const paid = total != null && was != null && player === before && Math.floor(total / PER) > Math.floor(was / PER);
  if (paid && !reducedMotion.value) {
    if (active) void playWrap();
    else pendingWrap = true;
    return;
  }
  if (!hold && !pendingWrap) roll(held);
});

onActivated(() => {
  active = true;
  if (pendingWrap) void playWrap();
  else if (!hold) roll(coins.value);
});
// Coins still flying when the page turns land at once; the balance is right when it comes back.
onDeactivated(() => {
  active = false;
  for (const a of ghosts) a.cancel();
});
onBeforeUnmount(() => {
  active = false;
  cancelAnimationFrame(rollFrame);
  for (const a of ghosts) a.cancel();
});

/** Each badge's name with the stamps toward it. */
const badgeTip = (i: number) => `${BADGES[i]} ${fmt(Math.min(stampsTotal.value, CFG.badges[i]))} / ${fmt(CFG.badges[i])}`;
</script>

<template>
  <section class="coins" aria-label="驼币">
    <div ref="sky" class="sky" aria-hidden="true"></div>
    <div class="stage">
      <div class="top" data-rise>
        <div class="wallet">
          <span ref="heroCoin" class="hero-coin">
            <span ref="spinner" class="spin"><ParkCoin fill sheen :tilt="false" /></span>
          </span>
          <div class="held">
            <p class="balance"><b>{{ fmt(shown) }}</b><span>驼币</span></p>
            <!-- Both lines keep their room while the park loads, so nothing jumps when it arrives. -->
            <p class="net" :class="{ up: net > 0, wait: !state }" :title="netTip">
              <span>今日</span><Icon name="shard" :size="14" /><b>{{ netText }}</b>
            </p>
          </div>
        </div>

        <div class="buy">
          <div class="packs" role="group" aria-label="买驼币">
            <button
              v-for="p in PACKS" :key="p.n" type="button" class="ui-btn pack"
              :class="{ primary: p.n === 1 && live1, pulse: p.n === 1 && live1 }"
              :disabled="outOfReach(p.n)" :aria-busy="busy === p.n" :aria-disabled="busy ? 'true' : undefined"
              :title="keyTip(p.n)" @click="buy(p.n, $event)"
            >
              <span class="pile"><CoinStack :count="p.pile" :size="32" :grey="outOfReach(p.n)" /></span>
              <span class="pack-n">{{ p.n }} 枚</span>
              <small class="pack-cost"><Icon name="shard" :size="11" />{{ fmt(p.n * CFG.price) }}</small>
            </button>
          </div>
          <p class="note" role="status">{{ note }}</p>
        </div>
      </div>

      <div ref="card" class="card" data-rise>
        <div class="stamps" :class="wrapping" :title="`${state?.stamps ?? 0} / ${PER}`">
          <Stamp v-for="i in PER" :key="i" :index="i" :empty="i > inked" :size="28" />
        </div>
        <div class="badges">
          <img
            v-for="(art, i) in BADGE_ART" :key="i" :src="art" :class="{ earned: i < badge }"
            :alt="BADGES[i]" :title="badgeTip(i)" draggable="false"
          />
        </div>
      </div>
    </div>

    <div class="park-actions">
      <RedeemForm />
    </div>
  </section>
</template>

<style scoped>
/* On the park's sheet, under the coral band: no side or bottom padding, so the bar sits at the sheet's foot. */
.coins {
  position: relative;
  display: flex;
  flex-direction: column;
}
.stage {
  flex: 1 0 auto;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 22px;
  padding: 22px 26px;
}
/* Coins in flight; above the page, under nothing that clips them but the body's scroll box. */
.sky {
  position: absolute;
  inset: 0;
  z-index: 3;
  overflow: hidden;
  pointer-events: none;
}

/* ---- the big coin and the coins held */
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px 24px;
}
.wallet {
  display: flex;
  align-items: center;
  gap: 20px;
  min-width: 0;
}
/* The coin is a thing: it leans and casts a shadow; under the pointer it straightens and lifts. */
.hero-coin {
  --size: 168px;
  flex: none;
  display: block;
  width: var(--size);
  height: var(--size);
  rotate: -8deg;
  transition: rotate var(--dur-slow) var(--ease-spring), translate var(--dur-slow) var(--ease-spring);
}
.hero-coin:hover {
  rotate: 0deg;
  translate: 0 -6px;
}
.spin {
  display: block;
  width: 100%;
  height: 100%;
}
.held {
  min-width: 0;
}
.balance {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0;
}
.balance b {
  font: 800 72px/0.9 var(--font-latin);
  color: var(--ink);
}
.balance span {
  font: 700 var(--fs-strong)/1 var(--font);
  color: var(--ink-2);
}
.net {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 10px 0 0;
  color: var(--ink-2);
}
.net span {
  margin-right: 4px;
  font: 700 var(--fs-label)/1 var(--font);
}
.net svg {
  color: var(--c-600);
}
.net b {
  font: 800 var(--fs-heading)/1 var(--font-latin);
}
.net.up b {
  color: var(--c-700);
}

/* ---- buying: three tall keys, and why not */
.buy {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}
.net.wait {
  visibility: hidden;
}
.packs {
  display: flex;
  gap: 12px;
  padding-bottom: 3px;
}
.pack {
  flex-direction: column;
  justify-content: flex-end;
  gap: 4px;
  width: 104px;
  height: 112px;
  padding: 10px 8px 12px;
}
.pile {
  flex: 1;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  margin-bottom: 2px;
}
.pack-n {
  font-size: var(--fs-number);
}
.pack-cost {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  letter-spacing: 0.02em;
  color: var(--ink-2);
}
.pack:disabled .pack-cost {
  color: var(--ink-3);
}
.note {
  min-height: 16px;
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--c-700);
}

/* ---- the stamp card: a tonal block, the stamps on the left and the badges they lead to on the right */
.card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 14px 24px;
  padding: 16px 22px;
  border-radius: var(--radius-m);
  background: var(--c-100);
}
.stamps {
  display: grid;
  grid-template-columns: repeat(10, 28px);
  gap: 10px 12px;
}
/* A full card: every stamp flashes at once, then the card clears. */
.stamps.flash :deep(.stamp) {
  animation: stamp-flash 420ms var(--ease-out);
}
.stamps.clear :deep(.stamp) {
  opacity: 0;
  scale: 0.6;
  transition: opacity 180ms var(--ease-in), scale 180ms var(--ease-in);
}
@keyframes stamp-flash {
  0% { scale: 1; filter: none; }
  40% { scale: 1.22; filter: brightness(1.25); }
  100% { scale: 1; filter: none; }
}
.badges {
  display: flex;
  align-items: center;
  gap: 14px;
}
.badges img {
  width: 52px;
  height: 52px;
  object-fit: contain;
  /* Not earned: the same badge in flat opaque grey, so silver and gold do not pass for earned metal. */
  filter: grayscale(1) contrast(0.55) brightness(1.18);
  user-select: none;
}
/* Earned: the badge in its metal, a die-cut sticker. */
.badges img.earned {
  filter: var(--sticker);
}

/* ---- reduced motion: nothing moves, the numbers just change */
.calm .hero-coin {
  transition: none;
}
.calm .hero-coin:hover {
  translate: none;
}

@container panel (max-width: 760px) {
  .stage {
    gap: 18px;
    padding: 18px 20px;
  }
  .top {
    flex-direction: column;
    align-items: stretch;
  }
  .hero-coin {
    --size: 120px;
  }
  .balance b {
    font-size: 60px;
  }
  .buy {
    align-items: stretch;
  }
  .pack {
    flex: 1;
    width: auto;
  }
  /* The badges stand in a column beside the stamps, as tall as the three rows. */
  .card {
    gap: 12px 16px;
    padding: 14px 18px;
  }
  .stamps {
    gap: 8px 6px;
  }
  .badges {
    flex-direction: column;
    gap: 5px;
  }
  .badges img {
    width: 30px;
    height: 30px;
  }
  .note:empty {
    display: none;
  }
}
@container panel (max-height: 560px) {
  .stage {
    gap: 12px;
    padding: 12px 16px 14px;
    justify-content: flex-start;
  }
  .hero-coin {
    --size: 96px;
  }
  .wallet {
    gap: 14px;
  }
  .balance b {
    font-size: 48px;
  }
  .net {
    margin-top: 6px;
  }
  .net b {
    font-size: var(--fs-section);
  }
  .buy {
    gap: 6px;
  }
  .pack {
    height: 84px;
    padding: 6px 8px 8px;
    gap: 2px;
  }
  .pile {
    zoom: 0.75;
  }
  .pack-n {
    font-size: var(--fs-strong);
  }
  .pack-cost {
    font-size: var(--fs-label);
  }
  .card {
    gap: 10px 16px;
    padding: 10px 12px;
  }
  .stamps {
    grid-template-columns: repeat(15, 28px);
    gap: 6px 4px;
    zoom: 0.8;
  }
  /* Two long rows leave no room beside them: the badges go in a row, beside or under the stamps. */
  .badges {
    flex-direction: row;
    gap: 8px;
  }
  .badges img {
    width: 32px;
    height: 32px;
  }
  .note:empty {
    display: none;
  }
}
</style>
