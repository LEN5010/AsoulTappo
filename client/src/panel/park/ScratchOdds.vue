<script setup lang="ts">
// The scratch odds (behind the band's info key): a tabular paytable aligned with ResonancePage's probability table,
// opening on the card in front; with one card on sale there is no switch. Best prize first: a tier material swatch,
// prize icon and amount/label, right-aligned tabular percentage with a proportional bar, and flat pity pill.
import { computed, ref } from "vue";
import { assetUrl } from "../../asset";
import { emoteCover } from "../../manifest";
import { HOST, SCRATCH_EMOTES, faceKey } from "../../scratch";
import { arrowSelect } from "../../ui/focus";
import Icon from "../../ui/Icon.vue";
import { COIN_SMALL } from "./coin";
import ParkSheet from "./ParkSheet.vue";
import {
  cellOf, levelOf, oddsRows, oddsText, onSale, parkScratch, topPrize,
  type CardKind, type OddsRow,
} from "./scratchCards";

const props = defineProps<{ kind: CardKind; complete: boolean }>();
defineEmits<{ close: [] }>();

const SCRATCH = parkScratch();
const NAMES: Record<CardKind, string> = { basic: "普通", premium: "豪华" };
const WORDS: Partial<Record<OddsRow["kind"], string>> = {
  skin: "皮肤", big: "大隐藏卡", emote: "阿草表情", again: "再来一张", miss: "没中",
};
/** A hidden card on the table opens on the first card on sale. */
const ON_SALE = onSale();
const shown = ref<CardKind>(ON_SALE.includes(props.kind) ? props.kind : ON_SALE[0] ?? props.kind);
const tabs = ref<HTMLElement>();
/** The emote row shows one of the set: the face 阿草 makes when a card pays one. */
const SAMPLE = faceKey(HOST.emote) ?? SCRATCH_EMOTES[0]?.key ?? "";
const sampleSrc = SAMPLE ? assetUrl(emoteCover(SAMPLE)) : "";
const fmt = (n: number) => n.toLocaleString("en-US");

function tierOf(kind: CardKind, row: OddsRow, top: number): string {
  if (row.kind === "miss") return "miss";
  if (row.kind === "shards" && row.shards === top) return "legendary top";
  if (row.kind === "big") return "legendary";
  if (row.kind === "skin") return "skin";
  if (row.kind === "emote") return "rare";
  if (row.kind === "again") return "uncommon";
  const lv = levelOf({ ...cellOf(String(row.shards ?? 0)), at: [0, 1, 2] }, kind);
  if (lv === 3) return "legendary";
  if (lv === 2) return "epic";
  if (lv === 1) return "rare";
  return "uncommon";
}

const lists = computed(() =>
  ON_SALE.map((k) => {
    const top = topPrize(k);
    return {
      kind: k,
      coins: SCRATCH.cards[k].coins,
      top,
      rows: oddsRows(k, props.complete).map((row) => ({ ...row, tier: tierOf(k, row, top) })),
    };
  }),
);
/** The bar's length in percent of its track: the chance itself, so both tabs share one scale. */
const barOf = (row: OddsRow) => `${Math.min(100, row.rate)}%`;
</script>

<template>
  <ParkSheet title="刮刮乐概率" @close="$emit('close')">
    <div v-if="ON_SALE.length > 1" ref="tabs" class="park-sheet-tabs" role="tablist" @keydown="arrowSelect($event, tabs)">
      <button
        v-for="l in lists" :key="l.kind" type="button" role="tab" class="ui-btn tab-key" :class="{ on: shown === l.kind }"
        :aria-selected="shown === l.kind" :tabindex="shown === l.kind ? 0 : -1" @click="shown = l.kind"
      >
        <span>{{ NAMES[l.kind] }}</span>
        <small class="tab-cost"><img :src="COIN_SMALL" alt="" draggable="false" />×{{ l.coins }}</small>
      </button>
    </div>

    <div class="stack">
      <table v-for="l in lists" :key="l.kind" class="rates" :hidden="l.kind !== shown" :aria-label="NAMES[l.kind]">
        <thead>
          <tr>
            <th>档位</th>
            <th>概率</th>
            <th>保底</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in l.rows" :key="i" :class="row.tier">
            <td>
              <span class="tier-cell">
                <i class="swatch" aria-hidden="true"></i>
                <span class="pay-icon" aria-hidden="true">
                  <Icon v-if="row.kind === 'shards'" name="shard" :size="18" />
                  <Icon v-else-if="row.kind === 'skin'" name="shirt" :size="18" />
                  <Icon v-else-if="row.kind === 'big'" name="card-spark" :size="18" />
                  <img v-else-if="row.kind === 'again'" class="coin" :src="COIN_SMALL" alt="" draggable="false" />
                  <img v-else-if="row.kind === 'emote' && sampleSrc" class="emote" :src="sampleSrc" alt="" draggable="false" />
                  <i v-else class="dash"></i>
                </span>
                <b v-if="row.kind === 'shards'" class="amount">{{ fmt(row.shards ?? 0) }}</b>
                <b v-else class="word">{{ WORDS[row.kind] }}</b>
              </span>
            </td>
            <td class="rate-col">
              <span class="rate-wrap">
                <span class="pay-bar" aria-hidden="true"><i :style="{ width: barOf(row) }"></i></span>
                <span class="num">{{ oddsText(row.rate) }}</span>
              </span>
            </td>
            <td class="pity-col">
              <span v-if="row.pity" class="pity-pill">{{ row.pity }} 张</span>
              <template v-else>—</template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </ParkSheet>
</template>

<style scoped>
.tab-key {
  gap: 6px;
}
.tab-cost {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  opacity: 0.85;
}
.tab-cost img {
  width: 15px;
  height: 15px;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.22));
}

/* Both tables share one grid cell so the dialog height stays steady when switching cards. */
.stack {
  display: grid;
  align-items: start;
}
.stack > * {
  grid-area: 1 / 1;
}
.stack > [hidden] {
  display: table;
  visibility: hidden;
}

/* Tabular probability sheet aligned with ResonancePage (.rates): material swatches, right-aligned Barlow figures,
 * and flat pity pills. */
.rates {
  --track: 108px;
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-body);
}
.rates th {
  padding: 2px 10px 9px;
  border-bottom: 1px solid var(--c-200);
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-3);
  text-align: right;
  white-space: nowrap;
}
.rates th:first-child {
  text-align: left;
}
.rates td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--c-100);
  font-weight: 700;
  color: var(--ink);
  white-space: nowrap;
}
.rates tbody tr:last-child td {
  border-bottom: 0;
}

.tier-cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.swatch {
  flex: none;
  width: 4px;
  height: 14px;
  border-radius: 2px;
  background: var(--swatch, var(--c-200));
}
.rates .legendary {
  --swatch: var(--grad-gold);
  --bar: var(--gold);
  background: linear-gradient(90deg, color-mix(in oklab, var(--gold-soft) 18%, var(--surface)), transparent 78%);
}
.rates .legendary.top {
  background: linear-gradient(90deg, color-mix(in oklab, var(--gold-soft) 32%, var(--surface)), transparent 84%);
}
.rates .epic {
  --swatch: var(--c-800);
  --bar: var(--c-700);
}
.rates .skin {
  --swatch: var(--c-500);
  --bar: var(--c-500);
}
.rates .rare {
  --swatch: var(--c-400);
  --bar: var(--c-400);
}
.rates .uncommon {
  --swatch: var(--c-300);
  --bar: var(--c-300);
}
.rates .miss {
  --swatch: var(--c-200);
  --bar: color-mix(in oklab, var(--ink-3) 35%, var(--surface));
}

.pay-icon {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  color: var(--c-600);
}
.legendary .pay-icon {
  color: color-mix(in oklab, var(--gold) 78%, var(--c-700));
}
.epic .pay-icon {
  color: var(--c-800);
}
.pay-icon .coin {
  width: 20px;
  height: 20px;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.24));
}
.pay-icon .emote {
  width: 24px;
  height: 24px;
  object-fit: contain;
  filter: var(--contour);
}
.dash {
  width: 12px;
  height: 2.5px;
  border-radius: 2px;
  background: var(--ink-3);
  opacity: 0.48;
}

.amount {
  font: 800 20px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.top .amount {
  font-size: 23px;
}
.word {
  font: 800 var(--fs-strong)/1.2 var(--font);
  color: var(--ink);
}

.rate-col {
  text-align: right;
}
.rate-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}
.pay-bar {
  width: var(--track);
  height: 4px;
  border-radius: 2px;
  background: var(--c-100);
}
.pay-bar i {
  display: block;
  min-width: 3px;
  height: 100%;
  border-radius: inherit;
  background: var(--bar, var(--c-400));
}
.num {
  min-width: 52px;
  text-align: right;
  font: 800 var(--fs-number)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}

.pity-col {
  width: 68px;
  text-align: right;
  font: 800 var(--fs-label)/1 var(--font-latin);
  color: var(--ink-3);
}
.pity-pill {
  display: inline-block;
  padding: 3px 7px;
  border-radius: var(--radius-s);
  background: var(--c-100);
  color: var(--c-700);
  font: 800 var(--fs-caption)/1 var(--font);
  font-variant-numeric: tabular-nums;
}

.miss .word,
.miss .num {
  color: var(--ink-3);
}

/* Short panels (including 920×620 where panel height is 600px): keep all nine rows comfortably visible. */
@container panel (max-height: 620px) {
  .rates td {
    padding: 5.5px 8px;
  }
  .amount {
    font-size: 18px;
  }
  .top .amount {
    font-size: 21px;
  }
}
@container panel (max-width: 560px) {
  .rates {
    --track: 64px;
  }
  .rates th,
  .rates td {
    padding-inline: 6px;
  }
}
</style>
