<script setup lang="ts">
// Full-panel reveal of every draw result. It covers the panel before the request goes out: the
// stores update as soon as a response lands, and the page underneath would give the result away.
import { computed, nextTick, onBeforeUnmount, onDeactivated, onMounted, ref } from "vue";
import { getCharacter } from "../characters";
import { assetUrl } from "../asset";
import { cardLabel, TIER_LABEL } from "../cards";
import { dropLabel, getItem, RARITY_LABEL } from "../items";
import { getCard, type ManifestCard, type Rarity } from "../manifest";
import type { Drop } from "../net/api";
import { groupDrops, needsSummary, nextRevealIndex, sortDrops, spotlightQueue } from "../reveal";
import { reducedMotion } from "../stores/theme";
import { takeFocus, trapTab } from "../ui/focus";
import ItemArt from "../ui/ItemArt.vue";
import CardBack from "./CardBack.vue";
import CardSpotlight from "./CardSpotlight.vue";
import SkinSpotlight from "./SkinSpotlight.vue";
import EmoteSpotlight from "./EmoteSpotlight.vue";

const props = defineProps<{
  /** Runs once the scene is up. null closes it, leaving the error to the page. */
  load: () => Promise<Drop[] | null>;
  /** Draws left for another round. */
  remaining?: number;
}>();
const emit = defineEmits<{ close: [] }>();

const CHARGE_MS = 760;
const FULL_ART_TIMEOUT_MS = 1500;

const phase = ref<"charge" | "spotlight" | "summary">("charge");
const drops = ref<Drop[]>([]);
const queue = ref<{ drop: Drop; card?: ManifestCard; art: string }[]>([]);
const at = ref(0);
const settled = ref(false);
const skipping = ref(false);
let alive = true;

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const cardOf = (d: Drop) => d.item.startsWith("card:") ? getCard(d.item.slice(5)) : undefined;

/** Full artwork when it decodes in time, otherwise the bundled thumbnail. */
async function artOf(card: ManifestCard): Promise<string> {
  if (card.video) return assetUrl(card.thumb);
  const img = new Image();
  img.src = assetUrl(card.full);
  const timeout = wait(FULL_ART_TIMEOUT_MS).then(() => Promise.reject(new Error("timeout")));
  return Promise.race([img.decode(), timeout]).then(
    () => img.src,
    () => assetUrl(card.thumb),
  );
}

function prepareArt(index: number) {
  const entry = queue.value[index];
  if (entry?.card) void artOf(entry.card).then((art) => { entry.art = art; });
}

async function run() {
  phase.value = "charge";
  drops.value = [];
  queue.value = [];
  at.value = 0;

  const [result] = await Promise.all([props.load(), wait(reducedMotion.value ? 0 : CHARGE_MS)]);
  if (!alive) return;
  if (!result?.length) {
    emit("close");
    return;
  }
  drops.value = sortDrops(result);
  const spot = spotlightQueue(result).map((drop) => ({ drop, card: cardOf(drop) }));
  queue.value = spot.map((s) => ({ ...s, art: s.card ? assetUrl(s.card.thumb) : "" }));
  const first = nextRevealIndex(result, 0, skipping.value);
  if (first < 0) {
    phase.value = "summary";
    return;
  }
  at.value = first;
  settled.value = reducedMotion.value;
  phase.value = "spotlight";
  prepareArt(first);
  prepareArt(first + 1);
}

function finish() {
  if (props.remaining) void run();
  else emit("close");
}
function next() {
  const index = nextRevealIndex(queue.value.map((entry) => entry.drop), at.value + 1, skipping.value);
  if (index >= 0) {
    at.value = index;
    settled.value = reducedMotion.value;
    prepareArt(index);
    prepareArt(at.value + 1);
  } else if (needsSummary(drops.value)) {
    phase.value = "summary";
  } else {
    finish();
  }
}
function skip() {
  skipping.value = true;
  if (phase.value !== "spotlight") return;
  const drops = queue.value.map((entry) => entry.drop);
  // Keep the current special reveal intact; later clicks advance after it settles.
  if (nextRevealIndex(drops, at.value, true) === at.value) {
    if (settled.value) next();
    return;
  }
  next();
}
function tap() {
  if (phase.value !== "spotlight") return;
  if (skipping.value && !settled.value) return;
  if (settled.value) next();
  else settled.value = true;
}

const action = computed(() => {
  if (!settled.value) return "翻开";
  if (at.value + 1 < queue.value.length) return "下一件";
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
const heading = computed(() => `本次共鸣获得 ${drops.value.length} 件`);
const results = computed(() => groupDrops(drops.value).flatMap((drop) => {
  const item = getItem(drop.item);
  const card = cardOf(drop);
  return item ? [{ drop, item, card, label: card ? cardLabel(card) : null }] : [];
}));
</script>

<template>
  <Teleport defer to=".panel-overlay">
    <div
      ref="root" class="scene" :class="phase" data-overlay
      role="dialog" aria-modal="true" aria-label="共鸣结果" tabindex="-1"
      @click="tap"
    >
      <div v-if="phase === 'charge'" class="charge">
        <i class="band one" aria-hidden="true"></i>
        <i class="band two" aria-hidden="true"></i>
        <div class="sealed"><div class="sealed-face ui-frame"><CardBack /></div></div>
        <button type="button" class="ui-btn large act" @click.stop="skip">{{ skipping ? '等待隐藏与皮肤' : '跳过普通结果' }}</button>
      </div>

      <template v-else-if="phase === 'spotlight'">
        <SkinSpotlight v-if="queue[at]!.drop.rarity === 'skin'" :key="`skin:${at}`" :drop="queue[at]!.drop" :settled="settled" @done="settled = true" />
        <CardSpotlight v-else-if="queue[at]!.card"
          :key="at" :drop="queue[at]!.drop" :card="queue[at]!.card!" :art="queue[at]!.art"
          :settled="settled" @done="settled = true"
        />
        <EmoteSpotlight v-else :key="`emote:${at}`" :drop="queue[at]!.drop" :settled="settled" @done="settled = true" />
        <span v-if="queue.length > 1" class="page"><b>{{ at + 1 }}</b> / {{ queue.length }}</span>
        <button v-if="needsSummary(drops)" type="button" class="ui-btn small show-all" :disabled="skipping && !settled" @click.stop="skip">{{ skipping ? '继续跳过普通结果' : '跳过普通结果' }}</button>
        <button type="button" class="ui-btn large act" :disabled="skipping && !settled" @click.stop="tap">{{ skipping && !settled ? '播放中…' : action }}</button>
      </template>

      <section v-else class="summary-body" :class="{ calm: reducedMotion }">
        <header>
          <h3>{{ heading }}</h3>
          <span v-if="shards" class="shards">碎片 +{{ shards }}</span>
        </header>

        <div class="results ui-scroll mixed">
          <article v-for="(r, i) in results" :key="r.item.id" class="result" :class="[r.drop.rarity, { sticker: r.item.kind === 'emote' }]" :style="{ '--i': Math.min(i, 14) }">
            <span v-if="r.card" class="art ui-frame">
              <img :src="assetUrl(r.card.thumb)" :alt="r.card.name" draggable="false" />
              <i v-if="r.card.tier !== 'normal'" class="tier ui-tag" :class="{ gold: r.card.tier === 'big' }">{{ TIER_LABEL[r.card.tier] }}</i>
              <b v-if="r.drop.new" class="fresh ui-tag dark">NEW</b>
              <b v-if="r.drop.got > 1" class="got ui-tag dark">+{{ r.drop.got }}</b>
            </span>
            <span v-else class="ui-frame ui-well">
              <img v-if="r.item.kind === 'character'" :src="getCharacter(r.item.ref)?.bg" :alt="r.item.name" />
              <ItemArt v-else :item="r.item" :size="84" />
              <b v-if="r.drop.new" class="fresh ui-tag dark">NEW</b>
              <b v-if="r.drop.got > 1" class="got ui-tag dark">+{{ r.drop.got }}</b>
            </span>
            <b class="name">{{ r.label?.title ?? r.item.name }}</b>
            <small>{{ r.drop.new ? RARITY_LABEL[r.drop.rarity as Rarity] : dropLabel(r.item, false) }} · ×{{ r.drop.count }}<template v-if="r.drop.shards"> · 碎片 +{{ r.drop.shards }}</template></small>
          </article>
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
.results.mixed { grid-template-columns: repeat(auto-fill, minmax(105px, 1fr)); }
.scene {
  position: absolute;
  inset: 0;
  z-index: 40;
  overflow: hidden;
  outline: none;
  background: var(--grad-sky);
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
    transform: translateX(-100%);
  }
}

.act {
  position: absolute;
  right: 30px;
  bottom: 26px;
  z-index: 5;
}
.show-all {
  position: absolute;
  left: 30px;
  top: 24px;
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
  font: 800 var(--fs-title)/1 var(--font-latin);
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
  filter: drop-shadow(0 12px 26px rgba(var(--ink-rgb), 0.32));
  animation: charge 760ms var(--ease-in-out) infinite alternate;
}
.sealed-face {
  --radius: var(--radius-l);
  height: 100%;
  background: var(--surface);
}
.sealed-face :deep(.back) {
  inset: 6px;
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
  font: 800 var(--fs-title)/1.15 var(--font);
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
.result {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  text-align: center;
  animation: result-in var(--dur-stage) var(--ease-out) calc(var(--i) * 45ms) backwards;
}
.calm .result {
  animation: none;
}
.result .art {
  --radius: var(--radius-m);
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
  background: var(--gold);
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

</style>
