<script setup lang="ts">
// The race rules (behind the band's info key), drawn more than written: how the field moves on the left, how bets
// pay on the right. Every row is a picture of the thing (a die, the start square, a stack, the board's own special
// squares drawn as on the board) with a few words beside it.
import { manifest } from "../../manifest";
import { economy } from "../../stores/economy";
import ParkCoin from "./ParkCoin.vue";
import ParkSheet from "./ParkSheet.vue";
import RaceDie from "./RaceDie.vue";
import TuanziToken from "./TuanziToken.vue";
import { KIND_NAMES, SKILL_NAMES, skillText, type RaceKind } from "./race";

defineEmits<{ close: [] }>();

// Shown inside the park, which opens only once the server's economy is known.
const CFG = economy.value!.park!.race!;
const MEMBERS = manifest.characters.map((c) => c.id);
const BOOST = CFG.squares.boost;
const TRIP = Math.abs(CFG.squares.trip);
/** A race is run on a map, whose boost and trip squares each carry their own number; and deals skills. */
const MAPS = !!CFG.maps?.length;
const SKILLS = CFG.skills ?? [];
/** Every die a race deals, best first; the config's own on a server without forms or skills. */
const DICE = SKILLS.length ? SKILLS.map((k) => k.dice) : CFG.forms?.length ? CFG.forms.map((f) => f.dice) : [CFG.dice];

const LOW = Math.min(...DICE.flat());
const HIGH = Math.max(...DICE.flat());
/** The dice beside the first rule: the plain die, or with skills (a die each) the lowest and highest face of all. */
const LEAD_DICE = SKILLS.length ? [LOW, HIGH] : CFG.dice;
/** The places each kind of bet covers, first to last, for its mini podium. */
const PLACES: Record<RaceKind, number[]> = { win: [0], top2: [0, 1], last: [MEMBERS.length - 1] };
/** Which places each kind pays on, in words. */
const PLACE_WORDS: Record<RaceKind, string> = { win: "第 1 名", top2: "前 2 名", last: "最后 1 名" };
</script>

<template>
  <ParkSheet title="赛跑规则" @close="$emit('close')">
    <div class="race-rules park-sheet-columns" :class="{ skilled: SKILLS.length }">
      <ul class="park-sheet-list single" aria-label="跑法">
        <li class="park-sheet-row">
          <span class="park-sheet-lead dice"><RaceDie v-for="(f, k) in LEAD_DICE" :key="k" :face="f" /></span>
          <span class="park-sheet-main"><b>每轮按顺序各掷一次骰子</b><small>前进 {{ LOW }}–{{ HIGH }} 格</small></span>
        </li>
        <li v-if="!SKILLS.length && CFG.forms?.length" class="park-sheet-row">
          <span class="park-sheet-lead forms" aria-hidden="true">
            <span v-for="(d, j) in [DICE[0], DICE[DICE.length - 1]]" :key="j" class="form-dice">
              <RaceDie v-for="(f, k) in d" :key="k" :face="f" />
            </span>
          </span>
          <span class="park-sheet-main"><b>每场状态不同，骰子不同</b><small>状态好的赔率低</small></span>
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
            <i class="sq"><span class="cap"><svg viewBox="0 0 12 12"><path d="M2.5 7.4 6 3.8l3.5 3.6M2.5 10.4 6 6.8l3.5 3.6" /></svg>+{{ BOOST }}</span></i>
          </span>
          <span class="park-sheet-main"><b>加速</b><small>{{ MAPS ? "再前进几格" : `再前进 ${BOOST} 格` }}</small></span>
          <span class="park-sheet-lead bare" aria-hidden="true">
            <i class="sq"><span class="pit"><svg viewBox="0 0 12 12"><path d="M2.5 1.8 6 5.4l3.5-3.6M2.5 4.8 6 8.4l3.5-3.6" /></svg>−{{ TRIP }}</span></i>
          </span>
          <span class="park-sheet-main"><b>绊倒</b><small>{{ MAPS ? "再后退几格" : `后退 ${TRIP} 格` }}</small></span>
        </li>
        <li class="park-sheet-row">
          <span class="park-sheet-lead bare" aria-hidden="true"><i class="sq"><span class="gate"><i></i></span></i></span>
          <span class="park-sheet-main"><b>传送门</b><small>移到另一端</small></span>
          <span class="park-sheet-lead bare" aria-hidden="true">
            <i class="sq"><span class="turn"><svg viewBox="0 0 16 16"><path d="M5 13.5V2.5M2 5.5l3-3 3 3M11 2.5v11M8 10.5l3 3 3-3" /></svg></span></i>
          </span>
          <span class="park-sheet-main"><b>翻转</b><small>整叠颠倒</small></span>
        </li>
        <li v-if="MAPS" class="park-sheet-row">
          <span class="park-sheet-lead bare" aria-hidden="true">
            <i class="sq"><span class="redo"><svg viewBox="0 0 16 16"><rect x="2.5" y="2.5" width="11" height="11" rx="2.6" /><circle cx="5.6" cy="5.6" r="1" /><circle cx="10.4" cy="5.6" r="1" /><circle cx="8" cy="8" r="1" /><circle cx="5.6" cy="10.4" r="1" /><circle cx="10.4" cy="10.4" r="1" /></svg></span></i>
          </span>
          <span class="park-sheet-main"><b>再掷</b><small>多掷一次</small></span>
          <span class="park-sheet-lead bare" aria-hidden="true">
            <i class="sq"><span class="grab"><svg viewBox="0 0 16 16"><path d="M8 2v7.2a3 3 0 1 1-6 0V8M8 2 5.6 4.4M8 2l2.4 2.4M11 9.5l3 3M14 9.5l-3 3" /></svg></span></i>
          </span>
          <span class="park-sheet-main"><b>钩索</b><small>追上前方团子</small></span>
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
            <i v-for="(_, p) in MEMBERS" :key="p" :class="{ on: PLACES[k].includes(p), gold: k === 'win' && p === 0 }" :style="{ '--p': p }"></i>
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
      <!-- The skills a race deals, one to a runner: under both columns, four to a row. -->
      <ul v-if="SKILLS.length" class="skills" aria-label="技能">
        <li v-for="k in SKILLS" :key="k.id">
          <b class="skill">{{ SKILL_NAMES[k.id] ?? k.id }}</b>
          <small>{{ skillText(k) }}</small>
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
/* The best and the worst form's dice, one over the other. */
.forms {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
}
.form-dice {
  display: flex;
  gap: 2px;
}
.form-dice .race-die {
  --s: 14px;
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
/* The start and finish: coral check, with a coral and white checkered line where the lap ends. */
.sq.start {
  padding-bottom: 3px;
  background: repeating-conic-gradient(var(--c-200) 0 25%, var(--c-50) 0 50%) 0 0 / 8px 8px;
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
  gap: 0;
  border-radius: 5px;
  font: 800 11px/1 var(--font-latin);
}
.cap {
  background: linear-gradient(180deg, var(--c-200), var(--c-300));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7), inset 0 0 0 1.5px var(--c-500);
  color: var(--ink);
}
.pit {
  background: var(--c-700);
  box-shadow: inset 0 2.5px 3px rgba(var(--c-900-rgb), 0.48), inset 0 -1px 0 rgba(255, 255, 255, 0.28);
  color: #fff;
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
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5), inset 0 0 0 1px var(--c-600);
}
.gate i {
  width: 58%;
  height: 58%;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 40%, #fff, var(--c-300) 58%, var(--c-600));
  box-shadow: inset 0 1px 2px rgba(var(--c-900-rgb), 0.42), 0 0 0 1.5px #fff;
}
.turn {
  position: absolute;
  inset: 14%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--c-100);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.75), inset 0 0 0 1.5px var(--c-500);
  color: var(--c-700);
}
.race-rules .turn svg {
  width: 62%;
  height: 62%;
  stroke-width: 1.9;
}
.redo {
  position: absolute;
  inset: 16%;
  display: grid;
  place-items: center;
  border-radius: 24%;
  background: var(--surface);
  box-shadow: inset 0 1px 0 #fff, inset 0 0 0 1.5px var(--c-500);
  color: var(--c-700);
  rotate: -6deg;
}
.race-rules .redo svg {
  width: 100%;
  height: 100%;
  stroke: none;
}
.redo rect {
  fill: none;
}
.redo circle {
  fill: currentColor;
}
.grab {
  position: absolute;
  inset: 14%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(180deg, var(--c-300), var(--c-400));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55), inset 0 0 0 1.5px var(--c-600);
  color: var(--ink);
}
.race-rules .grab svg {
  width: 62%;
  height: 62%;
  stroke-width: 1.8;
}
.skills {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.skills li {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  padding: 8px 6px;
  border-radius: var(--radius-m);
  background: var(--c-100);
  text-align: center;
}
.skills small {
  font: 600 var(--fs-caption)/1.3 var(--font);
  color: var(--ink-2);
}
/* With the skills under them the rows stand a little lower, and lower still on a short panel, so the sheet fits. */
.race-rules.skilled .park-sheet-row {
  --lead: 44px;
}
@container panel (max-height: 620px) {
  .race-rules.skilled .park-sheet-row {
    --lead: 34px;
    min-height: 40px;
  }
  .skills li {
    flex-direction: row;
    justify-content: center;
    padding: 5px 6px;
  }
}
/* A skill's name: the coral tab a runner wears on its key. */
.skill {
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--c-500);
  font: 800 var(--fs-caption)/1.1 var(--font);
  color: var(--ink);
  white-space: nowrap;
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
.podium i.gold {
  background: var(--grad-gold);
  box-shadow: inset 0 0 0 1px var(--gold);
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
