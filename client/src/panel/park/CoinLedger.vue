<script setup lang="ts">
// The save's own coin history (behind the coin page's band key): coins in and out per day with the day's net, and
// the redeem codes it used with what each gave. Loaded each time the sheet opens.
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
    <div ref="tabs" class="park-sheet-tabs" role="tablist" @keydown="arrowSelect($event, tabs)">
      <button
        v-for="t in TABS" :key="t.id" type="button" role="tab" class="ui-btn" :class="{ on: tab === t.id }"
        :aria-selected="tab === t.id" :tabindex="tab === t.id ? 0 : -1" @click="tab = t.id"
      >{{ t.label }}</button>
    </div>

    <p v-if="error" class="err" role="alert">{{ error }}</p>
    <div v-else-if="data && tab === 'coins'" class="ledger" role="tabpanel">
      <section v-for="d in days" :key="d.day" class="day">
        <p class="park-sheet-head head">
          <span>{{ dayName(d.day) }}</span>
          <b :class="{ up: d.net > 0 }"><img :src="COIN_SMALL" alt="" draggable="false" />{{ signed(d.net) }}</b>
        </p>
        <ul class="park-sheet-list">
          <li v-for="i in d.items" :key="i.source" class="park-sheet-row line">
            <span class="park-sheet-main"><b>{{ sourceLabel(i.source) }}</b></span>
            <span class="park-sheet-figure" :class="{ up: i.amount > 0 }">{{ signed(i.amount) }}</span>
          </li>
        </ul>
      </section>
      <p v-if="!days.length" class="ui-empty">暂无</p>
    </div>
    <div v-else-if="data" class="ledger" role="tabpanel">
      <ul v-if="data.redeems.length" class="park-sheet-list single">
        <li v-for="(r, k) in data.redeems" :key="k" class="park-sheet-row line">
          <span class="park-sheet-main">
            <b class="code">{{ r.code }}</b>
            <small>{{ dayName(chinaDay(r.ts)) }}</small>
          </span>
          <span class="park-sheet-figure got">
            <span v-if="r.shards"><Icon name="shard" :size="18" />+{{ fmt(r.shards) }}</span>
            <span v-if="r.coins"><img :src="COIN_SMALL" alt="" draggable="false" />+{{ fmt(r.coins) }}</span>
          </span>
        </li>
      </ul>
      <p v-else class="ui-empty">暂无</p>
    </div>
  </ParkSheet>
</template>

<style scoped>
.ledger {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
/* The day and its net coins. */
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.head b {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.head img {
  width: 18px;
  height: 18px;
}
/* Ledger lines carry no picture on the left: words and a number. */
.park-sheet-row.line {
  --lead: 0px;
  min-height: 0;
  padding: 10px 16px;
}
.line .park-sheet-figure {
  font-size: 20px;
}
/* Coins gained: coral, as the page's own result when it is up. */
.line .up,
.head b.up {
  color: var(--c-700);
}
.code {
  font-family: var(--font-latin);
  letter-spacing: 0.08em;
}
.got {
  display: inline-flex;
  align-items: center;
  gap: 14px;
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
  width: 20px;
  height: 20px;
}
.err {
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--c-700);
}
</style>
