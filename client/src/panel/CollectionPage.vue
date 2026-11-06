<script setup lang="ts">
// The dex brings card albums, searchable emote sets and skins together.
import { computed, nextTick, ref, watch } from "vue";
import { characterColor, getCard, manifest, RARITY_ORDER, type ManifestCard, type ManifestEmoteSet, type Rarity } from "../manifest";
import { assetUrl } from "../asset";
import { getItem, ownsEmote, RARITY_LABEL, type Item } from "../items";
import { collection, error } from "../stores/player";
import { settings } from "../stores/settings";
import { sendEmote } from "../stores/room";
import { ui } from "../stores/ui";
import Modal from "../ui/Modal.vue";
import ItemArt from "../ui/ItemArt.vue";
import VirtualGrid from "../ui/VirtualGrid.vue";
import SegTabs from "../ui/SegTabs.vue";
import FilterChips from "../ui/FilterChips.vue";
import Icon from "../ui/Icon.vue";
import { poolName } from "../cards";
import CardAlbum, { type AlbumFilter } from "./CardAlbum.vue";
import CardDetail from "./CardDetail.vue";
import CraftAction from "../ui/CraftAction.vue";
import SkinAlbum from "./SkinAlbum.vue";
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
    .sort((a, b) => RARITY_ORDER.indexOf(b.set.rarity) - RARITY_ORDER.indexOf(a.set.rarity)),
);

const albumGroups = computed(() =>
  [...RARITY_ORDER].reverse()
    .map((rarity) => ({ rarity, albums: albums.value.filter((a) => a.set.rarity === rarity) }))
    .filter((group) => group.albums.length),
);
const collapsedGroups = ref(new Set<Rarity>());
function toggleGroup(rarity: Rarity) {
  if (collapsedGroups.value.has(rarity)) collapsedGroups.value.delete(rarity);
  else collapsedGroups.value.add(rarity);
}

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

const selectedItem = ref<Item | null>(null);
const selectedItemOwned = computed(() =>
  selectedItem.value ? selectedItem.value.starter || !!collection.owned[selectedItem.value.id] : false,
);
const selectedItemCount = computed(() => (selectedItem.value ? collection.owned[selectedItem.value.id] ?? 0 : 0));
const actionNote = ref("");

function inspect(key: string) {
  selectedItem.value = getItem(`emote:${key}`) ?? null;
  actionNote.value = "";
}

watch(
  () => ui.craftTarget,
  (id) => {
    if (id) {
      if (id.startsWith('card:')) detail.value = getCard(id.slice(5)) ?? null;
      else selectedItem.value = getItem(id) ?? null;
      actionNote.value = "";
      ui.craftTarget = "";
    }
  },
  { flush: 'post' },
);

function toggleFav(item: Item) {
  const at = settings.favorites.indexOf(item.ref);
  if (at >= 0) settings.favorites.splice(at, 1);
  else if (settings.favorites.length < 8) settings.favorites.push(item.ref);
  else actionNote.value = "快捷表情已满 8/8";
}

function fireSelectedEmote(item: Item) {
  sendEmote(item.ref);
  selectedItem.value = null;
}

const category = ref("card");
const CATEGORIES = [{ id: "card", label: "卡片" }, { id: "emote", label: "表情" }, { id: "skin", label: "皮肤" }];
const selectedSeries = ref("all");
const cardFilter = ref<AlbumFilter>("all");
const CARD_FILTERS = [{ id: "all", label: "全部" }, { id: "hidden", label: "隐藏款" }, { id: "owned", label: "已拥有" }, { id: "missing", label: "未拥有" }];
const cards = computed(() => manifest.cards.filter((c) => selectedSeries.value === "all" || c.series === selectedSeries.value));
const seriesCount = (list: ManifestCard[]) => `${list.filter((c) => collection.owned[`card:${c.id}`]).length}/${list.length}`;
const poolTabs = computed(() => [
  { id: "all", label: "全部", count: seriesCount(manifest.cards) },
  ...manifest.series.map((s) => ({ id: s.id, label: poolName(s.name), count: seriesCount(manifest.cards.filter((c) => c.series === s.id)) })),
]);
const detail = ref<ManifestCard | null>(null);
const detailFrom = ref<DOMRect>();
function inspectCard(card: ManifestCard, from?: DOMRect) { detail.value = card; detailFrom.value = from; }
if (ui.craftTarget) {
  const target = ui.craftTarget;
  ui.craftTarget = '';
  if (target.startsWith('card:')) detail.value = getCard(target.slice(5)) ?? null;
  else selectedItem.value = getItem(target) ?? null;
}
</script>

<template>
  <div class="collection-page">
    <div class="dex-bar">
      <SegTabs v-model="category" class="dex-kind" :tabs="CATEGORIES" label="图鉴分类" />
      <FilterChips v-if="category === 'card'" v-model="cardFilter" :options="CARD_FILTERS" label="卡片筛选" />
      <span v-else-if="category === 'emote'" class="progress">已解锁 <b>{{ progress.owned }}</b> / {{ progress.total }}</span>
    </div>
    <template v-if="category === 'card'">
      <SegTabs v-model="selectedSeries" plain :tabs="poolTabs" label="卡片系列" />
      <CardAlbum :cards="cards" :filter="cardFilter" @inspect="inspectCard" />
    </template>
    <SkinAlbum v-else-if="category === 'skin'" />
    <template v-else>
    <div class="emote-bar">
      <SegTabs v-model="charTab" plain class="tabs-bar" :tabs="charTabs" label="角色筛选" />
      <input v-model="query" class="ui-input search-input" placeholder="搜索表情…" aria-label="搜索表情" />
    </div>

    <div v-if="!showWall" class="head">
      <template v-if="album && !searching">
        <button type="button" class="ui-btn small" @click="albumId = ''"><Icon name="back" :size="13" />全部专辑</button>
        <h3 class="album-title">{{ album.name }}</h3>
      </template>
      <FilterChips v-model="ownFilter" :options="OWN_FILTERS" label="持有筛选" />
    </div>

    <div ref="wall" class="wall ui-scroll">
      <div v-if="showWall" class="album-groups">
        <section v-for="group in albumGroups" :key="group.rarity" class="rarity-group">
          <h3 class="group-heading">
            <button
              type="button" class="group-toggle"
              :aria-expanded="!collapsedGroups.has(group.rarity)" :aria-controls="`emote-group-${group.rarity}`"
              @click="toggleGroup(group.rarity)"
            >
              <span>{{ RARITY_LABEL[group.rarity] }}</span>
              <svg class="group-arrow" :class="{ expanded: !collapsedGroups.has(group.rarity) }" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M5 3.5 11 8 5 12.5Z" /></svg>
              <small>{{ group.albums.length }} 套</small>
            </button>
          </h3>
          <div v-show="!collapsedGroups.has(group.rarity)" :id="`emote-group-${group.rarity}`" class="albums">
        <button
          v-for="a in group.albums" :key="a.set.id" type="button"
          class="album ui-tile" :class="a.set.rarity" :title="a.set.name" data-rise
          @click="openAlbum(a.set.id)"
        >
          <span class="collage ui-frame ui-well">
            <img
              v-for="e in a.collage" :key="e.key" :class="{ miss: !e.owned }"
              :src="assetUrl(e.thumb ?? e.img)" alt="" loading="lazy" decoding="async" draggable="false"
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
        </section>
      </div>

      <template v-else>
        <VirtualGrid class="emote-grid" :items="tiles" :item-key="(e) => e.key">
          <template #default="{ item: e }">
          <button
            type="button"
            class="ui-tile" :class="[e.rarity, { locked: !e.owned }]"
            :title="`${e.name}（${e.setName}）`" data-rise
            @click="inspect(e.key)"
          >
            <span class="ui-frame ui-well">
              <img :src="assetUrl(e.thumb ?? e.img)" :alt="e.name" loading="lazy" decoding="async" draggable="false" />
              <span v-if="e.animated" class="dynamic ui-tag dark" title="动态表情"><Icon name="play" :size="9" /></span>
            </span>
            <b class="ui-tile-name">{{ e.name }}</b>
          </button>
          </template>
        </VirtualGrid>
        <p v-if="!tiles.length" class="ui-empty">没有匹配的表情</p>
      </template>
    </div>

    <p v-if="error" class="ui-error" role="alert">{{ error }}</p>

    </template>
    <CardDetail v-if="detail" :card="detail" :from="detailFrom" @close="detail = null" />

    <Modal v-if="selectedItem" :title="selectedItem.name" @close="selectedItem = null">
      <div class="emote-detail">
        <div class="detail-well ui-frame">
          <ItemArt :item="selectedItem" :size="128" :locked="!selectedItemOwned" />
        </div>
        <h3>{{ selectedItem.name }}</h3>
        <p class="detail-sub">{{ selectedItem.group }}</p>
        <small v-if="actionNote" class="note">{{ actionNote }}</small>
        <template v-if="selectedItemOwned">
          <p class="held">已拥有<template v-if="selectedItemCount > 1"> ×{{ selectedItemCount }}</template></p>
          <div v-if="selectedItem.kind === 'emote'" class="buttons">
            <button type="button" class="ui-btn" @click="toggleFav(selectedItem)">
              {{ settings.favorites.includes(selectedItem.ref) ? "移出快捷表情" : "装入快捷表情" }}
            </button>
            <button type="button" class="ui-btn primary" @click="fireSelectedEmote(selectedItem)">发表情</button>
          </div>
        </template>
        <CraftAction :key="selectedItem.id" :item="selectedItem" />
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.dynamic { position: absolute; right: 5px; bottom: 5px; }
.collection-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 2px 20px 12px 16px;
}
.dex-bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.dex-kind {
  flex: 0 0 222px;
}
.emote-bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.tabs-bar {
  flex: 1 1 auto;
  min-width: 0;
}
@container panel (max-width: 860px) {
  .dex-bar {
    flex-wrap: wrap;
  }
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
  font: 800 var(--fs-section)/1.2 var(--font);
}
.progress {
  flex: none;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
  white-space: nowrap;
}
.progress b {
  font: 800 var(--fs-section)/1 var(--font-latin);
  color: var(--c-700);
}
.search-input {
  flex: none;
  width: 140px;
  height: 32px;
  padding: 0 10px;
  font-size: var(--fs-label);
}

.wall {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 6px;
}

.album-groups {
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding-top: 2px;
}
.rarity-group { min-width: 0; }
.group-heading { margin: 0 0 10px; }
.group-toggle {
  width: auto;
  min-height: 32px;
  padding: 4px 4px 4px 0;
  display: flex;
  align-items: center;
  gap: 9px;
  border: 0;
  background: none;
  color: var(--ink);
  font: 800 var(--fs-strong)/1.4 var(--font);
  text-align: left;
  cursor: pointer;
}
.group-toggle small { color: var(--ink-3); font: 500 var(--fs-label)/1 var(--font); white-space: nowrap; }
.group-arrow { flex: none; color: var(--ink-2); transition: transform var(--dur-fast) var(--ease-out); }
.group-arrow.expanded { transform: rotate(90deg); }
.group-toggle:hover { color: var(--c-700); }
.group-toggle:focus-visible { outline-offset: 3px; border-radius: var(--radius-s); }
.albums {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 16px 14px;
  padding: 2px 4px 6px 0;
}
.album {
  --well-ratio: 16 / 10;
  --radius: var(--radius-m);
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
}
.album-count {
  flex: none;
  font: 800 var(--fs-label)/1 var(--font-latin);
  color: var(--ink-3);
}
.album-count b {
  font: inherit;
  color: var(--c-700);
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
/* Unowned stickers are a dimmed original that lights up under the pointer. */
.emote-grid .ui-tile.locked .ui-well img {
  transition: transform var(--dur-base) var(--ease-out), filter var(--dur-base);
}
.emote-grid .ui-tile.locked:hover .ui-well img {
  filter: var(--contour);
}

.emote-detail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
}
.detail-well {
  --radius: var(--radius-l);
  padding: 16px;
  background: var(--c-100);
}
.emote-detail h3 {
  margin: 4px 0 0;
  font: 800 var(--fs-heading)/1.1 var(--font);
}
.detail-sub {
  margin: 0;
  font-size: var(--fs-label);
  color: var(--ink-2);
}
.note {
  color: var(--c-700);
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
  color: var(--c-700);
}
.buttons {
  display: flex;
  gap: 12px;
  margin-top: 4px;
}
</style>
