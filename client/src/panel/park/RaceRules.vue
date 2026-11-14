<script setup lang="ts">
// The race rules (behind the band's info key), drawn more than written: how the field moves on the left, how bets
// pay on the right. Every row is a picture of the thing (a die, the start square, a stack, the board's own special
// squares drawn as on the board) with a few words beside it.
import { manifest } from "../../manifest";
import ParkCoin from "./ParkCoin.vue";
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
/** Which places each kind pays on, in words. */
const PLACE_WORDS: Record<RaceKind, string> = { win: "第 1 名", top2: "前 2 名", last: "最后 1 名" };
</script>

<template>
  <ParkSheet title="赛跑规则" @close="$emit('close')">
    <div class="race-rules park-sheet-columns">
      <ul class="park-sheet-list single" aria-label="跑法">
        <li class="park-sheet-row">
          <span class="park-sheet-lead dice"><RaceDie v-for="f in CFG.dice" :key="f" :face="f" /></span>
          <span class="park-sheet-main"><b>每轮按顺序各掷一次骰子</b><small>前进 {{ LOW }}–{{ HIGH }} 格</small></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead dice order" aria-hidden="true"><RaceDie :face="6" class="hi" /><RaceDie :face="3" /></span>
          <span class="park-sheet-main"><b>开局掷骰决定行动顺序</b><small>点数大者先行，同点重掷</small></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead bare goal" aria-hidden="true">
            <i class="sq start"><TuanziToken :member="MEMBERS[0]" :size="24" /></i>
            <svg viewBox="0 0 16 12"><path d="M14 3H4.5a3 3 0 0 0 0 6H9M6.5 6.5 9 9l-2.5 2.5" /></svg>
          </span>
          <span class="park-sheet-main"><b>恰好走完一圈到达终点</b><small>超出的步数从终点折返</small></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead bare tower" aria-hidden="true">
            <TuanziToken v-for="(m, k) in MEMBERS.slice(0, 3)" :key="m" :member="m" :size="24" :style="{ '--k': k }" />
            <svg viewBox="0 0 12 12"><path d="M2 6h8M6.5 2.5 10 6l-3.5 3.5" /></svg>
          </span>
          <span class="park-sheet-main"><b>叠在格中已有团子的上方</b><small>移动时带上方的团子同行</small></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead bare" aria-hidden="true">
            <i class="sq"><span class="cap"><svg viewBox="0 0 12 12"><path d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" /></svg>+{{ BOOST }}</span></i>
          </span>
          <span class="park-sheet-main"><b>加速</b><small>再前进 {{ BOOST }} 格</small></span>
          <span class="park-sheet-lead bare" aria-hidden="true">
            <i class="sq"><span class="pit"><svg viewBox="0 0 12 12"><path d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" /></svg>−{{ TRIP }}</span></i>
          </span>
          <span class="park-sheet-main"><b>绊倒</b><small>后退 {{ TRIP }} 格</small></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead bare" aria-hidden="true"><i class="sq"><span class="gate"><i></i></span></i></span>
          <span class="park-sheet-main"><b>传送门</b><small>移到另一端</small></span>
          <span class="park-sheet-lead bare" aria-hidden="true">
            <i class="sq"><span class="turn"><svg viewBox="0 0 16 16"><path d="M5 13.5V2.5M2 5.5l3-3 3 3M11 2.5v11M8 10.5l3 3 3-3" /></svg></span></i>
          </span>
          <span class="park-sheet-main"><b>翻转</b><small>整叠颠倒</small></span>
        </li>
      </ul>
      <ul class="park-sheet-list single" aria-label="名次与押法">
        <li class="park-sheet-row">
          <span class="park-sheet-lead bare tower" aria-hidden="true">
            <TuanziToken v-for="(m, k) in MEMBERS.slice(2, 4)" :key="m" :member="m" :size="24" :style="{ '--k': k }" />
            <b class="first" :style="{ '--k': 2 }">1</b>
          </span>
          <span class="park-sheet-main"><b>同一格中位置靠上者名次在前</b></span>
        </li>
        <li v-for="k in CFG.kinds" :key="k" class="park-sheet-row">
          <span class="park-sheet-lead podium" aria-hidden="true">
            <i v-for="(_, p) in MEMBERS" :key="p" :class="{ on: PLACES[k].includes(p) }" :style="{ '--p': p }"></i>
          </span>
          <span class="park-sheet-main"><b>{{ KIND_NAMES[k] }}</b><small>{{ PLACE_WORDS[k] }}</small></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead odds" aria-hidden="true">
            <b>×4.2</b>
            <svg viewBox="0 0 12 12"><path d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" /></svg>
            <svg class="down" viewBox="0 0 12 12"><path d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" /></svg>
          </span>
          <span class="park-sheet-main"><b>赔率随押注变动</b><small>按下注时的赔率结算</small></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead odds" aria-hidden="true"><ParkCoin :size="24" :tilt="false" /><b>×4.2</b></span>
          <span class="park-sheet-main"><b>猜中得 押注 × 赔率 枚驼币</b><small>每场合计后四舍五入</small></span>
        </li>
      </ul>
    </div>
  </ParkSheet>
</template>

<style scoped>
/* Every drawing keeps its width when the rows shrink on short panels. */
.race-rules .park-sheet-lead:not(.bare) {
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
/* The order's dice: the higher face stands a step up. */
.order .hi {
  translate: 0 -5px;
}

/*
 * A square of the board (RaceTrack's .tile and its markers), drawn at --u: paper on the slab's coral hairline.
 */
.sq {
  --u: 34px;
  position: relative;
  display: grid;
  place-items: end center;
  width: var(--u);
  height: var(--u);
  flex: none;
  box-sizing: border-box;
  border-radius: 6px;
  background: var(--surface);
  box-shadow: 0 0 0 2px var(--c-300);
  overflow: hidden;
}
/* The start and finish: coral, a coral and white checkered line where the lap ends. */
.sq.start {
  padding-bottom: 3px;
  background: var(--c-200);
}
.sq.start::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 6px;
  background: repeating-conic-gradient(var(--c-500) 0 25%, #fff 0 50%) 0 0 / 6px 6px;
}
.sq.start .tuanzi-token {
  position: relative;
  z-index: 1;
}
.goal {
  display: flex;
  align-items: center;
  gap: 2px;
  color: var(--c-600);
}
.goal svg {
  width: 18px;
  height: 14px;
}
.cap,
.pit {
  position: absolute;
  inset: 12%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  border-radius: 5px;
  font: 800 11px/1 var(--font-latin);
  color: var(--ink);
}
.cap {
  bottom: calc(12% + 2px);
  background: linear-gradient(180deg, var(--c-400), var(--c-500));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45), 0 2px 0 var(--c-600);
}
.pit {
  background: color-mix(in oklab, var(--c-600) 80%, var(--c-700));
  box-shadow: inset 0 3px 3px rgba(var(--c-900-rgb), 0.55), inset 0 -1px 0 rgba(255, 255, 255, 0.35);
}
.race-rules .cap svg,
.race-rules .pit svg {
  width: 9px;
  height: 9px;
}
.gate {
  position: absolute;
  inset: 16%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--c-500);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45), 0 1px 0 var(--c-600);
}
.gate i {
  width: 58%;
  height: 58%;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 40%, var(--c-200), var(--c-400) 60%, var(--c-600));
  box-shadow: inset 0 1px 2px rgba(var(--c-900-rgb), 0.45), 0 0 0 1.5px #fff;
}
.turn {
  position: absolute;
  inset: 14%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--c-100);
  box-shadow: 0 0 0 2px var(--c-500), 0 2px 0 1px var(--c-600);
  color: var(--c-700);
}
.race-rules .turn svg {
  width: 62%;
  height: 62%;
  stroke-width: 1.8;
}
/* Two squares share a row: their words keep to one line. */
.race-rules .park-sheet-main small {
  white-space: nowrap;
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
