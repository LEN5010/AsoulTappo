<script setup lang="ts">
// The park's two numbers in the panel's top bar, left of the shard balance, while the park is shown: the coins held
// (with the +n of coins just come in rising into it) and the server-wide pool on a coral key, the top prize of the next
// lottery draw. The coins are plain paper; the pool is a button (the top bar's drag skips buttons) that turns to the
// lottery page, while the park is open.
import { computed } from "vue";
import { status } from "../../stores/player";
import { park } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import { parkTab } from "./band";
import ParkCoin from "./ParkCoin.vue";
import { coinPops } from "./pops";

const fmt = (n: number) => n.toLocaleString("en-US");
const coins = computed(() => park.value?.coins ?? status.value?.park?.coins ?? 0);
const open = computed(() => !!park.value?.unlocked);

function toLottery() {
  if (open.value) parkTab.value = "lottery";
}
</script>

<template>
  <span class="park-chips" :class="{ calm: reducedMotion }">
    <span class="chip held" aria-label="驼币">
      <ParkCoin :size="22" />
      <b>{{ fmt(coins) }}</b>
      <span class="pops" aria-hidden="true">
        <i v-for="p in coinPops" :key="p.id" class="pop">+{{ p.n }}</i>
      </span>
    </span>
    <button
      type="button" class="chip pot" :class="{ live: open }" title="全服奖池" :aria-label="`全服奖池 ${park ? fmt(park.jackpot) : ''}`"
      :aria-disabled="open ? undefined : 'true'" @click="toLottery"
    >
      <small>奖池</small>
      <Icon name="shard" :size="14" />
      <b>{{ park ? fmt(park.jackpot) : "—" }}</b>
    </button>
  </span>
</template>

<style scoped>
.park-chips {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-right: 8px;
}
.chip {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 12px 0 8px;
  box-sizing: border-box;
  border-radius: var(--radius-key);
  white-space: nowrap;
  cursor: default;
}
.chip b {
  min-width: 1ch;
  font: 800 18px/1 var(--font-latin);
  color: var(--ink);
}
.held {
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
/* The pool is the park's top prize: a coral key with white type, like the lottery's pool card. A button that keeps
   the chip's look. */
.pot {
  margin: 0;
  padding-left: 10px;
  border: 0;
  font: inherit;
  background: var(--c-400);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4), var(--shadow-paper);
  color: #fff;
  transition: filter var(--dur-fast) var(--ease-out);
}
.pot b {
  color: #fff;
}
.pot.live {
  cursor: pointer;
}
.pot.live:hover {
  filter: brightness(1.05);
}
.pot small {
  margin-right: 2px;
  font: 700 var(--fs-label)/1 var(--font);
}

/* +n comes up from under the chip into the count and fades: there is no room above the panel's edge. */
.pops {
  position: absolute;
  left: 30px;
  top: 100%;
  pointer-events: none;
}
.pop {
  position: absolute;
  left: 0;
  top: 0;
  font: 800 20px/1 var(--font-latin);
  font-style: normal;
  color: var(--c-700);
  white-space: nowrap;
  text-shadow: 0 0 2px var(--surface), 0 0 4px var(--surface);
  animation: pop-in 1100ms var(--ease-out) both;
}
.calm .pop {
  animation: none;
}
@keyframes pop-in {
  0% { opacity: 0; transform: translateY(14px) scale(0.8); }
  22% { opacity: 1; transform: translateY(2px) scale(1.08); }
  72% { opacity: 1; transform: translateY(-6px); }
  100% { opacity: 0; transform: translateY(-14px); }
}
</style>
