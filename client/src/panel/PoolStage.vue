<script setup lang="ts">
// The draw view of one pool: a card on stage, every card of the pool to browse, and the draw console.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { assetUrl } from "../asset";
import { byTier, cardLabel, poolName, TIER_LABEL } from "../cards";
import type { ManifestCard, ManifestSeries } from "../manifest";
import { collection, online, presenceUpdatedAt, status, tickets } from "../stores/player";
import { reducedMotion } from "../stores/theme";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ series: ManifestSeries; cards: ManifestCard[]; busy: boolean }>();
defineEmits<{ inspect: [card: ManifestCard]; draw: [all: boolean] }>();

const LINEUP_SIZE = 6;

const owned = (c: ManifestCard) => collection.owned[`card:${c.id}`] ?? 0;
const sorted = computed(() => [...props.cards].sort(byTier));
const owner = computed(() => (props.series.name.includes(" · ") ? props.series.name.split(" · ")[0] : "A-SOUL"));

const activeId = ref("");
const page = ref(0);
watch(
  () => props.series.id,
  () => {
    activeId.value = sorted.value[0]?.id ?? "";
    page.value = 0;
  },
  { immediate: true },
);
const active = computed(() => props.cards.find((c) => c.id === activeId.value) ?? props.cards[0]!);
const label = computed(() => cardLabel(active.value));

const pageCount = computed(() => Math.ceil(sorted.value.length / LINEUP_SIZE));
const lineup = computed(() => sorted.value.slice(page.value * LINEUP_SIZE, (page.value + 1) * LINEUP_SIZE));
/** The side a lineup page slides in from: -1 left, 1 right. */
const slideFrom = ref(0);
function turn(to: number, from = Math.sign(to - page.value)) {
  slideFrom.value = reducedMotion.value ? 0 : from;
  page.value = (to + pageCount.value) % pageCount.value;
}

const PITY = 400;
const pity = computed(() => status.value?.draw?.pity ?? 0);

const clock = ref(Date.now());
const timer = setInterval(() => (clock.value = Date.now()), 1000);
onBeforeUnmount(() => clearInterval(timer));
const remaining = computed(() => {
  const draw = status.value?.draw;
  if (!draw) return 300;
  const elapsed =
    online.value && presenceUpdatedAt.value
      ? Math.min(20, Math.max(0, (clock.value - presenceUpdatedAt.value) / 1000))
      : 0;
  return Math.max(0, Math.ceil(draw.secondsPerDraw - draw.seconds - elapsed));
});
const countdown = computed(
  () => `${Math.floor(remaining.value / 60).toString().padStart(2, "0")}:${(remaining.value % 60).toString().padStart(2, "0")}`,
);
</script>

<template>
  <div class="pool">
    <section class="stage ui-frame ui-ring" :class="active.tier" data-rise>
      <button type="button" class="hero" :title="active.name" @click="$emit('inspect', active)">
        <span class="hero-rays" aria-hidden="true"></span>
        <span class="hero-frame ui-frame">
          <video
            v-if="active.video && !reducedMotion" :key="active.id" class="hero-media"
            :src="assetUrl(active.video)" :poster="assetUrl(active.thumb)" autoplay loop muted playsinline
          ></video>
          <img
            v-else :key="active.id" class="hero-media" :src="assetUrl(active.full)"
            :style="{ backgroundImage: `url(${assetUrl(active.thumb)})` }" :alt="active.name" draggable="false"
          />
          <i class="foil" aria-hidden="true"></i>
        </span>
      </button>

      <div class="info">
        <div class="title-block">
          <p class="owner">{{ owner }}</p>
          <h3>{{ poolName(series.name) }}</h3>
          <p class="now">
            <b>{{ label.title }}</b>
            <span><em class="tier">{{ TIER_LABEL[active.tier] }}</em>{{ label.who }}<template v-if="owned(active)"> · ×{{ owned(active) }}</template></span>
          </p>
        </div>

        <div class="lineup">
          <button v-if="pageCount > 1" type="button" class="flip prev" aria-label="上一页" @click="turn(page - 1, -1)">
            <Icon name="down" :size="20" />
          </button>
          <div :key="page" class="row" :style="{ '--from': `${slideFrom * 20}px` }">
            <button
              v-for="c in lineup" :key="c.id" type="button"
              class="mini" :class="[c.tier, { on: c.id === active.id }]"
              :title="c.name" :aria-pressed="c.id === active.id" @click="activeId = c.id"
            >
              <span class="ui-frame"><img :src="assetUrl(c.thumb)" :alt="c.name" draggable="false" /></span>
            </button>
          </div>
          <button v-if="pageCount > 1" type="button" class="flip next" aria-label="下一页" @click="turn(page + 1, 1)">
            <Icon name="down" :size="20" />
          </button>
          <div v-if="pageCount > 1" class="dots">
            <button
              v-for="n in pageCount" :key="n" type="button" :class="{ on: n - 1 === page }"
              :aria-label="`第 ${n} 页`" :aria-current="n - 1 === page ? 'page' : undefined" @click="turn(n - 1)"
            ></button>
          </div>
        </div>
      </div>
    </section>

    <footer class="console ui-frame ui-ring" data-rise>
      <div class="tickets">
        <span class="tickets-count"><b>{{ tickets }}</b>次可抽</span>
        <small v-if="online">下一抽 {{ countdown }}</small>
      </div>

      <div class="pity">
        <span>大隐藏保底 <b>{{ pity }}</b> / {{ PITY }}</span>
        <div class="ui-bar"><i :style="{ width: `${(pity / PITY) * 100}%` }"></i></div>
      </div>

      <div class="actions">
        <button type="button" class="ui-btn large" :disabled="busy || !online || !tickets" @click="$emit('draw', true)">
          全部抽取<template v-if="tickets > 1"> ×{{ tickets }}</template>
        </button>
        <button type="button" class="ui-btn large primary pulse" :disabled="busy || !online || !tickets" @click="$emit('draw', false)">抽一次</button>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* Orange is kept for the main action, the pity bar and the selection. */
.pool {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.stage {
  --radius: var(--radius-l);
  --mini-w: 62px;
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 24px;
  padding: 14px 16px 14px 18px;
  box-sizing: border-box;
  background: var(--surface);
}

.hero {
  position: relative;
  z-index: 1;
  flex: none;
  align-self: center;
  height: min(100%, 420px);
  aspect-ratio: 2 / 3;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  display: grid;
  place-items: center;
  filter: drop-shadow(0 6px 14px rgba(var(--ink-rgb), 0.18));
  transition: transform var(--dur-slow) var(--ease-out);
}
.hero:hover {
  transform: translateY(-3px);
}
.hero-frame {
  --radius: var(--radius-m);
  position: relative;
  width: 100%;
  height: 100%;
  padding: 4px;
  box-sizing: border-box;
  background: var(--surface);
  display: flex;
}
.big .hero-frame {
  background: var(--gold);
}
.hero-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  background: var(--accent-soft) center / cover no-repeat;
}
.foil {
  position: absolute;
  inset: -10%;
  background: linear-gradient(112deg, transparent 38%, rgba(255, 255, 255, 0.46) 48%, rgba(255, 224, 190, 0.28) 54%, transparent 64%);
  transform: translateX(-70%);
  pointer-events: none;
}
.big .foil,
.small .foil {
  animation: foil 4.2s var(--ease-in-out) infinite;
}
@keyframes foil {
  0%, 12% {
    transform: translateX(-70%);
  }
  55%, 100% {
    transform: translateX(70%);
  }
}
.hero-rays {
  position: absolute;
  width: 170%;
  aspect-ratio: 1;
  background: repeating-conic-gradient(transparent 0deg 12deg, var(--ray) 12deg 24deg);
  mask: radial-gradient(closest-side, #000 62%, transparent);
  -webkit-mask: radial-gradient(closest-side, #000 62%, transparent);
  opacity: 0;
  pointer-events: none;
}
.big .hero-rays {
  --ray: rgba(var(--gold-rgb), 0.16);
}
.small .hero-rays {
  --ray: rgba(var(--accent-rgb), 0.14);
}
.big .hero-rays,
.small .hero-rays {
  opacity: 1;
  animation: spin 18s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.info {
  position: relative;
  z-index: 1;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: var(--ink);
}
.title-block {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}
.owner {
  margin: 0 0 6px;
  font-size: var(--fs-strong);
  font-weight: 500;
  color: var(--ink-2);
}
h3 {
  margin: 0;
  font: 800 var(--fs-display)/1.15 var(--font);
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.now {
  margin: 20px 0 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-body);
  font-weight: 500;
  color: var(--ink-2);
}
.now b {
  font: 800 var(--fs-heading)/1.2 var(--font);
  color: var(--ink);
}
.tier {
  margin-right: 6px;
  font-style: normal;
}
.normal .tier::after {
  content: " ·";
}
.big .tier,
.small .tier {
  padding: 2px 7px;
  font-size: var(--fs-label);
  font-weight: 800;
  color: var(--ink);
}
.big .tier {
  background: var(--gold-soft);
}
.small .tier {
  background: var(--accent-soft);
}

.lineup {
  flex: none;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 3px 4px;
  padding: 10px 8px;
  background: var(--accent-tint);
}
.row {
  grid-column: 2;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, var(--mini-w)));
  justify-content: center;
  gap: 8px;
  animation: lineup var(--dur-slow) var(--ease-out);
}
@keyframes lineup {
  from {
    opacity: 0;
    transform: translateX(var(--from));
  }
}
.flip {
  width: 20px;
  height: 40px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--ink-2);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out), color var(--dur-fast);
}
.flip:hover {
  color: var(--ink);
}
.flip .icon {
  stroke-width: 3;
}
.prev {
  grid-column: 1;
}
.next {
  grid-column: 3;
}
.prev .icon {
  transform: rotate(90deg);
}
.next .icon {
  transform: rotate(-90deg);
}
.prev:hover {
  transform: translateX(-2px);
}
.next:hover {
  transform: translateX(2px);
}
.dots {
  grid-column: 1 / -1;
  grid-row: 2;
  justify-self: center;
  display: flex;
  align-items: center;
  gap: 7px;
  height: 10px;
}
.dots button {
  position: relative;
  width: 8px;
  height: 4px;
  padding: 0;
  border: 0;
  background: var(--line-2);
  cursor: pointer;
  transition: width var(--dur-base) var(--ease-out), background var(--dur-fast);
}
.dots button::before {
  content: "";
  position: absolute;
  inset: -6px -3px;
}
.dots .on {
  width: 22px;
  background: var(--grad-main);
}

.mini {
  --radius: var(--radius-s);
  position: relative;
  min-width: 0;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out);
}
.mini span {
  display: block;
  aspect-ratio: 2 / 3;
  padding: 3px;
  box-sizing: border-box;
  background: var(--surface);
}
.mini.big span {
  background: var(--gold);
}
.mini img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.mini:hover,
.mini.on {
  transform: translateY(-3px);
}
.mini.on::after {
  content: "";
  position: absolute;
  inset: -2px;
  border-radius: var(--radius-m);
  pointer-events: none;
  box-shadow: 0 0 0 2px var(--accent), var(--glow-m);
}

.console {
  --radius: var(--radius-m);
  flex: none;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 18px 12px 20px;
  background: var(--surface);
}
.tickets {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tickets-count {
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-size: var(--fs-body);
  font-weight: 500;
  color: var(--ink-2);
}
.tickets-count b {
  font: 800 var(--fs-title)/1 var(--font);
  color: var(--ink);
}
.tickets small {
  font-size: var(--fs-label);
  font-weight: 500;
  color: var(--ink-3);
}
.pity {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: var(--fs-label);
  font-weight: 500;
  color: var(--ink-2);
  white-space: nowrap;
}
.pity b {
  font-weight: 800;
  color: var(--ink);
}
.actions {
  flex: none;
  display: flex;
  gap: 10px;
}
.actions .ui-btn {
  padding: 0 20px;
  font-weight: 700;
}
.actions .primary {
  padding: 0 34px;
  font-size: var(--fs-number);
  font-weight: 800;
}

@container panel (max-height: 620px) {
  .stage {
    --mini-w: 46px;
  }
  h3 {
    font-size: var(--fs-title);
  }
  .owner {
    margin-bottom: 2px;
    font-size: var(--fs-body);
  }
  .now {
    margin-top: 8px;
    gap: 2px;
  }
  .now b {
    font-size: var(--fs-section);
  }
}
@container panel (max-height: 520px) {
  .stage {
    padding: 10px 14px;
    gap: 16px;
  }
  .console {
    padding: 8px 14px;
  }
  .actions .ui-btn {
    height: 36px;
    padding: 0 14px;
  }
}
</style>
