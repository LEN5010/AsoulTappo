<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { manifest } from "../manifest";
import { assetUrl } from "../asset";
import { craftCost, getItem, ownsEmote, type Item } from "../items";
import {
  boxes,
  collection,
  craftItem,
  error,
  online,
  openBoxes,
  shards,
  status,
} from "../stores/player";
import { settings } from "../stores/settings";
import { sendEmote } from "../stores/room";
import { ui } from "../stores/ui";
import type { Drop } from "../net/api";
import RevealModal from "./RevealModal.vue";
import Modal from "../ui/Modal.vue";
import ItemArt from "../ui/ItemArt.vue";
import SegTabs from "../ui/SegTabs.vue";
import Icon from "../ui/Icon.vue";
import { rise } from "../ui/motion";

const charTab = ref<string>("all");
const setFilter = ref<string>("all");
const emoteOwnFilter = ref<"all" | "owned" | "missing">("all");
const wall = ref<HTMLElement>();
watch([charTab, setFilter, emoteOwnFilter], () => nextTick(() => rise(wall.value)));
const emoteQuery = ref("");
const emoteCollapsed = ref<Record<string, boolean>>({});

const emoteOwners = computed(() => [...new Set(manifest.emoteSets.map((s) => s.character))]);
const charTabs = computed(() => [
  { id: "all", label: "全部" },
  ...emoteOwners.value.map((c) => ({ id: c, label: c })),
]);

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
    .sort((a, b) => Number(b.owned) - Number(a.owned)),
);

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

const totalEmotesCount = computed(() => allEmotesInScope.value.length);
const totalOwnedEmotesCount = computed(() => allEmotesInScope.value.filter((e) => e.owned).length);

const selectedEmote = ref<Item | null>(null);
const selectedEmoteOwned = computed(() =>
  selectedEmote.value ? ownsEmote(selectedEmote.value.ref, collection.owned) : false,
);
const selectedEmoteCost = computed(() => (selectedEmote.value ? craftCost(selectedEmote.value) : null));
const actionNote = ref("");
const boxDrops = ref<Drop[]>([]);
const busy = ref(false);

watch(
  () => ui.craftTarget,
  (id) => {
    if (id) {
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
</script>

<template>
  <div class="collection-page">
    <div class="tabs-bar">
      <SegTabs v-model="charTab" :tabs="charTabs" label="角色筛选" />
    </div>

    <div class="filters">
      <div class="filter-pills">
        <button
          v-for="f in [{ id: 'all', label: '全部' }, { id: 'owned', label: '已拥有' }, { id: 'missing', label: '未拥有' }] as const"
          :key="f.id" type="button" class="ui-chip" :class="{ on: emoteOwnFilter === f.id }" @click="emoteOwnFilter = f.id"
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

      <span class="progress-tag">已解锁 <b>{{ totalOwnedEmotesCount }}</b> / {{ totalEmotesCount }}</span>

      <input v-model="emoteQuery" class="ui-input search-input" placeholder="搜索表情…" aria-label="搜索表情" />
    </div>

    <div ref="wall" class="wall ui-scroll">
      <section v-for="group in emoteGroups" :key="group.id" class="group">
        <button type="button" class="group-head" data-rise @click="emoteCollapsed[group.id] = !emoteCollapsed[group.id]">
          <i aria-hidden="true"></i>
          <span class="group-title">{{ group.name }}</span>
          <span class="group-count"><b>{{ group.owned }}</b>/{{ group.total }}</span>
          <svg class="caret" :class="{ shut: emoteCollapsed[group.id] }" viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
            <path d="M3.5 5.5L8 10.5l4.5-5z" fill="currentColor" />
          </svg>
        </button>

        <div v-show="!emoteCollapsed[group.id]" class="emote-grid">
          <button
            v-for="e in group.items" :key="e.key" type="button"
            class="ui-tile emote-tile"
            :class="[e.rarity, { locked: !e.owned }]"
            :title="`${e.name}（${e.setName}）· ${e.owned ? '已拥有' : '点击可使用碎片兑换'}`"
            data-rise
            @click="selectedEmote = getItem(`emote:${e.key}`) ?? null; actionNote = ''"
          >
            <span class="ui-frame ui-well">
              <img :src="assetUrl(e.img)" :alt="e.name" loading="lazy" decoding="async" draggable="false" />
            </span>
            <b class="ui-tile-name">{{ e.name }}</b>
          </button>
        </div>
      </section>

      <p v-if="!emoteGroups.length" class="ui-empty">当前筛选下没有匹配的表情</p>
    </div>

    <p v-if="error" class="ui-error" role="alert">{{ error }}</p>

    <footer class="drawbar ui-frame ui-ring">
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
          <small class="shard-badge"><Icon name="shard" :size="12" /> <b>{{ shards }}</b> 碎片</small>
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

    <!-- Emote detail / shard crafting modal -->
    <Modal v-if="selectedEmote" :title="selectedEmote.name" @close="selectedEmote = null">
      <div class="emote-detail">
        <div class="detail-well ui-frame">
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

    <RevealModal v-if="boxDrops.length" :drops="boxDrops" @close="boxDrops = []" />
  </div>
</template>

<style scoped>
.collection-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 0 20px 12px 16px;
}
.tabs-bar {
  flex: none;
  margin-bottom: 8px;
}

.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  flex: none;
  flex-wrap: wrap;
}
.filter-pills {
  display: flex;
  gap: 5px;
  padding-left: 3px;
}
.set-select {
  height: 26px;
  padding: 0 8px;
  border: 0;
  border-bottom: 2px solid var(--line-2);
  border-radius: 0;
  background: var(--accent-tint);
  color: var(--ink);
  font: 700 12px var(--font);
  cursor: pointer;
  outline: none;
}
.set-select:focus {
  border-color: var(--accent-deep);
}
.progress-tag {
  font-size: 12px;
  font-weight: 700;
  color: var(--ink-2);
}
.progress-tag b {
  font: italic 800 17px/1 var(--font-latin);
  color: var(--accent-deep);
}
.search-input {
  margin-left: auto;
  width: 140px;
  height: 26px;
  padding: 0 10px;
  font-size: 12px;
}

.wall {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 6px;
}
.group + .group {
  margin-top: 10px;
}
.group-head {
  position: sticky;
  top: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  margin: 0 0 8px;
  padding: 5px 0;
  box-sizing: border-box;
  border: 0;
  box-shadow: 0 2px 0 var(--line);
  background: rgba(255, 255, 255, 0.95);
  color: var(--ink);
  font: 16px/1 var(--font-display);
  cursor: pointer;
}
.group-head i {
  width: 7px;
  height: 14px;
  background: var(--accent);
  transform: skewX(var(--skew));
}
.group-count {
  font: italic 800 14px/1 var(--font-latin);
  color: var(--ink-3);
}
.group-count b {
  font: inherit;
  color: var(--accent-deep);
}
.caret {
  margin-left: auto;
  color: var(--ink-2);
  transition: transform 260ms var(--ease-out);
}
.caret.shut {
  transform: rotate(-90deg);
}

.emote-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(76px, 1fr));
  gap: 12px 10px;
  padding: 2px 4px 2px 0;
}
.emote-tile.rare .ui-well {
  background: var(--rar-epic-bg);
}

.drawbar {
  --cut: 14px;
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 6px;
  padding: 8px 14px;
  background: var(--accent-tint);
  flex: none;
}
.ticket {
  display: flex;
  align-items: center;
  gap: 9px;
  flex: none;
}
.ticket-icon {
  width: 34px;
  height: 32px;
  background: var(--accent);
  color: var(--on-accent);
  transform: skewX(var(--skew));
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
  font-size: 12px;
  font-weight: 700;
  color: var(--ink-2);
}
.ticket-main b {
  font: italic 800 22px/1 var(--font-latin);
  color: var(--ink);
  margin-right: 2px;
}
.ticket small {
  font-size: 10.5px;
  color: var(--ink-3);
}
.pity {
  flex: 1;
  max-width: 360px;
  display: flex;
  flex-direction: column;
  gap: 5px;
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
  gap: 10px;
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
  --cut: 16px;
  padding: 14px;
  background: var(--dots) 0 0 / 9px 9px, var(--accent-tint);
}
.emote-detail h3 {
  margin: 4px 0 0;
  font: 400 22px/1.1 var(--font-display);
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
  gap: 12px;
  margin-top: 4px;
}
</style>
