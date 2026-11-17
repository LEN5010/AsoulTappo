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
  calm?: boolean;
}>();

const fmt = (n: number) => n.toLocaleString("en-US");
/** A draw on the board stays blank while its first showing is still playing on the keys. */
const unseen = (day: string) => !!props.reveal && props.reveal === day && props.stopped < 3;
</script>

<template>
  <!-- One draw a row, newest first: its day, its number, who won the top prize and what each won. -->
  <div v-if="past.length" class="board" :class="{ calm }">
    <div class="board-head" aria-hidden="true"><span>日期</span><span>开奖号码</span><span>头奖</span><span>奖金</span></div>
    <ol class="rows ui-scroll">
      <li v-for="h in past" :key="h.day" :class="{ unseen: unseen(h.day), hit: h.top.length > 0 }">
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
/* The board: a header strip, then one draw a row, the newest featured on white with a coral (or gold) edge mark. */
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
  grid-template-columns: 54px 56px minmax(0, 1fr) 76px;
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
.board-head span {
  white-space: nowrap;
}
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
  -webkit-mask: linear-gradient(180deg, #000 calc(100% - 12px), transparent);
  mask: linear-gradient(180deg, #000 calc(100% - 12px), transparent);
}
.rows li {
  min-height: 33px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
  transition: background var(--dur-fast);
}
.rows li:not(:first-child):hover {
  background: color-mix(in oklab, var(--c-100) 55%, var(--c-50));
}
.rows li.hit:not(:first-child) {
  color: var(--ink);
}
.rows li + li + li {
  border-top: 1px solid var(--c-100);
}
.rows li:first-child {
  position: relative;
  min-height: 46px;
  padding-left: 14px;
  background: var(--surface);
  box-shadow: 0 1px 0 var(--c-100);
  color: var(--ink);
}
.rows li:first-child::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3.5px;
  border-radius: 0 3px 3px 0;
  background: var(--c-500);
}
.rows li:first-child.hit::before {
  background: var(--gold);
}
/* The drawn number in crisp fixed-width tabular digits; the newest one framed in soft coral tint. */
.num {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  font: 800 17px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  color: var(--ink);
}
.num i {
  display: inline-block;
  width: 0.62em;
  font-style: normal;
  text-align: center;
}
.rows li:first-child .num {
  gap: 2px;
  font-size: 21px;
  color: var(--c-700);
}
.rows li:first-child .num i {
  width: 0.76em;
  padding: 2px 0;
  border-radius: 4px;
  background: var(--c-50);
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
  color: color-mix(in oklab, var(--gold) 72%, var(--c-700));
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
.reveal .board:not(.calm) .num.in i {
  animation: ball-in 420ms var(--ease-pop) both;
  animation-delay: calc((2 - var(--i)) * 90ms);
}
.board.calm .rows li {
  transition: none;
}
@keyframes ball-in {
  from { transform: translateY(-24px); opacity: 0; }
  40% { opacity: 1; }
}

/* Side column too narrow for four columns (e.g. 920×620 where panel is 900px): drop the winner names into 往期 so the
 * header and rows share a clean three-column grid without wrapping. */
@container panel (max-width: 910px) {
  .board-head,
  .rows li {
    grid-template-columns: 54px 56px minmax(0, 1fr);
  }
  .board-head span:nth-child(3),
  .rows li .winners {
    display: none;
  }
}

@container panel (max-width: 760px) {
  .board-head,
  .rows li:not(:first-child) {
    display: none;
  }
  /* The latest draw on one line: its day, the number and the top prize; who won is in 往期. */
  .rows {
    overflow: visible;
    padding: 0;
    -webkit-mask: none;
    mask: none;
  }
  .rows li:first-child {
    grid-template-columns: minmax(0, 1fr) auto auto;
    min-height: 0;
    padding: 8px 10px 8px 13px;
    box-shadow: none;
  }
  .rows li:first-child::before {
    top: 6px;
    bottom: 6px;
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
