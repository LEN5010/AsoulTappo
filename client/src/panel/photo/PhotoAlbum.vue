<script setup lang="ts">
// The photocards in the dex (小卡): an album a series, a shelf of sleeves a member, then the shared cards. A card the save
// lacks is its own picture dimmed, lit up under the pointer.
import { computed, onMounted, ref, watch } from "vue";
import { characterColor, manifest } from "../../manifest";
import { photoItems, type PhotoItem } from "../../photocards";
import { placeOf, type CardPlace } from "../../photo/place";
import { loadPhotocards, photoAlbums, photoShelf, photoState, photoView } from "../../stores/photocards";
import { online } from "../../stores/player";
import { ui } from "../../stores/ui";
import { rise } from "../../ui/motion";
import Icon from "../../ui/Icon.vue";
import SegTabs from "../../ui/SegTabs.vue";
import PhotoThumb from "./PhotoThumb.vue";
import PhotoViewer from "./PhotoViewer.vue";
import { albumSections, filterPhotos, photoName, type PhotoFilter } from "./labels";
import { albumSeries, PHOTO_POOL, pickSeries } from "./shop";

const props = defineProps<{ filter: PhotoFilter }>();

const series = computed(() => (photoAlbums.value.includes(albumSeries.value) ? albumSeries.value : photoAlbums.value[0] ?? ""));
const view = computed(() => photoView(series.value));
const info = computed(() => manifest.photocards.find((s) => s.id === series.value));
const items = computed(() => photoItems(series.value));
const tabs = computed(() => photoAlbums.value.map((id) => {
  const mine = photoItems(id);
  const owned = photoView(id).owned;
  return { id, label: manifest.photocards.find((s) => s.id === id)?.name ?? id, count: `${mine.filter((i) => owned.has(i.id)).length}/${mine.length}` };
}));
const got = computed(() => items.value.filter((i) => view.value.owned.has(i.id)).length);
const shown = computed(() => filterPhotos(items.value, props.filter, view.value.owned));
const sections = computed(() => albumSections(shown.value).map((s) => ({
  ...s, color: s.member ? characterColor(s.member) : "",
  got: s.items.filter((i) => view.value.owned.has(i.id)).length,
})));

const wall = ref<HTMLElement>();
watch(online, (on) => { if (on && !photoState.value) void loadPhotocards(); }, { immediate: true });
onMounted(() => rise(wall.value));
watch([series, () => props.filter], () => {
  if (wall.value) wall.value.scrollTop = 0;
  requestAnimationFrame(() => rise(wall.value));
});

const open = ref<{ item: PhotoItem; from?: CardPlace } | null>(null);
function inspect(item: PhotoItem, e: Event) {
  open.value = { item, from: placeOf(e.currentTarget as HTMLElement) };
}
function toShop() {
  open.value = null;
  pickSeries(series.value);
  ui.pool = PHOTO_POOL;
  ui.page = "resonance";
}
</script>

<template>
  <SegTabs v-if="tabs.length > 1" :model-value="series" plain :tabs="tabs" label="小卡系列" @update:model-value="albumSeries = $event" />
  <div ref="wall" class="photo-album ui-scroll">
    <header class="head">
      <h3>{{ info?.name }}</h3>
      <p>{{ info?.event }}</p>
      <span class="count"><b>{{ got }}</b>/ {{ items.length }}</span>
      <span class="bar" aria-hidden="true"><i :style="{ width: `${items.length ? (got / items.length) * 100 : 0}%` }"></i></span>
    </header>
    <section v-for="s in sections" :key="s.key" class="shelf">
      <h4>
        <i v-if="s.color" :style="{ background: s.color }" aria-hidden="true"></i>{{ s.label }}
        <small :class="{ full: s.got === s.items.length }"><b>{{ s.got }}</b>/{{ s.items.length }}</small>
      </h4>
      <div class="row" :class="{ wide: s.wide }">
        <button
          v-for="item in s.items" :key="item.id" type="button" class="sleeve" :class="[item.kind, { miss: !view.owned.has(item.id) }]"
          :title="photoName(item)" :aria-label="photoName(item)" data-rise
          @click="inspect(item, $event)"
        >
          <PhotoThumb :item="item" :dim="!view.owned.has(item.id)" lazy />
          <span v-if="item.kind === 'sign'" class="mark" aria-hidden="true"><Icon name="pencil" :size="9" /></span>
        </button>
      </div>
    </section>
    <p v-if="!shown.length" class="ui-empty">没有符合的小卡</p>
  </div>
  <PhotoViewer
    v-if="open" :item="open.item" :list="shown" :from="open.from" :shop="photoShelf.some((c) => c.series === series && c.daily > 0)"
    @step="open = { item: $event }" @close="open = null" @shop="toShop"
  />
</template>

<style scoped>
.photo-album {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 6px 8px 0;
  scrollbar-gutter: stable;
}
.head {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: baseline;
  gap: 4px 10px;
  margin: 2px 0 14px;
}
.head h3 {
  margin: 0;
  font: 800 var(--fs-heading)/1.2 var(--font);
}
.head p {
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.count {
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink-3);
}
.count b {
  margin-right: 4px;
  font-size: 24px;
  color: var(--c-700);
}
.bar {
  grid-column: 1 / 4;
  height: 6px;
  border-radius: 3px;
  background: var(--c-100);
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--c-400), var(--c-500));
  transition: width var(--dur-stage) var(--ease-out);
}
.shelf {
  margin-bottom: 18px;
}
h4 {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 9px;
  font: 800 var(--fs-strong)/1 var(--font);
}
h4 > i {
  width: 4px;
  height: 14px;
}
h4 small {
  font: 800 var(--fs-label)/1 var(--font-latin);
  color: var(--ink-3);
}
h4 small b {
  color: var(--ink);
}
h4 small.full b {
  color: var(--c-700);
}
.row {
  display: grid;
  grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: 14px 13px;
}
.row.wide {
  grid-template-columns: repeat(6, minmax(0, 1fr));
}
/* A sleeve: the card with the rim of clear film around it. */
.sleeve {
  position: relative;
  display: block;
  padding: 3px;
  border: 0;
  border-radius: 4px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 6px 14px -8px rgba(var(--shadow-rgb), 0.4);
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base);
}
.sleeve::after {
  content: "";
  position: absolute;
  inset: 3px;
  background: linear-gradient(112deg, rgba(255, 255, 255, 0) 38%, rgba(255, 255, 255, 0.34) 47%, rgba(255, 255, 255, 0) 56%) 130% 0 / 260% 100% no-repeat;
  pointer-events: none;
}
.sleeve:hover {
  transform: translateY(-4px);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 12px 20px -9px rgba(var(--shadow-rgb), 0.5);
}
.sleeve:hover::after {
  background-position: -60% 0;
  transition: background-position 700ms var(--ease-out);
}
.sleeve:focus-visible {
  outline: 2px solid var(--c-500);
  outline-offset: 2px;
}
.sleeve.sign {
  background: linear-gradient(160deg, var(--gold-soft), #fff 34%, var(--gold-soft) 78%, var(--gold));
}
.sleeve.miss {
  background: var(--c-100);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.08);
}
.sleeve.miss :deep(img) {
  transition: filter var(--dur-base);
}
.sleeve.miss:hover :deep(img) {
  filter: none;
}
.mark {
  position: absolute;
  right: -5px;
  top: -5px;
  display: grid;
  place-items: center;
  width: 17px;
  height: 17px;
  border-radius: 50%;
  background: var(--grad-gold);
  box-shadow: 0 0 0 1.5px #fff, 0 2px 4px rgba(var(--shadow-rgb), 0.25);
  color: var(--ink);
}
.miss .mark {
  background: var(--c-200);
  color: var(--ink-3);
}
@container panel (max-width: 760px) {
  .row {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
  .row.wide {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
