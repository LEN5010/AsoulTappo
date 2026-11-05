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
import { ui } from "../stores/ui";
import { takeFocus, trapTab } from "../ui/focus";
import PetBust from "./PetBust.vue";
import "./reveal-stage.css";
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

const CHARGE_MS = 1280;
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
  if (!settled.value) return "揭晓";
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
// Hiding or minimizing the window deactivates the whole panel; keep this reveal so it can resume.
onDeactivated(() => {
  if (!ui.panelOpen || ui.panelMinimized) return;
  emit("close");
});

const shards = computed(() => drops.value.reduce((n, d) => n + d.shards, 0));
const heading = computed(() => `本次共鸣获得 ${drops.value.length} 件`);
const newItems = computed(() => drops.value.filter((drop) => drop.new).length);
const results = computed(() => {
  const list = drops.value.length <= 10
    ? drops.value.map((drop) => ({ ...drop, got: 1 }))
    : groupDrops(drops.value);
  return list.flatMap((drop) => {
    const item = getItem(drop.item);
    const card = cardOf(drop);
    return item ? [{ drop, item, card, label: card ? cardLabel(card) : null }] : [];
  });
});
</script>

<template>
  <Teleport defer to=".panel-overlay">
    <div
      ref="root" class="scene resonance-cinema" :class="phase" data-overlay
      role="dialog" aria-modal="true" aria-label="共鸣结果" tabindex="-1"
      @click="tap"
    >
      <div v-if="phase !== 'summary'" class="cinema-mast" aria-hidden="true"><i></i><span>此间共鸣</span></div>
      <div v-if="phase === 'charge'" class="charge" :class="{ calm: reducedMotion }">
        <div class="pack-set" aria-hidden="true">
          <div class="pack-card rear"><CardBack /></div>
          <div class="pack-card lead"><CardBack /></div>
          <div class="pack-envelope">
            <div class="pack-cover">
              <span class="pack-brand">A-SOUL</span>
              <i class="pack-record"></i>
              <span class="pack-title">此间共鸣<small>RESONANCE COLLECTION</small></span>
              <span class="pack-edition">共 鸣 收 藏 包</span>
            </div>
            <div class="pack-seal"><span>A-SOUL COLLECTION</span><i></i></div>
            <i class="pack-glint"></i>
          </div>
          <i class="pack-shadow"></i>
        </div>
        <button type="button" class="cinema-button quiet show-all" @click.stop="skip">跳过</button>
      </div>

      <template v-else-if="phase === 'spotlight'">
        <SkinSpotlight v-if="queue[at]!.drop.rarity === 'skin'" :key="`skin:${at}`" :drop="queue[at]!.drop" :settled="settled" @done="settled = true" />
        <CardSpotlight v-else-if="queue[at]!.card"
          :key="at" :drop="queue[at]!.drop" :card="queue[at]!.card!" :art="queue[at]!.art"
          :settled="settled" @done="settled = true"
        />
        <EmoteSpotlight v-else :key="`emote:${at}`" :drop="queue[at]!.drop" :settled="settled" @done="settled = true" />
        <span v-if="queue.length > 1" class="page"><b>{{ at + 1 }}</b> / {{ queue.length }}</span>
        <button v-if="needsSummary(drops)" type="button" class="cinema-button quiet show-all" :disabled="skipping && !settled" @click.stop="skip">跳过</button>
        <button type="button" class="cinema-button cinema-primary act" :disabled="skipping && !settled" @click.stop="tap">{{ skipping && !settled ? '揭晓中…' : action }}</button>
      </template>

      <section v-else class="summary-body" :class="{ calm: reducedMotion }">
        <header class="summary-heading">
          <div><span class="collection-label">A-SOUL / COLLECTION</span><h3>{{ heading }}</h3></div>
          <span v-if="shards" class="refund">重复返还 <b>+{{ shards }}</b> 碎片</span>
        </header>

        <div class="results ui-scroll" :class="{ few: results.length < 5 }" :style="{ '--result-count': results.length }">
          <article v-for="(r, i) in results" :key="`${r.item.id}:${i}`" class="result" :class="[`rarity-${r.drop.rarity}`, { sticker: r.item.kind === 'emote' }]" :style="{ '--i': Math.min(i, 14) }">
            <div class="result-media" :class="{ 'is-card': !!r.card, 'is-skin': r.item.kind === 'character' }">
              <img v-if="r.card" class="result-card" :src="assetUrl(r.card.thumb)" :alt="r.card.name" draggable="false" />
              <PetBust v-else-if="r.item.kind === 'character'" class="result-pet" detail :src="getCharacter(r.item.ref)!.bg" />
              <img v-else class="result-sticker" :src="assetUrl(r.item.art)" :alt="r.item.name" draggable="false" />
              <span v-if="r.drop.new" class="fresh">新</span>
              <span v-if="r.card && r.card.tier !== 'normal'" class="tier">{{ TIER_LABEL[r.card.tier] }}</span>
              <span v-if="r.drop.got > 1" class="got">本次 +{{ r.drop.got }}</span>
            </div>
            <b class="result-name">{{ r.label?.title ?? r.item.name }}</b>
            <small class="result-meta"><i></i>{{ r.drop.new ? RARITY_LABEL[r.drop.rarity as Rarity] : dropLabel(r.item, false) }}<span>×{{ r.drop.count }}</span></small>
          </article>
        </div>

        <footer class="summary-footer">
          <span><b>{{ newItems }}</b> 件新收藏<span class="footer-sep">/</span>共 {{ drops.length }} 件</span>
          <button type="button" class="cinema-button cinema-primary" @click="finish">
            {{ remaining ? `收下并继续（剩余 ${remaining} 次）` : "收下" }}<span aria-hidden="true">↗</span>
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

