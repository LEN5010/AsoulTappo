<script setup lang="ts">
// The board of the latest draws on 每日夺宝's side: one draw a row, newest first, with its day, its number, who won
// the top prize and what each won. While a draw's first showing plays on the keys its row stays blank; once all three
// digits rest, its number drops in.
import Icon from "../../ui/Icon.vue";
import { shortDay } from "./lottery";
import type { PastDraw } from "./lotteryState";

const props = defineProps<{
  past: PastDraw[];
  /** The day whose draw is showing on the keys; "" when none. */
  reveal: string;
  /** Trailing digits of that draw at rest. */
  stopped: number;
}>();

const fmt = (n: number) => n.toLocaleString("en-US");
/** A draw on the board stays blank while its first showing is still playing on the keys. */
const unseen = (day: string) => !!props.reveal && props.reveal === day && props.stopped < 3;
</script>

<template>
  <!-- One draw a row, newest first: its day, its number, who won the top prize and what each won. -->
  <div v-if="past.length" class="board">
    <div class="board-head" aria-hidden="true"><span>日期</span><span>开奖号码</span><span>头奖</span><span>奖金</span></div>
    <ol class="rows ui-scroll">
      <li v-for="h in past" :key="h.day" :class="{ unseen: unseen(h.day) }">
        <span class="day">{{ shortDay(h.day) }}</span>
        <span
          class="num" :class="{ in: !!reveal && reveal === h.day && stopped === 3 }"
          :aria-label="`开奖号码 ${h.number}`"
        ><i v-for="(d, i) in h.number.split('')" :key="i" :style="{ '--i': i }">{{ d }}</i></span>
        <span class="winners" :class="{ none: !h.top.length }" :title="h.top.length > 1 ? h.winners : undefined">{{ h.first }}</span>
        <span class="prize" :class="{ none: !h.top.length }">
          <template v-if="h.top.length"><Icon name="shard" :size="13" />{{ fmt(h.each) }}</template>
          <template v-else>—</template>
        </span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
/* The board: a header strip, then one draw a row, the newest on white. */
.board {
  flex: 0 1 auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  border-radius: var(--radius-l);
  background: var(--c-50);
}
.board-head,
.rows li {
  display: grid;
  grid-template-columns: 56px 48px minmax(0, 1fr) auto;
  align-items: center;
  column-gap: 8px;
  padding: 0 12px;
}
.board-head {
  flex: none;
  height: 30px;
  background: var(--c-100);
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-2);
}
/* The prize column is as wide as each row's amount, so it lines up on the right. */
.board-head span:nth-child(4) {
  text-align: right;
}
/* The rows fade out at the bottom edge, where they scroll under it. */
.rows {
  min-height: 0;
  margin: 0;
  padding: 0 0 12px;
  overflow-y: auto;
  list-style: none;
  mask: linear-gradient(180deg, #000 calc(100% - 12px), transparent);
}
.rows li {
  min-height: 32px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.rows li:first-child {
  min-height: 46px;
  background: var(--surface);
  color: var(--ink);
}
/* The drawn number in plain digits; the newest one larger, in the ramp's deep coral. */
.num {
  font: 800 17px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.06em;
  white-space: nowrap;
  color: var(--ink);
}
.num i {
  display: inline-block;
  font-style: normal;
}
.rows li:first-child .num {
  font-size: 22px;
  color: var(--c-700);
}
.day {
  white-space: nowrap;
}
.winners {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink);
}
.winners.none {
  color: var(--ink-3);
}
/* What each top ticket was paid; a dash when nobody won and the pool rolled over. */
.prize {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  font: 800 15px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  color: var(--ink);
}
.prize svg {
  color: var(--c-700);
}
.prize.none {
  color: var(--ink-3);
}
.rows li:first-child .prize {
  font-size: 17px;
}
/* Held back while the draw plays on the keys. */
.rows li.unseen .num,
.rows li.unseen .winners,
.rows li.unseen .prize {
  visibility: hidden;
}

/* Once the draw rests on the keys, its digits drop onto the board right to left. */
.reveal .num.in i {
  animation: ball-in 420ms var(--ease-pop) both;
  animation-delay: calc((2 - var(--i)) * 90ms);
}
@keyframes ball-in {
  from { transform: translateY(-24px); opacity: 0; }
  40% { opacity: 1; }
}

@container panel (max-width: 760px) {
  .board-head,
  .rows li:not(:first-child) {
    display: none;
  }
  .rows {
    overflow: visible;
    padding: 0;
  }
  /* The latest draw on one line: its day, the number and the top prize; who won is in 往期. */
  .rows {
    mask: none;
  }
  .rows li:first-child {
    grid-template-columns: minmax(0, 1fr) auto auto;
    min-height: 0;
    padding: 8px 8px 8px 10px;
  }
  .rows li:first-child .winners {
    display: none;
  }
  .rows li:first-child .num {
    font-size: 20px;
  }
}

@container panel (max-height: 560px) {
  .rows li {
    min-height: 30px;
  }
  .rows li:first-child {
    min-height: 40px;
  }
  .rows li:first-child .num {
    font-size: 20px;
  }
}

@container panel (max-width: 760px) and (max-height: 560px) {
  .rows li:first-child {
    row-gap: 4px;
    padding: 6px 10px 7px;
  }
}
</style>
