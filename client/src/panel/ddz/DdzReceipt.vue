<script setup lang="ts">
// How a game ended, as a receipt dropped onto the mat: who won and at what multiplier on top, where the multiplier
// came from as a row of tags, then the three seats with the shards they won or lost, the winners first. A spring is
// stamped in the corner. A seat that asked for another game gets a tick on its face.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { shownNick } from "../../stores/room";
import { settings } from "../../stores/settings";
import type { DdzState } from "../../stores/ddz";
import CharacterAvatar from "../../ui/CharacterAvatar.vue";
import Icon from "../../ui/Icon.vue";
import { countTo } from "../park/countTo";

const props = defineProps<{ table: DdzState }>();
const r = computed(() => props.table.result!);

/** Winners first, each side from the own seat on. */
const rows = computed(() => {
  const t = props.table;
  return [0, 1, 2].map((k) => (t.you + k) % 3)
    .sort((a, b) => Number(r.value.deltas[b]! > 0) - Number(r.value.deltas[a]! > 0))
    .map((seat) => {
      const s = t.seats[seat]!;
      return {
        seat, character: seat === t.you ? settings.character : s.character, again: s.again, delta: r.value.deltas[seat]!,
        nick: seat === t.you ? settings.nick.trim() || s.nick || "我" : shownNick(s), landlord: seat === r.value.landlord,
      };
    });
});
/** Where the multiplier came from; the last tag says it stopped at the table's cap. */
const why = computed(() => {
  const x = r.value;
  const tags = [{ label: "叫分", value: String(x.bid) }];
  if (x.bombs) tags.push({ label: "炸弹", value: `×${2 ** x.bombs}` });
  if (x.spring) tags.push({ label: x.spring === 1 ? "春天" : "反春", value: "×2" });
  if (x.bid * 2 ** x.bombs * (x.spring ? 2 : 1) > x.mult) tags.push({ label: "封顶", value: `×${x.mult}` });
  return tags;
});

// The shards count up from nothing, each row a beat after the one above.
const shown = ref([0, 0, 0]);
const stops: (() => void)[] = [];
const timers: ReturnType<typeof setTimeout>[] = [];
onMounted(() => {
  rows.value.forEach((row, i) => {
    const out = computed({ get: () => shown.value[i]!, set: (v) => (shown.value[i] = v) });
    timers.push(setTimeout(() => stops.push(countTo(out, row.delta, 700)), 260 + i * 120));
  });
});
onBeforeUnmount(() => {
  timers.forEach(clearTimeout);
  stops.forEach((stop) => stop());
});
const amount = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toLocaleString("en-US")}`;
</script>

<template>
  <div class="receipt" role="status">
    <div class="paper">
      <div class="head">
        <h3>{{ r.winner === "landlord" ? "地主胜" : "农民胜" }}</h3>
        <span class="x"><i>×</i>{{ r.mult }}</span>
      </div>
      <div class="why">
        <span v-for="tag in why" :key="tag.label" class="ui-tag">{{ tag.label }}<b>{{ tag.value }}</b></span>
      </div>
      <div class="rows">
        <div v-for="(row, i) in rows" :key="row.seat" class="row" :class="{ lose: row.delta < 0 }" :style="{ animationDelay: `${200 + i * 90}ms` }">
          <span class="face" :class="{ again: row.again }"><CharacterAvatar :character="row.character" :size="38" /></span>
          <span class="nick"><span>{{ row.nick }}</span><em v-if="row.landlord" class="ui-tag dark">地主</em></span>
          <span class="amount"><Icon name="shard" :size="18" />{{ amount(shown[i]!) }}</span>
        </div>
      </div>
      <span v-if="!table.closed" :key="table.until" class="wait" aria-hidden="true">
        <i :style="{ animationDuration: `${Math.max(0, table.until - Date.now())}ms` }"></i>
      </span>
    </div>
    <span v-if="r.spring" class="seal">{{ r.spring === 1 ? "春天" : "反春" }}</span>
  </div>
</template>

<style scoped>
/* The shadow is on the outer box, so the torn edge's mask does not cut it off. */
.receipt {
  position: absolute;
  left: 50%;
  top: max(120px, calc(50% - 190px));
  width: 372px;
  translate: -50% 0;
  rotate: -1.2deg;
  z-index: 6;
  filter: drop-shadow(0 14px 18px rgba(var(--c-900-rgb), 0.35));
  animation: drop 420ms var(--ease-spring) backwards;
}
@keyframes drop {
  from { opacity: 0; translate: -50% -46px; rotate: -7deg; scale: 0.92; }
}
.paper {
  position: relative;
  border-radius: 16px 16px 0 0;
  background: var(--surface);
  padding-bottom: 22px;
  mask: linear-gradient(#000, #000) top / 100% calc(100% - 8px) no-repeat,
    radial-gradient(circle at 8px 0, #000 7.5px, transparent 8px) bottom left / 16px 8px repeat-x;
}
/* White paper all the way up: who won in ink, the multiplier in deep coral, a perforation under them. */
.head {
  height: 78px;
  margin: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 2px dashed var(--c-200);
}
.head h3 { margin: 0; font: 800 26px/1 var(--font); letter-spacing: 1px; color: var(--ink); }
.head .x { font: 800 56px/1 var(--font-latin); letter-spacing: -1px; color: var(--c-700); }
.head .x i { font-style: normal; font-size: 30px; margin-right: 2px; opacity: 0.9; }
.why { display: flex; flex-wrap: wrap; gap: 6px; padding: 12px 20px 2px; }
.why .ui-tag { --tag-bg: var(--c-100); --tag-fg: var(--c-700); line-height: 22px; padding: 0 10px; font-size: 12px; }
.why .ui-tag b { font: 800 14px/1 var(--font-latin); margin-left: 4px; }
.rows { display: flex; flex-direction: column; gap: 6px; padding: 10px 16px 0; }
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 52px;
  padding: 0 16px 0 8px;
  border-radius: var(--radius-m);
  background: var(--c-100);
  animation: row 300ms var(--ease-out) backwards;
}
@keyframes row {
  from { opacity: 0; translate: -14px 0; }
}
.row.lose { background: color-mix(in oklab, var(--ink-3) 9%, var(--surface)); }
.face { position: relative; flex: none; display: flex; border-radius: 50%; background: #fff; box-shadow: 0 0 0 2px #fff; }
.face > :first-child { border-radius: 50%; }
.row.lose .face > :first-child { filter: grayscale(0.6); }
/* Asked for another game: a tick on the face. */
.face.again::after {
  content: "";
  position: absolute;
  right: -3px;
  bottom: -3px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--ok) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23fff' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M5 12.5l4.5 4.5L19 7.5'/%3E%3C/svg%3E") center / 10px no-repeat;
  box-shadow: 0 0 0 2px var(--c-100);
  animation: tick 240ms var(--ease-pop);
}
@keyframes tick {
  from { scale: 0; }
}
.nick { display: flex; align-items: center; gap: 7px; min-width: 0; font-size: 13px; font-weight: 800; white-space: nowrap; }
.nick > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.nick .ui-tag { flex: none; }
.amount { margin-left: auto; flex: none; display: flex; align-items: center; gap: 4px; font: 800 24px/1 var(--font-latin); color: var(--c-700); }
.row.lose .amount { color: var(--ink-2); }
/* The time left to ask for another game, along the foot of the paper. */
.wait { display: block; height: 4px; margin: 14px 16px 0; border-radius: 2px; background: var(--c-100); overflow: hidden; }
.wait i { display: block; height: 100%; border-radius: 2px; background: var(--c-300); transform-origin: 0 50%; animation: wait linear forwards; }
@keyframes wait {
  to { transform: scaleX(0); }
}
/* A spring: stamped in the corner, askew. */
.seal {
  position: absolute;
  right: 104px;
  top: 10px;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  rotate: -14deg;
  box-shadow: inset 0 0 0 2.5px var(--c-600);
  color: var(--c-600);
  opacity: 0.9;
  font: 800 17px/1 var(--font);
  letter-spacing: 1px;
  animation: stamp 320ms 620ms var(--ease-out) backwards;
}
.seal::before { content: ""; position: absolute; inset: 6px; border-radius: 50%; border: 1.5px solid var(--c-600); opacity: 0.6; }
@keyframes stamp {
  from { opacity: 0; scale: 2.4; }
  60% { opacity: 0.9; scale: 0.92; }
}
</style>
