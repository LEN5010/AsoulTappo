<script setup lang="ts">
// The race rules (behind the band's info key), drawn more than written: how the field moves on the left, how bets
// pay on the right. Every row is a picture of the thing (a die, the gate, a stack, the track's own special tiles)
// with a few words beside it.
import { manifest } from "../../manifest";
import ParkSheet from "./ParkSheet.vue";
import RaceDie from "./RaceDie.vue";
import TuanziToken from "./TuanziToken.vue";
import { KIND_NAMES, type RaceKind } from "./race";

defineEmits<{ close: [] }>();

const CFG = manifest.economy.park!.race!;
const MEMBERS = manifest.characters.map((c) => c.id);
const BOOST = CFG.squares.boost;
const TRIP = Math.abs(CFG.squares.trip);
const LOW = Math.min(...CFG.dice);
const HIGH = Math.max(...CFG.dice);
/** The places each kind of bet covers, first to last, for its mini podium. */
const PLACES: Record<RaceKind, number[]> = { win: [0], top2: [0, 1], last: [MEMBERS.length - 1] };
</script>

<template>
  <ParkSheet title="赛跑规则" @close="$emit('close')">
    <div class="race-rules park-sheet-columns">
      <ul class="park-sheet-list single" aria-label="跑法">
        <li class="park-sheet-row">
          <span class="park-sheet-lead dice"><RaceDie v-for="f in CFG.dice" :key="f" :face="f" /></span>
          <span class="park-sheet-main"><b>每轮各掷一次</b><small>走 {{ LOW }}–{{ HIGH }} 格</small></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead gate" aria-hidden="true">
            <i v-for="m in MEMBERS" :key="m"><TuanziToken :member="m" :size="24" /></i>
          </span>
          <span class="park-sheet-main"><b>起点各占一道</b></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead bare tower" aria-hidden="true">
            <TuanziToken v-for="(m, k) in MEMBERS.slice(0, 3)" :key="m" :member="m" :size="24" :style="{ '--k': k }" />
            <svg viewBox="0 0 12 12"><path d="M2 6h8M6.5 2.5 10 6l-3.5 3.5" /></svg>
          </span>
          <span class="park-sheet-main"><b>落到有团子的格子就叠上去</b><small>走时带上头上的</small></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead tile boost" aria-hidden="true">
            <svg viewBox="0 0 12 12"><path d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" /></svg>{{ BOOST }}
          </span>
          <span class="park-sheet-main"><b>再走 {{ BOOST }} 格</b></span>
          <span class="park-sheet-lead tile trip" aria-hidden="true">
            <svg viewBox="0 0 12 12"><path d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" /></svg>{{ TRIP }}
          </span>
          <span class="park-sheet-main"><b>退 {{ TRIP }} 格</b></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead bare tower" aria-hidden="true">
            <TuanziToken v-for="(m, k) in MEMBERS.slice(2, 4)" :key="m" :member="m" :size="24" :style="{ '--k': k }" />
            <b class="first" :style="{ '--k': 2 }">1</b>
          </span>
          <span class="park-sheet-main"><b>同一格，上面的在前</b></span>
        </li>
      </ul>
      <ul class="park-sheet-list single" aria-label="押法">
        <li v-for="k in CFG.kinds" :key="k" class="park-sheet-row">
          <span class="park-sheet-lead podium" aria-hidden="true">
            <i v-for="(_, p) in MEMBERS" :key="p" :class="{ on: PLACES[k].includes(p) }" :style="{ '--p': p }"></i>
          </span>
          <span class="park-sheet-main"><b>{{ KIND_NAMES[k] }}</b></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead odds" aria-hidden="true">
            <b>×4.2</b>
            <svg viewBox="0 0 12 12"><path d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" /></svg>
            <svg class="down" viewBox="0 0 12 12"><path d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" /></svg>
          </span>
          <span class="park-sheet-main"><b>押的人越多，赔率越低</b><small>押下时的赔率锁定</small></span>
        </li>
      </ul>
    </div>
  </ParkSheet>
</template>

<style scoped>
/* Every drawing keeps its width when the rows shrink on short panels. */
.race-rules .park-sheet-lead:not(.bare):not(.tile) {
  width: 72px;
}
.race-rules svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.dice {
  gap: 4px;
  display: flex;
  justify-content: center;
  align-items: center;
}
.dice .race-die {
  --s: 20px;
}
/* The start line: five lanes side by side, one tuanzi each, behind a coral checker. */
.gate {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 2px;
  padding-bottom: 14px;
  box-sizing: border-box;
  --tuanzi-size: 12px;
}
.gate i {
  display: flex;
  justify-content: center;
  padding: 3px 0 2px;
  width: 12px;
  border-radius: 3px;
  background: var(--c-100);
}
.gate::after {
  content: "";
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 7px;
  height: 5px;
  background: repeating-conic-gradient(var(--c-500) 0 25%, #fff 0 50%) 0 0 / 5px 5px;
}
/* A stack: three tuanzi, an arrow for where they go together; or two, the one on top ahead. */
.tower {
  position: relative;
  color: var(--c-600);
}
.tower > .tuanzi-token,
.tower .first {
  position: absolute;
  left: 8px;
  bottom: calc(4px + var(--k) * 9px);
}
.tower svg {
  position: absolute;
  right: 0;
  bottom: 10px;
}
.tower .first {
  left: 14px;
  bottom: calc(10px + var(--k) * 9px);
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--c-700);
}
/* The track's own special tiles. */
.tile {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1px;
  font: 800 var(--fs-number)/1 var(--font-latin);
  height: 30px;
  align-self: center;
  width: 46px;
}
.tile.boost {
  background: linear-gradient(180deg, var(--c-200), var(--c-300));
  box-shadow: 0 6px 0 var(--c-500);
  translate: 0 -3px;
  color: var(--ink);
}
.tile.trip {
  margin-left: 4px;
  background: color-mix(in oklab, var(--c-300) 70%, var(--c-500));
  box-shadow: inset 0 4px 5px rgba(var(--c-900-rgb), 0.38);
  color: var(--c-900);
}
/* A kind of bet: the five places as steps, the ones it pays on in coral. */
.podium {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 3px;
  padding-bottom: 8px;
  box-sizing: border-box;
}
.podium i {
  width: 9px;
  height: calc(30px - var(--p) * 5px);
  border-radius: 3px 3px 0 0;
  background: var(--c-100);
}
.podium i.on {
  background: var(--c-500);
}
.odds {
  gap: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-700);
}
.odds b {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}
.odds .down {
  color: var(--ink-3);
}
</style>
