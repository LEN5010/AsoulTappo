<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { characterColor, getEmote, manifest } from "../manifest";
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
import { rise } from "../ui/motion";

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
// Stickers run down the stage's slanted left edge.
const STICKER_ARC = [
  { x: 30, y: 2, rot: -9 },
  { x: 20, y: 44, rot: 6 },
  { x: 12, y: 86, rot: -5 },
  { x: 2, y: 128, rot: 8 },
];

function pokeStage() {
  const keys = quickKeys.value;
  if (keys.length) player.play(keys[Math.floor(Math.random() * keys.length)]!);
}

const root = ref<HTMLElement>();
const listing = ref<HTMLElement>();
watch([mainTab, charFilter], () => nextTick(() => rise(listing.value, root.value)));

// Replays the member-color band over the stage on every character switch.
const ribbon = ref(0);
watch(() => settings.character, () => ribbon.value++);

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
  <div ref="root" class="emotes-page ui-scroll">
    <section class="showcase">
      <div class="stage-cluster" data-rise>
        <div class="stage" title="点击桌宠预览表情" @click="pokeStage">
          <span class="stage-bg" aria-hidden="true">
            <i class="stage-dots"></i>
            <i class="stage-stripe"></i>
            <i v-if="ribbon" :key="ribbon" class="stage-ribbon"></i>
          </span>
          <div class="stage-pet">
            <PetView
              :character="settings.character" :scale="0.84"
              :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
              :left-down="pet.left" :right-down="pet.right" :emote="preview" :min-emote="38"
            />
          </div>
          <span class="stage-name"><i aria-hidden="true"></i>{{ settings.character }}</span>
        </div>

        <button
          v-for="(s, i) in stageStickers" :key="s.key" type="button"
          class="sticker" :title="`预览：${s.emo!.name}`"
          :style="{
            left: `${STICKER_ARC[i]?.x ?? 0}px`,
            top: `${STICKER_ARC[i]?.y ?? i * 34}px`,
            '--rot': `${STICKER_ARC[i]?.rot ?? 0}deg`,
          }"
          @click="player.play(s.key)"
        >
          <img :src="assetUrl(s.emo!.img)" :alt="s.emo!.name" decoding="async" draggable="false" />
        </button>
      </div>

      <div class="fav-panel" data-rise>
        <div class="fav-head">
          <h3 class="fav-title">我的预设</h3>
          <b class="fav-count">{{ settings.favorites.length }}<small>/8</small></b>
          <small class="fav-hint">点击下方表情即可装卸</small>
        </div>

        <div class="fav-body">
          <div class="slots">
            <button
              v-for="(item, n) in favorites" :key="n" type="button"
              class="sq-slot" :class="{ filled: !!item }"
              :title="item ? `${item.name}（点击移出预设）` : `预设槽位 ${n + 1}（点击下方表情装入）`"
              @dragover.prevent @drop.prevent="assign($event, n)"
              @click="item && favorite(item)"
            >
              <img v-if="item" :src="assetUrl(item.art)" :alt="item.name" decoding="async" draggable="false" />
              <Icon v-else name="plus" :size="18" />
            </button>
          </div>

          <div class="resources">
            <div class="res" title="表情碎片（可在图鉴中兑换未拥有的表情）">
              <Icon name="shard" :size="15" />
              <b>{{ shards }}</b><small>碎片</small>
            </div>
            <div
              class="res chest"
              :title="`敲击 ${status?.progress.taps ?? 0}/${status?.progress.tapsPerBox ?? 600} · 活跃 ${status?.progress.minutes ?? 0}/${status?.progress.minutesPerBox ?? 10} 分钟 · 今日 ${status?.boxesToday ?? 0}/${status?.dailyCap ?? 10} 箱`"
            >
              <Icon name="box" :size="15" />
              <b>{{ boxes }}</b><small>箱</small>
              <span class="ui-bar res-bar"><i :style="{ width: `${tapPct}%` }"></i></span>
            </div>
            <div class="res-actions">
              <button type="button" class="ui-btn small primary" :disabled="busy || !online || !boxes" @click="open(false)">开箱</button>
              <button v-if="boxes > 1" type="button" class="ui-btn small" :disabled="busy || !online" @click="open(true)">全开</button>
            </div>
          </div>
        </div>
        <small v-if="actionNote" class="fav-note">{{ actionNote }}</small>
      </div>
    </section>

    <div class="sticky-nav">
      <SegTabs v-model="mainTab" :tabs="mainTabs" label="背包分类" />

      <div class="sub-bar">
        <div class="char-chips">
          <button type="button" :class="{ on: charFilter === 'all' }" @click="charFilter = 'all'">全角色</button>
          <button
            v-for="name in emoteOwners" :key="name" type="button"
            :class="{ on: charFilter === name }" @click="charFilter = name"
          >
            <i :style="{ background: characterColor(name) }" aria-hidden="true"></i>{{ name }}
          </button>
        </div>
        <input v-model="query" class="ui-input search-input" placeholder="搜索背包…" aria-label="搜索背包" />
      </div>
    </div>

    <p v-if="error" class="error-note" role="alert">{{ error }}</p>

    <div ref="listing">
      <section v-if="showPets" class="pet-section">
        <div v-if="mainTab === 'all'" class="sec-label" data-rise>
          <i aria-hidden="true"></i>
          <b>桌宠形象</b>
          <em>CHARACTER</em>
          <small>{{ petSkins.length }}</small>
        </div>

        <div class="pet-grid">
          <button
            v-for="skin in petSkins" :key="`pet:${skin.name}`" type="button"
            class="pet-card" :class="{ active: settings.character === skin.name }"
            :title="`切换桌宠：${skin.name}`" data-rise
            @click="settings.character = skin.name; pokeStage()"
          >
            <span class="pet-well">
              <svg
                class="pet-svg"
                :viewBox="`${FACE_CROP.x} -8 ${FACE_CROP.w} ${FACE_CROP.h + 8}`"
                preserveAspectRatio="xMidYMax meet"
                aria-hidden="true"
              >
                <svg
                  :x="FACE_CROP.x"
                  :y="FACE_CROP.y"
                  :width="FACE_CROP.w"
                  :height="FACE_CROP.h"
                  :viewBox="`${FACE_CROP.x} ${FACE_CROP.y} ${FACE_CROP.w} ${FACE_CROP.h}`"
                  overflow="hidden"
                >
                  <image :href="skin.bg" x="0" y="0" :width="PET_BASE.width" :height="PET_BASE.height" />
                </svg>
              </svg>
              <span v-if="settings.character === skin.name" class="tag" aria-label="当前使用">使用中</span>
            </span>
            <b class="card-name"><i :style="{ background: characterColor(skin.name) }" aria-hidden="true"></i>{{ skin.name }}</b>
          </button>
        </div>
      </section>

      <section v-if="mainTab !== 'pet'" class="emote-section">
        <div v-if="mainTab === 'all' && showPets" class="sec-label" data-rise>
          <i aria-hidden="true"></i>
          <b>已拥有表情</b>
          <em>STICKER</em>
          <small>{{ ownedEmotes.length }}</small>
        </div>

        <div class="emote-grid">
          <div
            v-for="e in ownedEmotes" :key="e.key"
            class="emote-card"
            :class="[e.rarity, { fav: settings.favorites.includes(e.key) }]"
            :title="`${e.name}（${e.setName}）· 点击${settings.favorites.includes(e.key) ? '移出' : '装入'}预设`"
            draggable="true"
            role="button"
            tabindex="0"
            data-rise
            @dragstart="$event.dataTransfer?.setData('text/plain', e.key)"
            @click="toggleFavKey(e.key)"
          >
            <span class="art-well">
              <img :src="assetUrl(e.img)" :alt="e.name" loading="lazy" decoding="async" draggable="false" />
              <span v-if="settings.favorites.includes(e.key)" class="tag">预设</span>
            </span>
            <button
              type="button"
              class="send-mini"
              title="立即发送该表情"
              @click.stop="fireEmote(e.key)"
            >
              <Icon name="spark" :size="11" />
            </button>
            <b class="card-name">{{ e.name }}</b>
          </div>

          <!-- Shortcut tile to unlock/craft more emotes in Dex -->
          <button
            type="button"
            class="emote-card more-card"
            title="前往图鉴查看全部 375 个表情与碎片兑换"
            data-rise
            @click="ui.page = 'dex'"
          >
            <span class="art-well">
              <Icon name="book" :size="24" />
            </span>
            <b class="card-name">全部图鉴 →</b>
          </button>
        </div>
      </section>
    </div>

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
  padding: 0 20px 18px 16px;
}

.showcase {
  display: flex;
  align-items: stretch;
  gap: 18px;
  padding: 2px 0 12px;
}

/* The pet sits outside the clipped background so it and its emote bubble can break the frame. */
.stage-cluster {
  position: relative;
  width: 292px;
  height: 170px;
  flex: none;
}
.stage {
  position: absolute;
  inset: 0 0 0 26px;
  cursor: pointer;
}
.stage-bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: var(--accent);
  clip-path: polygon(24px 0, 100% 0, calc(100% - 24px) 100%, 0 100%);
}
.stage-dots {
  position: absolute;
  inset: 0;
  background: #fff;
  opacity: 0.4;
  mask: var(--halftone) left bottom / 150px auto repeat-x;
  -webkit-mask: var(--halftone) left bottom / 150px auto repeat-x;
}
.stage-stripe {
  position: absolute;
  top: 0;
  bottom: 0;
  right: 18px;
  width: 92px;
  background: rgba(255, 255, 255, 0.2);
  transform: skewX(var(--skew));
}
.stage-ribbon {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -20%;
  width: 140%;
  background: var(--char);
  transform: translateX(-112%) skewX(var(--skew));
  animation: ribbon 620ms var(--ease-in-out);
}
@keyframes ribbon {
  to {
    transform: translateX(112%) skewX(var(--skew));
  }
}
.stage-pet {
  position: absolute;
  left: 50%;
  bottom: 6px;
  transform: translateX(-46%);
}
/* Left of the head: the emote bubble grows to the right of it. */
.stage-name {
  position: absolute;
  left: 58px;
  top: 12px;
  isolation: isolate;
  display: flex;
  align-items: center;
  gap: 7px;
  height: 26px;
  padding: 0 12px 0 9px;
  font: 16px var(--font-display);
  color: #fff;
}
.stage-name::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -1;
  background: var(--ink);
  transform: skewX(var(--skew));
}
.stage-name i {
  width: 5px;
  height: 14px;
  background: var(--char);
  transform: skewX(var(--skew));
}

.sticker {
  --rot: 0deg;
  position: absolute;
  z-index: 2;
  width: 40px;
  height: 40px;
  padding: 3px;
  box-sizing: border-box;
  border: 0;
  background: var(--surface);
  box-shadow: 2px 2px 0 var(--ink);
  transform: rotate(var(--rot));
  cursor: pointer;
  transition: transform 240ms var(--ease-out);
}
.sticker:hover {
  z-index: 3;
  transform: rotate(0deg) scale(1.12);
}
.sticker img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
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
  align-items: baseline;
  gap: 8px;
}
.fav-title {
  margin: 0;
  font: 20px/1 var(--font-display);
  color: var(--ink);
}
.fav-count {
  font: italic 800 20px/1 var(--font-latin);
  color: var(--accent-deep);
}
.fav-count small {
  font: inherit;
  font-size: 14px;
  color: var(--ink-3);
}
.fav-hint {
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-3);
}
.fav-note {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent-deep);
}
.fav-body {
  display: flex;
  gap: 16px;
  min-width: 0;
}
.slots {
  display: grid;
  grid-template-columns: repeat(4, 60px);
  gap: 8px;
  flex: none;
}
.sq-slot {
  width: 60px;
  height: 60px;
  padding: 7px;
  box-sizing: border-box;
  border: 0;
  background: var(--accent-tint);
  color: var(--accent);
  clip-path: polygon(0 0, 100% 0, 100% calc(100% - 9px), calc(100% - 9px) 100%, 0 100%);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 160ms, transform 220ms var(--ease-out);
}
.sq-slot:hover {
  background: var(--accent-soft);
  transform: translate(-1px, -1px);
}
.sq-slot.filled {
  background: var(--accent-soft);
}
.sq-slot img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  display: block;
}

.resources {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 6px;
}
.res {
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: center;
  gap: 2px 6px;
  color: var(--accent-deep);
}
.res b {
  font: italic 800 24px/1 var(--font-latin);
  color: var(--ink);
}
.res small {
  font-size: 11.5px;
  font-weight: 700;
  color: var(--ink-2);
}
.res-bar {
  grid-column: 1 / -1;
  height: 5px;
  margin-top: 3px;
}
.res-actions {
  display: flex;
  gap: 8px;
  padding: 0 4px 3px 2px;
}
.res-actions .ui-btn {
  flex: 1;
  min-width: 0;
  padding: 0 6px;
}

.sticky-nav {
  position: sticky;
  top: 0;
  z-index: 6;
  background: rgba(255, 255, 255, 0.95);
  padding: 2px 0 8px;
}
.sub-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}
.char-chips {
  display: flex;
  gap: 5px;
  min-width: 0;
  padding-left: 3px;
}
.char-chips button {
  position: relative;
  isolation: isolate;
  height: 26px;
  padding: 0 11px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 0;
  background: none;
  color: var(--ink-2);
  font: 700 12px var(--font);
  cursor: pointer;
  white-space: nowrap;
  transition: color 160ms;
}
.char-chips button::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -1;
  background: var(--accent-tint);
  transform: skewX(var(--skew));
  transition: background 160ms;
}
.char-chips button:hover::before {
  background: var(--accent-soft);
}
.char-chips button.on {
  color: var(--on-accent);
}
.char-chips button.on::before {
  background: var(--accent);
}
.char-chips i {
  width: 4px;
  height: 11px;
  transform: skewX(var(--skew));
}
.search-input {
  margin-left: auto;
  width: 150px;
  height: 26px;
  padding: 0 10px;
  font-size: 12px;
}

.sec-label {
  display: flex;
  align-items: baseline;
  gap: 7px;
  margin: 4px 0 8px;
}
.sec-label i {
  align-self: center;
  width: 7px;
  height: 14px;
  background: var(--accent);
  transform: skewX(var(--skew));
}
.sec-label b {
  font: 16px/1 var(--font-display);
  color: var(--ink);
}
.sec-label em {
  font: italic 800 13px/1 var(--font-latin);
  letter-spacing: 0.08em;
  color: var(--accent);
}
.sec-label small {
  margin-left: auto;
  font: italic 800 15px/1 var(--font-latin);
  color: var(--ink-3);
}

/* Cards have no frame: a chamfered well and a name. Selection slides an offset block out from
   behind the well; clip-path would swallow a shadow, and a filter would double the name too. */
.pet-section {
  margin-bottom: 14px;
}
.pet-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}
.pet-card,
.emote-card {
  position: relative;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0;
  margin: 0;
  border: 0;
  background: none;
  cursor: pointer;
  font: inherit;
  color: var(--ink);
  user-select: none;
  transition: transform 240ms var(--ease-out);
  --well-clip: polygon(0 0, 100% 0, 100% calc(100% - var(--cut)), calc(100% - var(--cut)) 100%, 0 100%);
}
.pet-card {
  --cut: 14px;
  --well-ratio: 5 / 4;
}
.emote-card {
  --cut: 11px;
  --well-ratio: 1;
}
.pet-card::before,
.emote-card::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  aspect-ratio: var(--well-ratio);
  background: var(--accent);
  clip-path: var(--well-clip);
  opacity: 0;
  transition: transform 240ms var(--ease-out), opacity 120ms;
}
.pet-card:hover,
.emote-card:hover {
  transform: translate(-2px, -2px);
}
.pet-card:hover::before,
.pet-card.active::before,
.emote-card:hover::before,
.emote-card.fav::before {
  opacity: 1;
  transform: translate(4px, 4px);
}
.pet-well,
.art-well {
  position: relative;
  width: 100%;
  aspect-ratio: var(--well-ratio);
  box-sizing: border-box;
  display: flex;
  overflow: hidden;
  clip-path: var(--well-clip);
}
.pet-well {
  align-items: flex-end;
  justify-content: center;
  padding: 6px 4px 0;
  background: var(--dots) 0 0 / 9px 9px, var(--accent-tint);
}
.pet-card.active .pet-well {
  background: var(--accent-soft);
}
.pet-svg {
  width: 100%;
  height: 100%;
  display: block;
  transition: transform 260ms var(--ease-out);
}
.pet-card:hover .pet-svg {
  transform: scale(1.05);
}
.tag {
  position: absolute;
  left: 6px;
  top: 5px;
  z-index: 1;
  padding: 0 7px;
  font-size: 10px;
  font-weight: 800;
  line-height: 17px;
  color: var(--on-accent);
  isolation: isolate;
}
.tag::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -1;
  background: var(--accent);
  transform: skewX(var(--skew));
}

.emote-section {
  padding-bottom: 12px;
}
.emote-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(76px, 1fr));
  gap: 12px 10px;
}
.art-well {
  align-items: center;
  justify-content: center;
  padding: 7px;
  background: var(--rar-common-bg);
}
.emote-card.rare .art-well {
  background: var(--rar-rare-bg);
}
.emote-card.fav .art-well {
  background: var(--accent-soft);
}
.art-well img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  display: block;
  margin: auto;
  transition: transform 260ms var(--ease-out);
}
.emote-card:hover .art-well img {
  transform: scale(1.06);
}
.more-card .art-well {
  background: var(--accent);
  color: var(--on-accent);
}
.send-mini {
  position: absolute;
  right: 0;
  top: 0;
  width: 24px;
  height: 20px;
  padding: 0;
  border: 0;
  background: var(--ink);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity 140ms, background 140ms;
}
.emote-card:hover .send-mini,
.send-mini:focus-visible {
  opacity: 1;
}
.send-mini:hover {
  background: var(--accent-deep);
}
.card-name {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  width: 100%;
  margin-top: 5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11.5px;
  font-weight: 700;
}
.card-name i {
  flex: none;
  width: 4px;
  height: 11px;
  transform: skewX(var(--skew));
}
.pet-card .card-name {
  font: 15px var(--font-display);
}

.error-note {
  margin: 0 0 10px;
  padding: 4px 10px;
  background: #FDECEA;
  box-shadow: inset 3px 0 0 var(--bad);
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
  }
}
</style>
