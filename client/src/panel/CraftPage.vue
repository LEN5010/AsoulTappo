<script setup lang="ts">
// 合成: open boxes, and turn shards from duplicates into a chosen missing item.
import { computed, ref, watch } from "vue";
import { collectible, craftCost, getItem, isOwned, RARITY_DESC, RARITY_LABEL, type Item, type ItemKind } from "../items";
import { manifest } from "../manifest";
import type { Drop } from "../net/api";
import { boxes, collection, craftItem, error, online, openBoxes, shards, status, unlocked } from "../stores/player";
import { ui } from "../stores/ui";
import { skin, reducedMotion } from "../stores/theme";
import ChestIcon from "../pet/ChestIcon.vue";
import SegTabs from "../ui/SegTabs.vue";
import ItemCard from "../ui/ItemCard.vue";
import ItemArt from "../ui/ItemArt.vue";
import Icon from "../ui/Icon.vue";
import RevealModal from "./RevealModal.vue";

const prog = computed(() => status.value?.progress);
const pct = (v: number, max?: number) => (max ? Math.min(100, Math.round((v / max) * 100)) : 0);
const busy = ref(false);
const reveal = ref<{ drops: Drop[]; title?: string } | null>(null);
const batch = computed(() => Math.min(boxes.value, 10));

async function open(count: number) {
  busy.value = true;
  const drops = await openBoxes(count);
  if (drops && !reducedMotion.value) await new Promise((r) => setTimeout(r, 500));
  busy.value = false;
  if (drops?.length) reveal.value = { drops };
}

// ---- crafting
type Tab = "accessory" | "emote" | "card" | "theme";
const tab = ref<Tab>("accessory");
const query = ref("");
const own = computed(() => ({ owned: collection.owned, unlocked: unlocked.value }));
const missing = computed(() =>
  collectible
    .filter((i) => i.kind === (tab.value as ItemKind) && !isOwned(i, own.value))
    .filter((i) => !query.value.trim() || `${i.name}${i.group}${i.characters.join("")}`.includes(query.value.trim()))
    .sort((a, b) => RARITY_DESC.indexOf(a.rarity!) - RARITY_DESC.indexOf(b.rarity!)),
);
const tabs = computed(() =>
  ([["accessory", "配件"], ["emote", "表情"], ["card", "卡牌"], ["theme", "主题"]] as [Tab, string][]).map(([id, label]) => ({
    id, label, count: collectible.filter((i) => i.kind === id && !isOwned(i, own.value)).length,
  })),
);
const selected = ref<Item | null>(null);
watch(() => ui.craftTarget, (id) => {
  const it = id ? getItem(id) : undefined;
  if (it && it.kind !== "character" && it.kind !== "frame" && it.kind !== "badge") {
    tab.value = it.kind as Tab;
    selected.value = it;
    ui.craftTarget = "";
  }
}, { immediate: true });
const cost = computed(() => (selected.value ? craftCost(selected.value) ?? 0 : 0));
async function craft() {
  const it = selected.value;
  if (!it) return;
  busy.value = true;
  const ok = await craftItem(it.id);
  busy.value = false;
  if (ok) {
    reveal.value = { drops: [{ item: it.id, rarity: it.rarity!, new: true, count: 1, shards: 0 }], title: "合成成功" };
    selected.value = null;
  }
}
</script>

<template>
  <div class="craft">
    <section class="row">
      <div class="ui-card chest">
        <div class="art" :class="{ shake: busy }"><ChestIcon :size="72" :open="busy" /><span v-if="boxes" class="n">×{{ boxes }}</span></div>
        <div class="info">
          <b>宝箱</b>
          <div class="bars">
            <label>敲击 {{ prog?.taps ?? 0 }} / {{ prog?.tapsPerBox ?? 600 }}<div class="ui-bar"><i :style="{ width: `${pct(prog?.taps ?? 0, prog?.tapsPerBox)}%` }"></i></div></label>
            <label>活跃分钟 {{ prog?.minutes ?? 0 }} / {{ prog?.minutesPerBox ?? 10 }}<div class="ui-bar alt"><i :style="{ width: `${pct(prog?.minutes ?? 0, prog?.minutesPerBox)}%` }"></i></div></label>
          </div>
          <small class="ui-hint">今日已得 {{ status?.boxesToday ?? 0 }}/{{ status?.dailyCap ?? 10 }}</small>
          <div class="btns">
            <button type="button" class="ui-btn primary" :disabled="!boxes || busy || !online" @click="open(1)">
              <img v-if="busy && skin.loading && !reducedMotion" class="spin" :src="skin.loading" alt="" />开一个
            </button>
            <button type="button" class="ui-btn" :disabled="boxes < 2 || busy || !online" @click="open(batch)">全部打开{{ boxes > 1 ? `（${batch}）` : "" }}</button>
          </div>
          <small v-if="!online" class="err">{{ error || "服务器未连接" }}</small>
        </div>
      </div>
      <div class="ui-card shards">
        <div class="sh"><Icon name="shard" :size="26" /><b>{{ shards }}</b><span>碎片</span></div>
        <table>
          <thead><tr><th></th><th>重复获得</th><th>合成消耗</th></tr></thead>
          <tbody>
            <tr v-for="r in RARITY_DESC" :key="r" :class="`r-${r}`">
              <td><i></i>{{ RARITY_LABEL[r] }}</td><td>+{{ manifest.economy.dupShards[r] }}</td><td>{{ manifest.economy.craftCost[r] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="pick">
      <header>
        <h4 class="ui-label">合成指定物品</h4>
        <label class="search"><Icon name="search" :size="16" /><input v-model="query" class="ui-input" placeholder="搜索名字 / 系列 / 角色" /></label>
      </header>
      <SegTabs v-model="tab" :tabs="tabs" label="合成分类" />
      <div v-if="missing.length" class="grid">
        <ItemCard
          v-for="i in missing" :key="i.id" :item="i" :selected="selected?.id === i.id" :size="86"
          :note="`${craftCost(i)} 碎片`" @click="selected = selected?.id === i.id ? null : i"
        />
      </div>
      <p v-else class="ui-muted empty">{{ query ? "没有找到" : "这一类已经集齐啦" }}</p>
    </section>

    <Transition name="slide">
      <div v-if="selected" class="dock ui-card">
        <span class="tile" :class="`r-${selected.rarity}`"><ItemArt :item="selected" :size="44" /></span>
        <span class="what"><b>{{ selected.name }}</b><small>{{ RARITY_LABEL[selected.rarity!] }} · {{ selected.group }}</small></span>
        <button type="button" class="ui-btn primary" :disabled="busy || !online || shards < cost" @click="craft">
          {{ shards < cost ? `还差 ${cost - shards} 碎片` : `合成（消耗 ${cost} 碎片）` }}
        </button>
      </div>
    </Transition>

    <RevealModal v-if="reveal" :drops="reveal.drops" :title="reveal.title" @close="reveal = null" />
  </div>
</template>

<style scoped>
.craft { display: flex; flex-direction: column; gap: 20px; padding-bottom: 64px; }
.row { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr); gap: 12px; }
.chest { display: flex; gap: 16px; padding: 14px; align-items: center; }
.art { position: relative; width: 96px; height: 96px; border-radius: var(--r-l); display: grid; place-items: center; background: #fbf3e2; flex: none; }
.art.shake { animation: shake 320ms linear infinite; }
.art .n { position: absolute; right: 6px; top: 6px; padding: 0 5px; border-radius: var(--r-s); background: var(--accent); color: var(--on-accent); font-weight: 700; font-size: 12px; font-variant-numeric: tabular-nums; }
.info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.info > b { font-size: 15px; }
.bars { display: flex; flex-direction: column; gap: 6px; }
.bars label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--ink-2); font-variant-numeric: tabular-nums; }
.ui-bar.alt > i { background: var(--char); }
.btns { display: flex; gap: 8px; flex-wrap: wrap; }
.spin { width: 18px; height: 18px; object-fit: contain; }
.err { color: var(--bad); font-size: 12px; }
.shards { padding: 14px; display: flex; flex-direction: column; gap: 10px; }
.sh { display: flex; align-items: center; gap: 8px; color: var(--accent); }
.sh b { font-size: 24px; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }
.sh span { color: var(--ink-3); font-weight: 600; font-size: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { font-weight: 600; color: var(--ink-3); text-align: right; padding: 0 0 4px; border-bottom: 1px solid var(--line); }
td { padding: 4px 0; text-align: right; font-variant-numeric: tabular-nums; color: var(--ink-2); }
td:first-child { text-align: left; display: flex; align-items: center; gap: 6px; color: var(--ink); font-weight: 600; }
td i { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.r-common td i { background: var(--rar-common); } .r-rare td i { background: var(--rar-rare); }
.r-epic td i { background: var(--rar-epic); } .r-legendary td i { background: var(--rar-legendary); }
.pick { display: flex; flex-direction: column; gap: 12px; }
.pick header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.pick header .ui-label { margin: 0; }
.search { display: flex; align-items: center; gap: 6px; color: var(--ink-3); }
.search input { width: 200px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(90px, 1fr)); gap: 14px 10px; justify-items: center; }
.empty { text-align: center; padding: 24px 0; }
.dock { position: sticky; bottom: 0; display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-color: var(--line-2); box-shadow: var(--shadow-2); }
.tile { width: 52px; height: 52px; border-radius: var(--r-m); display: grid; place-items: center; background: var(--rar-common-bg); flex: none; }
.tile.r-rare { background: var(--rar-rare-bg); } .tile.r-epic { background: var(--rar-epic-bg); } .tile.r-legendary { background: var(--rar-legendary-bg); }
.what { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.what b { font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.what small { font-size: 12px; color: var(--ink-3); }
.slide-enter-active, .slide-leave-active { transition: opacity 160ms, transform 160ms; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(8px); }
@keyframes shake { 0%, 100% { transform: rotate(0); } 25% { transform: rotate(-4deg); } 75% { transform: rotate(4deg); } }
</style>
