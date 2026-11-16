<script setup lang="ts">
// The pool card of 每日夺宝: the top prize (the server-wide pool, rolling over until a draw has a top winner), with the
// second and the third under it, each with the trailing digits it takes. A new pool amount counts up from the one
// shown.
import { onBeforeUnmount, ref, watch } from "vue";
import Icon from "../../ui/Icon.vue";
import { countTo } from "./countTo";

const props = defineProps<{
  /** The top prize: the pool of the next draw; null before the state loads. */
  pool: number | null;
  second: number;
  third: number;
  /** The second prize is what each ticket wins, as the third is; on servers before it, a share of the sales. */
  secondEach: boolean;
  calm: boolean;
}>();

/** The top prize counts to a new amount over this long. */
const POOL_ROLL_MS = 700;
const fmt = (n: number) => n.toLocaleString("en-US");

const poolShown = ref(0);
let stopPool = () => {};
watch(() => props.pool, (to, was) => {
  stopPool();
  if (to == null) return;
  if (was == null || props.calm) poolShown.value = to;
  else stopPool = countTo(poolShown, to, POOL_ROLL_MS);
}, { immediate: true });
onBeforeUnmount(() => stopPool());
/** The trailing digits a prize takes, left to right: true where the digit must match. */
const needs = (hit: number) => [0, 1, 2].map((j) => j >= 3 - hit);
</script>

<template>
  <div class="pool-card" :aria-label="`头奖 累积奖池 ${fmt(pool ?? 0)}`">
    <div class="pool-head" aria-hidden="true">
      <span class="tier-name">头奖</span>
      <small>累积奖池</small>
      <span class="match"><i v-for="(on, j) in needs(3)" :key="j" :class="on ? 'lball' : 'hole'"></i></span>
    </div>
    <b class="pool-amount" aria-hidden="true"><Icon name="shard" :size="28" />{{ fmt(poolShown) }}</b>
    <ul class="tiers">
      <li :aria-label="`二等 ${fmt(second)}${secondEach ? ' /注' : ''}`">
        <span class="tier-head" aria-hidden="true">
          <span class="tier-name">二等</span>
          <span class="match"><i v-for="(on, j) in needs(2)" :key="j" :class="on ? 'lball' : 'hole'"></i></span>
        </span>
        <b class="amount" aria-hidden="true">
          <Icon name="shard" :size="14" />{{ fmt(second) }}<small v-if="secondEach">/注</small>
        </b>
      </li>
      <li :aria-label="`三等 ${fmt(third)} /注`">
        <span class="tier-head" aria-hidden="true">
          <span class="tier-name">三等</span>
          <span class="match"><i v-for="(on, j) in needs(1)" :key="j" :class="on ? 'lball' : 'hole'"></i></span>
        </span>
        <b class="amount" aria-hidden="true"><Icon name="shard" :size="14" />{{ fmt(third) }}<small>/注</small></b>
      </li>
    </ul>
  </div>
</template>

<style scoped src="./lottery-ball.css"></style>
<style scoped>
.pool-card {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 14px 14px 16px;
  border-radius: var(--radius-l);
  background: var(--grad-sky);
  box-shadow: inset 0 2px 0 rgba(255, 255, 255, 0.35);
  color: var(--ink);
}
.pool-head {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.tier-name {
  font: 800 var(--fs-label)/1 var(--font);
  white-space: nowrap;
}
.pool-head .tier-name {
  font-size: var(--fs-section);
}
.pool-head small {
  font: 700 var(--fs-label)/1 var(--font);
  white-space: nowrap;
}
.pool-head .match {
  align-self: center;
  margin-left: auto;
}
.pool-amount {
  display: flex;
  align-items: center;
  gap: 4px;
  font: 800 50px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.tiers {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.tiers li {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 8px 10px 9px;
  border-radius: var(--radius-m);
  background: var(--surface);
}
.tier-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
/* The number's three digits: a ball where the digit must match, an empty slot where it need not. */
.match {
  display: inline-flex;
  gap: 3px;
}
.match .lball {
  --s: 12px;
}
.match .hole {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: rgba(var(--c-900-rgb), 0.1);
}
/* On the coral card the balls are white. */
.pool-head .match .lball {
  --s: 15px;
  background: var(--surface);
}
.amount {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font: 800 22px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.amount svg {
  color: var(--c-700);
}
.amount small {
  margin-left: 2px;
  font: 600 var(--fs-caption) var(--font);
  color: var(--ink-2);
}

@container panel (max-width: 760px) {
  .pool-card {
    gap: 6px;
    padding: 10px 12px;
  }
  .pool-head .tier-name {
    font-size: var(--fs-strong);
  }
  .pool-head .match i {
    width: 11px;
    height: 11px;
  }
  .pool-amount {
    font-size: 32px;
  }
  .pool-amount svg {
    width: 20px;
    height: 20px;
  }
  .tiers {
    grid-template-columns: 1fr;
    gap: 4px;
  }
  .tiers li {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    padding: 5px 8px;
  }
  .tiers .match {
    display: none;
  }
  .tiers .amount {
    font-size: 17px;
  }
}

@container panel (max-height: 560px) {
  .pool-card {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    grid-template-areas:
      "head head"
      "amount tiers";
    align-items: center;
    gap: 6px 12px;
    padding: 10px 12px;
  }
  .pool-head {
    grid-area: head;
  }
  .pool-head .tier-name {
    font-size: var(--fs-strong);
  }
  .pool-amount {
    grid-area: amount;
    font-size: 38px;
  }
  .pool-amount svg {
    width: 22px;
    height: 22px;
  }
  .tiers {
    grid-area: tiers;
    grid-template-columns: 1fr;
    gap: 4px;
  }
  .tiers li {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    padding: 5px 8px;
  }
  .tiers .match {
    display: none;
  }
  .tiers .amount {
    font-size: 17px;
  }
}

@container panel (max-width: 760px) and (max-height: 560px) {
  .pool-card {
    display: flex;
    align-items: stretch;
  }
  .pool-amount {
    font-size: 28px;
  }
  .pool-amount svg {
    width: 18px;
    height: 18px;
  }
}
</style>
