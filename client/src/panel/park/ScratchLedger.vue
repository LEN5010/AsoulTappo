<script setup lang="ts">
// The save's own coin scratch cards (behind the 明细 key in the scratch page's bottom bar): aligned with LotteryBoard's
// crisp tabular record sheet. One day group per row, newest featured on white with a coral (or gold) edge mark, showing
// tier tags, cards scratched, coins spent vs refunded, shards won, and any collectibles dropped.
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

const SHORT_KIND: Record<string, string> = { basic: "普通", premium: "豪华" };
const kindTag = (kind: string) => SHORT_KIND[kind] ?? scratchKindName(kind);

const today = chinaDay(Date.now() / 1000);
const dayName = (d: string) => (d === today ? "今日" : d === dayBefore(today) ? "昨日" : shortDay(d));
/** An item's kind in the words of the drop it is: 表情, 皮肤, or the card's rarity (大隐藏). */
const itemTag = (item: Item) =>
  item.kind === "emote" ? KIND_LABEL.emote : (item.rarity && RARITY_LABEL[item.rarity]) || KIND_LABEL[item.kind];

const days = computed(() =>
  (data.value ?? []).map((d) => {
    const items = d.kinds.flatMap((k) =>
      k.items
        .map(getItem)
        .filter((i): i is Item => !!i)
        .map((item) => ({ item, kind: k.kind })),
    );
    return {
      day: d.day,
      spent: d.spent,
      coinsWon: d.kinds.reduce((sum, k) => sum + k.coins, 0),
      won: dayShards(d),
      kinds: d.kinds,
      items,
      gold: items.some((w) => w.item.rarity === "legendary"),
    };
  }),
);
const fmt = (n: number) => n.toLocaleString("en-US");
</script>

<template>
  <ParkSheet title="刮刮乐明细" @close="$emit('close')">
    <p v-if="error" class="ui-error err" role="alert">{{ error }}</p>
    <div v-else-if="data && days.length" class="board">
      <div class="board-head" aria-hidden="true">
        <span>日期</span>
        <span>档位</span>
        <span class="num-col">花费</span>
        <span class="num-col">赢得</span>
      </div>
      <ol class="rows ui-scroll">
        <li v-for="d in days" :key="d.day" class="day-entry" :class="{ hit: d.gold }">
          <div class="day-line">
            <span class="day">{{ dayName(d.day) }}</span>
            <span class="tiers">
              <span v-for="k in d.kinds" :key="k.kind" class="tier-chip" :title="`${scratchKindName(k.kind)} ${fmt(k.cards)} 张`">
                <i class="ui-tag tier-badge" :class="{ dark: k.kind === 'premium' }">{{ kindTag(k.kind) }}</i>
                <b class="cards-num">{{ fmt(k.cards) }}</b><small>张</small>
              </span>
            </span>
            <span class="spent" :title="`花费 ${fmt(d.spent)} 驼币`">
              <img :src="COIN_SMALL" alt="驼币" draggable="false" />{{ signed(-d.spent) }}
            </span>
            <span class="won">
              <span v-if="d.coinsWon > 0" class="coin-back" :title="`再来一张 +${fmt(d.coinsWon)}`">
                <img :src="COIN_SMALL" alt="驼币" draggable="false" />+{{ fmt(d.coinsWon) }}
              </span>
              <span class="shard-won" :class="{ up: d.won > 0, none: !d.won }" :title="`赢得 ${fmt(d.won)} 碎片`">
                <template v-if="d.won > 0"><Icon name="shard" :size="14" />+{{ fmt(d.won) }}</template>
                <template v-else>—</template>
              </span>
            </span>
          </div>

          <ul v-if="d.kinds.length > 1" class="sub-kinds">
            <li v-for="k in d.kinds" :key="k.kind" class="sub-line">
              <span class="sub-spacer" aria-hidden="true"></span>
              <span class="sub-name">
                <i class="swatch" :class="{ dark: k.kind === 'premium' }" aria-hidden="true"></i>
                {{ scratchKindName(k.kind) }}
                <small>{{ fmt(k.cards) }} 张</small>
              </span>
              <span class="sub-empty" aria-hidden="true"></span>
              <span class="won">
                <span v-if="k.coins > 0" class="coin-back">
                  <img :src="COIN_SMALL" alt="驼币" draggable="false" />+{{ fmt(k.coins) }}
                </span>
                <span class="shard-won" :class="{ up: k.shards > 0, none: !k.shards }">
                  <template v-if="k.shards > 0"><Icon name="shard" :size="13" />+{{ fmt(k.shards) }}</template>
                  <template v-else>—</template>
                </span>
              </span>
            </li>
          </ul>

          <ul v-if="d.items.length" class="drops">
            <li v-for="(w, i) in d.items" :key="i" class="drop-chip">
              <span class="drop-art"><ItemArt :item="w.item" :size="36" /></span>
              <span class="drop-meta">
                <b>{{ w.item.name }}</b>
                <span class="drop-tags">
                  <i
                    class="ui-tag"
                    :class="{ gold: w.item.rarity === 'legendary', dark: w.item.rarity === 'skin' }"
                  >{{ itemTag(w.item) }}</i>
                  <small>{{ kindTag(w.kind) }}</small>
                </span>
              </span>
            </li>
          </ul>
        </li>
      </ol>
    </div>
    <p v-else-if="data" class="ui-empty">暂无</p>
  </ParkSheet>
</template>

<style scoped>
.err {
  margin: 0;
}

/* Clean record board aligned with LotteryBoard: --c-100 column strip over --c-50 ground, newest day featured on white
 * with a coral (or legendary gold) left bar. */
.board {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  border-radius: var(--radius-l);
  background: var(--c-50);
}
.board-head,
.day-line,
.sub-line {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) 82px 132px;
  align-items: center;
  column-gap: 10px;
  padding: 0 14px;
}
.board-head {
  flex: none;
  height: 32px;
  background: var(--c-100);
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-2);
}
.board-head span {
  white-space: nowrap;
}
.board-head .num-col {
  text-align: right;
}

.rows {
  margin: 0;
  padding: 0;
  list-style: none;
}
.day-entry {
  position: relative;
  padding: 2px 0;
  color: var(--ink-2);
}
.day-entry + .day-entry {
  border-top: 1px solid var(--c-100);
}
.day-entry:first-child {
  background: var(--surface);
  box-shadow: 0 1px 0 var(--c-100);
  color: var(--ink);
}
.day-entry:first-child + .day-entry {
  border-top: 0;
}
.day-entry:first-child::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3.5px;
  border-radius: 0 3px 3px 0;
  background: var(--c-500);
}
.day-entry:first-child.hit::before {
  background: var(--gold);
}

.day-line {
  min-height: 40px;
  font-size: var(--fs-label);
  font-weight: 700;
}
.day-entry:first-child .day-line {
  min-height: 46px;
}
.day {
  white-space: nowrap;
  color: inherit;
}

.tiers {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  min-width: 0;
}
.tier-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}
.tier-badge {
  --tag-bg: var(--c-200);
  --tag-fg: var(--ink);
}
.day-entry:first-child .tier-badge:not(.dark) {
  --tag-bg: var(--c-400);
}
.cards-num {
  font: 800 var(--fs-strong)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.tier-chip small {
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-2);
}

.spent {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
  white-space: nowrap;
}
.spent img,
.coin-back img {
  width: 15px;
  height: 15px;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.22));
}

.won {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  font: 800 16px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.day-entry:first-child .won {
  font-size: 18px;
}
.coin-back,
.shard-won {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.coin-back,
.shard-won.up {
  color: var(--c-700);
}
.shard-won.up svg {
  color: var(--c-600);
}
.shard-won.none {
  color: var(--ink-3);
}

/* Breakdown rows when multiple card kinds were played on the same day. */
.sub-kinds {
  margin: 0;
  padding: 0 0 6px;
  list-style: none;
}
.sub-line {
  min-height: 28px;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-2);
}
.sub-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.sub-name small {
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-3);
}
.swatch {
  width: 3.5px;
  height: 11px;
  border-radius: 2px;
  background: var(--c-400);
}
.swatch.dark {
  background: var(--c-800);
}
.sub-line .won {
  font-size: var(--fs-strong);
}

/* Collectible items dropped on that day, tucked neatly under the day's tabular row. */
.drops {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 2px 14px 10px 66px;
  list-style: none;
}
.drop-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 4px 10px 4px 5px;
  border-radius: var(--radius-m);
  background: var(--c-100);
}
.drop-art {
  flex: none;
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: var(--radius-s);
  background: var(--surface);
}
.drop-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.drop-meta b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 800 var(--fs-label)/1.2 var(--font);
  color: var(--ink);
}
.drop-tags {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.drop-tags small {
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-2);
}

@container panel (max-width: 560px) {
  .board-head,
  .day-line,
  .sub-line {
    grid-template-columns: 48px minmax(0, 1fr) 68px 106px;
    column-gap: 6px;
    padding: 0 10px;
  }
  .drops {
    padding: 2px 10px 8px 10px;
  }
}
</style>
