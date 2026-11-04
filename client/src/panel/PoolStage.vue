<script setup lang="ts">
// The draw view of one pool: its hidden cards on stage and the draw console below.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { assetUrl } from "../asset";
import { byTier, cardLabel, poolName, poolSkin, TIER_LABEL } from "../cards";
import type { ManifestCard, ManifestSeries } from "../manifest";
import { collection, online, presenceUpdatedAt, status, tickets } from "../stores/player";
import { reducedMotion } from "../stores/theme";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ series: ManifestSeries; cards: ManifestCard[]; busy: boolean }>();
defineEmits<{ inspect: [card: ManifestCard]; draw: [all: boolean] }>();

const owned = (c: ManifestCard) => collection.owned[`card:${c.id}`] ?? 0;
const hidden = computed(() => props.cards.filter((c) => c.tier !== "normal").sort(byTier));
const owner = computed(() => (props.series.name.includes(" · ") ? props.series.name.split(" · ")[0] : "A-SOUL"));

const activeId = ref("");
watch(() => props.series.id, () => (activeId.value = hidden.value[0]?.id ?? props.cards[0]?.id ?? ""), { immediate: true });
const active = computed(() => props.cards.find((c) => c.id === activeId.value) ?? props.cards[0]!);
const activeOwned = computed(() => owned(active.value) > 0);
const label = computed(() => cardLabel(active.value));

const skin = computed(() => poolSkin(props.series.id));

// The old pool's color slides off along the slant, uncovering the new one.
const wipe = ref({ n: 0, color: "" });
watch(() => props.series.id, (_, old) => {
  if (!reducedMotion.value) wipe.value = { n: wipe.value.n + 1, color: poolSkin(old).accent };
});

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
      <i class="halftone" aria-hidden="true"></i>
      <i class="stripe" aria-hidden="true"></i>
      <div v-if="skin.mascots.length" class="mascots" aria-hidden="true">
        <img v-for="m in skin.mascots" :key="m" :src="assetUrl(m)" alt="" draggable="false" />
      </div>

      <button type="button" class="hero" :title="active.name" @click="$emit('inspect', active)">
        <span class="hero-rays" aria-hidden="true"></span>
        <span class="hero-frame ui-frame">
          <video
            v-if="activeOwned && active.video" :key="active.id" class="hero-media"
            :src="assetUrl(active.video)" :poster="assetUrl(active.thumb)" autoplay loop muted playsinline
          ></video>
          <img
            v-else class="hero-media" :class="{ locked: !activeOwned }"
            :src="assetUrl(activeOwned ? active.full : active.thumb)" :alt="active.name" draggable="false"
          />
          <i class="foil" aria-hidden="true"></i>
        </span>
      </button>

      <div class="info">
        <p class="owner">{{ owner }}</p>
        <h3>{{ poolName(series.name) }}</h3>

        <div class="now">
          <span class="ui-tag" :class="{ gold: active.tier === 'big', light: active.tier === 'small', dark: active.tier === 'normal' }">{{ TIER_LABEL[active.tier] }}</span>
          <b>{{ label.title }}</b>
          <small>{{ label.who }}<template v-if="activeOwned"> · ×{{ owned(active) }}</template></small>
        </div>

        <div v-if="hidden.length > 1" class="lineup">
          <button
            v-for="c in hidden" :key="c.id" type="button"
            class="mini ui-frame" :class="[c.tier, { on: c.id === active.id, missing: !owned(c) }]"
            :title="c.name" :aria-pressed="c.id === active.id" @click="activeId = c.id"
          >
            <img :src="assetUrl(c.thumb)" :alt="c.name" draggable="false" />
          </button>
        </div>
      </div>

      <i v-if="wipe.n" :key="wipe.n" class="wipe" :style="{ background: wipe.color }" aria-hidden="true"></i>
    </section>

    <footer class="console ui-frame ui-ring" data-rise>
      <div class="tickets">
        <span class="tickets-icon"><Icon name="card" :size="18" /></span>
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
        <button type="button" class="ui-btn large primary" :disabled="busy || !online || !tickets" @click="$emit('draw', true)">
          全部抽取<span v-if="tickets > 1">×{{ tickets }}</span>
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
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 26px;
  padding: 14px 24px 14px 20px;
  box-sizing: border-box;
  background: var(--accent);
}
.halftone {
  position: absolute;
  inset: auto 0 0;
  height: 140px;
  background: var(--surface);
  opacity: 0.34;
  mask: var(--halftone) left bottom / 280px auto repeat-x;
  -webkit-mask: var(--halftone) left bottom / 280px auto repeat-x;
}
.stripe {
  position: absolute;
  top: -10px;
  bottom: -10px;
  right: 22%;
  width: 150px;
  background: rgba(255, 255, 255, 0.2);
  transform: skewX(var(--skew));
}

.mascots {
  position: absolute;
  right: 14px;
  top: 10px;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  pointer-events: none;
}
.mascots img {
  width: 104px;
  height: auto;
  display: block;
  filter: var(--sticker);
  rotate: -6deg;
}
.mascots img + img {
  width: 84px;
  margin: 26px 0 0 -18px;
  rotate: 8deg;
}
.wipe {
  position: absolute;
  inset: -2px -14%;
  z-index: 4;
  pointer-events: none;
  transform: skewX(var(--skew)) translateX(112%);
  animation: wipe var(--dur-stage) var(--ease-in-out) backwards;
}
@keyframes wipe {
  from {
    transform: skewX(var(--skew)) translateX(0);
  }
}

.hero {
  position: relative;
  z-index: 1;
  flex: none;
  height: 100%;
  aspect-ratio: 2 / 3;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: transform var(--dur-slow) var(--ease-out);
}
.hero:hover {
  transform: translate(-2px, -3px);
}
.hero-frame {
  --cut: var(--cut-m);
  width: 100%;
  height: 100%;
  padding: 4px;
  box-sizing: border-box;
  background: var(--surface);
  display: flex;
}
.big .hero-frame {
  background: linear-gradient(145deg, var(--gold-soft), var(--gold));
}
.hero-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  background: var(--accent-soft);
}
.hero-media.locked {
  filter: grayscale(1);
  transition: filter var(--dur-base);
}
.hero:hover .hero-media.locked {
  filter: none;
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
.hero-frame {
  position: relative;
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
  color: var(--on-accent);
}
.owner {
  margin: 8px 0 2px;
  font-size: var(--fs-strong);
  font-weight: 800;
}
h3 {
  margin: 0;
  font: var(--fs-display)/1.15 var(--font-display);
}
.now {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}
.now b {
  font: var(--fs-heading)/1.2 var(--font-display);
}
.now small {
  font-size: var(--fs-body);
  font-weight: 700;
}
.lineup {
  margin-top: auto;
  display: flex;
  gap: 8px;
  padding-bottom: 6px;
}
.mini {
  --cut: var(--cut-s);
  flex: 0 1 62px;
  min-width: 0;
  aspect-ratio: 2 / 3;
  padding: 3px;
  box-sizing: border-box;
  border: 0;
  background: var(--surface);
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out), background var(--dur-fast);
}
.mini img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.mini.missing img {
  filter: grayscale(1);
  transition: filter var(--dur-base);
}
.mini.missing:hover img {
  filter: none;
}
.mini.big {
  background: linear-gradient(145deg, var(--gold-soft), var(--gold));
}
.mini:hover {
  transform: translateY(-3px);
}
.mini.on {
  background: var(--ink);
  transform: translateY(-3px);
}

.console {
  --cut: var(--cut-m);
  flex: none;
  display: flex;
  align-items: center;
  gap: 20px;
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
  width: 38px;
  height: 36px;
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
  color: var(--ink);
}
.tickets small {
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-3);
}
.pity {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
  white-space: nowrap;
}
.pity b {
  font: italic 800 var(--fs-section)/1 var(--font-latin);
  color: var(--accent-deep);
}
.actions {
  flex: none;
  display: flex;
  gap: 12px;
  padding-right: 4px;
}
.actions .one {
  padding: 0 18px;
}
.actions span {
  margin-left: 2px;
  font: italic 800 var(--fs-section)/1 var(--font-latin);
}

@container panel (max-height: 620px) {
  h3 {
    font-size: var(--fs-title);
  }
  .owner {
    margin-top: 0;
  }
  .now {
    margin-top: 8px;
  }
  .now b {
    font-size: var(--fs-section);
  }
  .mini {
    flex-basis: 46px;
  }
  .mascots img {
    width: 84px;
  }
  .mascots img + img {
    display: none;
  }
}
@container panel (max-height: 520px) {
  .mascots {
    display: none;
  }
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
