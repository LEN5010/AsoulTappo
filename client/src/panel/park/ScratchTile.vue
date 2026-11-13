<script setup lang="ts">
// What a scratch card cell shows: an amount, an emote, or one of the named symbols. The same face is drawn on the
// card, on the prize shelf beside it and in the odds table, so a prize looks alike wherever it is listed. It fills the
// nearest positioned box (the caller's tile, which draws the background) and sizes itself by that box's width.
import { assetUrl } from "../../asset";
import { emoteCover } from "../../manifest";
import Icon from "../../ui/Icon.vue";
import { COIN_SMALL } from "./coin";
import type { Cell } from "./scratchCards";

defineProps<{ cell: Cell }>();
</script>

<template>
  <span class="tile-face">
    <span v-if="cell.kind === 'shards'" class="amount" :class="{ long: cell.amount >= 10000, longer: cell.amount >= 100000 }">
      <Icon name="shard" :size="16" />{{ cell.amount }}
    </span>
    <img v-else-if="cell.kind === 'emote'" class="emote" :src="assetUrl(emoteCover(cell.key))" alt="" draggable="false" />
    <span v-else-if="cell.kind === 'again'" class="sym again"><img :src="COIN_SMALL" alt="" draggable="false" /><small>再来</small></span>
    <span v-else-if="cell.kind === 'skin'" class="sym item"><Icon name="shirt" :size="26" /><small>皮肤</small></span>
    <span v-else-if="cell.kind === 'big'" class="sym item"><Icon name="card-spark" :size="26" /><small>大隐藏</small></span>
    <i v-else class="blank"></i>
  </span>
</template>

<style scoped>
.tile-face {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  container-type: inline-size;
  user-select: none;
}
/* Amounts scale with the tile, so a long one stays inside it on a small panel. */
.amount {
  display: inline-flex;
  align-items: center;
  gap: 0.06em;
  font: 800 36cqi/1 var(--font-latin);
  color: var(--ink);
}
.amount.long {
  font-size: 30cqi;
}
.amount.longer {
  font-size: 26cqi;
}
.amount svg {
  width: 0.56em;
  height: 0.56em;
  color: var(--c-600);
}
/* An emote is sized by the tile, not by the picture. */
.emote {
  position: absolute;
  inset: 8%;
  width: 84%;
  height: 84%;
  object-fit: contain;
  filter: var(--sticker);
}
/* The named symbols: a mark and a word under it. */
.sym {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2.5cqi;
  color: var(--c-700);
}
.sym svg {
  width: 35cqi;
  height: 35cqi;
}
.sym small {
  font: 800 clamp(11px, 13cqi, 15px)/1 var(--font);
  color: var(--ink-2);
  white-space: nowrap;
}
.sym.again img {
  width: 38cqi;
  height: 38cqi;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.25));
}
/* A blank cell: the A-SOUL mark, faint. */
.blank {
  width: 52%;
  aspect-ratio: 3.172;
  background: var(--c-200);
  mask: url("../../assets/brand/asoul-logo.svg") center / contain no-repeat;
  -webkit-mask: url("../../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
</style>
