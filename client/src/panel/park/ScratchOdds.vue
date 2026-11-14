<script setup lang="ts">
// The scratch odds (behind the band's info key): a paytable a card, opening on the card in front. One row a prize on
// one sheet, best prize first: a small icon, the prize, then its chance as a percent with a bar as long as the chance.
// The top prize has the only gold; a miss is grey.
import { computed, ref } from "vue";
import { assetUrl } from "../../asset";
import { emoteCover } from "../../manifest";
import { HOST, SCRATCH_EMOTES, faceKey } from "../../scratch";
import { arrowSelect } from "../../ui/focus";
import Icon from "../../ui/Icon.vue";
import { COIN_SMALL } from "./coin";
import ParkSheet from "./ParkSheet.vue";
import { KINDS, oddsRows, oddsText, topPrize, type CardKind, type OddsRow } from "./scratchCards";

const props = defineProps<{ kind: CardKind; complete: boolean }>();
defineEmits<{ close: [] }>();

const NAMES: Record<CardKind, string> = { basic: "普通", premium: "豪华" };
const WORDS: Partial<Record<OddsRow["kind"], string>> = { skin: "皮肤", big: "大隐藏卡", emote: "阿草表情", again: "再来一张", miss: "没中" };
const shown = ref<CardKind>(props.kind);
const tabs = ref<HTMLElement>();
/** The emote row shows one of the set: the face 阿草 makes when a card pays one. */
const SAMPLE = faceKey(HOST.emote) ?? SCRATCH_EMOTES[0]?.key ?? "";
const sampleSrc = SAMPLE ? assetUrl(emoteCover(SAMPLE)) : "";
const fmt = (n: number) => n.toLocaleString("en-US");

const lists = computed(() => KINDS.map((k) => ({ kind: k, rows: oddsRows(k, props.complete), top: topPrize(k) })));
/** The bar's length in percent of its track: the chance itself, so both tabs share one scale. */
const barOf = (row: OddsRow) => `${Math.min(100, row.rate)}%`;
</script>

<template>
  <ParkSheet title="刮刮乐概率" @close="$emit('close')">
    <div ref="tabs" class="seg" role="tablist" @keydown="arrowSelect($event, tabs)">
      <button
        v-for="k in KINDS" :key="k" type="button" role="tab" class="seg-key" :class="{ on: shown === k }"
        :aria-selected="shown === k" :tabindex="shown === k ? 0 : -1" @click="shown = k"
      >{{ NAMES[k] }}</button>
    </div>
    <div class="stack">
      <ol v-for="l in lists" :key="l.kind" class="pay" :hidden="l.kind !== shown" :aria-label="NAMES[l.kind]">
        <li
          v-for="(row, i) in l.rows" :key="i" class="pay-row"
          :class="{ top: row.kind === 'shards' && row.shards === l.top, miss: row.kind === 'miss' }"
        >
          <span class="pay-icon" aria-hidden="true">
            <Icon v-if="row.kind === 'shards'" name="shard" :size="24" />
            <Icon v-else-if="row.kind === 'skin'" name="shirt" :size="24" />
            <Icon v-else-if="row.kind === 'big'" name="card-spark" :size="24" />
            <img v-else-if="row.kind === 'again'" class="coin" :src="COIN_SMALL" alt="" draggable="false" />
            <img v-else-if="row.kind === 'emote' && sampleSrc" class="emote" :src="sampleSrc" alt="" draggable="false" />
            <i v-else-if="row.kind === 'miss'" class="dash"></i>
          </span>
          <span class="pay-prize">
            <b v-if="row.kind === 'shards'" class="amount">{{ fmt(row.shards ?? 0) }}</b>
            <b v-else class="word">{{ WORDS[row.kind] }}</b>
            <small v-if="row.pity" class="pity">{{ row.pity }} 张保底</small>
          </span>
          <span class="pay-bar" aria-hidden="true"><i :style="{ width: barOf(row) }"></i></span>
          <span class="pay-rate">{{ oddsText(row.rate) }}</span>
        </li>
      </ol>
    </div>
  </ParkSheet>
</template>

<style scoped>
/* A segmented switch: the card shown is a filled coral key, the other a quiet white one. */
.seg {
  display: inline-flex;
  align-self: flex-start;
  gap: 3px;
  padding: 3px;
  border-radius: calc(var(--radius-key) + 3px);
  background: var(--c-100);
}
.seg-key {
  min-width: 84px;
  height: 32px;
  padding: 0 18px;
  border: 0;
  border-radius: var(--radius-key);
  background: var(--surface);
  box-shadow: 0 1px 0 var(--c-200);
  font: 800 var(--fs-number)/1 var(--font);
  color: var(--ink-2);
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.seg-key:hover:not(.on) {
  color: var(--ink);
  background: color-mix(in oklab, var(--c-50) 50%, var(--surface));
}
.seg-key.on {
  background: linear-gradient(180deg, var(--c-500), var(--c-600));
  box-shadow: 0 1px 0 var(--c-700), 0 2px 6px -2px rgba(var(--c-900-rgb), 0.35);
  color: #fff;
  text-shadow: 0 1px 1px rgba(var(--c-900-rgb), 0.3);
  cursor: default;
}
.seg-key:focus-visible {
  outline: 2px solid var(--ink);
  outline-offset: 2px;
}

/* The two tables share one grid cell, so the sheet keeps its height when the tab changes; each keeps its own. */
.stack {
  display: grid;
  align-items: start;
}
.stack > * {
  grid-area: 1 / 1;
}
.stack > [hidden] {
  display: block;
  visibility: hidden;
}

/* One sheet of paper, rows split by hairlines. */
.pay {
  --row-h: 46px;
  --track: 128px;
  margin: 0;
  padding: 0 4px;
  list-style: none;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: 0 0 0 1px var(--c-100), var(--shadow-paper);
}
.pay-row {
  position: relative;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) var(--track) 58px;
  align-items: center;
  gap: 14px;
  min-height: var(--row-h);
  padding: 0 14px;
}
.pay-row + .pay-row {
  border-top: 1px solid var(--c-100);
}
/* The top prize: a gold mark on the left edge and a gold icon. */
.pay-row.top::before {
  content: "";
  position: absolute;
  left: -4px;
  top: 8px;
  bottom: 8px;
  width: 4px;
  border-radius: 0 3px 3px 0;
  background: var(--gold);
}

.pay-icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  color: var(--c-600);
}
.top .pay-icon {
  color: var(--gold);
}
.pay-icon .coin {
  width: 24px;
  height: 24px;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.25));
}
.pay-icon .emote {
  width: 28px;
  height: 28px;
  object-fit: contain;
}
.dash {
  width: 14px;
  height: 3px;
  border-radius: 2px;
  background: var(--ink-3);
  opacity: 0.5;
}

.pay-prize {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  white-space: nowrap;
}
.amount {
  font: 800 22px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.top .amount {
  font-size: 26px;
}
.word {
  font: 800 var(--fs-number)/1.2 var(--font);
  color: var(--ink);
}
.pity {
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--c-700);
}

/* The chance: a thin bar as long as the chance (a dot at the least), then the figure, smaller than the prize. */
.pay-bar {
  height: 4px;
  border-radius: 2px;
  background: var(--c-100);
}
.pay-bar i {
  display: block;
  min-width: 4px;
  height: 100%;
  border-radius: inherit;
  background: var(--c-400);
}
.pay-rate {
  text-align: right;
  font: 700 var(--fs-number)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
}

.miss .word,
.miss .pay-rate {
  color: var(--ink-3);
}
.miss .pay-bar i {
  background: color-mix(in oklab, var(--ink-3) 35%, var(--surface));
}

/* Short panels: rows tighten so all nine fit without scrolling. */
@container panel (max-height: 560px) {
  .pay {
    --row-h: 34px;
  }
  .seg-key {
    height: 28px;
  }
  .amount {
    font-size: 19px;
  }
  .top .amount {
    font-size: 22px;
  }
  .pay-row.top::before {
    top: 5px;
    bottom: 5px;
  }
}
@container panel (max-width: 560px) {
  .pay {
    --track: 72px;
  }
  .pay-row {
    gap: 10px;
    padding: 0 10px;
  }
}
</style>
