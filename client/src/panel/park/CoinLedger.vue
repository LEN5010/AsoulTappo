<script setup lang="ts">
// The save's own coin history (behind the 明细 key in the coin page's bottom bar): coins in and out per day with the
// day's net, and the redeem codes it used with what each gave. Aligned with LotteryBoard's tabular rows and soft
// hairline rules. Loaded each time the sheet opens.
import { computed, onMounted, ref } from "vue";
import { arrowSelect } from "../../ui/focus";
import Icon from "../../ui/Icon.vue";
import { COIN_SMALL } from "./coin";
import { chinaDay, dayNet, loadLedger, signed, sortItems, sourceLabel, type Ledger } from "./ledger";
import { dayBefore, shortDay } from "./lottery";
import ParkSheet from "./ParkSheet.vue";

defineEmits<{ close: [] }>();

type Tab = "coins" | "codes";
const TABS: { id: Tab; label: string }[] = [{ id: "coins", label: "驼币明细" }, { id: "codes", label: "兑换记录" }];
const tab = ref<Tab>("coins");
const tabs = ref<HTMLElement>();

const data = ref<Ledger | null>(null);
const error = ref("");

onMounted(async () => {
  const r = await loadLedger();
  if (r.ok) data.value = r.data;
  else error.value = r.message;
});

const today = chinaDay(Date.now() / 1000);
const dayName = (d: string) => (d === today ? "今日" : d === dayBefore(today) ? "昨日" : shortDay(d));
const days = computed(() => (data.value?.days ?? []).map((d) => ({ day: d.day, net: dayNet(d), items: sortItems(d.items) })));
const fmt = (n: number) => n.toLocaleString("en-US");
</script>

<template>
  <ParkSheet title="明细" @close="$emit('close')">
    <div ref="tabs" class="park-sheet-tabs" role="tablist" aria-label="明细分类" @keydown="arrowSelect($event, tabs)">
      <button
        v-for="t in TABS" :id="`ledger-tab-${t.id}`" :key="t.id" type="button" role="tab"
        class="ui-btn" :class="{ on: tab === t.id }" :aria-selected="tab === t.id"
        :aria-controls="`ledger-panel-${t.id}`" :tabindex="tab === t.id ? 0 : -1"
        @click="tab = t.id"
      >{{ t.label }}</button>
    </div>

    <p v-if="error" class="err" role="alert">{{ error }}</p>
    <div v-else-if="data && tab === 'coins'" id="ledger-panel-coins" class="ledger" role="tabpanel" aria-labelledby="ledger-tab-coins">
      <section v-for="d in days" :key="d.day" class="day-board" :class="{ gain: d.net > 0, loss: d.net < 0 }">
        <header class="day-head">
          <span class="day-name">{{ dayName(d.day) }}</span>
          <b class="day-net" :class="{ up: d.net > 0, down: d.net < 0 }">
            <img :src="COIN_SMALL" alt="" draggable="false" />{{ signed(d.net) }}
          </b>
        </header>
        <ol class="day-rows">
          <li v-for="i in d.items" :key="i.source" :class="{ gain: i.amount > 0 }">
            <span class="src">
              <i class="swatch" aria-hidden="true"></i>
              <b>{{ sourceLabel(i.source) }}</b>
            </span>
            <span class="cnt"><template v-if="i.count > 1">{{ fmt(i.count) }} 次</template></span>
            <span class="amt" :class="{ up: i.amount > 0, down: i.amount < 0 }">{{ signed(i.amount) }}</span>
          </li>
        </ol>
      </section>
      <p v-if="!days.length" class="ui-empty">暂无</p>
    </div>
    <div v-else-if="data" id="ledger-panel-codes" class="ledger" role="tabpanel" aria-labelledby="ledger-tab-codes">
      <div v-if="data.redeems.length" class="code-board">
        <div class="board-head" aria-hidden="true"><span>兑换码</span><span>日期</span><span>获得</span></div>
        <ol class="code-rows">
          <li v-for="(r, k) in data.redeems" :key="k">
            <b class="code">{{ r.code }}</b>
            <span class="when">{{ dayName(chinaDay(r.ts)) }}</span>
            <span class="got">
              <span v-if="r.shards"><Icon name="shard" :size="16" />+{{ fmt(r.shards) }}</span>
              <span v-if="r.coins"><img :src="COIN_SMALL" alt="" draggable="false" />+{{ fmt(r.coins) }}</span>
            </span>
          </li>
        </ol>
      </div>
      <p v-else class="ui-empty">暂无</p>
    </div>
  </ParkSheet>
</template>

<style scoped>
.ledger {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ---- Daily coin board: --c-100 day header strip over tabular --c-50 rows split by soft hairlines, as LotteryBoard. */
.day-board,
.code-board {
  overflow: hidden;
  border-radius: var(--radius-l);
  background: var(--c-50);
}
.day-head {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  height: 36px;
  padding: 0 16px;
  background: var(--c-100);
}
.day-board.gain .day-head::before {
  content: "";
  position: absolute;
  left: 0;
  top: 7px;
  bottom: 7px;
  width: 3.5px;
  border-radius: 0 3px 3px 0;
  background: var(--c-500);
}
.day-name {
  font: 800 var(--fs-strong)/1 var(--font);
  color: var(--ink);
}
.day-net {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font: 800 17px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-3);
}
.day-net img {
  width: 18px;
  height: 18px;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.2));
}
.day-net.up {
  color: var(--c-700);
}
.day-net.down {
  color: var(--ink-2);
}

.day-rows,
.code-rows {
  margin: 0;
  padding: 0;
  list-style: none;
}
.day-rows li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 64px 86px;
  align-items: center;
  column-gap: 10px;
  min-height: 40px;
  padding: 0 16px;
}
.day-rows li + li {
  border-top: 1px solid var(--c-100);
}
.day-rows li.gain {
  background: color-mix(in oklab, var(--surface) 65%, var(--c-50));
}
.src {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.swatch {
  flex: none;
  width: 4px;
  height: 14px;
  border-radius: 2px;
  background: var(--c-200);
}
.day-rows li.gain .swatch {
  background: var(--c-500);
}
.src b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 700 var(--fs-body)/1.2 var(--font);
  color: var(--ink);
}
.cnt {
  text-align: right;
  font: 700 var(--fs-label)/1 var(--font);
  font-variant-numeric: tabular-nums;
  color: var(--ink-3);
  white-space: nowrap;
}
.amt {
  text-align: right;
  font: 800 19px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-3);
  white-space: nowrap;
}
.amt.up {
  color: var(--c-700);
}
.amt.down {
  color: var(--ink-2);
}

/* ---- Redeem history board: header strip + newest entry highlighted on crisp surface, as LotteryBoard. */
.board-head,
.code-rows li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 68px auto;
  align-items: center;
  column-gap: 12px;
  padding: 0 16px;
}
.board-head {
  height: 30px;
  background: var(--c-100);
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-2);
}
.board-head span:nth-child(3) {
  text-align: right;
}
.code-rows li {
  min-height: 42px;
}
.code-rows li + li {
  border-top: 1px solid var(--c-100);
}
.code-rows li:first-child {
  position: relative;
  min-height: 46px;
  background: var(--surface);
  box-shadow: 0 1px 0 var(--c-100);
}
.code-rows li:first-child::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3.5px;
  border-radius: 0 3px 3px 0;
  background: var(--c-500);
}
.code {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 800 16px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.08em;
  color: var(--ink);
}
.when {
  font: 700 var(--fs-label)/1 var(--font);
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
  white-space: nowrap;
}
.got {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  font: 800 18px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--c-700);
  white-space: nowrap;
}
.got span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.got svg {
  color: var(--c-600);
}
.got img {
  width: 18px;
  height: 18px;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.2));
}
.err {
  margin: 0;
  padding: 6px 10px;
  border-radius: var(--radius-s);
  background: var(--bad-soft);
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--bad);
}

@container panel (max-height: 560px) {
  .day-rows li,
  .code-rows li {
    min-height: 36px;
  }
  .code-rows li:first-child {
    min-height: 40px;
  }
}
</style>
