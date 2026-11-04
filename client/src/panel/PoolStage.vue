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
    <section class="stage ui-frame" :class="active.tier" data-rise>
      <i class="stripe" aria-hidden="true"></i>
      <i class="band" aria-hidden="true"></i>

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
          <div class="now">
            <span class="ui-tag" :class="{ gold: active.tier === 'big', light: active.tier === 'small', dark: active.tier === 'normal' }">{{ TIER_LABEL[active.tier] }}</span>
            <p>
              <b>{{ label.title }}</b>
              <span>{{ label.who }}<template v-if="owned(active)"> · ×{{ owned(active) }}</template></span>
            </p>
            <i class="rule" aria-hidden="true"></i>
          </div>
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
        <span class="tickets-icon"><Icon name="card" :size="20" /></span>
        <div>
          <span class="tickets-count"><b>{{ tickets }}</b>次可抽</span>
          <small v-if="online">下一抽 {{ countdown }}</small>
        </div>
      </div>

      <div class="pity">
        <span>大隐藏保底 <b>{{ pity }}</b> / {{ PITY }}</span>
        <div class="ui-bar"><i :style="{ width: `${(pity / PITY) * 100}%` }"></i></div>
      </div>

      <div class="actions">
        <button type="button" class="ui-btn large one" :disabled="busy || !online || !tickets" @click="$emit('draw', false)">抽一次</button>
        <button type="button" class="ui-btn large primary all" :disabled="busy || !online || !tickets" @click="$emit('draw', true)">
          <Icon name="spark" :size="13" class="glint" />
          全部抽取<span v-if="tickets > 1">×{{ tickets }}</span>
          <Icon name="spark" :size="10" class="glint" />
        </button>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.pool {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.stage {
  --cut: var(--cut-l);
  --band-h: 128px;
  --mini-w: 62px;
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 24px;
  padding: 14px 24px 12px 22px;
  box-sizing: border-box;
  background: var(--accent-mid);
}
.stripe {
  position: absolute;
  top: -10px;
  bottom: -10px;
  right: 16%;
  width: 150px;
  background: rgba(255, 255, 255, 0.2);
  transform: skewX(var(--skew));
}
/* The lineup rests on this band; its slanted end disappears behind the hero. */
.band {
  position: absolute;
  left: 18%;
  right: -40px;
  bottom: 0;
  height: var(--band-h);
  background: var(--accent);
  transform: skewX(var(--skew));
}

.hero {
  position: relative;
  z-index: 1;
  flex: none;
  align-self: center;
  height: min(100%, 396px);
  aspect-ratio: 2 / 3;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: transform var(--dur-slow) var(--ease-out);
}
/* A sheet peeking out behind the card. */
.hero::before {
  content: "";
  position: absolute;
  inset: 7px -9px -7px 9px;
  background: rgba(255, 255, 255, 0.36);
  rotate: 1.6deg;
}
.hero:hover {
  transform: translate(-2px, -3px);
}
.hero-frame {
  --cut: var(--cut-m);
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
  background: repeating-conic-gradient(rgba(255, 255, 255, 0) 0deg 12deg, rgba(255, 255, 255, 0.22) 12deg 24deg);
  mask: radial-gradient(closest-side, #000 62%, transparent);
  -webkit-mask: radial-gradient(closest-side, #000 62%, transparent);
  opacity: 0;
  pointer-events: none;
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
  color: var(--ink);
}
.title-block {
  flex: 1;
  min-height: 0;
  padding-bottom: 14px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.owner {
  margin: 0 0 2px;
  font: italic 800 var(--fs-section)/1.1 var(--font-latin);
  letter-spacing: 0.04em;
}
h3 {
  margin: 0;
  font: var(--fs-display)/1.15 var(--font-display);
  white-space: nowrap;
}
.now {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}
.now .ui-tag {
  padding: 0 11px;
  font-size: var(--fs-label);
  line-height: 21px;
}
.now p {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 10px;
}
.now b {
  font: var(--fs-heading)/1.2 var(--font-display);
}
.now p span {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: var(--fs-strong);
  font-weight: 800;
}
.now p span::before {
  content: "";
  width: 2px;
  height: 15px;
  background: var(--ink);
  transform: skewX(var(--skew));
}
.rule {
  width: 190px;
  max-width: 100%;
  height: 6px;
  margin-top: 2px;
  background: repeating-linear-gradient(98deg, var(--ink) 0 2px, transparent 2px 6px);
}

.lineup {
  flex: none;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 3px 4px;
  margin-right: -14px;
}
.row {
  grid-column: 2;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, var(--mini-w)));
  justify-content: start;
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
  color: var(--on-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out);
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
  height: 6px;
  padding: 0;
  border: 0;
  background: rgba(255, 255, 255, 0.62);
  cursor: pointer;
  transform: skewX(var(--skew));
  transition: width var(--dur-base) var(--ease-out), background var(--dur-fast);
}
.dots button::before {
  content: "";
  position: absolute;
  inset: -6px -3px;
}
.dots .on {
  width: 22px;
  background: var(--surface);
}

.mini {
  --cut: var(--cut-s);
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
/* Corner brackets: eight bars drawn as background layers. */
.mini.on::after {
  --bar: linear-gradient(var(--ink), var(--ink));
  --long: 13px;
  --thick: 2.5px;
  content: "";
  position: absolute;
  inset: -4px;
  pointer-events: none;
  background:
    var(--bar) 0 0 / var(--long) var(--thick),
    var(--bar) 0 0 / var(--thick) var(--long),
    var(--bar) 100% 0 / var(--long) var(--thick),
    var(--bar) 100% 0 / var(--thick) var(--long),
    var(--bar) 0 100% / var(--long) var(--thick),
    var(--bar) 0 100% / var(--thick) var(--long),
    var(--bar) 100% 100% / var(--long) var(--thick),
    var(--bar) 100% 100% / var(--thick) var(--long);
  background-repeat: no-repeat;
}

.console {
  --cut: var(--cut-m);
  flex: none;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 12px 18px 12px 14px;
  background: var(--surface);
}
.tickets {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
}
.tickets-icon {
  width: 44px;
  height: 42px;
  background: var(--accent);
  color: var(--on-accent);
  transform: skewX(var(--skew));
  display: flex;
  align-items: center;
  justify-content: center;
}
.tickets > div {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.tickets-count {
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.tickets-count b {
  margin-right: 3px;
  font: italic 800 var(--fs-title)/1 var(--font-latin);
  color: var(--accent-deep);
}
.tickets small {
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-3);
}
.pity {
  position: relative;
  flex: 1;
  min-width: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
  white-space: nowrap;
}
.pity::before {
  content: "";
  position: absolute;
  left: 0;
  top: 2px;
  bottom: 2px;
  width: 2px;
  background: var(--line-2);
  transform: skewX(var(--skew));
}
.pity b {
  font: italic 800 var(--fs-heading)/1 var(--font-latin);
  color: var(--accent-deep);
}
.actions {
  flex: none;
  display: flex;
  gap: 12px;
  padding-right: 4px;
}
.actions .ui-btn {
  font: 400 var(--fs-section)/1 var(--font-display);
}
.actions .one {
  padding: 0 18px;
}
.actions span {
  margin-left: 2px;
  font: italic 800 var(--fs-section)/1 var(--font-latin);
}
.glint {
  position: absolute;
  left: 9px;
  top: 6px;
  color: var(--surface);
  fill: currentColor;
}
.glint:last-child {
  left: auto;
  right: 9px;
  top: auto;
  bottom: 6px;
}
.all:disabled .glint {
  display: none;
}

@container panel (max-height: 620px) {
  .stage {
    --band-h: 96px;
    --mini-w: 46px;
  }
  h3 {
    font-size: var(--fs-title);
  }
  .owner {
    font-size: var(--fs-strong);
  }
  .now {
    margin-top: 6px;
    gap: 5px;
  }
  .now b {
    font-size: var(--fs-section);
  }
  .rule {
    display: none;
  }
  .title-block {
    padding-bottom: 6px;
  }
}
@container panel (max-height: 520px) {
  .stage {
    padding: 10px 18px 10px 14px;
    gap: 16px;
  }
  .console {
    padding: 8px 14px 8px 12px;
  }
  .actions .ui-btn {
    height: 36px;
    padding: 0 14px;
  }
}
</style>
