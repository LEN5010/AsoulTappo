<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onDeactivated, ref, watch } from "vue";
import { characterColor, emoteCover, manifest, memberOf } from "../manifest";
import { characters } from "../characters";
import { assetUrl } from "../asset";
import { getItem, ownsCharacter, ownsEmote, starterEmotesOf, type Item } from "../items";
import { collection, error } from "../stores/player";
import { settings } from "../stores/settings";
import { reducedMotion } from "../stores/theme";
import { sendEmote } from "../stores/room";
import { ui } from "../stores/ui";
import { EmotePlayer, type EmoteFrame } from "../pet/EmotePlayer";
import MemberStrip from "./MemberStrip.vue";
import StagePet from "./StagePet.vue";
import PetBust from "./PetBust.vue";
import VirtualGrid from "../ui/VirtualGrid.vue";
import SegTabs from "../ui/SegTabs.vue";
import Icon from "../ui/Icon.vue";
import { flyArc, rise, squash } from "../ui/motion";

type MainKind = "all" | "emote" | "pet";
const mainTab = ref<MainKind>("all");
const query = ref("");
const actionNote = ref("");

// A member card narrows the shelves to her and equips her original skin; ALL only lifts the filter.
const member = ref("all");
function pickMember(name: string) {
  member.value = name;
  if (name !== "all") settings.character = name;
}
const inMember = (name: string) => member.value === "all" || memberOf(name) === member.value;

// ---- live stage preview
const preview = ref<EmoteFrame | null>(null);
const player = new EmotePlayer((f) => (preview.value = f), () => settings.emoteHoldMs);
onBeforeUnmount(() => player.clear());
onDeactivated(() => player.clear());

const quickKeys = computed(() =>
  settings.favorites.length ? settings.favorites : starterEmotesOf(settings.character),
);

function pokeStage() {
  const keys = quickKeys.value;
  if (keys.length) player.play(keys[Math.floor(Math.random() * keys.length)]!);
}

const root = ref<HTMLElement>();
const listing = ref<HTMLElement>();
watch([mainTab, member], () => nextTick(() => rise(listing.value, root.value)));

// Replays the member-color band over the stage on every character switch.
const ribbon = ref(0);
watch(() => settings.character, () => ribbon.value++);

const MEMBER_ORDER = manifest.characters.map((c) => c.name);
const skinRank = (name: string) => {
  const idx = MEMBER_ORDER.indexOf(memberOf(name));
  return idx >= 0 ? idx : 999;
};

// Dynamic pet skins from characters.ts: owned ones first, each group in canonical member order (supports future outfits/skins)
const lockedRank = (name: string) => Number(!ownsCharacter(name, collection.owned));
const petSkins = computed(() =>
  Object.values(characters)
    .filter((c) => inMember(c.name) && (!query.value || c.name.includes(query.value)))
    .sort((a, b) => lockedRank(a.name) - lockedRank(b.name) || skinRank(a.name) - skinRank(b.name)
      || a.name.localeCompare(b.name, "zh-CN")),
);

// Single flat list of OWNED emotes for the Backpack (no 21 Bilibili pack accordions!)
const ownedEmotes = computed(() => {
  if (mainTab.value === "pet") return [];
  const list: { key: string; name: string; img: string; animated?: boolean; character: string; setName: string; rarity: string }[] = [];
  for (const s of manifest.emoteSets) {
    if (!inMember(s.character)) continue;
    for (const e of s.emotes) {
      if (!ownsEmote(e.key, collection.owned)) continue;
      if (query.value && !e.name.includes(query.value) && !s.name.includes(query.value)) continue;
      list.push({
        key: e.key,
        name: e.name,
        img: e.thumb ?? e.img,
        animated: e.animated,
        character: s.character,
        setName: s.name,
        rarity: s.rarity,
      });
    }
  }
  return list;
});

const totalOwnedEmotes = computed(() =>
  manifest.emoteSets
    .filter((s) => inMember(s.character))
    .reduce((acc, s) => acc + s.emotes.filter((e) => ownsEmote(e.key, collection.owned)).length, 0),
);

const mainTabs = computed(() => [
  { id: "all" as const, label: "全部" },
  { id: "emote" as const, label: "表情", count: totalOwnedEmotes.value },
  { id: "pet" as const, label: "桌宠", count: petSkins.value.length },
]);

const nothingFound = computed(
  () => !ownedEmotes.value.length && (mainTab.value === "emote" || !petSkins.value.length),
);

const favorites = computed(() => Array.from({ length: 8 }, (_, n) => getItem(`emote:${settings.favorites[n]}`)));
/** The quick key a sticker sits on, 1-8, or 0. */
const keyOf = (key: string) => settings.favorites.indexOf(key) + 1;

// ---- stickers fly between their tiles and the quick keys
const pad = ref<HTMLElement>();
const keyEl = (n: number) => pad.value?.querySelectorAll<HTMLElement>(".sq-slot")[n];
const keyArt = (n: number) => keyEl(n)?.querySelector<HTMLImageElement>("img");
/** The sticker's tile while it is drawn on screen; the virtual grid leaves most of them out. */
function tileArt(key: string): HTMLImageElement | null {
  const img = root.value?.querySelector<HTMLImageElement>(`[data-emote="${CSS.escape(key)}"] .ui-well img`);
  if (!img || !root.value) return null;
  const box = img.getBoundingClientRect();
  const view = root.value.getBoundingClientRect();
  return box.bottom > view.top && box.top < view.bottom ? img : null;
}
function sink(el: HTMLElement | undefined) {
  if (reducedMotion.value) return;
  el?.animate([{ transform: "translateY(0)" }, { transform: "translateY(3px)" }, { transform: "translateY(0)" }], { duration: 240, easing: "ease-out" });
}
async function flyIn(key: string, from: DOMRect | undefined, n: number) {
  await nextTick();
  const art = keyArt(n);
  if (!from || !art) return;
  art.style.visibility = "hidden";
  await flyArc(art, art.src, from, art.getBoundingClientRect());
  art.style.visibility = "";
  if (settings.favorites[n] !== key) return;
  squash(art);
  sink(keyEl(n));
}
async function flyOut(key: string, n: number) {
  const art = keyArt(n);
  if (!art) return;
  const from = art.getBoundingClientRect();
  const src = art.src;
  await nextTick();
  const home = tileArt(key);
  if (home) home.style.visibility = "hidden";
  await flyArc(pad.value ?? art, src, from, home?.getBoundingClientRect() ?? null, true);
  if (home) {
    home.style.visibility = "";
    squash(home);
  }
}

function toggleFavKey(key: string, from?: Element | null) {
  actionNote.value = "";
  const at = settings.favorites.indexOf(key);
  if (at >= 0) {
    void flyOut(key, at);
    settings.favorites.splice(at, 1);
  } else if (settings.favorites.length < 8) {
    const n = settings.favorites.length;
    settings.favorites.push(key);
    player.play(key);
    void flyIn(key, from?.getBoundingClientRect(), n);
  } else {
    player.play(key);
    actionNote.value = "快捷表情已满 8/8";
  }
}

function favorite(item: Item) {
  toggleFavKey(item.ref);
}

// While a sticker is dragged over the pad, its empty keys light up as places to drop it.
const dragDepth = ref(0);
function dropOn(e: DragEvent, n: number) {
  dragDepth.value = 0;
  assign(e, n);
}

function assign(e: DragEvent, n: number) {
  const key = e.dataTransfer?.getData("text/plain");
  if (!key || !ownsEmote(key, collection.owned)) return;
  const next = settings.favorites.filter((k) => k !== key);
  next.splice(Math.min(n, next.length), 0, key);
  settings.favorites = next.slice(0, 8);
  player.play(key);
}

function fireEmote(key: string) {
  player.play(key);
  sendEmote(key);
}

</script>

<template>
  <div class="emotes-page">
    <section class="showcase">
      <div class="stage" data-rise @click="pokeStage">
        <span class="stage-bg" aria-hidden="true">
          <i class="stage-light"></i>
          <i class="stage-floor"></i>
          <i v-if="ribbon" :key="ribbon" class="stage-ribbon"></i>
        </span>
        <div class="stage-pet">
          <StagePet :character="settings.character" :emote="preview" />
        </div>
        <button type="button" class="stage-name ui-btn" title="更换桌宠" @click.stop="mainTab = 'pet'">
          <i aria-hidden="true"></i>{{ settings.character }}<Icon name="down" :size="12" />
        </button>
      </div>

      <div
        ref="pad" class="desk" :class="{ dropping: dragDepth > 0 }" data-rise
        @dragenter="dragDepth++" @dragleave="dragDepth = Math.max(0, dragDepth - 1)" @drop="dragDepth = 0"
      >
        <div class="fav-head">
          <h3 class="ui-label fav-title">
            <span>快捷表情</span>
            <small v-if="!actionNote">{{ settings.favorites.length }}/8</small>
          </h3>
          <small v-if="actionNote" class="fav-note">{{ actionNote }}</small>
        </div>
        <div class="slots">
          <button
            v-for="(item, n) in favorites" :key="n" type="button"
            class="sq-slot ui-btn" :class="{ filled: !!item }"
            :title="item ? item.name : `快捷表情 ${n + 1}`"
            @dragover.prevent @drop.prevent="dropOn($event, n)"
            @click="item && favorite(item)"
          >
            <img v-if="item" :src="assetUrl(emoteCover(item.ref))" :alt="item.name" decoding="async" draggable="false" />
            <span v-else class="slot-no" aria-hidden="true">{{ n + 1 }}</span>
          </button>
        </div>
      </div>
    </section>

    <div class="filters">
      <MemberStrip :model-value="member" @update:model-value="pickMember" />
      <SegTabs v-model="mainTab" class="kind-tabs" :tabs="mainTabs" label="背包分类" />
      <label class="search">
        <Icon name="search" :size="14" />
        <input v-model="query" class="ui-input" placeholder="搜索背包…" aria-label="搜索背包" />
      </label>
    </div>

    <p v-if="error" class="ui-error" role="alert">{{ error }}</p>

    <div ref="root" class="scroller ui-scroll" @dragend="dragDepth = 0">
      <div ref="listing" class="shelves">
        <section v-if="mainTab !== 'emote' && petSkins.length" class="shelf">
          <h4 class="ui-label shelf-head"><span>桌宠形象</span><small>{{ petSkins.length }}</small></h4>
          <div class="pet-grid">
            <button
              v-for="skin in petSkins" :key="`pet:${skin.name}`" type="button"
              class="pet-card ui-tile" :class="{ picked: settings.character === skin.name, locked: !ownsCharacter(skin.name, collection.owned) }"
              :disabled="!ownsCharacter(skin.name, collection.owned)"
              :title="`${ownsCharacter(skin.name, collection.owned) ? '切换桌宠' : '未解锁'}：${skin.name}`" data-rise
              @click="settings.character = skin.name; pokeStage()"
            >
              <span class="pet-well ui-frame ui-well">
                <PetBust class="pet-svg" :src="skin.bg" />
                <span v-if="settings.character === skin.name" class="badge in-use" aria-label="当前使用"><Icon name="check" :size="11" /></span>
                <span v-else-if="!ownsCharacter(skin.name, collection.owned)" class="badge lock" aria-label="未解锁"><Icon name="lock" :size="11" /></span>
              </span>
              <b class="ui-tile-name"><i :style="{ background: characterColor(skin.name) }" aria-hidden="true"></i>{{ skin.name }}</b>
            </button>
          </div>
        </section>

        <section v-if="mainTab !== 'pet'" class="shelf">
          <h4 class="ui-label shelf-head"><span>表情贴纸</span><small>{{ ownedEmotes.length }}</small></h4>
          <VirtualGrid class="emote-grid" :items="ownedEmotes" :item-key="(e) => e.key" extra>
            <template #default="{ item: e }">
            <div
              class="emote-cell" draggable="true" data-rise :data-emote="e.key"
              @dragstart="$event.dataTransfer?.setData('text/plain', e.key)"
            >
              <button
                type="button" class="emote-card ui-tile"
                :class="[e.rarity, { picked: keyOf(e.key) > 0 }]"
                :title="`${e.name}（${e.setName}）`" :aria-pressed="keyOf(e.key) > 0"
                @click="toggleFavKey(e.key, ($event.currentTarget as HTMLElement).querySelector('img'))"
              >
                <span class="ui-frame ui-well">
                  <img :src="assetUrl(e.img)" :alt="e.name" loading="lazy" decoding="async" draggable="false" />
                  <span v-if="e.animated" class="dynamic ui-tag dark" title="动态表情"><Icon name="play" :size="9" /></span>
                  <span v-if="keyOf(e.key)" class="key-no" :aria-label="`快捷表情 ${keyOf(e.key)}`">{{ keyOf(e.key) }}</span>
                </span>
                <b class="ui-tile-name">{{ e.name }}</b>
              </button>
              <button type="button" class="send-mini ui-btn small primary" title="发送" :aria-label="`发送 ${e.name}`" @click="fireEmote(e.key)">
                <Icon name="spark" :size="12" />
              </button>
            </div>

            </template>
            <template #extra>
            <!-- Shortcut tile to unlock/craft more emotes in Dex -->
            <button
              type="button"
              class="emote-card more-card ui-tile"
              data-rise
              @click="ui.page = 'dex'"
            >
              <span class="ui-frame ui-well">
                <Icon name="codex" :size="24" />
              </span>
              <b class="ui-tile-name">全部图鉴 →</b>
            </button>
            </template>
          </VirtualGrid>
        </section>
      </div>

      <p v-if="nothingFound" class="ui-empty">没有匹配的内容</p>
    </div>
  </div>
</template>

<style scoped>
/* Only the shelves scroll: the pet and the quick keys stay put, so a sticker can be dragged up from any depth. */
.emotes-page {
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 20px 0 16px;
}

.showcase {
  flex: none;
  display: flex;
  gap: 12px;
  height: 214px;
}

/* The pet sits outside the clipped background so it can break the frame. */
.stage {
  position: relative;
  flex: 1;
  min-width: 0;
  cursor: pointer;
}
.stage-bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border-radius: var(--radius-l);
  background: linear-gradient(180deg, var(--c-200), var(--c-300));
}
/* A soft white spotlight behind the pet, and its shadow on the floor. */
.stage-light {
  position: absolute;
  left: 50%;
  top: 0;
  width: 360px;
  height: 100%;
  transform: translateX(-50%);
  background: radial-gradient(ellipse 50% 60% at 50% 46%, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0) 100%);
}
.stage-floor {
  position: absolute;
  left: 50%;
  bottom: 4px;
  width: 260px;
  height: 26px;
  transform: translateX(-50%);
  border-radius: 50%;
  background: radial-gradient(closest-side, rgba(var(--c-900-rgb), 0.2), transparent);
}
.stage-ribbon {
  position: absolute;
  inset: 0 -4%;
  background: var(--char);
  transform: translateX(-112%);
  animation: ribbon 760ms var(--ease-in-out);
}
@keyframes ribbon {
  to {
    transform: translateX(112%);
  }
}
.stage-pet {
  position: absolute;
  z-index: 1;
  left: 50%;
  bottom: 0;
  transform: translateX(-50%);
}

/* The pet's name is a key: it opens the pet shelf. */
.stage-name {
  position: absolute;
  z-index: 2;
  left: 12px;
  top: 12px;
  gap: 7px;
  padding: 0 12px 0 11px;
  font-size: var(--fs-strong);
}
.stage-name i {
  width: 4px;
  height: 14px;
  border-radius: 1px;
  background: var(--char);
}
.stage-name .icon {
  color: var(--ink-3);
}

/* The quick keys: a sheet of paper holding two rows of four keys. */
.desk {
  flex: none;
  width: 264px;
  padding: 12px 14px 15px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.fav-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.fav-title {
  margin: 0;
  white-space: nowrap;
}
.fav-note {
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--c-700);
  white-space: nowrap;
}
.slots {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px 8px;
}
.sq-slot {
  width: auto;
  height: auto;
  aspect-ratio: 1;
  min-width: 0;
  padding: 5px;
}
.sq-slot img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  display: block;
  filter: var(--sticker);
}
.slot-no {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--c-300);
}
/* A sticker on its way: every empty key lights up as a place to drop it. */
.dropping .sq-slot:not(.filled) {
  --key-top: var(--c-100);
  --key-bottom: var(--c-100);
  outline: 2px solid var(--c-500);
  outline-offset: -2px;
}
.dropping .sq-slot:not(.filled) .slot-no {
  color: var(--c-600);
}

/* One row of 32px controls on one line. */
.filters {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 3px;
}
.kind-tabs {
  flex: 1 1 200px;
  min-width: 0;
}
.search {
  flex: 0 1 148px;
  min-width: 96px;
  position: relative;
  display: flex;
  align-items: center;
  color: var(--ink-3);
}
.search .icon {
  position: absolute;
  z-index: 1;
  left: 10px;
  pointer-events: none;
}
.search input {
  width: 100%;
  height: 32px;
  padding: 0 10px 0 30px;
  font-size: var(--fs-label);
}

/* Bleeds past the page gutters so a tile's lift is not cut at the edge. */
.scroller {
  flex: 1;
  min-height: 0;
  margin: -4px -14px 0 -8px;
  padding: 4px 14px 14px 8px;
  overflow-y: auto;
  overflow-x: hidden;
}
.shelves {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.shelf-head {
  margin: 0 0 10px;
}
.pet-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
  gap: 12px;
}
.pet-card {
  --radius: var(--radius-m);
  --well-ratio: 5 / 4;
}
/* Acrylic standees: the contour, a soft clear edge around it and an oval base (as many filter passes as a sticker). */
.pet-well {
  align-items: flex-end;
  padding: 6px 4px 0;
}
.pet-well::after {
  content: "";
  position: absolute;
  left: 18%;
  right: 18%;
  bottom: 5px;
  height: 9px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.85);
  box-shadow: 0 2px 0 var(--c-200);
}
.pet-svg {
  position: relative;
  z-index: 1;
  width: 100%;
  height: calc(100% - 8px);
  margin-bottom: 8px;
  display: block;
  filter: var(--contour) drop-shadow(0 0 2.5px rgba(255, 255, 255, 0.9));
  transition: transform var(--dur-base) var(--ease-out);
}
.pet-card:hover:not(:disabled) .pet-svg {
  transform: translateY(-3px);
}
.pet-card:disabled {
  cursor: default;
}
.pet-card.locked .pet-svg {
  filter: var(--dim);
}
.pet-card .ui-tile-name {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  font: 800 var(--fs-strong) var(--font);
}
.pet-card .ui-tile-name i {
  flex: none;
  width: 4px;
  height: 11px;
}
.badge {
  position: absolute;
  z-index: 2;
  right: 6px;
  top: 6px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
}
.badge.in-use {
  background: var(--c-500);
  color: var(--ink);
}
.badge.lock {
  background: var(--surface);
  color: var(--ink-3);
}
.dynamic { position: absolute; right: 5px; bottom: 5px; }
/* The quick key a sticker sits on, matching the numbers on the pad. */
.key-no {
  position: absolute;
  z-index: 1;
  left: 5px;
  top: 5px;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  box-sizing: border-box;
  border-radius: 9px;
  background: var(--c-500);
  color: var(--ink);
  font: 800 var(--fs-label)/17px var(--font-latin);
  text-align: center;
}

.emote-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(76px, 1fr));
  gap: 12px 10px;
}
.emote-cell {
  position: relative;
  min-width: 0;
  display: flex;
}
.emote-cell .emote-card {
  width: 100%;
}
/* Its key number says it is on the pad; the coral ring stays for the pet in use. */
.emote-card.picked:not(:focus-visible) .ui-well {
  outline: none;
}
/* A quiet tile: no slot until the pointer is over it. */
.more-card .ui-well {
  background: transparent;
  color: var(--c-700);
  transition: background var(--dur-fast);
}
.more-card:hover .ui-well {
  background: var(--c-100);
}
.more-card .ui-tile-name {
  color: var(--ink-2);
}
.send-mini {
  position: absolute;
  right: 4px;
  top: 4px;
  z-index: 4;
  width: 26px;
  height: 24px;
  padding: 0;
  opacity: 0;
  transition: opacity var(--dur-fast), transform var(--dur-release) var(--ease-spring), box-shadow var(--dur-release) var(--ease-spring);
}
.emote-cell:hover .send-mini,
.send-mini:focus-visible {
  opacity: 1;
}

@container panel (max-width: 860px) {
  .filters {
    flex-wrap: wrap;
    gap: 8px 10px;
  }
  .desk {
    width: 196px;
  }
  .stage-pet {
    transform: translateX(-50%) scale(0.74);
    transform-origin: 50% 100%;
  }
  .stage-light {
    width: 280px;
  }
  .stage-floor {
    width: 200px;
  }
  .slots {
    gap: 6px;
  }
}
/* Short windows give the stage's height to the shelves. */
@container panel (max-height: 580px) {
  .showcase {
    height: 142px;
  }
  .stage-pet {
    transform: translateX(-50%) scale(0.62);
    transform-origin: 50% 100%;
  }
  .stage-floor {
    width: 170px;
    height: 18px;
  }
  .desk {
    padding: 8px 10px 11px;
    gap: 6px;
  }
  .slots {
    grid-template-columns: repeat(4, minmax(0, 44px));
    justify-content: space-between;
    gap: 6px 4px;
  }
}
</style>
