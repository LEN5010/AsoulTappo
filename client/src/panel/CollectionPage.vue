<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { manifest, type ManifestCard } from "../manifest";
import { assetUrl } from "../asset";
import { craftCost, getItem, ownsEmote, type Item } from "../items";
import {
  boxes,
  collection,
  craftItem,
  drawCards,
  error,
  online,
  openBoxes,
  presenceUpdatedAt,
  shards,
  status,
  tickets,
} from "../stores/player";
import { settings } from "../stores/settings";
import { sendEmote } from "../stores/room";
import { ui } from "../stores/ui";
import type { Drop } from "../net/api";
import ItemDetail from "./ItemDetail.vue";
import CardReveal from "./CardReveal.vue";
import RevealModal from "./RevealModal.vue";
import Modal from "../ui/Modal.vue";
import ItemArt from "../ui/ItemArt.vue";
import SegTabs from "../ui/SegTabs.vue";
import Icon from "../ui/Icon.vue";

type DexMode = "emotes" | "cards";
const mode = ref<DexMode>("emotes");

// ---- Emote Codex state (no 21 accordion headers! Clean Rarity grouping like WuwaTappo Image 1)
const charTab = ref<string>("all");
const setFilter = ref<string>("all");
const emoteOwnFilter = ref<"all" | "owned" | "missing">("all");
const emoteQuery = ref("");
const emoteCollapsed = ref<Record<string, boolean>>({});

const emoteOwners = computed(() => [...new Set(manifest.emoteSets.map((s) => s.character))]);
const charTabs = computed(() => [
  { id: "all", label: "全部" },
  ...emoteOwners.value.map((c) => ({ id: c, label: c })),
]);

// Reset setFilter if switching character and current set belongs to another character
watch(charTab, (c) => {
  if (setFilter.value !== "all") {
    const s = manifest.emoteSets.find((x) => x.id === setFilter.value);
    if (s && c !== "all" && s.character !== c) setFilter.value = "all";
  }
});

const availableSets = computed(() =>
  manifest.emoteSets.filter((s) => charTab.value === "all" || s.character === charTab.value),
);

interface FlatEmote {
  key: string;
  name: string;
  img: string;
  character: string;
  setId: string;
  setName: string;
  rarity: "common" | "rare" | "epic" | "legendary";
  owned: boolean;
}

const allEmotesInScope = computed<FlatEmote[]>(() => {
  const list: FlatEmote[] = [];
  for (const s of manifest.emoteSets) {
    if (charTab.value !== "all" && s.character !== charTab.value) continue;
    if (setFilter.value !== "all" && s.id !== setFilter.value) continue;
    for (const e of s.emotes) {
      list.push({
        key: e.key,
        name: e.name,
        img: e.img,
        character: s.character,
        setId: s.id,
        setName: s.name,
        rarity: s.rarity,
        owned: ownsEmote(e.key, collection.owned),
      });
    }
  }
  return list;
});

const filteredEmotes = computed(() =>
  allEmotesInScope.value
    .filter((e) => {
      if (emoteQuery.value && !e.name.includes(emoteQuery.value) && !e.setName.includes(emoteQuery.value)) {
        return false;
      }
      if (emoteOwnFilter.value === "owned") return e.owned;
      if (emoteOwnFilter.value === "missing") return !e.owned;
      return true;
    })
    // Owned items first within each tier so unlocked emotes aren't buried
    .sort((a, b) => Number(b.owned) - Number(a.owned)),
);

// Just 2 clean Rarity tiers like WuwaTappo Image 1 (Rare vs Common) instead of 21 pack headers
const emoteGroups = computed(() => {
  const rareAll = allEmotesInScope.value.filter((e) => e.rarity !== "common");
  const commonAll = allEmotesInScope.value.filter((e) => e.rarity === "common");
  return [
    {
      id: "rare",
      name: "Rare · 珍稀款",
      owned: rareAll.filter((e) => e.owned).length,
      total: rareAll.length,
      items: filteredEmotes.value.filter((e) => e.rarity !== "common"),
    },
    {
      id: "common",
      name: "Common · 常驻款",
      owned: commonAll.filter((e) => e.owned).length,
      total: commonAll.length,
      items: filteredEmotes.value.filter((e) => e.rarity === "common"),
    },
  ].filter((g) => g.items.length > 0);
});

const totalEmotesCount = computed(() => manifest.emoteSets.reduce((acc, s) => acc + s.emotes.length, 0));
const totalOwnedEmotesCount = computed(() =>
  manifest.emoteSets.reduce(
    (acc, s) => acc + s.emotes.filter((e) => ownsEmote(e.key, collection.owned)).length,
    0,
  ),
);

const selectedEmote = ref<Item | null>(null);
const selectedEmoteOwned = computed(() =>
  selectedEmote.value ? ownsEmote(selectedEmote.value.ref, collection.owned) : false,
);
const selectedEmoteCost = computed(() => (selectedEmote.value ? craftCost(selectedEmote.value) : null));
const actionNote = ref("");
const boxDrops = ref<Drop[]>([]);

watch(
  () => ui.craftTarget,
  (id) => {
    if (id) {
      mode.value = "emotes";
      selectedEmote.value = getItem(id) ?? null;
      ui.craftTarget = "";
    }
  },
  { immediate: true },
);

async function openBoxBatch(all: boolean) {
  if (busy.value) return;
  busy.value = true;
  const count = all ? boxes.value : 1;
  const results: Drop[] = [];
  let rem = count;
  while (rem > 0) {
    const batch = await openBoxes(Math.min(10, rem));
    if (!batch?.length) break;
    results.push(...batch);
    rem -= batch.length;
  }
  boxDrops.value = results;
  busy.value = false;
}

async function craftSelectedEmote() {
  if (!selectedEmote.value || busy.value) return;
  busy.value = true;
  const item = selectedEmote.value;
  if (await craftItem(item.id)) actionNote.value = `已兑换 ${item.name}`;
  busy.value = false;
}

function toggleFav(item: Item) {
  const at = settings.favorites.indexOf(item.ref);
  if (at >= 0) settings.favorites.splice(at, 1);
  else if (settings.favorites.length < 8) settings.favorites.push(item.ref);
  else actionNote.value = "预设栏已满（8/8），可前往「背包」调整";
}

function fireSelectedEmote(item: Item) {
  sendEmote(item.ref);
  selectedEmote.value = null;
}

const tapPct = computed(() =>
  Math.min(100, ((status.value?.progress.taps ?? 0) / (status.value?.progress.tapsPerBox ?? 600)) * 100),
);

// ---- Collection Cards state
const selectedSeries = ref(manifest.series[0]!.id);
const cardFilter = ref<"all" | "owned" | "missing">("all");
const cardCollapsed = ref<Record<string, boolean>>({});

const cards = computed(() => manifest.cards.filter((c) => c.series === selectedSeries.value));
const ownedCount = (c: ManifestCard) => collection.owned[`card:${c.id}`] ?? 0;
const haveCards = computed(() => cards.value.filter(ownedCount).length);
const totalOwnedCardsCount = computed(() => manifest.cards.filter(ownedCount).length);
const visibleCards = computed(() =>
  cards.value.filter(
    (c) => cardFilter.value === "all" || (cardFilter.value === "owned" ? ownedCount(c) > 0 : !ownedCount(c)),
  ),
);

const shortName = (name: string) =>
  name.replace(/^A-SOUL\s*[·\s]\s*/, "").replace(/收藏集$/, "").trim() || name;
const poolTabs = computed(() =>
  manifest.series.map((p) => ({
    id: p.id,
    label: shortName(p.name),
  })),
);

const cardGroups = computed(() => {
  const hiddenAll = cards.value.filter((c) => c.tier !== "normal");
  const normalAll = cards.value.filter((c) => c.tier === "normal");
  return [
    {
      id: "hidden",
      name: "Epic · 隐藏款",
      owned: hiddenAll.filter(ownedCount).length,
      total: hiddenAll.length,
      cards: visibleCards.value
        .filter((c) => c.tier !== "normal")
        .sort((a, b) => Number(b.tier === "big") - Number(a.tier === "big")),
    },
    {
      id: "normal",
      name: "Rare · 普通款",
      owned: normalAll.filter(ownedCount).length,
      total: normalAll.length,
      cards: visibleCards.value.filter((c) => c.tier === "normal"),
    },
  ].filter((g) => g.cards.length > 0);
});

function probability(c: ManifestCard) {
  const mass = { big: 0.5, small: 4.5, normal: 95 }[c.tier];
  return (mass / cards.value.filter((x) => x.tier === c.tier).length).toFixed(2) + "%";
}

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
  <div class="collection-page">
    <!-- Top mode switcher: Emote Codex vs Card Album -->
    <div class="top-row">
      <div class="mode-switch" role="tablist" aria-label="图鉴类别">
        <button type="button" :class="{ on: mode === 'emotes' }" @click="mode = 'emotes'">
          <Icon name="smile" :size="14" />
          <span>表情图鉴</span>
          <small>{{ totalOwnedEmotesCount }}/{{ totalEmotesCount }}</small>
          <i v-if="boxes > 0" class="badge-dot">{{ boxes }}</i>
        </button>
        <button type="button" :class="{ on: mode === 'cards' }" @click="mode = 'cards'">
          <Icon name="book" :size="14" />
          <span>典藏卡册</span>
          <small>{{ totalOwnedCardsCount }}/{{ manifest.cards.length }}</small>
          <i v-if="tickets > 0" class="badge-dot">{{ tickets }}</i>
        </button>
      </div>

      <div class="tabs-bar">
        <SegTabs
          v-if="mode === 'emotes'"
          v-model="charTab"
          :tabs="charTabs"
          label="角色筛选"
        />
        <SegTabs
          v-else
          v-model="selectedSeries"
          :tabs="poolTabs"
          :disabled="busy || cardDrops.length > 0"
          label="收藏集卡池"
        />
      </div>
    </div>

    <!-- EMOTE CODEX VIEW (Matching WuwaTappo Image 1: Clean Rare / Common groups, no 21 pack headers!) -->
    <template v-if="mode === 'emotes'">
      <div class="filters">
        <div class="filter-pills">
          <button
            v-for="f in [{ id: 'all', label: '全部' }, { id: 'owned', label: '已拥有' }, { id: 'missing', label: '未拥有' }] as const"
            :key="f.id" type="button" :class="{ on: emoteOwnFilter === f.id }" @click="emoteOwnFilter = f.id"
          >
            {{ f.label }}
          </button>
        </div>

        <select v-model="setFilter" class="set-select" aria-label="按表情包专辑筛选">
          <option value="all">全部专辑 ({{ availableSets.length }}套)</option>
          <option v-for="s in availableSets" :key="s.id" :value="s.id">
            {{ s.name }} ({{ s.emotes.filter((e) => ownsEmote(e.key, collection.owned)).length }}/{{ s.emotes.length }})
          </option>
        </select>

        <input v-model="emoteQuery" class="ui-input search-input" placeholder="搜索表情…" aria-label="搜索表情" />
      </div>

      <div class="wall ui-scroll">
        <section v-for="group in emoteGroups" :key="group.id" class="group">
          <button type="button" class="group-head" @click="emoteCollapsed[group.id] = !emoteCollapsed[group.id]">
            <span class="group-title">{{ group.name }}</span>
            <span class="group-count">({{ group.owned }}/{{ group.total }})</span>
            <svg class="caret" :class="{ shut: emoteCollapsed[group.id] }" viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
              <path d="M3.5 5.5L8 10.5l4.5-5z" fill="currentColor" />
            </svg>
          </button>

          <div v-show="!emoteCollapsed[group.id]" class="emote-grid">
            <button
              v-for="e in group.items" :key="e.key" type="button"
              class="sq-card emote-tile"
              :class="[e.rarity, { owned: e.owned, locked: !e.owned }]"
              :title="`${e.name}（${e.setName}）· ${e.owned ? '已拥有' : '点击可使用碎片兑换'}`"
              @click="selectedEmote = getItem(`emote:${e.key}`) ?? null; actionNote = ''"
            >
              <span class="well emote-well">
                <img :src="assetUrl(e.img)" :alt="e.name" loading="lazy" draggable="false" />
                <span class="corner-badge" aria-hidden="true"><Icon name="smile" :size="9" /></span>
              </span>
              <b class="name">{{ e.name }}</b>
            </button>
          </div>
        </section>

        <p v-if="!emoteGroups.length" class="empty">当前筛选下没有匹配的表情</p>
      </div>

      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <footer class="drawbar">
        <div class="ticket">
          <span class="ticket-icon"><Icon name="box" :size="18" /></span>
          <div>
            <span class="ticket-main"><b>{{ boxes }}</b> 箱可开</span>
            <small>今日 {{ status?.boxesToday ?? 0 }}/{{ status?.dailyCap ?? 10 }} 箱</small>
          </div>
        </div>

        <div class="pity">
          <div class="pity-head">
            <span>敲击 <b>{{ status?.progress.taps ?? 0 }}</b>/{{ status?.progress.tapsPerBox ?? 600 }} · 活跃 {{ status?.progress.minutes ?? 0 }}/{{ status?.progress.minutesPerBox ?? 10 }}分</span>
            <small class="shard-badge"><Icon name="shard" :size="12" /> <b>{{ shards }}</b> 碎片 · 点击未解锁表情可兑换</small>
          </div>
          <div class="ui-bar"><i :style="{ width: `${tapPct}%` }"></i></div>
        </div>

        <div class="draw-actions">
          <button type="button" class="ui-btn" :disabled="busy || !online || !boxes" @click="openBoxBatch(false)">
            {{ busy ? "开启中…" : "开一箱" }}
          </button>
          <button type="button" class="ui-btn primary" :disabled="busy || !online || !boxes" @click="openBoxBatch(true)">
            全部开启 <span v-if="boxes">×{{ boxes }}</span>
          </button>
        </div>
      </footer>
    </template>

    <!-- CARD ALBUM VIEW (6 columns: 6 Epic hidden on 1 row + 18 Rare normal on 3 rows!) -->
    <template v-else>
      <div class="filters">
        <div class="filter-pills">
          <button
            v-for="f in [{ id: 'all', label: '全部' }, { id: 'owned', label: '已拥有' }, { id: 'missing', label: '未拥有' }] as const"
            :key="f.id" type="button" :class="{ on: cardFilter === f.id }" @click="cardFilter = f.id"
          >
            {{ f.label }}
          </button>
        </div>
        <span class="progress-tag">本套已收集 <b>{{ haveCards }}</b> / {{ cards.length }}</span>
      </div>

      <div class="wall ui-scroll">
        <section v-for="group in cardGroups" :key="group.id" class="group">
          <button type="button" class="group-head" @click="cardCollapsed[group.id] = !cardCollapsed[group.id]">
            <span class="group-title">{{ group.name }}</span>
            <span class="group-count">({{ group.owned }}/{{ group.total }})</span>
            <svg class="caret" :class="{ shut: cardCollapsed[group.id] }" viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
              <path d="M3.5 5.5L8 10.5l4.5-5z" fill="currentColor" />
            </svg>
          </button>

          <div v-show="!cardCollapsed[group.id]" class="card-grid">
            <button
              v-for="c in group.cards" :key="c.id" type="button"
              class="sq-card" :class="[c.tier, { owned: ownedCount(c) > 0, locked: !ownedCount(c) }]"
              :title="`${c.name}（概率 ${probability(c)}）`"
              @click="detail = getItem(`card:${c.id}`) ?? null"
            >
              <span class="well">
                <img :src="assetUrl(c.thumb)" :alt="c.name" loading="lazy" draggable="false" />
                <i v-if="c.tier !== 'normal'" class="tier-pill">{{ c.tier === "big" ? "大隐藏" : "小隐藏" }}</i>
                <b v-if="ownedCount(c)" class="count-pill">×{{ ownedCount(c) }}</b>
                <span class="corner-badge" :class="{ video: !!c.video }" aria-hidden="true">
                  <Icon :name="c.video ? 'play' : 'person'" :size="9" />
                </span>
              </span>
              <b class="name">{{ shortName(c.name) }}</b>
            </button>
          </div>
        </section>

        <p v-if="!visibleCards.length" class="empty">当前筛选下暂无卡牌</p>
      </div>

      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <footer class="drawbar">
        <div class="ticket">
          <span class="ticket-icon"><Icon name="book" :size="18" /></span>
          <div>
            <span class="ticket-main"><b>{{ tickets }}</b> 次可抽</span>
            <small>{{ online ? `下一抽 ${countdown}` : "连接服务器后累计在线时长" }}</small>
          </div>
        </div>

        <div class="pity">
          <div class="pity-head">
            <span>大隐藏保底 <b>{{ status?.draw?.pity ?? 0 }}</b> / 400</span>
            <small>大隐藏 0.5% · 小隐藏 4.5%</small>
          </div>
          <div class="ui-bar"><i :style="{ width: `${(status?.draw?.pity ?? 0) / 4}%` }"></i></div>
        </div>

        <div class="draw-actions">
          <button type="button" class="ui-btn" :disabled="busy || !online || !tickets" @click="draw(false)">
            {{ busy ? "抽取中…" : "抽一次" }}
          </button>
          <button type="button" class="ui-btn primary" :disabled="busy || !online || !tickets" @click="draw(true)">
            全部抽取 <span v-if="tickets">×{{ tickets }}</span>
          </button>
        </div>
      </footer>
    </template>

    <!-- Emote detail / shard crafting modal -->
    <Modal v-if="selectedEmote" :title="selectedEmote.name" @close="selectedEmote = null">
      <div class="emote-detail">
        <div class="detail-well">
          <ItemArt :item="selectedEmote" :size="128" :locked="!selectedEmoteOwned" />
        </div>
        <h3>{{ selectedEmote.name }}</h3>
        <p class="detail-sub">{{ selectedEmote.group }}</p>
        <small v-if="actionNote" class="note">{{ actionNote }}</small>
        <div v-if="selectedEmoteOwned" class="buttons">
          <button type="button" class="ui-btn" @click="toggleFav(selectedEmote)">
            {{ settings.favorites.includes(selectedEmote.ref) ? "移出预设" : "装入预设" }}
          </button>
          <button type="button" class="ui-btn primary" @click="fireSelectedEmote(selectedEmote)">发表情</button>
        </div>
        <template v-else>
          <span class="craft-info">开宝箱获得 · 或使用 {{ selectedEmoteCost }} 碎片兑换（当前 {{ shards }} 碎片）</span>
          <button
            type="button" class="ui-btn primary"
            :disabled="busy || !online || selectedEmoteCost === null || shards < selectedEmoteCost"
            @click="craftSelectedEmote"
          >
            {{ selectedEmoteCost !== null && shards < selectedEmoteCost ? `还差 ${selectedEmoteCost - shards} 碎片` : `兑换（${selectedEmoteCost} 碎片）` }}
          </button>
        </template>
      </div>
    </Modal>

    <ItemDetail v-if="detail" :item="detail" @close="detail = null" />
    <CardReveal v-if="cardDrops.length" :drops="cardDrops" :remaining="pending" @close="collect" />
    <RevealModal v-if="boxDrops.length" :drops="boxDrops" @close="boxDrops = []" />
  </div>
</template>

<style scoped>
.collection-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 6px 20px 12px;
}

.top-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  flex: none;
}
.mode-switch {
  display: inline-flex;
  padding: 3px;
  border-radius: 999px;
  background: var(--paper-2);
  border: 1.5px solid var(--tile-border);
  gap: 3px;
  flex: none;
}
.mode-switch button {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 11px;
  border-radius: 999px;
  border: 1.5px solid transparent;
  background: transparent;
  color: var(--ink-2);
  font: 800 12px var(--font);
  cursor: pointer;
  white-space: nowrap;
}
.mode-switch button small {
  font-size: 10.5px;
  font-weight: 700;
  opacity: 0.8;
}
.mode-switch button.on {
  background: linear-gradient(180deg, #FFB596 0%, var(--accent) 100%);
  border-color: var(--accent-deep);
  color: var(--on-accent);
  box-shadow: 0 2px 0 var(--accent-deep);
}
.badge-dot {
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  box-sizing: border-box;
  border-radius: 999px;
  background: #FFF6EC;
  color: #7A3B1E;
  border: 1px solid #B85832;
  font-style: normal;
  font-size: 10px;
  font-weight: 900;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.tabs-bar {
  flex: 1;
  min-width: 0;
}

.filters {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex: none;
  flex-wrap: wrap;
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
.set-select {
  height: 25px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1.5px solid var(--tile-border);
  background: var(--card);
  color: var(--ink);
  font: 700 11.5px var(--font);
  cursor: pointer;
  outline: none;
}
.set-select:focus {
  border-color: var(--accent);
}
.search-input {
  margin-left: auto;
  width: 144px;
  height: 25px;
  font-size: 11.5px;
}
.progress-tag {
  margin-left: auto;
  font-size: 12px;
  font-weight: 700;
  color: var(--ink-2);
}
.progress-tag b {
  color: var(--accent-deep);
}

.wall {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 2px 4px 10px 2px;
}
.group + .group {
  margin-top: 12px;
}
.group-head {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin: 0 0 6px 2px;
  padding: 2px 6px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ink-2);
  font: 800 13px var(--font);
  cursor: pointer;
}
.group-head:hover {
  background: rgba(239, 224, 206, 0.6);
  color: var(--ink);
}
.group-count {
  font-weight: 700;
  font-size: 12px;
  color: var(--ink-2);
}
.caret {
  color: var(--ink-2);
  transition: transform 160ms ease;
}
.caret.shut {
  transform: rotate(-90deg);
}

/* Dense 8-column Emote Codex grid & 6-column Card Album grid */
.emote-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(76px, 1fr));
  gap: 8px;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 9px;
}
.sq-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 4px 5px;
  margin: 0;
  box-sizing: border-box;
  border-radius: 15px;
  background: var(--tile-frame);
  border: 1.5px solid var(--tile-border);
  box-shadow: 0 2px 0 var(--tile-lip);
  cursor: pointer;
  font: inherit;
  color: var(--ink);
  transition: transform 120ms cubic-bezier(0.34, 1.56, 0.64, 1), border-color 140ms, box-shadow 140ms;
}
.sq-card:hover {
  transform: translateY(-2px);
  border-color: var(--accent);
}
.sq-card.owned {
  background: #FFF8F0;
  border-color: #F4B99A;
  box-shadow: 0 2px 0 #DF9B78;
}
.sq-card.big.owned {
  border-color: var(--accent);
  box-shadow: 0 2px 0 var(--accent-deep), 0 0 12px rgba(var(--accent-rgb), 0.45);
}

.well {
  position: relative;
  width: 100%;
  aspect-ratio: 1 / 0.94;
  border-radius: 11px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.22) 0 8px, transparent 8px 18px),
    var(--rar-rare-bg);
}
.well.emote-well {
  aspect-ratio: 1;
  padding: 6px;
  box-sizing: border-box;
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.22) 0 8px, transparent 8px 18px),
    var(--rar-common-bg);
}
.sq-card.rare .well.emote-well {
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.24) 0 8px, transparent 8px 18px),
    var(--rar-epic-bg);
}
.sq-card.big .well,
.sq-card.small .well {
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.24) 0 8px, transparent 8px 18px),
    var(--rar-epic-bg);
}
.well img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 16%;
  display: block;
  transition: transform 160ms;
}
.well.emote-well img {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  margin: auto;
}
.sq-card:hover .well img {
  transform: scale(1.05);
}
.sq-card.locked .well img {
  filter: saturate(0.48) contrast(0.9);
  opacity: 0.5;
}
.sq-card.locked .name {
  color: var(--ink-3);
}

.tier-pill {
  position: absolute;
  left: 4px;
  top: 4px;
  padding: 1px 5px;
  border-radius: 999px;
  background: linear-gradient(180deg, #FFB596, var(--accent));
  color: var(--on-accent);
  border: 1px solid rgba(120, 50, 20, 0.25);
  font-size: 9px;
  font-style: normal;
  font-weight: 800;
}
.sq-card.small .tier-pill {
  background: rgba(255, 245, 234, 0.92);
  color: #8A5132;
}
.count-pill {
  position: absolute;
  right: 4px;
  top: 4px;
  padding: 1px 5px;
  border-radius: 999px;
  background: rgba(92, 59, 40, 0.78);
  color: #FFF9F2;
  font-size: 9px;
  font-weight: 800;
}
.corner-badge {
  position: absolute;
  left: 3px;
  bottom: 3px;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: var(--tile-frame);
  border: 1px solid var(--tile-border);
  color: #B48967;
  display: flex;
  align-items: center;
  justify-content: center;
}
.corner-badge.video {
  background: #FFF3E8;
  border-color: #F2B28E;
  color: var(--accent-deep);
}

.name {
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

.drawbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 4px;
  padding: 7px 14px;
  border-radius: 16px;
  background: var(--tile-frame);
  border: 1.5px solid var(--tile-border);
  box-shadow: 0 2px 0 var(--tile-lip);
  flex: none;
}
.ticket {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}
.ticket-icon {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: var(--accent-soft);
  border: 1.5px solid #F3B391;
  color: var(--accent-deep);
  display: flex;
  align-items: center;
  justify-content: center;
}
.ticket > div {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.ticket-main {
  font-size: 11.5px;
  font-weight: 700;
  color: var(--ink-2);
}
.ticket-main b {
  font-size: 16px;
  font-weight: 900;
  color: var(--ink);
  margin-right: 2px;
}
.ticket small {
  font-size: 10.5px;
  color: var(--ink-3);
}
.pity {
  flex: 1;
  max-width: 340px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pity-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-2);
}
.pity-head b {
  color: var(--ink);
}
.pity-head small {
  font-size: 10.5px;
  color: var(--ink-3);
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.shard-badge :deep(.icon) {
  color: var(--accent-deep);
}
.draw-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.emote-detail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
}
.detail-well {
  padding: 12px;
  border-radius: 22px;
  background: var(--tile-frame);
  border: 2px solid var(--tile-border);
}
.emote-detail h3 {
  margin: 4px 0 0;
  font-size: 17px;
  font-weight: 800;
}
.detail-sub {
  margin: 0;
  font-size: 12px;
  color: var(--ink-2);
}
.note {
  color: var(--accent-deep);
  font-weight: 700;
}
.craft-info {
  font-size: 12px;
  color: var(--ink-2);
}
.buttons {
  display: flex;
  gap: 10px;
  margin-top: 4px;
}

.empty {
  color: var(--ink-3);
  padding: 28px 0;
  text-align: center;
  font-size: 13px;
  font-weight: 700;
}
.error {
  margin: 3px 0;
  color: var(--bad);
  font-size: 12px;
  font-weight: 700;
}

@media (max-width: 760px) {
  .top-row {
    flex-direction: column;
    align-items: stretch;
  }
  .card-grid {
    grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  }
  .drawbar {
    flex-wrap: wrap;
    gap: 10px;
  }
}
</style>
