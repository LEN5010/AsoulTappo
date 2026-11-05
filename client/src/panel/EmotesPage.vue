<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { characterColor, manifest, memberOf } from "../manifest";
import { characters } from "../characters";
import { assetUrl } from "../asset";
import { getItem, ownsCharacter, ownsEmote, starterEmotesOf, type Item } from "../items";
import { draws, collection, error, shards } from "../stores/player";
import { settings } from "../stores/settings";
import { pet } from "../stores/pet";
import { sendEmote } from "../stores/room";
import { ui } from "../stores/ui";
import { EmotePlayer, type EmoteFrame } from "../pet/EmotePlayer";
import PetView from "../pet/PetView.vue";
import MemberStrip from "./MemberStrip.vue";
import PetBust from "./PetBust.vue";
import SegTabs from "../ui/SegTabs.vue";
import Icon from "../ui/Icon.vue";
import { rise } from "../ui/motion";

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

const quickKeys = computed(() =>
  settings.favorites.length ? settings.favorites : starterEmotesOf(settings.character),
);
const STAGE_SCALE = 1.42;
// The pet nearly fills the stage's height, so the bubble hangs off the side of the head and stays in frame.
const STAGE_EMOTE = 86;
const STAGE_BUBBLE = { x: 36, y: 62 };

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

// Dynamic pet skins from characters.ts, sorted in canonical member order (supports future outfits/skins)
const petSkins = computed(() =>
  Object.values(characters)
    .filter((c) => inMember(c.name) && (!query.value || c.name.includes(query.value)))
    .sort((a, b) => skinRank(a.name) - skinRank(b.name) || a.name.localeCompare(b.name, "zh-CN")),
);

// Single flat list of OWNED emotes for the Backpack (no 21 Bilibili pack accordions!)
const ownedEmotes = computed(() => {
  if (mainTab.value === "pet") return [];
  const list: { key: string; name: string; img: string; character: string; setName: string; rarity: string }[] = [];
  for (const s of manifest.emoteSets) {
    if (!inMember(s.character)) continue;
    for (const e of s.emotes) {
      if (!ownsEmote(e.key, collection.owned)) continue;
      if (query.value && !e.name.includes(query.value) && !s.name.includes(query.value)) continue;
      list.push({
        key: e.key,
        name: e.name,
        img: e.img,
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

function toggleFavKey(key: string) {
  actionNote.value = "";
  const at = settings.favorites.indexOf(key);
  if (at >= 0) {
    settings.favorites.splice(at, 1);
  } else if (settings.favorites.length < 8) {
    settings.favorites.push(key);
    player.play(key);
  } else {
    player.play(key);
    actionNote.value = "预设已满 8/8";
  }
}

function favorite(item: Item) {
  toggleFavKey(item.ref);
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
          <i class="stage-disc"></i>
          <i v-if="ribbon" :key="ribbon" class="stage-ribbon"></i>
        </span>
        <div class="stage-pet">
          <PetView
            :character="settings.character" :scale="STAGE_SCALE"
            :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
            :left-down="pet.left" :right-down="pet.right" :emote="preview" :min-emote="38"
            :max-emote="STAGE_EMOTE" :bubble-shift="STAGE_BUBBLE"
          />
        </div>
        <button type="button" class="stage-name ui-plate" title="更换桌宠" @click.stop="mainTab = 'pet'">
          <i aria-hidden="true"></i>{{ settings.character }}<Icon name="down" :size="11" />
        </button>
        <Icon name="star5" :size="24" class="stage-deco big" />
        <Icon name="star5" :size="14" class="stage-deco small" />
        <Icon name="heart" :size="16" class="stage-deco heart" />
      </div>

      <div class="desk" data-rise>
        <div class="fav-head">
          <h3 class="ui-label fav-title"><span>我的预设</span><em>MY PRESET</em></h3>
          <small v-if="actionNote" class="fav-note">{{ actionNote }}</small>
          <b v-else class="fav-count">{{ settings.favorites.length }}<small>/8</small></b>
        </div>
        <div class="slots">
          <button
            v-for="(item, n) in favorites" :key="n" type="button"
            class="sq-slot ui-frame" :class="{ filled: !!item }"
            :title="item ? item.name : `预设槽位 ${n + 1}`"
            @dragover.prevent @drop.prevent="assign($event, n)"
            @click="item && favorite(item)"
          >
            <img v-if="item" :src="assetUrl(item.art)" :alt="item.name" decoding="async" draggable="false" />
            <Icon v-else name="plus" :size="15" />
          </button>
        </div>
        <div class="resources">
          <div class="res" title="表情碎片">
            <Icon name="shard" :size="15" />
            <b>{{ shards }}</b><small>碎片</small>
          </div>
          <button type="button" class="ui-btn open" :class="{ primary: draws > 0, pulse: draws > 0 }" @click="ui.page = 'resonance'">去共鸣</button>
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

    <div ref="root" class="scroller ui-scroll">
      <div ref="listing" class="shelves">
        <section v-if="mainTab !== 'emote' && petSkins.length" class="shelf">
          <h4 class="ui-label shelf-head"><span>桌宠形象</span><em>DESKTOP PET</em><small>{{ petSkins.length }}</small></h4>
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
                <span v-if="settings.character === skin.name" class="tag ui-tag" aria-label="当前使用">使用中</span>
                <span v-else-if="!ownsCharacter(skin.name, collection.owned)" class="tag ui-tag">未解锁</span>
              </span>
              <b class="ui-tile-name"><i :style="{ background: characterColor(skin.name) }" aria-hidden="true"></i>{{ skin.name }}</b>
            </button>
          </div>
        </section>

        <section v-if="mainTab !== 'pet'" class="shelf">
          <h4 class="ui-label shelf-head"><span>表情贴纸</span><em>STICKER</em><small>{{ ownedEmotes.length }}</small></h4>
          <div class="emote-grid">
            <div
              v-for="e in ownedEmotes" :key="e.key"
              class="emote-cell" draggable="true" data-rise
              @dragstart="$event.dataTransfer?.setData('text/plain', e.key)"
            >
              <button
                type="button" class="emote-card ui-tile"
                :class="[e.rarity, { picked: settings.favorites.includes(e.key) }]"
                :title="`${e.name}（${e.setName}）`" :aria-pressed="settings.favorites.includes(e.key)"
                @click="toggleFavKey(e.key)"
              >
                <span class="ui-frame ui-well">
                  <img :src="assetUrl(e.img)" :alt="e.name" loading="lazy" decoding="async" draggable="false" />
                  <span v-if="settings.favorites.includes(e.key)" class="tag ui-tag">预设</span>
                </span>
                <b class="ui-tile-name">{{ e.name }}</b>
              </button>
              <button type="button" class="send-mini" title="发送" :aria-label="`发送 ${e.name}`" @click="fireEmote(e.key)">
                <Icon name="spark" :size="11" />
              </button>
            </div>

            <!-- Shortcut tile to unlock/craft more emotes in Dex -->
            <button
              type="button"
              class="emote-card more-card ui-tile"
              data-rise
              @click="ui.page = 'dex'"
            >
              <span class="ui-frame ui-well">
                <Icon name="book" :size="24" />
              </span>
              <b class="ui-tile-name">全部图鉴 →</b>
            </button>
          </div>
        </section>
      </div>

      <p v-if="nothingFound" class="ui-empty">没有匹配的内容</p>
    </div>
  </div>
</template>

<style scoped>
/* Only the shelves scroll: the pet and the presets stay put, so a sticker can be dragged up from any depth. */
.emotes-page {
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 10px;
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
  background: var(--grad-sky);
}
/* The sidebar's disc rising behind the pet like a spotlight. */
.stage-disc {
  position: absolute;
  left: 50%;
  top: 22px;
  width: 340px;
  aspect-ratio: 1;
  border-radius: 50%;
  transform: translateX(-50%);
  background: radial-gradient(circle at 50% 30%, rgba(255, 255, 255, 0.62), rgba(255, 255, 255, 0.16) 70%);
  box-shadow: 0 0 0 16px rgba(255, 255, 255, 0.12), 0 0 0 34px rgba(255, 255, 255, 0.07);
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
/* Above the stars, so an emote is never drawn under them. */
.stage-pet {
  position: absolute;
  z-index: 1;
  left: 50%;
  bottom: 0;
  transform: translateX(-50%);
}
.stage-pet :deep(.art) {
  filter: var(--sticker-lg);
}
.stage-name {
  --plate-bg: var(--surface);
  --plate-edge: 0 4px 10px -4px rgba(var(--ink-rgb), 0.34);
  position: absolute;
  z-index: 2;
  left: 12px;
  top: 12px;
  display: flex;
  align-items: center;
  gap: 7px;
  height: 28px;
  padding: 0 10px;
  border: 0;
  background: none;
  font: 800 var(--fs-strong) var(--font);
  color: var(--ink);
  cursor: pointer;
}
.stage-name:hover {
  --plate-bg: var(--accent-tint);
}
.stage-name i {
  width: 5px;
  height: 14px;
  border-radius: 1px;
  background: var(--char);
}
.stage-deco {
  position: absolute;
  color: var(--on-ink);
  pointer-events: none;
}
.stage-deco.big {
  right: 26px;
  top: 18px;
  transform: rotate(14deg);
}
.stage-deco.small {
  right: 18px;
  top: 56px;
}
.stage-deco.heart {
  left: 26px;
  top: 60px;
  fill: var(--on-ink);
  transform: rotate(-12deg);
}

.desk {
  flex: none;
  width: 264px;
  padding: 11px 12px 12px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 9px;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: inset 0 0 0 1.5px var(--line);
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
.fav-count {
  font: 800 var(--fs-section)/1 var(--font-latin);
  color: var(--accent-deep);
}
.fav-count small {
  font: inherit;
  font-size: var(--fs-strong);
  color: var(--ink-3);
}
.fav-note {
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--accent-deep);
  white-space: nowrap;
}
.slots {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}
.sq-slot {
  --radius: var(--radius-s);
  aspect-ratio: 1;
  min-width: 0;
  padding: 4px;
  box-sizing: border-box;
  border: 0;
  background: var(--accent-tint);
  box-shadow: inset 0 0 0 1.5px var(--line);
  color: var(--accent);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--dur-fast), transform var(--dur-base) var(--ease-out);
}
.sq-slot:hover {
  background: var(--accent-soft);
  transform: translateY(-2px);
}
.sq-slot.filled {
  background: var(--accent-soft);
}
.sq-slot img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  display: block;
  filter: var(--sticker);
}
.resources {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.res {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--accent-deep);
}
.res b {
  font: 800 var(--fs-heading)/1 var(--font-latin);
  color: var(--ink);
}
.res small {
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-2);
}
.open {
  flex: none;
  width: 92px;
}

.filters {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
}
.kind-tabs {
  flex: 1 1 200px;
  min-width: 0;
  border-radius: var(--radius-s);
}
.search {
  flex: 0 1 136px;
  min-width: 96px;
  position: relative;
  display: flex;
  align-items: center;
  color: var(--ink-3);
}
.search .icon {
  position: absolute;
  left: 9px;
  pointer-events: none;
}
.search input {
  width: 100%;
  height: 32px;
  padding: 0 10px 0 29px;
  font-size: var(--fs-label);
}

/* Bleeds past the page gutters so a tile's lift and glow are not cut at the edge. */
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
  gap: 16px;
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
.pet-well {
  align-items: flex-end;
  padding: 6px 4px 0;
}
.pet-card.picked .pet-well {
  background: var(--accent-soft);
}
.pet-svg {
  width: 100%;
  height: 100%;
  display: block;
  filter: var(--sticker);
  transition: transform var(--dur-base) var(--ease-out);
}
.pet-card:hover:not(:disabled) .pet-svg {
  transform: scale(1.05);
}
.pet-card:disabled {
  cursor: default;
  transform: none;
}
.pet-card:disabled::before {
  display: none;
}
.pet-card.locked .pet-svg {
  filter: brightness(0.54);
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
.tag {
  position: absolute;
  left: 7px;
  top: 6px;
  z-index: 1;
}
.emote-card .tag {
  left: 6px;
  top: auto;
  bottom: 5px;
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
.emote-card.picked .ui-well {
  background: var(--accent-soft);
}
.more-card .ui-well {
  background: var(--grad-main);
  color: var(--on-accent);
}
.send-mini {
  position: absolute;
  right: 0;
  top: 0;
  z-index: 4;
  width: 24px;
  height: 20px;
  padding: 0;
  border: 0;
  background: var(--ink);
  color: var(--on-ink);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity var(--dur-fast), background var(--dur-fast);
}
.emote-cell:hover .send-mini,
.send-mini:focus-visible {
  opacity: 1;
}
.send-mini:hover {
  background: var(--accent-deep);
}

@container panel (max-width: 860px) {
  .filters {
    flex-wrap: wrap;
    gap: 6px 10px;
  }
  .desk {
    width: 196px;
  }
  .fav-title em,
  .res small,
  .stage-deco {
    display: none;
  }
  .stage-pet {
    transform: translateX(-50%) scale(0.74);
    transform-origin: 50% 100%;
  }
  .stage-disc {
    top: 46px;
    width: 250px;
  }
  .open {
    width: 76px;
    padding: 0;
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
  .stage-disc {
    top: 26px;
    width: 200px;
  }
  .desk {
    padding: 8px 10px;
    gap: 6px;
  }
  .slots {
    grid-template-columns: repeat(4, minmax(0, 44px));
    justify-content: space-between;
    gap: 4px;
  }
  .resources {
    display: none;
  }
}
</style>
