<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { manifest, type ManifestCard } from "../manifest";
import { assetUrl } from "../asset";
import { getItem, type Item } from "../items";
import { collection, drawCards, error, online, presenceUpdatedAt, status, tickets } from "../stores/player";
import type { Drop } from "../net/api";
import ItemDetail from "./ItemDetail.vue";
import CardReveal from "./CardReveal.vue";
import SegTabs from "../ui/SegTabs.vue";
import Icon from "../ui/Icon.vue";

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
  if (!draw) return 900;
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
          class="hero-stage"
          :class="[activeCard.tier, { owned: activeOwned, locked: !activeOwned }]"
          @click="openActiveDetail"
        >
          <span v-if="activeCard.tier !== 'normal'" class="hero-rays" aria-hidden="true"></span>

          <div class="hero-card-frame">
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
            <span class="hero-tier" :class="activeCard.tier">
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
              class="up-dot" :class="[h.tier, { on: activeCard.id === h.id }]"
              :title="`预览隐藏款：${h.name}`"
              @click="activeCardId = h.id"
            >
              {{ shortName(h.name) }}
            </button>
          </div>
        </div>

        <!-- Gacha Console Box -->
        <div class="gacha-box">
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
        <header class="binder-head">
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
              :class="{ on: filter === f.id }"
              @click="filter = f.id"
            >
              {{ f.label }}
            </button>
          </div>
        </header>

        <p v-if="error" class="error-banner" role="alert">{{ error }}</p>

        <div class="binder-scroll ui-scroll">
          <div class="binder-grid" :class="{ dense: cards.length > 12 }">
            <button
              v-for="c in visibleCards" :key="c.id" type="button"
              class="v-card"
              :class="[
                c.tier,
                {
                  owned: ownedCount(c) > 0,
                  locked: !ownedCount(c),
                  active: activeCard?.id === c.id,
                },
              ]"
              :title="`${c.name}（${tierLabel(c.tier)} · 概率 ${probability(c)}）· 点击在左侧预览，再次点击全屏赏析`"
              @click="selectOrInspect(c)"
            >
              <span class="v-art">
                <img :src="assetUrl(c.thumb)" :alt="c.name" loading="lazy" draggable="false" />
                <span class="v-foil" aria-hidden="true"></span>
                <i v-if="c.tier !== 'normal'" class="v-tier" :class="c.tier">
                  {{ c.tier === "big" ? "大隐藏" : "小隐藏" }}
                </i>
                <b v-if="ownedCount(c)" class="v-count">×{{ ownedCount(c) }}</b>
                <span v-if="c.video" class="v-live" title="含动态视频卡面">
                  <Icon name="play" :size="9" />
                </span>
              </span>
              <span class="v-name">{{ shortName(c.name) }}</span>
            </button>
          </div>

          <p v-if="!visibleCards.length" class="empty">当前筛选下没有匹配的典藏卡</p>
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
  padding: 6px 20px 14px;
  gap: 8px;
}

.series-bar {
  flex: none;
}

.stage-layout {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
}

/* LEFT COLUMN: 2:3 Featured Card Stage + Gacha Console */
.showcase-col {
  width: 242px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}

.hero-stage {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 8px 10px;
  border-radius: 22px;
  background: radial-gradient(circle at 50% 38%, #FFF7EC 0%, #F3DEC4 100%);
  border: 2px solid var(--tile-border);
  box-shadow: inset 0 -4px 0 rgba(210, 172, 134, 0.3);
  overflow: hidden;
  cursor: pointer;
}
.hero-stage.big {
  border-color: #E89668;
  background: radial-gradient(circle at 50% 35%, #FFF8EE 0%, #F7D8BE 100%);
}
.hero-rays {
  position: absolute;
  width: 340px;
  height: 340px;
  border-radius: 50%;
  background: conic-gradient(
    from 0deg,
    rgba(252, 150, 110, 0) 0deg 12deg,
    rgba(255, 224, 178, 0.55) 12deg 24deg,
    rgba(252, 150, 110, 0) 24deg 36deg
  );
  animation: spin 14s linear infinite;
  pointer-events: none;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.hero-card-frame {
  position: relative;
  z-index: 1;
  height: 100%;
  max-height: 280px;
  aspect-ratio: 2 / 3;
  border-radius: 16px;
  padding: 4px;
  box-sizing: border-box;
  background: linear-gradient(145deg, #FFFDF9 0%, #EED5BA 100%);
  border: 2.5px solid #C89B72;
  box-shadow: 0 8px 22px rgba(72, 36, 16, 0.22), 0 3px 0 #9E724C;
  overflow: hidden;
  display: flex;
  transition: transform 180ms cubic-bezier(0.34, 1.56, 0.64, 1);
}
.hero-stage:hover .hero-card-frame {
  transform: translateY(-2px) scale(1.015);
}
.hero-stage.big .hero-card-frame {
  background: linear-gradient(145deg, #FFE6B8 0%, #FC966E 55%, #FFD2A6 100%);
  border-color: #B44D25;
  box-shadow: 0 8px 24px rgba(252, 150, 110, 0.42), 0 3px 0 #8E3918;
}
.hero-stage.small .hero-card-frame {
  background: linear-gradient(145deg, #FFF0E4 0%, #F3B391 100%);
  border-color: #C46840;
}

.hero-media {
  width: 100%;
  height: 100%;
  border-radius: 11px;
  object-fit: cover;
  display: block;
  background: #EAD7C2;
}
.hero-stage.locked .hero-media {
  filter: saturate(0.75) contrast(0.95);
}

.foil-sheen {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    115deg,
    transparent 25%,
    rgba(255, 255, 255, 0.32) 45%,
    rgba(255, 232, 200, 0.18) 52%,
    transparent 70%
  );
  pointer-events: none;
}

.hero-tier {
  position: absolute;
  left: 8px;
  top: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(68, 36, 18, 0.76);
  color: #FFF7EE;
  font-size: 10px;
  font-weight: 800;
  backdrop-filter: blur(4px);
}
.hero-tier.big {
  background: linear-gradient(180deg, #FFB899 0%, var(--accent) 100%);
  color: var(--on-accent);
  border: 1px solid rgba(114, 46, 18, 0.35);
}
.hero-tier.small {
  background: rgba(255, 244, 232, 0.92);
  color: #8A4B2A;
  border: 1px solid #E4A888;
}

.hero-zoom {
  position: absolute;
  right: 8px;
  top: 8px;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid rgba(255, 246, 236, 0.55);
  background: rgba(64, 32, 16, 0.72);
  color: #FFF8F0;
  font: 800 10px var(--font);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  backdrop-filter: blur(4px);
}
.hero-zoom:hover {
  background: var(--accent);
  color: var(--on-accent);
}

.hero-plate {
  position: absolute;
  left: 4px;
  right: 4px;
  bottom: 4px;
  padding: 16px 8px 6px;
  border-radius: 0 0 11px 11px;
  background: linear-gradient(180deg, transparent 0%, rgba(44, 22, 10, 0.84) 48%, rgba(36, 18, 8, 0.92) 100%);
  color: #FFF8F0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.plate-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}
.plate-main b {
  font-size: 12.5px;
  font-weight: 900;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.char-tag {
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(252, 150, 110, 0.28);
  border: 1px solid rgba(252, 150, 110, 0.55);
  color: #FFE4D4;
  font-size: 9.5px;
  font-weight: 800;
  flex: none;
}
.plate-state {
  font-size: 10px;
  color: rgba(255, 238, 222, 0.82);
  font-weight: 700;
}

.up-pills {
  position: relative;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 4px;
  margin-top: 6px;
}
.up-dot {
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid var(--tile-border);
  background: rgba(255, 249, 242, 0.88);
  color: var(--ink-2);
  font: 700 10px var(--font);
  cursor: pointer;
}
.up-dot.on {
  background: var(--accent);
  border-color: var(--accent-deep);
  color: var(--on-accent);
  font-weight: 800;
}

/* Gacha Console Box */
.gacha-box {
  flex: none;
  padding: 9px 11px;
  border-radius: 18px;
  background: var(--tile-frame);
  border: 2px solid var(--tile-border);
  box-shadow: 0 2.5px 0 var(--tile-lip);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pity-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-2);
}
.pity-row b {
  color: var(--ink);
  font-weight: 900;
}
.pity-row small {
  font-size: 9.5px;
  color: var(--ink-3);
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
  font-size: 11.5px;
  font-weight: 800;
  color: var(--ink);
}
.ticket-badge :deep(.icon) {
  color: var(--accent-deep);
}
.ticket-badge b {
  font-size: 14px;
  font-weight: 900;
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
  gap: 6px;
}
.gacha-btns .ui-btn {
  min-height: 30px;
  padding: 4px 8px;
  font-size: 12px;
}

/* RIGHT COLUMN: 2:3 Vertical Portrait Card Binder */
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
  margin-bottom: 8px;
  flex: none;
  flex-wrap: wrap;
}
.series-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.series-meta h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 900;
  color: var(--ink);
}
.collect-pill {
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--paper-2);
  border: 1.5px solid var(--tile-border);
  font-size: 11px;
  font-weight: 800;
  color: var(--ink-2);
}
.collect-pill b {
  color: var(--accent-deep);
}

.filter-pills {
  display: flex;
  gap: 4px;
}
.filter-pills button {
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1.5px solid transparent;
  background: var(--paper-2);
  color: var(--ink-2);
  font: 700 11.5px var(--font);
  cursor: pointer;
}
.filter-pills button.on {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--on-accent);
}

.binder-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 2px 4px 10px 2px;
}

/* 5 columns for 9-10 card series (fits in just 2 neat rows!), 6 columns for 24-card series */
.binder-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 9px;
}
.binder-grid.dense {
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}

.v-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 4px 5px;
  margin: 0;
  box-sizing: border-box;
  border-radius: 14px;
  background: var(--tile-frame);
  border: 1.5px solid var(--tile-border);
  box-shadow: 0 2px 0 var(--tile-lip);
  cursor: pointer;
  font: inherit;
  color: var(--ink);
  transition: transform 130ms cubic-bezier(0.34, 1.56, 0.64, 1), border-color 140ms, box-shadow 140ms;
}
.v-card:hover {
  transform: translateY(-3px);
  border-color: var(--accent);
}
.v-card.owned {
  background: #FFF9F2;
  border-color: #F2B594;
  box-shadow: 0 2px 0 #DF9B78;
}
.v-card.big.owned {
  background: linear-gradient(180deg, #FFF7EB 0%, #FFE8D1 100%);
  border-color: var(--accent);
  box-shadow: 0 2.5px 0 var(--accent-deep);
}
.v-card.active {
  border-color: var(--accent);
  box-shadow: 0 2.5px 0 var(--accent-deep), 0 0 0 2.5px rgba(var(--accent-rgb), 0.45);
}

.v-art {
  position: relative;
  width: 100%;
  aspect-ratio: 2 / 3;
  border-radius: 10px;
  overflow: hidden;
  background: var(--rar-rare-bg);
  display: block;
}
.v-card.big .v-art,
.v-card.small .v-art {
  background: var(--rar-epic-bg);
}
.v-art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 180ms;
}
.v-card:hover .v-art img {
  transform: scale(1.05);
}
.v-card.locked .v-art img {
  filter: saturate(0.45) contrast(0.92);
  opacity: 0.55;
}
.v-card.locked .v-name {
  color: var(--ink-3);
}
.v-foil {
  position: absolute;
  inset: 0;
  background: linear-gradient(125deg, transparent 35%, rgba(255, 255, 255, 0.25) 50%, transparent 65%);
  pointer-events: none;
}

.v-tier {
  position: absolute;
  left: 4px;
  top: 4px;
  padding: 1px 5px;
  border-radius: 999px;
  background: linear-gradient(180deg, #FFB596, var(--accent));
  color: var(--on-accent);
  border: 1px solid rgba(120, 50, 20, 0.25);
  font-size: 8.5px;
  font-style: normal;
  font-weight: 800;
}
.v-tier.small {
  background: rgba(255, 245, 234, 0.94);
  color: #8A5132;
}
.v-count {
  position: absolute;
  right: 4px;
  top: 4px;
  padding: 1px 5px;
  border-radius: 999px;
  background: rgba(68, 36, 18, 0.78);
  color: #FFF9F2;
  font-size: 9px;
  font-weight: 800;
}
.v-live {
  position: absolute;
  left: 4px;
  bottom: 4px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(255, 243, 232, 0.94);
  border: 1px solid #F2B28E;
  color: var(--accent-deep);
  display: flex;
  align-items: center;
  justify-content: center;
}

.v-name {
  display: block;
  width: 100%;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  font-weight: 700;
  text-align: center;
}

.error-banner {
  margin: 0 0 6px;
  color: var(--bad);
  font-size: 12px;
  font-weight: 700;
}
.empty {
  color: var(--ink-3);
  padding: 28px 0;
  text-align: center;
  font-size: 13px;
  font-weight: 700;
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
