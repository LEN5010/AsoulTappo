<script setup lang="ts">
// The two collections a pool's page sums up under its own: the 衣橱 series (in the limited tier) and the holo versions
// (镭射款). Each is a row on the sheet's paper: a small card on the left (the newest owned one) in the collection's
// material, its name and count, and one pip a card, lit in that material when owned. The 衣橱 pips stand in a group a
// member, each group a way into her plate; the holo row opens the collection's page at the holo filter.
import { computed, ref } from "vue";
import { assetUrl } from "../asset";
import { ownsHolo } from "../cards";
import { characterColor, manifest } from "../manifest";
import { allPlates, plateMembers, type Plate } from "../pet/plates";
import { collection } from "../stores/player";
import { economy } from "../stores/economy";
import { reducedMotion } from "../stores/theme";
import { openPanel, ui } from "../stores/ui";
import { tiltTransform } from "../holo/shader";
import { useTilt } from "../holo/useTilt";
import Icon from "../ui/Icon.vue";

defineProps<{ closet?: boolean; holo?: boolean; busy: boolean; hold?: boolean }>();
const emit = defineEmits<{ plate: [plate: Plate] }>();

/** The newest of [owned]: the first one among the recent drops, else the last in catalogue order. */
function newest<T extends { id: string }>(owned: readonly T[], item: (x: T) => string): T | undefined {
  const byItem = new Map(owned.map((x) => [item(x), x]));
  for (const drop of collection.recent) {
    const hit = byItem.get(drop.item);
    if (hit) return hit;
  }
  return owned.at(-1);
}

/** The 衣橱 series, one video plate a member (a picture plate's series is not 衣橱), and the newest owned card of all
 * on the left. */
const closets = allPlates().flatMap((plate) => (plate.kind === "series" ? [plate] : []));
const closetPick = ref("");
const wardrobe = computed(() => {
  const members = closets.map((plate) => {
    const cards = plate.cards.map((c) => ({ id: c.id, on: !!collection.owned[`card:${c.id}`] }));
    const ownedCards = plate.cards.filter((c) => collection.owned[`card:${c.id}`]);
    const member = plateMembers(plate)[0] ?? "";
    const cover = newest(ownedCards, (c) => `card:${c.id}`);
    return {
      plate, member, color: characterColor(member), cards, got: ownedCards.length, total: plate.cards.length,
      cover: (cover ?? plate.cards[0])?.thumb, has: !!cover,
    };
  });
  const all = closets.flatMap((p) => p.cards);
  const owned = all.filter((c) => collection.owned[`card:${c.id}`]);
  const cover = newest(owned, (c) => `card:${c.id}`);
  const first = cover ? members.find((m) => m.plate.cards.some((c) => c.id === cover.id)) : members[0];
  const picked = members.find((m) => m.plate.id === closetPick.value);
  return {
    members,
    got: owned.length,
    total: all.length,
    cover: picked ? picked.cover : (cover ?? all[0])?.thumb,
    has: picked ? picked.has : !!cover,
    plate: (picked ?? first ?? members[0])?.plate ?? null,
    peeking: !!picked,
  };
});
function onClosetKey(e: KeyboardEvent) {
  const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
  const root = e.currentTarget as HTMLElement | null;
  if (!step || !root) return;
  const items = [...root.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
  const idx = items.indexOf(document.activeElement as HTMLButtonElement);
  if (idx < 0) return;
  e.preventDefault();
  items[(idx + step + items.length) % items.length]?.focus();
}

/** The holo versions, only where the server deals them: the newest owned one shines on the left. */
const holoCards = manifest.cards.filter((c) => c.holo);
const holoOn = computed(() => holoCards.length > 0 && !!economy.value?.resonance.holoChance);
const shine = computed(() => {
  const cards = holoCards.map((c) => ({ id: c.id, on: ownsHolo(c, collection.owned) }));
  const owned = holoCards.filter((c) => ownsHolo(c, collection.owned));
  return { cards, got: owned.length, total: holoCards.length, card: newest(owned, (c) => `holo:${c.id}`) };
});
const holoEl = ref<HTMLElement>();
const { tilt: holoTilt, lit: holoLit, moving: holoMoving, follow: holoFollow, leave: holoLeave } = useTilt();
/**
 * At this size the shading would only blur the art: the art stays a plain image, and the foil is the spectrum through
 * the card's own mask, drifting on its own; the card leans under the pointer.
 */
const holoFoil = computed(() => {
  const mask = shine.value.card?.holo ? `url(${assetUrl(shine.value.card.holo.mask)})` : "";
  return { WebkitMaskImage: mask, maskImage: mask };
});
/** The collection's page, at the holo filter. */
function openHolo() {
  ui.dexFilter = "holo";
  openPanel("dex");
}
</script>

<template>
  <div v-if="(closet && wardrobe.total) || (holo && holoOn)" class="rows" :class="{ hold, calm: reducedMotion }">
    <div
      v-if="closet && wardrobe.total" class="c-row closet" :class="{ peeking: wardrobe.peeking }" role="group" aria-label="衣橱"
      @pointerleave="closetPick = ''"
    >
      <button
        type="button" class="thumb pearl" :class="{ dim: !wardrobe.has }" tabindex="-1" :disabled="busy || !wardrobe.plate"
        :title="wardrobe.plate?.name" aria-hidden="true" @click="wardrobe.plate && emit('plate', wardrobe.plate)"
      >
        <img v-if="wardrobe.cover" :src="assetUrl(wardrobe.cover)" alt="" draggable="false" />
      </button>
      <span class="c-head"><em>衣橱</em><b>{{ wardrobe.got }}</b><i>/{{ wardrobe.total }}</i><slot name="closet" /></span>
      <span class="groups" @keydown="onClosetKey">
        <button
          v-for="w in wardrobe.members" :key="w.plate.id" type="button"
          class="group" :class="{ done: w.got === w.total, active: closetPick === w.plate.id }"
          :disabled="busy" :title="w.plate.name" :aria-label="`${w.plate.name} ${w.got}/${w.total}`"
          @pointerenter="closetPick = w.plate.id"
          @focus="closetPick = w.plate.id"
          @blur="closetPick === w.plate.id && (closetPick = '')"
          @click="emit('plate', w.plate)"
        >
          <span class="who">
            <i :style="{ background: w.color }"></i>{{ w.member }}
            <Icon v-if="w.got === w.total" name="check" :size="10" /><b v-else>{{ w.got }}</b>
          </span>
          <span class="pips" :style="{ '--n': w.cards.length }" aria-hidden="true">
            <i v-for="(c, k) in w.cards" :key="c.id" :class="{ on: c.on }" :style="{ '--k': k }"></i>
          </span>
        </button>
      </span>
    </div>
    <button
      v-if="holo && holoOn" type="button" class="c-row shine" :disabled="busy" title="镭射" :aria-label="`镭射 ${shine.got}/${shine.total}`"
      @click="openHolo" @pointermove="holoFollow($event, holoEl)" @pointerleave="holoLeave"
    >
      <span
        ref="holoEl" class="thumb foil" :class="{ lit: holoLit }"
        :style="holoMoving ? { transform: tiltTransform(holoTilt, 300) } : undefined" aria-hidden="true"
      >
        <span v-if="shine.card?.holo" class="foil-art">
          <img :src="assetUrl(shine.card.thumb)" alt="" draggable="false" />
          <i class="foil-sheen" :style="holoFoil"></i>
        </span>
        <span v-else class="foil-back"><Icon name="spark" :size="14" /></span>
      </span>
      <span class="c-head"><em>镭射</em><b>{{ shine.got }}</b><i>/{{ shine.total }}</i><slot name="holo" /></span>
      <span class="pips" :style="{ '--n': shine.cards.length }" aria-hidden="true">
        <i v-for="(c, k) in shine.cards" :key="c.id" :class="{ on: c.on }" :style="{ '--k': k }"></i>
      </span>
    </button>
  </div>
</template>

<style scoped>
/* Rows on the sheet's own paper, a hairline between them: no box inside the box. */
.rows {
  flex: none;
  display: flex;
  flex-direction: column;
}
.c-row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  grid-template-rows: auto auto;
  align-items: center;
  gap: 5px 12px;
  width: 100%;
  margin: 0;
  padding: 8px 0;
  box-sizing: border-box;
  border: 0;
  border-top: 1px solid var(--c-100);
  background: none;
  color: var(--ink);
  font: inherit;
  text-align: left;
}
.c-row:last-child {
  padding-bottom: 10px;
}
button.c-row {
  cursor: pointer;
}
button.c-row:focus-visible {
  outline: 2px solid var(--c-500);
  outline-offset: 2px;
  border-radius: var(--radius-s);
}

/* The small card: a collectible lying on the paper, a little askew; it straightens under the pointer. */
.thumb {
  grid-row: 1 / 3;
  display: block;
  width: 34px;
  aspect-ratio: 2 / 3;
  padding: 2px;
  box-sizing: border-box;
  border: 0;
  border-radius: 5px;
  rotate: -5deg;
  box-shadow: 0 3px 7px -3px rgba(var(--shadow-rgb), 0.5);
  transition: rotate var(--dur-base) var(--ease-out), translate var(--dur-base) var(--ease-out), box-shadow var(--dur-base);
}
.thumb img,
.thumb > :deep(*) {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 3px;
  overflow: hidden;
}
.c-row:hover .thumb,
.closet.peeking .thumb {
  rotate: 0deg;
  translate: 0 -2px;
  box-shadow: 0 0 0 1.5px #fff, 0 6px 12px -4px rgba(var(--shadow-rgb), 0.5);
}
.calm .thumb {
  rotate: 0deg;
  translate: none;
}
.thumb.pearl {
  cursor: pointer;
  background: linear-gradient(125deg, var(--pearl), var(--holo-pink) 20%, #fff 30%, var(--holo-lilac) 45%, var(--pearl-deep) 62%,
    var(--holo-mint) 80%, var(--holo-cream));
  background-size: 200% 200%;
}
.closet.peeking .thumb.pearl,
.thumb.pearl:hover:not(:disabled) {
  background-position: 85% 80%;
}
.thumb.pearl.dim img {
  filter: var(--dim);
}
.thumb.foil {
  background: var(--grad-holo);
  background-size: 300% 100%;
  animation: holo-drift 7s ease-in-out infinite alternate;
}
.hold .thumb.foil,
.calm .thumb.foil,
.hold .foil-sheen,
.calm .foil-sheen {
  animation-play-state: paused;
}
.foil-art {
  position: relative;
  isolation: isolate;
}
.foil-art img {
  position: absolute;
  inset: 0;
}
/* The spectrum through the card's mask, light over the art; brighter under the pointer. */
.foil-sheen {
  position: absolute;
  inset: 0;
  background: var(--grad-holo);
  background-size: 300% 100%;
  -webkit-mask-size: 100% 100%;
  -webkit-mask-repeat: no-repeat;
  mask-size: 100% 100%;
  mask-repeat: no-repeat;
  mix-blend-mode: soft-light;
  opacity: 0.7;
  animation: holo-drift 5s ease-in-out infinite alternate;
  transition: opacity var(--dur-base) var(--ease-out);
}
.thumb.lit .foil-sheen {
  opacity: 1;
}
.foil-back {
  display: grid !important;
  place-items: center;
  background: var(--grad-holo);
  background-size: 300% 100%;
  color: #fff;
}

.c-head {
  display: flex;
  align-items: baseline;
  gap: 3px;
  min-width: 0;
  white-space: nowrap;
}
.c-head em {
  margin-right: 5px;
  font: 800 var(--fs-body)/1 var(--font);
  font-style: normal;
  color: var(--ink);
}
.c-head b {
  font: 800 18px/1 var(--font-latin);
  color: var(--ink);
}
.c-head i {
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}

/* One pip a card, the shape of a card: lit in the collection's material once it is owned. */
.pips {
  display: flex;
  gap: 2px;
  min-width: 0;
}
.pips i {
  flex: 1 1 0;
  max-width: 9px;
  height: 11px;
  border-radius: 2px;
  background: var(--c-100);
}
/* A lit pip shows its own stretch of one spectrum laid along the whole row. */
.pips i.on {
  background: var(--lit) calc(var(--k) / max(1, var(--n) - 1) * 100%) 0 / calc(var(--n) * 100%) 100% no-repeat;
}
.closet .pips {
  --lit: linear-gradient(90deg, #F48FB8, #B493F2 50%, #7FA8F0);
}
.shine .pips {
  --lit: linear-gradient(90deg, #5FC8F5, #9A84F5 25%, #F27DBE 50%, #F7B860 75%, #5ED6B4);
}
.shine .pips i {
  max-width: 11px;
}

/* A group a member: her colour and name over her cards' pips, a way into her plate. */
.groups {
  display: flex;
  gap: 12px;
  min-width: 0;
}
.group {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: -3px -4px;
  padding: 3px 4px;
  border: 0;
  border-radius: var(--radius-s);
  background: none;
  color: var(--ink-2);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--dur-fast);
}
.group.active:not(:disabled) {
  background: var(--c-50);
}
.group:focus-visible {
  outline: 2px solid var(--c-500);
  outline-offset: 1px;
}
.who {
  display: flex;
  align-items: center;
  gap: 4px;
  font: 700 var(--fs-caption)/1 var(--font);
  white-space: nowrap;
}
.who i {
  flex: none;
  width: 3px;
  height: 10px;
  border-radius: 2px;
}
.who b {
  margin-left: auto;
  font: 800 var(--fs-label)/1 var(--font-latin);
  color: var(--ink);
}
.who svg {
  margin-left: auto;
  color: var(--pearl-deep);
}
@container panel (max-width: 820px) {
  .groups {
    gap: 8px;
  }
}
</style>
