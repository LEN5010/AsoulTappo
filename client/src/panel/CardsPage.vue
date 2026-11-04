<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { manifest, type ManifestCard } from "../manifest";
import { assetUrl } from "../asset";
import { getItem, type Item } from "../items";
import { collection, drawCards, error, online, presenceUpdatedAt, status, tickets } from "../stores/player";
import type { Drop } from "../net/api";
import ItemDetail from "./ItemDetail.vue";
import CardReveal from "./CardReveal.vue";
import SegTabs from "../ui/SegTabs.vue";
import Icon from "../ui/Icon.vue";
import { rise } from "../ui/motion";

const selectedSeries = ref(manifest.series[0]!.id);
const filter = ref<"all" | "owned" | "missing" | "hidden">("all");
const activeCardId = ref<string>("");

const seriesObj = computed(() => manifest.series.find((s) => s.id === selectedSeries.value) ?? manifest.series[0]!);
const cards = computed(() => manifest.cards.filter((c) => c.series === selectedSeries.value));
const ownedCount = (c: ManifestCard) => collection.owned[`card:${c.id}`] ?? 0;
const haveCount = computed(() => cards.value.filter(ownedCount).length);

const shortName = (name: string) =>
  name.replace(/^A-SOUL\s*[·\s]\s*/, "").replace(/收藏集$/, "").trim() || name;

const poolTabs = computed(() =>
  manifest.series.map((p) => {
    const allInSeries = manifest.cards.filter((c) => c.series === p.id);
    const ownedInSeries = allInSeries.filter(ownedCount).length;
    return {
      id: p.id,
      label: shortName(p.name),
      count: ownedInSeries,
    };
  }),
);

const TIER_RANK: Record<ManifestCard["tier"], number> = { big: 0, small: 1, normal: 2 };

const sortedCards = computed(() =>
  [...cards.value].sort((a, b) => TIER_RANK[a.tier] - TIER_RANK[b.tier]),
);

const featuredHiddenCards = computed(() =>
  sortedCards.value.filter((c) => c.tier !== "normal"),
);

// Default active showcase card to the first big-hidden card when switching series
watch(
  selectedSeries,
  () => {
    const first = featuredHiddenCards.value[0] ?? sortedCards.value[0];
    activeCardId.value = first?.id ?? "";
  },
  { immediate: true },
);

const activeCard = computed(
  () => cards.value.find((c) => c.id === activeCardId.value) ?? featuredHiddenCards.value[0] ?? sortedCards.value[0],
);
const binder = ref<HTMLElement>();
watch([selectedSeries, filter], () => nextTick(() => rise(binder.value)));

const activeOwned = computed(() => (activeCard.value ? ownedCount(activeCard.value) > 0 : false));

const visibleCards = computed(() =>
  sortedCards.value.filter((c) => {
    if (filter.value === "owned") return ownedCount(c) > 0;
    if (filter.value === "missing") return ownedCount(c) === 0;
    if (filter.value === "hidden") return c.tier !== "normal";
    return true;
  }),
);

function probability(c: ManifestCard) {
  const mass = { big: 0.5, small: 4.5, normal: 95 }[c.tier];
  const tierCount = cards.value.filter((x) => x.tier === c.tier).length || 1;
  return (mass / tierCount).toFixed(2) + "%";
}

function tierLabel(tier: ManifestCard["tier"]) {
  if (tier === "big") return "大隐藏";
  if (tier === "small") return "小隐藏";
  return "普通款";
}

function selectOrInspect(c: ManifestCard) {
  if (activeCardId.value === c.id) {
    detail.value = getItem(`card:${c.id}`) ?? null;
  } else {
    activeCardId.value = c.id;
  }
}

function openActiveDetail() {
  if (activeCard.value) {
    detail.value = getItem(`card:${activeCard.value.id}`) ?? null;
  }
}

// ---- Draw timer & actions
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

const detail = ref<Item | null>(null);
const cardDrops = ref<Drop[]>([]);
const busy = ref(false);
const pending = ref(0);

async function draw(all: boolean) {
  if (busy.value || !tickets.value) return;
  busy.value = true;
  pending.value = all ? tickets.value : 1;
  await nextBatch();
}
async function nextBatch() {
  const result = await drawCards(selectedSeries.value, Math.min(pending.value, 100));
  if (result) {
    pending.value -= result.length;
    cardDrops.value = result;
    // Highlight the highest-tier card drawn on the stage
    const best = [...result].sort(
      (a, b) => (a.tier === "big" ? 0 : a.tier === "small" ? 1 : 2) - (b.tier === "big" ? 0 : b.tier === "small" ? 1 : 2),
    )[0];
    if (best?.item.startsWith("card:")) {
      activeCardId.value = best.item.slice(5);
    }
  } else {
    pending.value = 0;
  }
  busy.value = false;
}
async function collect() {
  cardDrops.value = [];
  if (pending.value > 0) {
    busy.value = true;
    await nextBatch();
  }
}
</script>

<template>
  <div class="cards-page">
    <!-- Series Capsule Bar -->
    <div class="series-bar">
      <SegTabs
        v-model="selectedSeries"
        :tabs="poolTabs"
        :disabled="busy || cardDrops.length > 0"
        label="B站收藏集卡池"
      />
    </div>

    <div class="stage-layout">
      <!-- LEFT: Featured Card Showcase Stage + Gacha Console -->
      <aside class="showcase-col">
        <div
          v-if="activeCard"
          class="hero-stage ui-frame"
          :class="[activeCard.tier, { owned: activeOwned, locked: !activeOwned }]"
          data-rise
          @click="openActiveDetail"
        >
          <span class="hero-dots" aria-hidden="true"></span>
          <span class="hero-stripe" aria-hidden="true"></span>
          <span v-if="activeCard.tier !== 'normal'" class="hero-rays" aria-hidden="true"></span>

          <div class="hero-card-frame ui-frame">
            <video
              v-if="activeOwned && activeCard.video"
              :key="activeCard.id"
              class="hero-media"
              :src="assetUrl(activeCard.video)"
              :poster="assetUrl(activeCard.thumb)"
              autoplay
              loop
              muted
              playsinline
            ></video>
            <img
              v-else
              class="hero-media"
              :src="assetUrl(activeOwned ? activeCard.full : activeCard.thumb)"
              :alt="activeCard.name"
              draggable="false"
            />

            <span class="foil-sheen" aria-hidden="true"></span>

            <!-- Top-left tier ribbon -->
            <span class="hero-tier ui-tag" :class="{ dark: activeCard.tier === 'normal' }">
              {{ tierLabel(activeCard.tier) }} · {{ probability(activeCard) }}
            </span>

            <!-- Top-right expand / live badge -->
            <button
              type="button"
              class="hero-zoom"
              :title="activeOwned ? '全屏赏析（含动效/原画）' : '查看卡牌详情'"
              @click.stop="openActiveDetail"
            >
              <Icon :name="activeCard.video ? 'play' : 'spark'" :size="11" />
              <span>{{ activeOwned && activeCard.video ? "LIVE" : "赏析" }}</span>
            </button>

            <!-- Bottom card nameplate overlay -->
            <div class="hero-plate">
              <div class="plate-main">
                <b>{{ shortName(activeCard.name) }}</b>
                <span v-if="activeCard.characters.length" class="char-tag">
                  {{ activeCard.characters.join(" · ") }}
                </span>
              </div>
              <small class="plate-state">
                {{ activeOwned ? `已典藏 ×${ownedCount(activeCard)}` : "待解锁 · 卡池抽取" }}
              </small>
            </div>
          </div>

          <!-- Quick switcher pills for the series' UP hidden cards -->
          <div v-if="featuredHiddenCards.length > 1" class="up-pills" @click.stop>
            <button
              v-for="h in featuredHiddenCards" :key="h.id" type="button"
              class="up-dot ui-chip" :class="[h.tier, { on: activeCard.id === h.id }]"
              :title="`预览隐藏款：${h.name}`"
              @click="activeCardId = h.id"
            >
              {{ shortName(h.name) }}
            </button>
          </div>
        </div>

        <!-- Gacha Console Box -->
        <div class="gacha-box ui-frame ui-ring" data-rise>
          <div class="pity-row">
            <span>大隐藏保底 <b>{{ status?.draw?.pity ?? 0 }}</b> / 400</span>
            <small>大隐藏 0.5% · 小隐藏 4.5%</small>
          </div>
          <div class="ui-bar"><i :style="{ width: `${(status?.draw?.pity ?? 0) / 4}%` }"></i></div>

          <div class="ticket-row">
            <span class="ticket-badge">
              <Icon name="card" :size="14" />
              <b>{{ tickets }}</b> 次可抽
            </span>
            <small class="cd-text">{{ online ? `下一抽 ${countdown}` : "连接服务器累积在线时长" }}</small>
          </div>

          <div class="gacha-btns">
            <button type="button" class="ui-btn" :disabled="busy || !online || !tickets" @click="draw(false)">
              {{ busy ? "抽取中…" : "抽一次" }}
            </button>
            <button type="button" class="ui-btn primary" :disabled="busy || !online || !tickets" @click="draw(true)">
              {{ tickets > 1 ? `全部抽取 ×${tickets}` : "全部抽取" }}
            </button>
          </div>
        </div>
      </aside>

      <!-- RIGHT: 2:3 Vertical Portrait Card Binder -->
      <section class="binder-col">
        <header class="binder-head" data-rise>
          <div class="series-meta">
            <h3>{{ seriesObj.name }}</h3>
            <span class="collect-pill">已集齐 <b>{{ haveCount }}</b> / {{ cards.length }}</span>
          </div>

          <div class="filter-pills">
            <button
              v-for="f in [
                { id: 'all', label: '全部' },
                { id: 'hidden', label: '隐藏款' },
                { id: 'owned', label: '已拥有' },
                { id: 'missing', label: '未拥有' },
              ] as const"
              :key="f.id"
              type="button"
              class="ui-chip"
              :class="{ on: filter === f.id }"
              @click="filter = f.id"
            >
              {{ f.label }}
            </button>
          </div>
        </header>

        <p v-if="error" class="ui-error" role="alert">{{ error }}</p>

        <div ref="binder" class="binder-scroll ui-scroll">
          <div class="binder-grid" :class="{ dense: cards.length > 12 }">
            <button
              v-for="c in visibleCards" :key="c.id" type="button"
              class="v-card ui-tile"
              :class="[
                c.tier,
                {
                  locked: !ownedCount(c),
                  picked: activeCard?.id === c.id,
                },
              ]"
              data-rise
              :title="`${c.name}（${tierLabel(c.tier)} · 概率 ${probability(c)}）· 点击在左侧预览，再次点击全屏赏析`"
              @click="selectOrInspect(c)"
            >
              <span class="v-art ui-frame ui-well">
                <img :src="assetUrl(c.thumb)" :alt="c.name" loading="lazy" decoding="async" draggable="false" />
                <span class="v-foil" aria-hidden="true"></span>
                <i v-if="c.tier !== 'normal'" class="v-tier ui-tag" :class="{ light: c.tier === 'small' }">
                  {{ c.tier === "big" ? "大隐藏" : "小隐藏" }}
                </i>
                <b v-if="ownedCount(c)" class="v-count ui-tag dark">×{{ ownedCount(c) }}</b>
                <span v-if="c.video" class="v-live" title="含动态视频卡面">
                  <Icon name="play" :size="9" />
                </span>
              </span>
              <span class="ui-tile-name">{{ shortName(c.name) }}</span>
            </button>
          </div>

          <p v-if="!visibleCards.length" class="ui-empty">当前筛选下没有匹配的典藏卡</p>
        </div>
      </section>
    </div>

    <ItemDetail v-if="detail" :item="detail" @close="detail = null" />
    <CardReveal v-if="cardDrops.length" :drops="cardDrops" :remaining="pending" @close="collect" />
  </div>
</template>

<style scoped>
.cards-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 0 20px 14px 16px;
  gap: 10px;
}
.series-bar {
  flex: none;
}
.stage-layout {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 18px;
}

.showcase-col {
  width: 242px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.hero-stage {
  --cut: 18px;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 10px;
  background: var(--accent);
  cursor: pointer;
}
.hero-dots {
  position: absolute;
  inset: auto 0 0;
  height: 140px;
  background: #fff;
  opacity: 0.34;
  mask: var(--halftone) left bottom / 280px auto repeat-x;
  -webkit-mask: var(--halftone) left bottom / 280px auto repeat-x;
}
.hero-stripe {
  position: absolute;
  top: -10px;
  bottom: -10px;
  left: 46%;
  width: 96px;
  background: rgba(255, 255, 255, 0.2);
  transform: skewX(var(--skew));
}
.hero-rays {
  position: absolute;
  width: 420px;
  height: 420px;
  background: conic-gradient(
    from 0deg,
    rgba(255, 255, 255, 0) 0deg 12deg,
    rgba(255, 255, 255, 0.22) 12deg 24deg,
    rgba(255, 255, 255, 0) 24deg 36deg
  );
  animation: spin 18s linear infinite;
  pointer-events: none;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.hero-card-frame {
  --cut: 14px;
  z-index: 1;
  height: 100%;
  max-height: 290px;
  aspect-ratio: 2 / 3;
  padding: 4px;
  box-sizing: border-box;
  background: var(--surface);
  display: flex;
  transition: transform 300ms var(--ease-out);
}
.hero-stage:hover .hero-card-frame {
  transform: translate(-2px, -3px);
}

.hero-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  background: var(--accent-soft);
}
.hero-stage.locked .hero-media {
  filter: saturate(0.75) contrast(0.95);
}

/* Foil: a single band that crosses hidden cards every few seconds. */
.foil-sheen {
  position: absolute;
  inset: -10%;
  z-index: 1;
  background: linear-gradient(112deg, transparent 38%, rgba(255, 255, 255, 0.46) 48%, rgba(255, 224, 190, 0.28) 54%, transparent 64%);
  transform: translateX(-70%);
  pointer-events: none;
}
.hero-stage.big .foil-sheen,
.hero-stage.small .foil-sheen {
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

.hero-tier {
  position: absolute;
  left: 11px;
  top: 10px;
  z-index: 2;
}
.hero-zoom {
  position: absolute;
  right: 9px;
  top: 9px;
  z-index: 2;
  isolation: isolate;
  height: 20px;
  padding: 0 8px;
  border: 0;
  background: none;
  color: #fff;
  font: 800 10px var(--font);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}
.hero-zoom::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -1;
  background: var(--ink);
  transform: skewX(var(--skew));
  transition: background 140ms;
}
.hero-zoom:hover::before {
  background: var(--accent-deep);
}

.hero-plate {
  position: absolute;
  left: 6px;
  right: 6px;
  bottom: 6px;
  z-index: 2;
  padding: 18px 8px 6px;
  background: linear-gradient(180deg, transparent 0%, rgba(43, 37, 48, 0.82) 46%, rgba(43, 37, 48, 0.94) 100%);
  color: #fff;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.plate-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}
.plate-main b {
  font: 400 16px/1.1 var(--font-display);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.char-tag {
  flex: none;
  font-size: 10px;
  font-weight: 800;
  color: var(--accent);
}
.plate-state {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.78);
  font-weight: 700;
}

.up-pills {
  position: relative;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 5px 8px;
  margin-top: 8px;
}
.up-dot {
  height: 20px;
  padding: 0 7px;
  font-size: 10px;
  color: var(--ink);
}
.up-dot::before {
  background: var(--surface);
}
.up-dot:hover::before {
  background: var(--accent-tint);
}
.up-dot.on {
  color: #fff;
}
.up-dot.on::before {
  background: var(--ink);
}

.gacha-box {
  --cut: 14px;
  flex: none;
  padding: 10px 12px 12px;
  background: var(--accent-tint);
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.pity-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-2);
  white-space: nowrap;
}
.pity-row b {
  font: italic 800 17px/1 var(--font-latin);
  color: var(--accent-deep);
}
.pity-row small {
  font-size: 9.5px;
  color: var(--ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
}
.ticket-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.ticket-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 800;
  color: var(--ink);
}
.ticket-badge :deep(.icon) {
  color: var(--accent-deep);
}
.ticket-badge b {
  font: italic 800 20px/1 var(--font-latin);
  color: var(--accent-deep);
}
.cd-text {
  font-size: 10px;
  font-weight: 700;
  color: var(--ink-3);
}
.gacha-btns {
  display: grid;
  grid-template-columns: 1fr 1.25fr;
  gap: 8px;
  padding: 0 4px 3px 2px;
}
.gacha-btns .ui-btn {
  height: 32px;
  padding: 0 8px;
  font-size: 12px;
}

.binder-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.binder-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  flex: none;
  flex-wrap: wrap;
}
.series-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.series-meta h3 {
  margin: 0;
  font: 400 19px/1.1 var(--font-display);
  color: var(--ink);
}
.collect-pill {
  font-size: 11px;
  font-weight: 800;
  color: var(--ink-2);
  white-space: nowrap;
}
.collect-pill b {
  font: italic 800 17px/1 var(--font-latin);
  color: var(--accent-deep);
}
.filter-pills {
  display: flex;
  gap: 5px;
  padding-left: 3px;
}

.binder-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 2px 8px 10px 0;
}
.binder-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px 10px;
}
.binder-grid.dense {
  grid-template-columns: repeat(6, minmax(0, 1fr));
}

.v-card {
  --well-ratio: 2 / 3;
}
.v-art {
  padding: 0;
  background: var(--rar-rare-bg);
}
.v-art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  filter: none;
}
.v-card.locked .v-art img {
  filter: saturate(0.48) contrast(0.9);
}
.v-card.big .v-art,
.v-card.small .v-art {
  background: var(--rar-epic-bg);
}
.v-foil {
  position: absolute;
  inset: 0;
  background: linear-gradient(125deg, transparent 35%, rgba(255, 255, 255, 0.25) 50%, transparent 65%);
  pointer-events: none;
}
.v-tier {
  position: absolute;
  left: 6px;
  top: 5px;
  font-size: 9px;
  line-height: 15px;
  padding: 0 5px;
}
.v-count {
  position: absolute;
  right: 6px;
  top: 5px;
  font-size: 9px;
  line-height: 15px;
  padding: 0 5px;
}
.v-live {
  position: absolute;
  left: 6px;
  bottom: 6px;
  width: 20px;
  height: 15px;
  background: var(--ink);
  color: #fff;
  transform: skewX(var(--skew));
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 780px) {
  .stage-layout {
    flex-direction: column;
  }
  .showcase-col {
    width: 100%;
    flex-direction: row;
  }
  .binder-grid,
  .binder-grid.dense {
    grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
  }
}
</style>
