<script setup lang="ts">
// Full-panel reveal of a draw or a box. It covers the panel before the request goes out: the
// stores update as soon as a response lands, and the page underneath would give the result away.
import { computed, nextTick, onBeforeUnmount, onDeactivated, onMounted, ref } from "vue";
import { assetUrl } from "../asset";
import { cardLabel, TIER_LABEL } from "../cards";
import { dropLabel, getItem, RARITY_LABEL } from "../items";
import { getCard, type ManifestCard, type Rarity } from "../manifest";
import type { Drop } from "../net/api";
import ChestIcon from "../pet/ChestIcon.vue";
import { groupDrops, needsSummary, sortDrops, spotlightQueue } from "../reveal";
import { reducedMotion } from "../stores/theme";
import { takeFocus, trapTab } from "../ui/focus";
import ItemArt from "../ui/ItemArt.vue";
import CardBack from "./CardBack.vue";
import CardSpotlight from "./CardSpotlight.vue";

const props = defineProps<{
  kind: "card" | "box";
  /** Runs once the scene is up. null closes it, leaving the error to the page. */
  load: () => Promise<Drop[] | null>;
  /** Draws left for another round. */
  remaining?: number;
  tint?: Record<string, string>;
}>();
const emit = defineEmits<{ close: [] }>();

const CHARGE_MS = 760;
const FULL_ART_TIMEOUT_MS = 1500;

const phase = ref<"charge" | "spotlight" | "summary">("charge");
const drops = ref<Drop[]>([]);
const queue = ref<{ drop: Drop; card: ManifestCard; art: string }[]>([]);
const at = ref(0);
const settled = ref(false);
const opened = ref(false);
let skipping = false;
let alive = true;

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const cardOf = (d: Drop) => getCard(d.item.slice(5));

/** Full artwork when it decodes in time, otherwise the bundled thumbnail. */
async function artOf(card: ManifestCard): Promise<string> {
  const img = new Image();
  img.src = assetUrl(card.full);
  const timeout = wait(FULL_ART_TIMEOUT_MS).then(() => Promise.reject(new Error("timeout")));
  return Promise.race([img.decode(), timeout]).then(
    () => img.src,
    () => assetUrl(card.thumb),
  );
}

async function run() {
  phase.value = "charge";
  drops.value = [];
  queue.value = [];
  at.value = 0;
  opened.value = false;
  skipping = false;

  const [result] = await Promise.all([props.load(), wait(reducedMotion.value ? 0 : CHARGE_MS)]);
  if (!alive) return;
  if (!result?.length) {
    emit("close");
    return;
  }
  drops.value = sortDrops(result);
  opened.value = true;
  if (props.kind === "card") {
    const spot = spotlightQueue(result).flatMap((drop) => {
      const card = cardOf(drop);
      return card ? [{ drop, card }] : [];
    });
    const arts = await Promise.all(spot.map((s) => artOf(s.card)));
    if (!alive) return;
    queue.value = spot.map((s, i) => ({ ...s, art: arts[i]! }));
  }
  if (!queue.value.length || (skipping && needsSummary(drops.value))) {
    phase.value = "summary";
    return;
  }
  settled.value = skipping || reducedMotion.value;
  phase.value = "spotlight";
}

function finish() {
  if (props.remaining) void run();
  else emit("close");
}
function next() {
  if (at.value + 1 < queue.value.length) {
    at.value++;
    settled.value = reducedMotion.value;
  } else if (needsSummary(drops.value)) {
    phase.value = "summary";
  } else {
    finish();
  }
}
function skip() {
  if (phase.value === "charge") skipping = true;
  else if (needsSummary(drops.value)) phase.value = "summary";
  else settled.value = true;
}
function tap() {
  if (phase.value !== "spotlight") return;
  if (settled.value) next();
  else settled.value = true;
}

const action = computed(() => {
  if (!settled.value) return "跳过";
  if (at.value + 1 < queue.value.length) return "下一张";
  return needsSummary(drops.value) ? "查看全部" : "收下";
});

const root = ref<HTMLElement>();
let release: (() => void) | undefined;
function onKey(e: KeyboardEvent) {
  if (e.key === "Tab" && root.value) trapTab(root.value, e);
  if (e.key !== "Escape") return;
  const ending = phase.value === "summary" || (phase.value === "spotlight" && settled.value && !needsSummary(drops.value));
  if (ending) finish();
  else skip();
}
onMounted(async () => {
  window.addEventListener("keydown", onKey);
  void run();
  await nextTick();
  release = takeFocus(root.value);
});
onBeforeUnmount(() => {
  alive = false;
  window.removeEventListener("keydown", onKey);
  release?.();
});
// Teleported content stays behind when its page turns away (a desk shortcut can do that).
onDeactivated(() => emit("close"));

const shards = computed(() => drops.value.reduce((n, d) => n + d.shards, 0));
const heading = computed(() =>
  props.kind === "card" ? `本次抽卡获得 ${drops.value.length} 张` : `开出了 ${drops.value.length} 个表情`,
);
const cardResults = computed(() =>
  groupDrops(drops.value).flatMap((drop) => {
    const card = cardOf(drop);
    return card ? [{ drop, card, label: cardLabel(card) }] : [];
  }),
);
const boxResults = computed(() =>
  groupDrops(drops.value).flatMap((drop) => {
    const item = getItem(drop.item);
    return item ? [{ drop, item }] : [];
  }),
);
</script>

<template>
  <Teleport defer to=".panel-overlay">
    <div
      ref="root" class="scene" :class="phase" :style="tint" data-overlay
      role="dialog" aria-modal="true" :aria-label="kind === 'card' ? '抽卡结果' : '开箱结果'" tabindex="-1"
      @click="tap"
    >
      <div v-if="phase === 'charge'" class="charge">
        <i class="band one" aria-hidden="true"></i>
        <i class="band two" aria-hidden="true"></i>
        <div v-if="kind === 'card'" class="sealed"><div class="sealed-face ui-frame"><CardBack /></div></div>
        <div v-else class="chest" :class="{ open: opened }"><ChestIcon :size="168" :open="opened" /></div>
        <button type="button" class="ui-btn large act" @click="skip">跳过</button>
      </div>

      <template v-else-if="phase === 'spotlight'">
        <CardSpotlight
          :key="at" :drop="queue[at]!.drop" :card="queue[at]!.card" :art="queue[at]!.art"
          :settled="settled" @done="settled = true"
        />
        <span v-if="queue.length > 1" class="page"><b>{{ at + 1 }}</b> / {{ queue.length }}</span>
        <button type="button" class="ui-btn large act" @click.stop="settled ? next() : skip()">{{ action }}</button>
      </template>

      <section v-else class="summary-body" :class="{ calm: reducedMotion }">
        <header>
          <h3>{{ heading }}</h3>
          <span v-if="shards" class="shards">碎片 +{{ shards }}</span>
        </header>

        <div class="results ui-scroll" :class="kind">
          <template v-if="kind === 'card'">
            <article
              v-for="(r, i) in cardResults" :key="i" class="result" :class="r.card.tier"
              :style="{ '--i': Math.min(i, 14) }"
            >
              <span class="art ui-frame">
                <img :src="assetUrl(r.card.thumb)" :alt="r.card.name" draggable="false" />
                <i v-if="r.card.tier !== 'normal'" class="tier ui-tag" :class="{ gold: r.card.tier === 'big' }">{{ TIER_LABEL[r.card.tier] }}</i>
                <b v-if="r.drop.new" class="fresh ui-tag dark">NEW</b>
                <b v-if="r.drop.got > 1" class="got ui-tag dark">+{{ r.drop.got }}</b>
              </span>
              <b class="name">{{ r.label.title }}</b>
              <small>{{ r.label.who }} · ×{{ r.drop.count }}</small>
            </article>
          </template>
          <template v-else>
            <article
              v-for="(r, i) in boxResults" :key="i" class="result sticker ui-tile" :class="r.drop.rarity"
              :style="{ '--i': Math.min(i, 14) }"
            >
              <span class="ui-frame ui-well">
                <ItemArt :item="r.item" :size="84" />
                <b v-if="r.drop.new" class="fresh ui-tag dark">NEW</b>
                <b v-if="r.drop.got > 1" class="got ui-tag dark">+{{ r.drop.got }}</b>
              </span>
              <b class="name">{{ r.item.name }}</b>
              <small>{{ r.drop.new ? RARITY_LABEL[r.drop.rarity as Rarity] : dropLabel(r.item, false) }}<template v-if="r.drop.shards"> · 碎片 +{{ r.drop.shards }}</template></small>
            </article>
          </template>
        </div>

        <footer>
          <button type="button" class="ui-btn large primary" @click="finish">
            {{ remaining ? `收下并继续（剩余 ${remaining} 次）` : "收下" }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.scene {
  position: absolute;
  inset: 0;
  z-index: 40;
  overflow: hidden;
  outline: none;
  background: var(--accent);
  color: var(--on-accent);
  cursor: pointer;
  animation: scene-in var(--dur-base) var(--ease-out);
}
.scene.summary {
  background: var(--page);
  color: var(--ink);
  cursor: default;
}
@keyframes scene-in {
  from {
    transform: translateX(-100%) skewX(var(--skew));
  }
}

.act {
  position: absolute;
  right: 30px;
  bottom: 26px;
  z-index: 5;
}
.page {
  position: absolute;
  right: 34px;
  top: 24px;
  z-index: 5;
  font-size: var(--fs-body);
  font-weight: 800;
  color: var(--on-ink);
}
.page b {
  font: italic 800 var(--fs-title)/1 var(--font-latin);
}

.charge {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
}
.band {
  position: absolute;
  top: -10px;
  bottom: -10px;
  width: 26%;
  background: rgba(255, 255, 255, 0.16);
  transform: skewX(var(--skew));
  animation: band 1.5s linear infinite;
}
.band.two {
  width: 12%;
  animation-delay: -0.7s;
}
.sealed {
  position: relative;
  height: min(380px, 62cqh);
  aspect-ratio: 2 / 3;
  filter: drop-shadow(var(--drop-l) var(--ink));
  animation: charge 760ms var(--ease-in-out) infinite alternate;
}
.sealed-face {
  --cut: var(--cut-l);
  height: 100%;
  background: var(--surface);
}
.sealed-face :deep(.back) {
  inset: 6px;
}
.chest {
  filter: drop-shadow(var(--drop-m) rgba(var(--ink-rgb), 0.28));
  animation: shake 180ms linear infinite;
}
.chest.open {
  animation: pop var(--dur-slow) var(--ease-pop);
}
@keyframes band {
  from {
    left: -30%;
  }
  to {
    left: 110%;
  }
}
@keyframes charge {
  from {
    transform: scale(0.96);
  }
  to {
    transform: scale(1.03);
  }
}
@keyframes shake {
  0%, 100% {
    transform: rotate(0);
  }
  25% {
    transform: rotate(-5deg);
  }
  75% {
    transform: rotate(5deg);
  }
}
@keyframes pop {
  from {
    transform: scale(0.8);
  }
}

.summary-body {
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 26px 34px 22px;
}
header {
  flex: none;
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-bottom: 16px;
}
header h3 {
  margin: 0;
  font: 400 var(--fs-title)/1.15 var(--font-display);
}
.shards {
  font-size: var(--fs-strong);
  font-weight: 800;
  color: var(--accent-deep);
}
.results {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 148px));
  justify-content: center;
  align-content: start;
  gap: 14px 16px;
  padding: 2px 6px 8px 0;
}
.results.box {
  grid-template-columns: repeat(auto-fill, minmax(112px, 128px));
}
.result {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  text-align: center;
  animation: result-in var(--dur-stage) var(--ease-out) calc(var(--i) * 45ms) backwards;
}
.results.box .result {
  animation-name: fly-in;
  cursor: default;
}
.calm .result {
  animation: none;
}
.result .art {
  --cut: var(--cut-m);
  width: 100%;
  aspect-ratio: 2 / 3;
  background: var(--surface);
}
.result .art img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}
.result.small .art {
  --ring: var(--accent);
  padding: 3px;
  box-sizing: border-box;
  background: var(--accent);
}
.result.big .art {
  padding: 3px;
  box-sizing: border-box;
  background: linear-gradient(145deg, var(--gold-soft), var(--gold));
}
.tier {
  position: absolute;
  left: 7px;
  top: 6px;
}
.fresh {
  position: absolute;
  right: 8px;
  top: 6px;
  z-index: 1;
}
.got {
  position: absolute;
  left: 8px;
  bottom: 7px;
  z-index: 1;
}
.name {
  max-width: 100%;
  margin-top: 5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--fs-label);
  font-weight: 800;
}
.result small {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-2);
}
footer {
  flex: none;
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}
@keyframes result-in {
  from {
    opacity: 0;
    transform: perspective(700px) rotateY(70deg) translateY(10px);
  }
}
/* Stickers burst out of the chest at the middle of the scene. */
@keyframes fly-in {
  from {
    opacity: 0;
    transform: translate(calc(3 * (6px - var(--i) * 8px)), 120px) scale(0.3) rotate(-14deg);
  }
}
</style>
