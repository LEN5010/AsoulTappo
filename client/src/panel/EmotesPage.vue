<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { getEmote, manifest } from "../manifest";
import { characters, FACE_CROP, PET_BASE } from "../characters";
import { assetUrl } from "../asset";
import { getItem, ownsEmote, starterEmotesOf, type Item } from "../items";
import { boxes, collection, error, online, openBoxes, shards, status } from "../stores/player";
import { settings } from "../stores/settings";
import { pet } from "../stores/pet";
import { sendEmote } from "../stores/room";
import { ui } from "../stores/ui";
import type { Drop } from "../net/api";
import { EmotePlayer, type EmoteFrame } from "../pet/EmotePlayer";
import PetView from "../pet/PetView.vue";
import RevealModal from "./RevealModal.vue";
import SegTabs from "../ui/SegTabs.vue";
import Icon from "../ui/Icon.vue";

type MainKind = "all" | "pet" | "emote";
const mainTab = ref<MainKind>("all");
const charFilter = ref<string>("all");
const query = ref("");
const actionNote = ref("");

// ---- live stage preview
const preview = ref<EmoteFrame | null>(null);
const player = new EmotePlayer((f) => (preview.value = f), () => settings.emoteHoldMs);
onBeforeUnmount(() => player.clear());

const quickKeys = computed(() =>
  settings.favorites.length ? settings.favorites : starterEmotesOf(settings.character),
);
const stageStickers = computed(() =>
  quickKeys.value
    .slice(0, 4)
    .map((k) => ({ key: k, emo: getEmote(k) }))
    .filter((x) => x.emo),
);
const STICKER_ARC = [
  { x: 18, y: 2, rot: -25 },
  { x: 2, y: 38, rot: -10 },
  { x: 2, y: 78, rot: 8 },
  { x: 18, y: 112, rot: 24 },
];

function pokeStage() {
  const keys = quickKeys.value;
  if (keys.length) player.play(keys[Math.floor(Math.random() * keys.length)]!);
}

const MEMBER_ORDER = manifest.characters.map((c) => c.name);
const skinRank = (name: string) => {
  const idx = MEMBER_ORDER.findIndex((m) => name.startsWith(m));
  return idx >= 0 ? idx : 999;
};

// Dynamic pet skins from characters.ts, sorted in canonical member order (supports future outfits/skins)
const petSkins = computed(() =>
  Object.values(characters)
    .filter(
      (c) =>
        (charFilter.value === "all" || c.name.includes(charFilter.value)) &&
        (!query.value || c.name.includes(query.value)),
    )
    .sort((a, b) => skinRank(a.name) - skinRank(b.name) || a.name.localeCompare(b.name, "zh-CN")),
);

const emoteOwners = computed(() => [...new Set(manifest.emoteSets.map((s) => s.character))]);

// Single flat list of OWNED emotes for the Backpack (no 21 Bilibili pack accordions!)
const ownedEmotes = computed(() => {
  if (mainTab.value === "pet") return [];
  const list: { key: string; name: string; img: string; character: string; setName: string; rarity: string }[] = [];
  for (const s of manifest.emoteSets) {
    if (charFilter.value !== "all" && s.character !== charFilter.value) continue;
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
  manifest.emoteSets.reduce(
    (acc, s) => acc + s.emotes.filter((e) => ownsEmote(e.key, collection.owned)).length,
    0,
  ),
);

const mainTabs = computed(() => [
  { id: "all" as const, label: "全部", count: Object.keys(characters).length + totalOwnedEmotes.value },
  { id: "pet" as const, label: "角色", count: Object.keys(characters).length },
  { id: "emote" as const, label: "表情", count: totalOwnedEmotes.value },
]);

const showPets = computed(() => (mainTab.value === "all" || mainTab.value === "pet") && petSkins.value.length > 0);
const showEmotes = computed(() => mainTab.value !== "pet" && ownedEmotes.value.length > 0);

const favorites = computed(() => Array.from({ length: 8 }, (_, n) => getItem(`emote:${settings.favorites[n]}`)));
const busy = ref(false);
const drops = ref<Drop[]>([]);

async function open(all: boolean) {
  if (busy.value) return;
  busy.value = true;
  const count = all ? boxes.value : 1;
  const results: Drop[] = [];
  let remaining = count;
  while (remaining > 0) {
    const batch = await openBoxes(Math.min(10, remaining));
    if (!batch?.length) break;
    results.push(...batch);
    remaining -= batch.length;
  }
  drops.value = results;
  busy.value = false;
}

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
    actionNote.value = "预设栏已满（8/8），先点击上方预设槽移出一个吧";
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

const tapPct = computed(() =>
  Math.min(100, ((status.value?.progress.taps ?? 0) / (status.value?.progress.tapsPerBox ?? 600)) * 100),
);
</script>

<template>
  <div class="emotes-page ui-scroll">
    <!-- Generous top showcase matching Reference Image 2 (WuwaTappo): Left Pet Dome + Arc | Right 2x4 Squircle Preset Slots -->
    <section class="showcase">
      <div class="stage-cluster">
        <div class="fan-arc" aria-label="快捷表情预览">
          <button
            v-for="(s, i) in stageStickers" :key="s.key" type="button"
            class="fan-card" :title="`预览：${s.emo!.name}`"
            :style="{
              left: `${STICKER_ARC[i]?.x ?? 0}px`,
              top: `${STICKER_ARC[i]?.y ?? i * 34}px`,
              transform: `rotate(${STICKER_ARC[i]?.rot ?? 0}deg)`,
            }"
            @click="player.play(s.key)"
          >
            <img :src="assetUrl(s.emo!.img)" :alt="s.emo!.name" draggable="false" />
          </button>
        </div>

        <div class="dome" title="点击桌宠预览表情" @click="pokeStage">
          <div class="dome-pet">
            <PetView
              :character="settings.character" :scale="0.72"
              :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
              :left-down="pet.left" :right-down="pet.right" :emote="preview" :min-emote="38"
            />
          </div>
          <span class="dome-name">{{ settings.character }}</span>
        </div>
      </div>

      <div class="stage-divider" aria-hidden="true"></div>

      <div class="fav-panel">
        <div class="fav-head">
          <span class="fav-title">
            我的预设 <small>({{ settings.favorites.length }}/8 · 点击下方表情即可装卸)</small>
          </span>
          <div class="resource-pills">
            <span class="res-pill" title="表情碎片（可在图鉴中兑换未拥有的表情）">
              <Icon name="shard" :size="13" /><b>{{ shards }}</b><small>碎片</small>
            </span>
            <div
              class="chest-pill"
              :title="`敲击 ${status?.progress.taps ?? 0}/${status?.progress.tapsPerBox ?? 600} · 活跃 ${status?.progress.minutes ?? 0}/${status?.progress.minutesPerBox ?? 10} 分钟 · 今日 ${status?.boxesToday ?? 0}/${status?.dailyCap ?? 10} 箱`"
            >
              <Icon name="box" :size="14" />
              <b>{{ boxes }}</b><small>箱</small>
              <span class="mini-bar"><i :style="{ width: `${tapPct}%` }"></i></span>
              <button type="button" class="mini-btn" :disabled="busy || !online || !boxes" @click="open(false)">开箱</button>
              <button v-if="boxes > 1" type="button" class="mini-btn primary" :disabled="busy || !online" @click="open(true)">全开</button>
            </div>
          </div>
        </div>

        <div class="slots">
          <button
            v-for="(item, n) in favorites" :key="n" type="button"
            class="sq-slot" :class="{ filled: !!item }"
            :title="item ? `${item.name}（点击移出预设）` : `预设槽位 ${n + 1}（点击下方表情装入）`"
            @dragover.prevent @drop.prevent="assign($event, n)"
            @click="item && favorite(item)"
          >
            <span class="slot-inner">
              <img v-if="item" :src="assetUrl(item.art)" :alt="item.name" draggable="false" />
              <svg v-else class="plus-cross" viewBox="0 0 36 36" width="26" height="26" aria-hidden="true">
                <path d="M18 7v22M7 18h22" stroke="currentColor" stroke-width="3.8" stroke-linecap="round" />
              </svg>
            </span>
          </button>
        </div>
        <small v-if="actionNote" class="fav-note">{{ actionNote }}</small>
      </div>
    </section>

    <!-- Sticky navigation bar -->
    <div class="sticky-nav">
      <div class="tabs-bar">
        <SegTabs v-model="mainTab" :tabs="mainTabs" label="背包分类" />
      </div>

      <div class="sub-bar">
        <div class="char-pills">
          <button type="button" :class="{ on: charFilter === 'all' }" @click="charFilter = 'all'">全角色</button>
          <button
            v-for="name in emoteOwners" :key="name" type="button"
            :class="{ on: charFilter === name }" @click="charFilter = name"
          >
            {{ name }}
          </button>
        </div>
        <input v-model="query" class="ui-input search-input" placeholder="搜索背包…" aria-label="搜索背包" />
      </div>
    </div>

    <p v-if="error" class="error-pill" role="alert">{{ error }}</p>

    <!-- Dedicated Character Row (separate from emotes, clean SVG portrait crop without monitor/desk) -->
    <section v-if="showPets" class="pet-section">
      <div v-if="mainTab === 'all'" class="sec-label">
        <Icon name="person" :size="13" />
        <span>桌宠形象</span>
        <small>{{ petSkins.length }}</small>
      </div>

      <div class="pet-grid">
        <button
          v-for="skin in petSkins" :key="`pet:${skin.name}`" type="button"
          class="pet-card" :class="{ active: settings.character === skin.name }"
          :title="`切换桌宠：${skin.name}`"
          @click="settings.character = skin.name; pokeStage()"
        >
          <span class="pet-well">
            <svg
              class="pet-svg"
              :viewBox="`${FACE_CROP.x} ${FACE_CROP.y} ${FACE_CROP.size} ${FACE_CROP.size}`"
              aria-hidden="true"
            >
              <image :href="skin.bg" :width="PET_BASE.width" :height="PET_BASE.height" />
            </svg>
            <span class="corner-badge" aria-hidden="true"><Icon name="person" :size="9" /></span>
            <span v-if="settings.character === skin.name" class="active-dot" aria-label="当前使用">
              <Icon name="star" :size="10" />
            </span>
          </span>
          <b class="card-name">{{ skin.name }}</b>
        </button>
      </div>
    </section>

    <!-- Owned Emotes in their own separate flat grid -->
    <section v-if="mainTab !== 'pet'" class="emote-section">
      <div v-if="mainTab === 'all' && showPets" class="sec-label">
        <Icon name="smile" :size="13" />
        <span>已拥有表情</span>
        <small>{{ ownedEmotes.length }}</small>
      </div>

      <div class="emote-grid">
        <div
          v-for="e in ownedEmotes" :key="e.key"
          class="emote-card owned"
          :class="[e.rarity, { fav: settings.favorites.includes(e.key) }]"
          :title="`${e.name}（${e.setName}）· 点击${settings.favorites.includes(e.key) ? '移出' : '装入'}预设`"
          draggable="true"
          role="button"
          tabindex="0"
          @dragstart="$event.dataTransfer?.setData('text/plain', e.key)"
          @click="toggleFavKey(e.key)"
        >
          <span class="art-well">
            <img :src="assetUrl(e.img)" :alt="e.name" loading="lazy" draggable="false" />
            <span class="corner-badge" aria-hidden="true"><Icon name="smile" :size="9" /></span>
            <span v-if="settings.favorites.includes(e.key)" class="eq-tag">预设</span>
            <button
              type="button"
              class="send-mini"
              title="立即发送该表情"
              @click.stop="fireEmote(e.key)"
            >
              <Icon name="spark" :size="10" />
            </button>
          </span>
          <b class="card-name">{{ e.name }}</b>
        </div>

        <!-- Shortcut tile to unlock/craft more emotes in Dex -->
        <button
          type="button"
          class="emote-card more-card"
          title="前往图鉴查看全部 375 个表情与碎片兑换"
          @click="ui.page = 'dex'"
        >
          <span class="art-well more-well">
            <Icon name="book" :size="22" />
          </span>
          <b class="card-name">全部图鉴 →</b>
        </button>
      </div>
    </section>

    <p v-if="!showPets && !showEmotes" class="empty">
      还没有匹配的物品，去 <button type="button" class="link-btn" @click="ui.page = 'dex'">图鉴</button> 开箱或用碎片兑换吧
    </p>

    <RevealModal v-if="drops.length" :drops="drops" @close="drops = []" />
  </div>
</template>

<style scoped>
.emotes-page {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  box-sizing: border-box;
  padding: 4px 22px 18px;
}

/* Generous top showcase matching WuwaTappo Reference Image 2 */
.showcase {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 2px 6px 8px;
}
.stage-cluster {
  position: relative;
  width: 244px;
  height: 158px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}
.fan-arc {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 72px;
  z-index: 2;
}
.fan-card {
  position: absolute;
  width: 40px;
  height: 40px;
  padding: 5px;
  margin: 0;
  box-sizing: border-box;
  border-radius: 10px;
  background: #FFF9F2;
  border: 1.5px solid var(--tile-border);
  box-shadow: 0 2px 5px rgba(92, 59, 40, 0.14);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 140ms, box-shadow 140ms;
}
.fan-card:hover {
  border-color: var(--accent);
  z-index: 3;
}
.fan-card img {
  max-width: 28px;
  max-height: 28px;
  width: auto;
  height: auto;
  object-fit: contain;
  display: block;
}

.dome {
  position: relative;
  width: 196px;
  height: 154px;
  border-radius: 90px 90px 36px 36px;
  background: radial-gradient(circle at 50% 42%, #FFF5E8 0%, #F4DFC7 100%);
  border: 2.5px solid #E4C9AC;
  box-shadow: inset 0 -5px 0 rgba(215, 180, 145, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  overflow: visible;
}
.dome-pet {
  display: flex;
  align-items: center;
  justify-content: center;
  transform: translateY(-2px);
}
.dome-name {
  position: absolute;
  bottom: 6px;
  padding: 1px 10px;
  border-radius: 999px;
  background: rgba(255, 249, 242, 0.92);
  border: 1.5px solid var(--tile-border);
  font-size: 11px;
  font-weight: 800;
  color: var(--ink-2);
}

.stage-divider {
  width: 2px;
  align-self: stretch;
  margin: 8px 0;
  background: var(--line);
  border-radius: 999px;
  flex: none;
}

.fav-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.fav-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.fav-title {
  font-size: 13.5px;
  font-weight: 800;
  color: var(--ink-2);
}
.fav-title small {
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-3);
}
.fav-note {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent-deep);
}
.resource-pills {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.res-pill,
.chest-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 9px;
  border-radius: 999px;
  background: var(--paper-2);
  border: 1.5px solid var(--tile-border);
  font-size: 11.5px;
  font-weight: 700;
  color: var(--ink);
}
.res-pill :deep(.icon),
.chest-pill :deep(.icon) {
  color: var(--accent-deep);
}
.res-pill small,
.chest-pill small {
  font-size: 10.5px;
  color: var(--ink-2);
}
.mini-bar {
  width: 36px;
  height: 5px;
  border-radius: 999px;
  background: #DFCCB6;
  overflow: hidden;
}
.mini-bar > i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
}
.mini-btn {
  height: 19px;
  padding: 0 7px;
  border-radius: 999px;
  border: 1.5px solid var(--tile-border);
  background: var(--card);
  color: var(--ink);
  font: 800 10.5px var(--font);
  cursor: pointer;
}
.mini-btn.primary {
  background: var(--accent);
  border-color: var(--accent-deep);
  color: var(--on-accent);
}
.mini-btn:disabled {
  opacity: 0.45;
  cursor: default;
}

/* 2 rows x 4 columns of chunky squircle + slots (matching WuwaTappo Image 2) */
.slots {
  display: grid;
  grid-template-columns: repeat(4, 64px);
  gap: 8px 10px;
}
.sq-slot {
  width: 64px;
  height: 62px;
  padding: 5px;
  margin: 0;
  box-sizing: border-box;
  border-radius: 18px;
  background: var(--tile-frame);
  border: 2px solid var(--tile-border);
  box-shadow: 0 3px 0 var(--tile-lip);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 120ms, border-color 140ms;
}
.sq-slot:hover {
  border-color: var(--accent);
  transform: translateY(-2px);
}
.sq-slot.filled {
  background: #FFF6EB;
  border-color: #F3B391;
}
.slot-inner {
  width: 100%;
  height: 100%;
  padding: 4px;
  box-sizing: border-box;
  border-radius: 12px;
  background: #F8EFE3;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.slot-inner img {
  max-width: 38px;
  max-height: 38px;
  width: auto;
  height: auto;
  object-fit: contain;
  display: block;
  margin: auto;
}
.plus-cross {
  color: #DAC5AE;
  display: block;
}

/* Sticky navigation & filter bar */
.sticky-nav {
  position: sticky;
  top: -4px;
  z-index: 6;
  background: var(--paper);
  padding: 4px 0 8px;
}
.tabs-bar {
  margin-bottom: 6px;
}
.sub-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.char-pills {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.char-pills button {
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1.5px solid transparent;
  background: var(--paper-2);
  color: var(--ink-2);
  font: 700 11.5px var(--font);
  cursor: pointer;
}
.char-pills button.on {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--on-accent);
}
.search-input {
  margin-left: auto;
  width: 148px;
  height: 25px;
  font-size: 11.5px;
}

.sec-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin: 2px 0 6px 2px;
  font-size: 12.5px;
  font-weight: 800;
  color: var(--ink-2);
}
.sec-label small {
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-3);
}

/* Dedicated Character Row (separate from emotes, clean SVG portrait crop) */
.pet-section {
  margin-bottom: 12px;
}
.pet-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
  gap: 10px;
  padding: 2px;
}
.pet-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 5px 5px 6px;
  margin: 0;
  box-sizing: border-box;
  border-radius: 18px;
  background: var(--tile-frame);
  border: 2px solid var(--tile-border);
  box-shadow: 0 2.5px 0 var(--tile-lip);
  cursor: pointer;
  font: inherit;
  color: var(--ink);
  transition: transform 120ms cubic-bezier(0.34, 1.56, 0.64, 1), border-color 140ms, box-shadow 140ms;
}
.pet-card:hover {
  transform: translateY(-2px);
  border-color: var(--accent);
}
.pet-card.active {
  background: #FFF6EB;
  border-color: var(--accent);
  box-shadow: 0 2.5px 0 var(--accent-deep), 0 0 12px rgba(var(--accent-rgb), 0.45);
}
.pet-well {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 3px;
  box-sizing: border-box;
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.25) 0 9px, transparent 9px 18px),
    var(--rar-epic-bg);
}
.pet-svg {
  width: 100%;
  height: 100%;
  display: block;
  transition: transform 150ms;
}
.pet-card:hover .pet-svg {
  transform: scale(1.06);
}
.active-dot {
  position: absolute;
  right: 4px;
  bottom: 4px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--accent);
  border: 1px solid var(--accent-deep);
  color: var(--on-accent);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Flat, compact Squircle Emote Grid */
.emote-section {
  padding-bottom: 12px;
}
.emote-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(78px, 1fr));
  gap: 8px;
  padding: 2px;
}
.emote-card {
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
  user-select: none;
  transition: transform 120ms cubic-bezier(0.34, 1.56, 0.64, 1), border-color 140ms, box-shadow 140ms;
}
.emote-card:hover {
  transform: translateY(-2px);
  border-color: var(--accent);
}
.emote-card.owned {
  background: #FFF8F0;
  border-color: #F4B99A;
  box-shadow: 0 2px 0 #DF9B78;
}
.emote-card.fav {
  background: #FFF5E8;
  border-color: var(--accent);
  box-shadow: 0 2px 0 var(--accent-deep), 0 0 10px rgba(var(--accent-rgb), 0.45);
}
.more-card {
  border-style: dashed;
  background: rgba(244, 230, 212, 0.55);
  color: var(--ink-2);
}
.more-well {
  background: rgba(255, 248, 240, 0.65) !important;
  color: var(--accent-deep);
}
.art-well {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 6px;
  box-sizing: border-box;
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.22) 0 8px, transparent 8px 18px),
    var(--rar-common-bg);
}
.emote-card.rare .art-well {
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.22) 0 8px, transparent 8px 18px),
    var(--rar-rare-bg);
}
.art-well img {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  display: block;
  margin: auto;
  transition: transform 150ms;
}
.emote-card:hover .art-well img {
  transform: scale(1.06);
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
.eq-tag {
  position: absolute;
  left: 3px;
  top: 3px;
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--accent);
  color: var(--on-accent);
  font-size: 9px;
  font-weight: 800;
}
.send-mini {
  position: absolute;
  right: 3px;
  top: 3px;
  width: 19px;
  height: 19px;
  padding: 0;
  margin: 0;
  box-sizing: border-box;
  border-radius: 50%;
  border: 1px solid var(--tile-border);
  background: rgba(255, 249, 242, 0.92);
  color: var(--accent-deep);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity 120ms, transform 120ms;
}
.emote-card:hover .send-mini {
  opacity: 1;
}
.send-mini:hover {
  transform: scale(1.12);
  background: var(--accent);
  color: var(--on-accent);
}
.card-name {
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

.error-pill {
  align-self: flex-start;
  margin: 0 0 6px;
  padding: 3px 12px;
  border-radius: 999px;
  background: #FDE8E6;
  border: 1px solid #F3B7B2;
  color: var(--bad);
  font-size: 12px;
  font-weight: 700;
}
.empty {
  color: var(--ink-3);
  text-align: center;
  padding: 32px 0;
  font-size: 13px;
  font-weight: 700;
}
.link-btn {
  border: 0;
  background: transparent;
  color: var(--accent-deep);
  font: inherit;
  font-weight: 800;
  text-decoration: underline;
  cursor: pointer;
}

@media (max-width: 780px) {
  .showcase {
    flex-direction: column;
    align-items: stretch;
  }
  .stage-divider {
    display: none;
  }
}
</style>
