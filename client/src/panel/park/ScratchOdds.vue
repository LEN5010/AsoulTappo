<script setup lang="ts">
// The scratch odds (behind the band's info key): a tab a card, opening on the card in front. Each prize is a row, the
// prize drawn as the card's own tile and its odds on the right, rarest first; the top prize in gold, a miss in grey.
import { computed, ref } from "vue";
import { HOST, SCRATCH_EMOTES, faceKey } from "../../scratch";
import { arrowSelect } from "../../ui/focus";
import ParkSheet from "./ParkSheet.vue";
import ScratchTile from "./ScratchTile.vue";
import { KINDS, oddsRows, oddsText, topPrize, type CardKind, type Cell, type OddsRow } from "./scratchCards";

const props = defineProps<{ kind: CardKind; complete: boolean }>();
defineEmits<{ close: [] }>();

const NAMES: Record<CardKind, string> = { basic: "普通", premium: "豪华" };
const shown = ref<CardKind>(props.kind);
const tabs = ref<HTMLElement>();
/** The emote row shows one of the set: the face 阿草 makes when a card pays one. */
const SAMPLE = faceKey(HOST.emote) ?? SCRATCH_EMOTES[0]?.key ?? "";

const lists = computed(() => KINDS.map((k) => ({ kind: k, rows: oddsRows(k, props.complete), top: topPrize(k) })));
const cellOf = (row: OddsRow): Cell | null => {
  if (row.kind === "shards") return { kind: "shards", amount: row.shards ?? 0 };
  if (row.kind === "emote") return SAMPLE ? { kind: "emote", key: SAMPLE } : null;
  if (row.kind === "miss") return null;
  return { kind: row.kind };
};
</script>

<template>
  <ParkSheet title="刮刮乐概率" @close="$emit('close')">
    <div ref="tabs" class="park-sheet-tabs" role="tablist" @keydown="arrowSelect($event, tabs)">
      <button
        v-for="k in KINDS" :key="k" type="button" role="tab" class="ui-btn" :class="{ on: shown === k }"
        :aria-selected="shown === k" @click="shown = k"
      >{{ NAMES[k] }}</button>
    </div>
    <div class="park-sheet-stack">
      <ol v-for="l in lists" :key="l.kind" class="park-sheet-list" :hidden="l.kind !== shown" :aria-label="NAMES[l.kind]">
        <li
          v-for="(row, i) in l.rows" :key="i" class="park-sheet-row"
          :class="{ top: row.shards === l.top, wide: row.shards === l.top, muted: row.kind === 'miss' }"
        >
          <span class="park-sheet-lead">
            <ScratchTile v-if="cellOf(row)" :cell="cellOf(row)!" />
            <template v-else>没中</template>
          </span>
          <span v-if="row.pity" class="park-sheet-main"><small>{{ row.pity }} 张保底</small></span>
          <b class="park-sheet-figure">{{ oddsText(row.rate) }}</b>
        </li>
      </ol>
    </div>
  </ParkSheet>
</template>
