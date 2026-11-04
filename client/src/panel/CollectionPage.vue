<script setup lang="ts">
// Emote dex: a wall of albums that open onto their stickers. A search query lists matches across albums.
import { computed, nextTick, ref, watch } from "vue";
import { characterColor, manifest, type ManifestEmoteSet } from "../manifest";
import { assetUrl } from "../asset";
import { craftCost, getItem, ownsEmote, RARITY_LABEL, type Item } from "../items";
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
import RevealScene from "./RevealScene.vue";
import Modal from "../ui/Modal.vue";
import ItemArt from "../ui/ItemArt.vue";
import SegTabs from "../ui/SegTabs.vue";
import FilterChips from "../ui/FilterChips.vue";
import Icon from "../ui/Icon.vue";
import { rise } from "../ui/motion";

type OwnFilter = "all" | "owned" | "missing";
const OWN_FILTERS = [
  { id: "all", label: "全部" },
  { id: "owned", label: "已拥有" },
  { id: "missing", label: "未拥有" },
] as const;

const charTab = ref("all");
const albumId = ref("");
const ownFilter = ref<OwnFilter>("all");
const query = ref("");
const wall = ref<HTMLElement>();

const charTabs = computed(() => [
  { id: "all", label: "全部" },
  ...[...new Set(manifest.emoteSets.map((s) => s.character))].map((c) => ({ id: c, label: c })),
]);

const sets = computed(() =>
  manifest.emoteSets.filter((s) => charTab.value === "all" || s.character === charTab.value),
);
const stickersOf = (set: ManifestEmoteSet) =>
  set.emotes.map((e) => ({ ...e, setName: set.name, rarity: set.rarity, owned: ownsEmote(e.key, collection.owned) }));

const albums = computed(() =>
  sets.value
    .map((set) => {
      const stickers = stickersOf(set);
      const owned = stickers.filter((e) => e.owned);
      return {
        set,
        owned: owned.length,
        total: stickers.length,
        collage: [...owned, ...stickers.filter((e) => !e.owned)].slice(0, 3),
      };
    })
    .sort((a, b) => Number(b.set.rarity !== "common") - Number(a.set.rarity !== "common")),
);

const album = computed(() => manifest.emoteSets.find((s) => s.id === albumId.value) ?? null);
const searching = computed(() => !!query.value.trim());
const showWall = computed(() => !album.value && !searching.value);

const tiles = computed(() => {
  const q = query.value.trim();
  const scope = searching.value ? sets.value : album.value ? [album.value] : [];
  const list = scope
    .flatMap(stickersOf)
    .filter((e) => !q || e.name.includes(q) || e.setName.includes(q))
    .filter((e) => ownFilter.value === "all" || e.owned === (ownFilter.value === "owned"));
  return searching.value ? list.sort((a, b) => Number(b.owned) - Number(a.owned)) : list;
});

const progress = computed(() => {
  const stickers = (album.value && !searching.value ? [album.value] : sets.value).flatMap(stickersOf);
  return { owned: stickers.filter((e) => e.owned).length, total: stickers.length };
});

let wallTop = 0;
function openAlbum(id: string) {
  wallTop = wall.value?.scrollTop ?? 0;
  albumId.value = id;
}
watch(charTab, () => {
  albumId.value = "";
  wallTop = 0;
});
watch(albumId, () => (ownFilter.value = "all"));
watch([charTab, albumId, ownFilter, searching], () =>
  nextTick(() => {
    if (wall.value) wall.value.scrollTop = showWall.value ? wallTop : 0;
    rise(wall.value);
  }),
);

const selectedEmote = ref<Item | null>(null);
const selectedEmoteOwned = computed(() =>
  selectedEmote.value ? ownsEmote(selectedEmote.value.ref, collection.owned) : false,
);
const selectedEmoteCount = computed(() => (selectedEmote.value ? collection.owned[selectedEmote.value.id] ?? 0 : 0));
const selectedEmoteCost = computed(() => (selectedEmote.value ? craftCost(selectedEmote.value) : null));
const actionNote = ref("");
const opening = ref(0);
const busy = ref(false);

function inspect(key: string) {
  selectedEmote.value = getItem(`emote:${key}`) ?? null;
  actionNote.value = "";
}

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

async function loadBoxes(): Promise<Drop[] | null> {
  const results: Drop[] = [];
  let rem = opening.value;
  while (rem > 0) {
    const batch = await openBoxes(Math.min(10, rem));
    if (!batch?.length) break;
    results.push(...batch);
    rem -= batch.length;
  }
  return results.length ? results : null;
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
  else actionNote.value = "预设已满 8/8";
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
    <SegTabs v-model="charTab" class="tabs-bar" :tabs="charTabs" label="角色筛选" />

    <div class="head">
      <template v-if="album && !searching">
        <button type="button" class="ui-btn small" @click="albumId = ''"><Icon name="back" :size="13" />全部专辑</button>
        <h3 class="album-title">{{ album.name }}</h3>
      </template>
      <FilterChips v-if="!showWall" v-model="ownFilter" :options="OWN_FILTERS" label="持有筛选" />
      <span class="progress">已解锁 <b>{{ progress.owned }}</b> / {{ progress.total }}</span>
      <input v-model="query" class="ui-input search-input" placeholder="搜索表情…" aria-label="搜索表情" />
    </div>

    <div ref="wall" class="wall ui-scroll">
      <div v-if="showWall" class="albums">
        <button
          v-for="a in albums" :key="a.set.id" type="button"
          class="album ui-tile" :class="a.set.rarity" :title="a.set.name" data-rise
          @click="openAlbum(a.set.id)"
        >
          <span class="collage ui-frame ui-well">
            <img
              v-for="e in a.collage" :key="e.key" :class="{ miss: !e.owned }"
              :src="assetUrl(e.img)" alt="" loading="lazy" decoding="async" draggable="false"
            />
            <span class="flags">
              <i v-if="a.set.rarity !== 'common'" class="ui-tag">{{ RARITY_LABEL[a.set.rarity] }}</i>
              <i v-if="a.owned === a.total" class="ui-tag gold">集齐</i>
            </span>
          </span>
          <span class="album-meta">
            <b class="album-name"><i :style="{ background: characterColor(a.set.character) }" aria-hidden="true"></i>{{ a.set.name }}</b>
            <span class="album-count"><b>{{ a.owned }}</b>/{{ a.total }}</span>
          </span>
          <span class="ui-bar album-bar"><i :style="{ width: `${(a.owned / a.total) * 100}%` }"></i></span>
        </button>
      </div>

      <template v-else>
        <div class="emote-grid">
          <button
            v-for="e in tiles" :key="e.key" type="button"
            class="ui-tile" :class="[e.rarity, { locked: !e.owned }]"
            :title="`${e.name}（${e.setName}）`" data-rise
            @click="inspect(e.key)"
          >
            <span class="ui-frame ui-well">
              <img :src="assetUrl(e.img)" :alt="e.name" loading="lazy" decoding="async" draggable="false" />
            </span>
            <b class="ui-tile-name">{{ e.name }}</b>
          </button>
        </div>
        <p v-if="!tiles.length" class="ui-empty">没有匹配的表情</p>
      </template>
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
        <button type="button" class="ui-btn" :disabled="!!opening || !online || !boxes" @click="opening = 1">开一箱</button>
        <button type="button" class="ui-btn primary" :disabled="!!opening || !online || !boxes" @click="opening = boxes">
          全部开启 <span v-if="boxes">×{{ boxes }}</span>
        </button>
      </div>
    </footer>

    <Modal v-if="selectedEmote" :title="selectedEmote.name" @close="selectedEmote = null">
      <div class="emote-detail">
        <div class="detail-well ui-frame">
          <ItemArt :item="selectedEmote" :size="128" :locked="!selectedEmoteOwned" />
        </div>
        <h3>{{ selectedEmote.name }}</h3>
        <p class="detail-sub">{{ selectedEmote.group }}</p>
        <small v-if="actionNote" class="note">{{ actionNote }}</small>
        <template v-if="selectedEmoteOwned">
          <p class="held">已拥有<template v-if="selectedEmoteCount > 1"> ×{{ selectedEmoteCount }}</template></p>
          <div class="buttons">
            <button type="button" class="ui-btn" @click="toggleFav(selectedEmote)">
              {{ settings.favorites.includes(selectedEmote.ref) ? "移出预设" : "装入预设" }}
            </button>
            <button type="button" class="ui-btn primary" @click="fireSelectedEmote(selectedEmote)">发表情</button>
          </div>
        </template>
        <template v-else>
          <p class="held"><Icon name="shard" :size="13" />持有 {{ shards }} 碎片</p>
          <button
            v-if="selectedEmoteCost !== null" type="button" class="ui-btn primary"
            :disabled="busy || !online || shards < selectedEmoteCost"
            @click="craftSelectedEmote"
          >
            {{ shards < selectedEmoteCost ? `还差 ${selectedEmoteCost - shards} 碎片` : `兑换（${selectedEmoteCost} 碎片）` }}
          </button>
        </template>
      </div>
    </Modal>

    <RevealScene v-if="opening" kind="box" :load="loadBoxes" @close="opening = 0" />
  </div>
</template>

<style scoped>
.collection-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 8px 20px 12px 16px;
}
.tabs-bar {
  flex: none;
  margin-bottom: 8px;
}

.head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 28px;
  margin-bottom: 10px;
}
.album-title {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 400 var(--fs-section)/1.2 var(--font-display);
}
.progress {
  flex: none;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
  white-space: nowrap;
}
.progress b {
  font: italic 800 var(--fs-section)/1 var(--font-latin);
  color: var(--accent-deep);
}
.search-input {
  flex: none;
  margin-left: auto;
  width: 140px;
  height: 28px;
  padding: 0 10px;
  font-size: var(--fs-label);
}

.wall {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 6px;
}

.albums {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 16px 14px;
  padding: 2px 4px 6px 0;
}
.album {
  --well-ratio: 16 / 10;
  --cut: var(--cut-m);
  align-items: stretch;
}
.collage {
  padding: 0;
}
.collage img {
  position: absolute;
  width: 41%;
  aspect-ratio: 1;
  max-width: none;
  max-height: none;
  margin: 0;
}
.collage img:nth-of-type(1) {
  left: 4%;
  top: 28%;
  rotate: -8deg;
}
.collage img:nth-of-type(2) {
  left: 30%;
  top: 8%;
  rotate: 4deg;
}
.collage img:nth-of-type(3) {
  left: 56%;
  top: 30%;
  rotate: 9deg;
}
.collage img.miss {
  filter: var(--dim) var(--contour);
}
.album:hover .collage img.miss {
  filter: var(--contour);
}
.flags {
  position: absolute;
  left: 7px;
  top: 6px;
  z-index: 1;
  display: flex;
  gap: 6px;
}
.album-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 7px;
}
.album-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
  font-size: var(--fs-label);
  font-weight: 800;
}
.album-name i {
  display: inline-block;
  width: 4px;
  height: 11px;
  margin: 0 6px 0 2px;
  vertical-align: -1px;
  transform: skewX(var(--skew));
}
.album-count {
  flex: none;
  font: italic 800 var(--fs-label)/1 var(--font-latin);
  color: var(--ink-3);
}
.album-count b {
  font: inherit;
  color: var(--accent-deep);
}
.album-bar {
  height: 5px;
  margin: 5px 1px 0;
}

.emote-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(76px, 1fr));
  gap: 12px 10px;
  padding: 2px 4px 2px 0;
}

.drawbar {
  --cut: var(--cut-m);
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
  padding: 8px 14px;
  background: var(--surface);
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
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.ticket-main b {
  font: italic 800 var(--fs-heading)/1 var(--font-latin);
  color: var(--ink);
  margin-right: 2px;
}
.ticket small {
  font-size: var(--fs-caption);
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
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-2);
}
.pity-head b {
  color: var(--ink);
}
.pity-head small {
  font-size: var(--fs-caption);
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
  --cut: var(--cut-m);
  padding: 14px;
  background: var(--dots) 0 0 / 9px 9px, var(--surface);
}
.emote-detail h3 {
  margin: 4px 0 0;
  font: 400 var(--fs-heading)/1.1 var(--font-display);
}
.detail-sub {
  margin: 0;
  font-size: var(--fs-label);
  color: var(--ink-2);
}
.note {
  color: var(--accent-deep);
  font-weight: 700;
}
.held {
  margin: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.held :deep(.icon) {
  color: var(--accent-deep);
}
.buttons {
  display: flex;
  gap: 12px;
  margin-top: 4px;
}
</style>
