<script setup lang="ts">
// 图鉴: everything that exists, grouped by rarity, with what is still missing as silhouettes.
import { computed, reactive, ref } from "vue";
import { isOwned, items, RARITY_DESC, RARITY_LABEL, type Item, type ItemKind } from "../items";
import { collection, freshItems, unlocked } from "../stores/player";
import SegTabs from "../ui/SegTabs.vue";
import ItemCard from "../ui/ItemCard.vue";
import Icon from "../ui/Icon.vue";
import ItemDetail from "./ItemDetail.vue";

type Tab = "all" | "character" | "accessory" | "emote" | "card" | "dress";
const tab = ref<Tab>("all");
const TAB_KINDS: Record<Tab, ItemKind[]> = {
  all: ["character", "accessory", "emote", "card", "theme", "frame", "badge"],
  character: ["character"],
  accessory: ["accessory"],
  emote: ["emote"],
  card: ["card"],
  dress: ["theme", "frame", "badge"],
};
const own = computed(() => ({ owned: collection.owned, unlocked: unlocked.value }));
const has = (i: Item) => isOwned(i, own.value);

const tabs = computed(() =>
  (Object.keys(TAB_KINDS) as Tab[]).map((id) => {
    const list = items.filter((i) => TAB_KINDS[id].includes(i.kind));
    const label = { all: "全部", character: "角色", accessory: "配件", emote: "表情", card: "卡牌", dress: "装扮" }[id];
    return { id, label, count: undefined as number | undefined, have: list.filter(has).length, total: list.length };
  }),
);
const current = computed(() => tabs.value.find((t) => t.id === tab.value)!);

const groups = computed(() => {
  const list = items.filter((i) => TAB_KINDS[tab.value].includes(i.kind));
  const out: { id: string; name: string; list: Item[]; have: number }[] = [];
  for (const r of RARITY_DESC) {
    const g = list.filter((i) => i.rarity === r && !i.starter);
    if (g.length) out.push({ id: r, name: RARITY_LABEL[r], list: g, have: g.filter(has).length });
  }
  const start = list.filter((i) => i.starter || i.kind === "character");
  if (start.length) out.push({ id: "starter", name: "初始", list: start, have: start.length });
  const decor = list.filter((i) => i.kind === "frame" || i.kind === "badge");
  if (decor.length) out.push({ id: "decor", name: "集卡解锁", list: decor, have: decor.filter(has).length });
  return out;
});

// big groups start folded so the page opens quickly
const folded = reactive(new Set<string>());
const isFolded = (g: { id: string; list: Item[] }) =>
  folded.has(`${tab.value}:${g.id}`) !== (g.list.length > 80);
function toggle(g: { id: string }) {
  const k = `${tab.value}:${g.id}`;
  if (folded.has(k)) folded.delete(k);
  else folded.add(k);
}
const pct = computed(() => Math.round((current.value.have / Math.max(1, current.value.total)) * 100));
const detail = ref<Item | null>(null);
function show(i: Item) {
  freshItems.delete(i.id);
  detail.value = i;
}
</script>

<template>
  <div class="dex">
    <div class="progress ui-card">
      <div class="nums"><b>{{ current.have }}</b><span>/ {{ current.total }}</span></div>
      <div class="meter">
        <div class="ui-bar"><i :style="{ width: `${pct}%` }"></i></div>
        <small class="ui-hint">已收集 {{ pct }}%，重复获得的会变成碎片，可以去合成换没有的</small>
      </div>
    </div>

    <SegTabs v-model="tab" :tabs="tabs.map((t) => ({ id: t.id, label: t.label }))" label="图鉴分类" />

    <section v-for="g in groups" :key="`${tab}-${g.id}`" class="group" :class="`g-${g.id}`">
      <button type="button" class="ghead" :aria-expanded="!isFolded(g)" @click="toggle(g)">
        <span class="dot"></span>
        <b>{{ g.name }}</b>
        <span class="count">{{ g.have }}/{{ g.list.length }}</span>
        <Icon name="down" :size="16" class="chev" :class="{ up: !isFolded(g) }" />
      </button>
      <div v-if="!isFolded(g)" class="grid">
        <ItemCard
          v-for="i in g.list" :key="i.id" :item="i" :locked="!has(i)" :fresh="freshItems.has(i.id)"
          :count="collection.owned[i.id] ?? 0" :size="88" @click="show(i)"
        />
      </div>
    </section>

    <ItemDetail v-if="detail" :item="detail" @close="detail = null" />
  </div>
</template>

<style scoped>
.dex { display: flex; flex-direction: column; gap: 16px; }
.progress { display: flex; align-items: center; gap: 18px; padding: 14px 18px; }
.nums b { font-size: 28px; font-weight: 800; color: var(--accent); font-variant-numeric: tabular-nums; }
.nums span { margin-left: 4px; font-size: 14px; color: var(--ink-3); font-weight: 700; }
.meter { flex: 1; display: flex; flex-direction: column; gap: 6px; }
.group { display: flex; flex-direction: column; gap: 12px; }
.ghead { align-self: flex-start; display: flex; align-items: center; gap: 8px; border: none; background: none; cursor: pointer; font: inherit; color: var(--ink); padding: 2px 0; }
.ghead b { font-size: 15px; }
.count { font-size: 13px; color: var(--ink-3); font-weight: 700; font-variant-numeric: tabular-nums; }
.dot { width: 10px; height: 10px; border-radius: 50%; background: var(--paper-3); }
.g-legendary .dot { background: var(--rar-legendary); } .g-epic .dot { background: var(--rar-epic); }
.g-rare .dot { background: var(--rar-rare); } .g-common .dot { background: var(--rar-common); }
.g-starter .dot, .g-decor .dot { background: var(--accent); }
.chev { color: var(--ink-3); transition: transform 150ms; }
.chev.up { transform: rotate(180deg); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); gap: 14px 10px; justify-items: center; }
</style>
