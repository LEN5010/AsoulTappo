<script setup lang="ts">
// A playing card of the dou dizhu table: white paper, the rank in Barlow with its suit under it, hearts and diamonds
// in deep coral. The jokers are 阿草, grey on the small one. `card` null draws the back. Everything is sized from
// `width` (px), so one card serves the hand, the table and the receipt.
import { computed } from "vue";
import { isRed, rank, rankLabel, suit } from "../../ddz/rules";
import alpaca from "../../assets/brand/side-alpaca.webp";

// `plain` leaves the large suit off the corner: for a card lying under another, where a sliver of it would show.
const props = withDefaults(defineProps<{ card: number | null; width?: number; plain?: boolean }>(), { width: 64 });

/** 24×24 outlines: spade, heart, club, diamond. */
const SUITS = [
  "M12 2s8 6.2 8 11.2c0 2.700-2 4.500-4.300 4.500-1.300 0-2.400-.5-3.100-1.400.2 2 .9 3.600 2.400 4.700H9c1.500-1.100 2.200-2.700 2.400-4.700-.7.9-1.800 1.400-3.100 1.400C6 17.700 4 15.900 4 13.200 4 8.200 12 2 12 2z",
  "M12 21s-7.500-4.600-9.300-9.400C1.300 7.800 3.600 4 7.200 4c2 0 3.700 1 4.800 2.700C13.100 5 14.800 4 16.800 4c3.600 0 5.900 3.800 4.500 7.600C19.500 16.400 12 21 12 21z",
  "M7.600 7a4.400 4.400 0 1 0 8.800 0 4.400 4.400 0 1 0-8.800 0zM2.200 13.600a4.400 4.400 0 1 0 8.800 0 4.400 4.400 0 1 0-8.800 0zM13 13.600a4.400 4.400 0 1 0 8.800 0 4.400 4.400 0 1 0-8.800 0zM12 11c.2 5 .9 8 2.600 10H9.400c1.700-2 2.400-5 2.600-10z",
  "M12 2l7.500 10L12 22 4.500 12z",
];
const face = computed(() => (props.card === null || props.card >= 52 ? null : {
  label: rankLabel(rank(props.card)), path: SUITS[suit(props.card)]!, red: isRed(props.card),
}));
</script>

<template>
  <span v-if="card === null" class="ddz-card back" :style="{ '--w': width }"></span>
  <span v-else-if="!face" class="ddz-card joker" :class="{ small: card === 52 }" :style="{ '--w': width }">
    <span class="word"><i v-for="c in 'JOKER'" :key="c">{{ c }}</i></span>
    <img :src="alpaca" alt="" draggable="false" />
  </span>
  <span v-else class="ddz-card" :class="{ red: face.red }" :style="{ '--w': width }">
    <span class="idx">
      <b class="rank" :class="{ ten: face.label === '10' }">{{ face.label }}</b>
      <svg class="suit" viewBox="0 0 24 24" aria-hidden="true"><path :d="face.path" /></svg>
    </span>
    <svg v-if="!plain" class="suit pip" viewBox="0 0 24 24" aria-hidden="true"><path :d="face.path" /></svg>
  </span>
</template>

<style scoped>
.ddz-card {
  --px: calc(var(--w) * 1px);
  position: relative;
  flex: none;
  display: block;
  width: var(--px);
  height: calc(var(--px) * 1.42);
  box-sizing: border-box;
  border-radius: calc(var(--px) * 0.125);
  background: linear-gradient(180deg, #fff 55%, var(--key-white-shade));
  color: var(--ink);
  box-shadow: 0 0 0 1px rgba(var(--c-900-rgb), 0.12), -3px 3px 6px -2px rgba(var(--c-900-rgb), 0.3);
  user-select: none;
}
.red { color: var(--c-700); }
.suit { display: block; fill: currentColor; }
.idx {
  position: absolute;
  left: 0;
  top: calc(var(--px) * 0.08);
  width: calc(var(--px) * 0.46);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
}
.rank {
  font: 800 calc(var(--px) * 0.44) / 0.93 var(--font-latin);
  letter-spacing: -0.5px;
}
/* Two digits in the room of one. */
.rank.ten { letter-spacing: -1.5px; transform: scaleX(0.86); }
.idx .suit { width: calc(var(--px) * 0.235); height: calc(var(--px) * 0.235); }
.pip {
  position: absolute;
  right: calc(var(--px) * 0.11);
  bottom: calc(var(--px) * 0.11);
  width: calc(var(--px) * 0.44);
  height: calc(var(--px) * 0.44);
}
/* The jokers: the word down the edge, 阿草 on the face. */
.word {
  position: absolute;
  left: 0;
  top: calc(var(--px) * 0.09);
  width: calc(var(--px) * 0.44);
  display: flex;
  flex-direction: column;
  align-items: center;
  font: 800 calc(var(--px) * 0.215) / 0.86 var(--font-latin);
  color: var(--c-700);
}
.word i { font-style: normal; }
/* The big joker is the warm one: coral rises from its foot. The small one stays grey. */
.joker:not(.small) { background: linear-gradient(180deg, #fff 30%, var(--c-200)); }
.joker.small .word { color: var(--ink-3); }
.joker img {
  position: absolute;
  right: 1px;
  bottom: 0;
  height: 78%;
  border-bottom-right-radius: calc(var(--px) * 0.1);
  pointer-events: none;
}
.joker.small img { filter: grayscale(1); opacity: 0.8; }
/* The back: coral, a white edge, a line inside it. */
.back {
  background: var(--grad-sky);
  box-shadow: inset 0 0 0 calc(var(--px) * 0.09) #fff, 0 1px 3px rgba(var(--c-900-rgb), 0.35);
}
.back::after {
  content: "";
  position: absolute;
  inset: calc(var(--px) * 0.19);
  border-radius: calc(var(--px) * 0.06);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.6);
}
</style>
