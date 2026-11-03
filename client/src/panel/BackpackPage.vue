<script setup lang="ts">
// 背包: what the pet wears (live preview), quick emotes, presets and everything owned.
import { computed, onBeforeUnmount, ref } from "vue";
import { getItem, items, isOwned, ownsEmote, starterEmotesOf, type Item } from "../items";
import { getAccessory } from "../manifest";
import { settings } from "../stores/settings";
import { pet } from "../stores/pet";
import {
  applyPreset, chooseDecor, clearPreset, collection, freshItems, online, presets, savePreset, status, unlocked,
} from "../stores/player";
import { syncProfile } from "../stores/room";
import { skin } from "../stores/theme";
import { ui, type BagTab } from "../stores/ui";
import { EmotePlayer, type EmoteFrame } from "../pet/EmotePlayer";
import PetView from "../pet/PetView.vue";
import SegTabs from "../ui/SegTabs.vue";
import ItemCard from "../ui/ItemCard.vue";
import ItemArt from "../ui/ItemArt.vue";
import CharacterAvatar from "../ui/CharacterAvatar.vue";
import Icon from "../ui/Icon.vue";
import ItemDetail from "./ItemDetail.vue";

const MAX_FAVS = 8;
const own = computed(() => ({ owned: collection.owned, unlocked: unlocked.value }));
const has = (i: Item) => isOwned(i, own.value);

// ---- live preview
const preview = ref<EmoteFrame | null>(null);
const player = new EmotePlayer((f) => (preview.value = f), () => settings.emoteHoldMs);
onBeforeUnmount(() => player.clear());
const quickKeys = computed(() => (settings.favorites.length ? settings.favorites : starterEmotesOf(settings.character)));
function pokeStage() {
  const keys = quickKeys.value;
  if (keys.length) player.play(keys[Math.floor(Math.random() * keys.length)]);
}

// ---- favorites
const hint = ref("");
function toggleFavorite(key: string) {
  const i = settings.favorites.indexOf(key);
  if (i >= 0) settings.favorites.splice(i, 1);
  else if (settings.favorites.length < MAX_FAVS) settings.favorites.push(key);
  else {
    hint.value = `最多 ${MAX_FAVS} 个`;
    setTimeout(() => (hint.value = ""), 2400);
    return;
  }
  player.play(key);
}
const favSlots = computed(() => Array.from({ length: MAX_FAVS }, (_, i) => settings.favorites[i] ?? null));

// ---- tabs and lists
const tabs = computed<{ id: BagTab; label: string; count?: number }[]>(() => [
  { id: "recent", label: "最近获得" },
  { id: "character", label: "角色", count: lists.value.character.length },
  { id: "accessory", label: "配件", count: lists.value.accessory.length },
  { id: "emote", label: "表情", count: lists.value.emote.length },
  { id: "card", label: "卡牌", count: lists.value.card.length },
  { id: "dress", label: "装扮", count: lists.value.dress.length },
]);
const lists = computed(() => {
  const mine = items.filter(has);
  const recentIds = [...new Set(collection.recent.map((r) => r.item))];
  return {
    recent: recentIds.map(getItem).filter((i): i is Item => !!i),
    character: mine.filter((i) => i.kind === "character"),
    accessory: mine.filter((i) => i.kind === "accessory"),
    emote: mine.filter((i) => i.kind === "emote" && ownsEmote(i.ref, collection.owned)),
    card: mine.filter((i) => i.kind === "card"),
    dress: mine.filter((i) => i.kind === "theme" || i.kind === "frame" || i.kind === "badge"),
  };
});
const shown = computed(() => lists.value[ui.bagTab]);
const emoteGroups = computed(() => {
  const groups = new Map<string, Item[]>();
  for (const i of lists.value.emote) groups.set(i.group, [...(groups.get(i.group) ?? []), i]);
  return [...groups.entries()].map(([name, list]) => ({ name, list }));
});

function equipped(i: Item): boolean {
  switch (i.kind) {
    case "character": return settings.character === i.ref;
    case "accessory": return settings.head === i.ref || settings.desk === i.ref;
    case "emote": return settings.favorites.includes(i.ref);
    case "theme": return settings.theme === i.ref;
    case "frame": return status.value?.frame === i.ref;
    case "badge": return status.value?.badge === i.ref;
    default: return false;
  }
}

const detail = ref<Item | null>(null);
async function use(i: Item) {
  freshItems.delete(i.id);
  switch (i.kind) {
    case "character":
      settings.character = i.ref;
      break;
    case "accessory": {
      const slot = getAccessory(i.ref)?.slot;
      if (slot) settings[slot] = settings[slot] === i.ref ? "" : i.ref;
      break;
    }
    case "emote":
      toggleFavorite(i.ref);
      break;
    case "theme":
      settings.theme = i.ref;
      break;
    case "frame":
    case "badge": {
      const next = equipped(i) ? "" : i.ref;
      if (await chooseDecor({ [i.kind]: next })) syncProfile({ [i.kind]: next });
      break;
    }
    default:
      detail.value = i;
  }
}

// ---- presets
async function onPreset(slot: number) {
  if (!presets.value[slot]) {
    await savePreset(slot);
    return;
  }
  const decor = await applyPreset(slot);
  if (decor) syncProfile(decor);
}
const headItem = computed(() => (settings.head ? getItem(`acc:${settings.head}`) : undefined));
const deskItem = computed(() => (settings.desk ? getItem(`acc:${settings.desk}`) : undefined));
const presetHead = (slot: number) => {
  const h = presets.value[slot]?.loadout.head;
  return h ? getItem(`acc:${h}`) : undefined;
};
</script>

<template>
  <div class="bag">
    <section class="top">
      <div class="stage ui-card" :style="{ backgroundImage: skin.banner ? `url(${skin.banner})` : undefined }">
        <div class="scrim"></div>
        <button type="button" class="pet-btn" title="戳一下" @click="pokeStage">
          <PetView
            :character="settings.character" :scale="1.12" :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
            :left-down="pet.left" :right-down="pet.right" :head="settings.head" :desk="settings.desk" :emote="preview"
          />
        </button>
        <div class="worn">
          <span class="tag">{{ settings.character }}</span>
          <span v-if="headItem" class="tag">头顶 · {{ headItem.name }}</span>
          <span v-if="deskItem" class="tag">桌面 · {{ deskItem.name }}</span>
        </div>
      </div>

      <div class="side">
        <div class="presets">
          <header><h4 class="ui-label">我的预设</h4><small v-if="!online" class="ui-hint">服务器未连接</small></header>
          <div class="slots">
            <div v-for="(p, i) in presets" :key="i" class="slot" :class="{ empty: !p }">
              <button type="button" class="main" :disabled="!online" :title="p ? `换上「${p.name}」` : '保存当前搭配'" @click="onPreset(i)">
                <template v-if="p">
                  <span class="av">
                    <CharacterAvatar :character="p.loadout.character || settings.character" :size="34" />
                    <ItemArt v-if="presetHead(i)" class="mini" :item="presetHead(i)!" :size="20" />
                  </span>
                  <span class="pname">{{ p.name }}</span>
                </template>
                <Icon v-else name="plus" :size="22" />
              </button>
              <span v-if="p" class="ops">
                <button type="button" title="用当前搭配覆盖" aria-label="覆盖保存" @click="savePreset(i, p.name)"><Icon name="refresh" :size="13" /></button>
                <button type="button" title="删除" aria-label="删除预设" @click="clearPreset(i)"><Icon name="trash" :size="13" /></button>
              </span>
            </div>
          </div>
        </div>
        <div class="favs">
          <header><h4 class="ui-label">常用表情</h4><small v-if="hint" class="ui-hint">{{ hint }}</small></header>
          <div class="fav-row">
            <button
              v-for="(k, i) in favSlots" :key="i" type="button" class="fav" :class="{ empty: !k }" :disabled="!k"
              :title="k ? '点一下移出常用' : '空位'" @click="k && toggleFavorite(k)"
            >
              <ItemArt v-if="k && getItem(`emote:${k}`)" :item="getItem(`emote:${k}`)!" :size="44" />
            </button>
          </div>
        </div>
      </div>
    </section>

    <SegTabs v-model="ui.bagTab" :tabs="tabs" label="背包分类" />

    <section class="list">
      <template v-if="ui.bagTab === 'emote'">
        <div v-for="g in emoteGroups" :key="g.name" class="group">
          <h4>{{ g.name }}</h4>
          <div class="grid">
            <ItemCard v-for="i in g.list" :key="i.id" :item="i" :equipped="equipped(i)" :fresh="freshItems.has(i.id)" :size="84" @click="use(i)" />
          </div>
        </div>
      </template>
      <div v-else-if="shown.length" class="grid">
        <ItemCard
          v-for="i in shown" :key="i.id" :item="i" :equipped="equipped(i)" :fresh="freshItems.has(i.id)"
          :count="collection.owned[i.id] ?? 0" @click="use(i)"
        />
      </div>
      <p v-else class="none ui-muted">
        {{ ui.bagTab === "recent" ? "还没有获得物品" : "这里还空着" }}
      </p>
    </section>

    <ItemDetail v-if="detail" :item="detail" @close="detail = null" />
  </div>
</template>

<style scoped>
.bag { display: flex; flex-direction: column; gap: 18px; }
.top { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr); gap: 20px; }
.stage { position: relative; overflow: hidden; min-height: 236px; display: flex; flex-direction: column; align-items: center; justify-content: center; background: var(--tint) center / cover; }
.scrim { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(252, 251, 250, 0.1), rgba(252, 251, 250, 0.7)); }
.pet-btn { position: relative; margin-top: 18px; padding: 0; border: none; background: none; cursor: pointer; }
.worn { position: relative; display: flex; flex-wrap: wrap; justify-content: center; gap: 4px; margin: 10px 12px 12px; }
.tag { font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: var(--r-s); background: rgba(255, 255, 255, 0.92); color: var(--ink-2); }
.side { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.side header { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.slots { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
.slot { position: relative; }
.slot .main {
  width: 100%; aspect-ratio: 1; border-radius: var(--r-l); border: 1px solid var(--line); cursor: pointer; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; padding: 4px; overflow: hidden; box-sizing: border-box;
  background: #fff; color: var(--ink-3); font: inherit; transition: border-color 120ms, background 120ms;
}
.slot .main:hover:not(:disabled) { border-color: var(--line-2); background: var(--paper-2); }
.slot.empty .main { border-style: dashed; border-color: var(--line-2); background: none; }
.av { position: relative; display: grid; }
.av .mini { position: absolute; right: -8px; top: -8px; }
.pname { font-size: 10px; font-weight: 600; color: var(--ink-2); max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ops { position: absolute; right: -4px; top: -6px; display: none; gap: 2px; }
.slot:hover .ops, .slot:focus-within .ops { display: flex; }
.ops button { width: 22px; height: 22px; border-radius: var(--r-s); border: 1px solid var(--line-2); display: grid; place-items: center; background: #fff; color: var(--ink-2); cursor: pointer; }
.ops button:hover { color: var(--ink); background: var(--paper-2); }
.fav-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.fav { width: 100%; min-width: 0; aspect-ratio: 1; max-height: 54px; border-radius: var(--r-l); border: 1px solid var(--line); padding: 0; display: grid; place-items: center; background: #fff; cursor: pointer; box-sizing: border-box; }
.fav.empty { background: none; border-style: dashed; border-color: var(--line-2); cursor: default; }
.fav:not(.empty):hover { border-color: rgba(207, 75, 71, 0.5); background: rgba(207, 75, 71, 0.06); }
.list { min-height: 120px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 14px 12px; justify-items: center; }
.group + .group { margin-top: 16px; }
.group h4 { margin: 0 0 8px; font-size: 12px; font-weight: 700; color: var(--ink-3); }
.group .grid { grid-template-columns: repeat(auto-fill, minmax(84px, 1fr)); }
.none { text-align: center; padding: 30px 0; font-size: 13px; }
</style>
