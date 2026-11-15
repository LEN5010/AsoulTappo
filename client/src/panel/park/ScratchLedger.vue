<script setup lang="ts">
// The save's own coin scratch cards (behind the 明细 key in the scratch page's bottom bar): per day the coins spent
// and the shards won, per kind the cards scratched with the shards and coins they paid, and each item won with its
// picture. Loaded each time the sheet opens.
import { computed, onMounted, ref } from "vue";
import { getItem, KIND_LABEL, RARITY_LABEL, type Item } from "../../items";
import Icon from "../../ui/Icon.vue";
import ItemArt from "../../ui/ItemArt.vue";
import { COIN_SMALL } from "./coin";
import { chinaDay, dayShards, loadScratchHistory, scratchKindName, signed, type ScratchDay } from "./ledger";
import { dayBefore, shortDay } from "./lottery";
import ParkSheet from "./ParkSheet.vue";

defineEmits<{ close: [] }>();

const data = ref<ScratchDay[] | null>(null);
const error = ref("");

onMounted(async () => {
  const r = await loadScratchHistory();
  if (r.ok) data.value = r.days;
  else error.value = r.message;
});

const today = chinaDay(Date.now() / 1000);
const dayName = (d: string) => (d === today ? "今日" : d === dayBefore(today) ? "昨日" : shortDay(d));
/** An item's kind in the words of the drop it is: 表情, 皮肤, or the card's rarity (大隐藏). */
const itemTag = (item: Item) =>
  item.kind === "emote" ? KIND_LABEL.emote : (item.rarity && RARITY_LABEL[item.rarity]) || KIND_LABEL[item.kind];
const days = computed(() => (data.value ?? []).map((d) => ({
  day: d.day,
  spent: d.spent,
  won: dayShards(d),
  kinds: d.kinds,
  // Items this client does not know (a newer release's) are left out.
  items: d.kinds.flatMap((k) => k.items.map(getItem).filter((i): i is Item => !!i).map((item) => ({ item, kind: k.kind }))),
})));
const fmt = (n: number) => n.toLocaleString("en-US");
</script>

<template>
  <ParkSheet title="刮刮乐明细" @close="$emit('close')">
    <p v-if="error" class="err" role="alert">{{ error }}</p>
    <div v-else-if="data" class="ledger">
      <section v-for="d in days" :key="d.day">
        <p class="park-sheet-head head">
          <span>{{ dayName(d.day) }}</span>
          <span class="sums">
            <b :title="`花费 ${fmt(d.spent)} 驼币`"><img :src="COIN_SMALL" alt="驼币" draggable="false" />{{ signed(-d.spent) }}</b>
            <b :class="{ up: d.won > 0 }" :title="`赢得 ${fmt(d.won)} 碎片`"><Icon name="shard" :size="16" />{{ signed(d.won) }}</b>
          </span>
        </p>
        <ul class="park-sheet-list single">
          <li v-for="k in d.kinds" :key="k.kind" class="park-sheet-row line">
            <span class="park-sheet-main">
              <b>{{ scratchKindName(k.kind) }}</b>
              <small>{{ fmt(k.cards) }} 张</small>
            </span>
            <span class="park-sheet-figure figs">
              <span v-if="k.coins" class="up"><img :src="COIN_SMALL" alt="驼币" draggable="false" />{{ signed(k.coins) }}</span>
              <span :class="{ up: k.shards > 0 }"><Icon name="shard" :size="18" />{{ signed(k.shards) }}</span>
            </span>
          </li>
          <li v-for="(w, i) in d.items" :key="i" class="park-sheet-row prize">
            <span class="park-sheet-lead bare"><ItemArt :item="w.item" :size="44" /></span>
            <span class="park-sheet-main">
              <b>{{ w.item.name }}</b>
              <small>{{ itemTag(w.item) }} · {{ scratchKindName(w.kind) }}</small>
            </span>
          </li>
        </ul>
      </section>
      <p v-if="!days.length" class="ui-empty">暂无</p>
    </div>
  </ParkSheet>
</template>

<style scoped>
.ledger {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
/* The day, the coins it spent on cards and the shards they won. */
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.sums {
  display: inline-flex;
  align-items: center;
  gap: 16px;
}
.sums b,
.figs span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.sums b {
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.sums img {
  width: 18px;
  height: 18px;
}
.park-sheet-row.line {
  --lead: 0px;
  min-height: 0;
  padding: 10px 16px;
}
.figs {
  display: inline-flex;
  align-items: center;
  gap: 16px;
  font-size: 20px;
}
.figs img {
  width: 20px;
  height: 20px;
}
/* An item won: its picture on the left, as the odds sheet's rows. */
.park-sheet-row.prize {
  --lead: 44px;
}
/* Won: coral, as the coin ledger's gains. */
.up,
.sums b.up {
  color: var(--c-700);
}
.err {
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--c-700);
}
</style>
