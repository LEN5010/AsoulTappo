<script setup lang="ts">
// The photocards' side of the resonance page's bar: the two promises toward a signed card (or the bags of a box that
// waits to be opened), the boxes left today, and the key that buys a box or goes on with one.
import { computed, shallowRef, watch } from "vue";
import { formatCount, nextTapText, todayIncome } from "../../income";
import { photoBuying, photoLeft, photoView } from "../../stores/photocards";
import { online, shards, status } from "../../stores/player";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import { photoBusy } from "./shop";

const props = defineProps<{ series: string; busy: boolean; now: number }>();
const emit = defineEmits<{ buy: []; resume: []; swap: []; odds: []; album: [] }>();

const live = computed(() => ({ view: photoView(props.series), left: photoLeft(props.series, props.now), shards: shards.value }));
/** What the bar shows: while a box is on its way to the table, as things were before it. */
const shown = shallowRef(live.value);
watch([live, photoBusy], () => { if (!photoBusy.value) shown.value = live.value; }, { flush: "sync" });
const view = computed(() => shown.value.view);
const left = computed(() => shown.value.left);
const cfg = computed(() => view.value.cfg);
const bags = computed(() => view.value.box?.cards.length ?? 0);
const short = computed(() => (cfg.value ? Math.max(0, cfg.value.price - shown.value.shards) : 0));
const income = computed(() => todayIncome(status.value));

/** What the key does, in the order it matters. */
const key = computed(() => {
  if (view.value.opening) return "resume";
  if (!cfg.value || !cfg.value.daily) return "gone";
  if (left.value === 0) return "out";
  return short.value ? "short" : "buy";
});
const label = computed(() => ({
  resume: view.value.opened ? "继续拆" : "开盒", gone: "已停售", out: "今日已买满", short: "买一盒", buy: "买一盒",
})[key.value]);
const ready = computed(() => !props.busy && !photoBuying.value && (key.value === "resume"
  || (key.value === "buy" && online.value && left.value !== null)));
const press = () => { if (key.value === "resume") emit("resume"); else emit("buy"); };

const PITY_NEAR = 1;
const pity = computed(() => {
  const c = cfg.value;
  const left = view.value.pity;
  if (!c || left === null) return null;
  const count = c.signPity - left;
  return { left, count, hard: c.signPity, percent: (count / c.signPity) * 100, near: left <= PITY_NEAR };
});
const swap = computed(() => {
  const c = cfg.value;
  if (!c || !view.value.save || view.value.signsWhole) return null;
  const n = view.value.spare;
  return { n, of: c.swap, percent: Math.min(100, (n / c.swap) * 100), ready: view.value.canSwap };
});
</script>

<template>
  <div class="photo-bar" :class="{ calm: reducedMotion }">
    <div class="gauges">
      <div v-if="view.opening" class="gauge bags">
        <span><Icon name="box" :size="14" />已拆<b>{{ view.opened }}</b><i>/ {{ bags }}</i></span>
        <div class="cells" :style="{ '--n': bags }"><i v-for="k in bags" :key="k" :class="{ on: k <= view.opened }"></i></div>
      </div>
      <div v-else-if="pity" class="gauge sign" :class="{ near: pity.near }" :title="`剩余 ${pity.left} 盒保底`">
        <span>
          <Icon name="pencil" :size="14" />签名保底<em v-if="pity.near" class="near-tag">即将</em><b>{{ pity.count }}</b><i>/ {{ pity.hard }}</i>
        </span>
        <div class="ui-bar"><i :style="{ width: `${pity.percent}%` }"></i></div>
      </div>
      <div v-if="swap" class="gauge swap" :class="{ full: swap.ready }">
        <span><Icon name="swap" :size="14" />换签名<b>{{ swap.n }}</b><i>/ {{ swap.of }}</i></span>
        <div class="ui-bar"><i :style="{ width: `${swap.percent}%` }"></i></div>
      </div>
      <p v-if="!view.opening && !pity && !swap && view.save" class="whole"><Icon name="check" :size="14" />签名已集齐</p>
    </div>

    <div class="supply">
      <p v-if="left !== null && key !== 'gone'" class="left-line">
        <span>今日可买</span><b :class="{ empty: !left }">{{ left }}</b><span>盒</span>
      </p>
      <p v-if="key === 'short'" class="today short" :title="income ? nextTapText(income) : undefined">
        <Icon name="shard" :size="13" />还差<b>{{ formatCount(short) }}</b>碎片
      </p>
      <p v-else-if="income" class="today" :title="nextTapText(income)">
        <Icon name="shard" :size="13" />今日已获得<b>{{ formatCount(income.today) }}</b>
      </p>
    </div>

    <div class="keys">
      <button
        v-if="swap?.ready" type="button" class="ui-btn large swap-key" :class="{ pulse: !reducedMotion }"
        :disabled="busy || !online" @click="emit('swap')"
      >
        <span class="act-label">换签名</span>
        <small class="act-cost">{{ swap.of }} 张</small>
      </button>
      <button
        type="button" class="ui-btn act primary main" :class="{ pulse: ready && !reducedMotion }" :disabled="!ready"
        @click="press"
      >
        <span class="act-label">{{ label }}</span>
        <small v-if="key === 'resume'" class="act-cost">{{ view.opened }} / {{ bags }}</small>
        <small v-else-if="cfg && key !== 'gone'" class="act-cost"><Icon name="shard" :size="11" />{{ formatCount(cfg.price) }}</small>
      </button>
      <span class="side-keys">
        <button type="button" class="ui-btn ghost small side-key" title="概率" aria-label="概率" :disabled="busy || !cfg" @click="emit('odds')">
          <Icon name="info" :size="16" />
        </button>
        <button type="button" class="ui-btn ghost small side-key" title="卡册" aria-label="卡册" :disabled="busy" @click="emit('album')">
          <Icon name="book" :size="16" />
        </button>
      </span>
    </div>
  </div>
</template>

<style scoped>
/* The measures of the resonance page's bar (ResonancePage.vue). */
.photo-bar {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 18px;
}
.gauges {
  flex: 0 1 190px;
  min-width: 0;
  min-height: 56px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}
.gauge {
  --near-glow: rgba(var(--gold-rgb), 0.72);
  min-width: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.gauge span {
  display: flex;
  align-items: baseline;
  gap: 4px;
  white-space: nowrap;
}
.gauge svg {
  align-self: center;
  color: var(--c-700);
}
.gauge b {
  margin-left: auto;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.gauge span i {
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.gauge .ui-bar {
  height: 6px;
  margin-top: 4px;
}
.sign svg,
.swap.full svg {
  color: var(--gold);
}
.sign .ui-bar > i,
.swap.full .ui-bar > i {
  background: var(--grad-gold);
}
.near-tag {
  padding: 1px 5px;
  border-radius: 4px;
  background: color-mix(in oklab, var(--gold-soft) 55%, var(--surface));
  color: var(--ink);
  font: 800 10px/1.2 var(--font);
  font-style: normal;
}
.gauge.near b {
  color: color-mix(in oklab, var(--gold) 65%, var(--ink));
}
.gauge.near .ui-bar,
.swap.full .ui-bar {
  overflow: visible;
}
.gauge.near .ui-bar > i,
.swap.full .ui-bar > i {
  position: relative;
  box-shadow: 0 0 10px 1px var(--near-glow);
  animation: near-breathe 2.8s var(--ease-in-out) infinite;
}
.calm .gauge .ui-bar > i {
  animation: none;
}
@keyframes near-breathe {
  50% { box-shadow: 0 0 4px 0 color-mix(in srgb, var(--near-glow) 45%, transparent); }
}
/* A cell a bag: what is open is filled. */
.cells {
  display: flex;
  gap: 2px;
  margin-top: 5px;
}
.cells i {
  flex: 1 1 0;
  height: 7px;
  border-radius: 2px;
  background: var(--c-100);
}
.cells i.on {
  background: var(--c-500);
}
.whole {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 0;
  font-size: var(--fs-body);
  font-weight: 800;
  color: var(--c-700);
}
.supply {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.supply p {
  display: flex;
  align-items: baseline;
  gap: 5px;
  margin: 0;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink-2);
  white-space: nowrap;
}
.left-line b {
  font: 800 26px/1 var(--font-latin);
  color: var(--c-700);
}
.left-line b.empty {
  color: var(--ink-3);
}
.supply .today {
  gap: 4px;
  font-size: var(--fs-label);
}
.supply .today svg {
  align-self: center;
  color: var(--c-700);
}
.supply .today b {
  margin-left: 2px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.supply .today.short,
.supply .today.short svg {
  color: var(--ink-3);
}
.supply .today.short b {
  color: var(--ink-2);
}
.keys {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 4px;
}
.act,
.swap-key {
  flex-direction: column;
  gap: 3px;
}
.swap-key {
  min-width: 104px;
}
.main {
  height: 60px;
  min-width: clamp(160px, 22cqw, 230px);
  padding: 0 26px;
  font-size: 18px;
}
.main:not(:disabled) {
  --key-lip-h: 4px;
}
.main:not(:disabled):active {
  --key-y: 4px;
  --key-lip-h: 0px;
}
.main:not(:disabled)::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.38);
  pointer-events: none;
}
.act-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.act-cost {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-label)/1 var(--font-latin);
  letter-spacing: 0.04em;
  opacity: 0.78;
}
.main:not(:disabled) .act-cost svg {
  color: var(--c-800);
  fill: rgba(255, 255, 255, 0.42);
}
.side-keys {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.side-key {
  width: 28px;
  padding: 0;
}
@container panel (max-width: 920px) {
  .photo-bar {
    gap: 14px;
  }
  .gauges {
    flex: 0 1 162px;
  }
  .main {
    min-width: 148px;
    padding: 0 20px;
  }
}
@container panel (max-width: 820px) {
  .photo-bar {
    gap: 12px;
  }
  .gauges {
    flex: 0 1 152px;
  }
  .supply .today {
    display: none;
  }
}
@container panel (max-width: 720px) {
  .photo-bar {
    gap: 8px;
  }
  .supply {
    display: none;
  }
  .gauges {
    flex: 1 1 auto;
  }
  .keys {
    gap: 6px;
  }
  .main {
    min-width: 0;
  }
}
@container panel (max-height: 600px) {
  .main {
    height: 52px;
  }
  .side-keys {
    gap: 0;
  }
}
</style>
