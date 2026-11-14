<script setup lang="ts">
// The premium card's prize showcase beside the table: the top shard prize on a gold plate, and under it the two items
// the card gives as collectibles, a skin bust and a big hidden card, tilted as on the reveal board. The art is one the
// save does not own yet (what the card would give, park_scratch.py ParkScratch._items); with all of them owned the
// prize pays shards instead and any one is shown. While the shelf is in view the two take turns changing to another
// every few seconds, with a crossfade; never under reduced motion.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import { assetUrl } from "../../asset";
import { characters } from "../../characters";
import { cardFrame } from "../../cards";
import { ownsCharacter } from "../../items";
import { manifest, skinTitle } from "../../manifest";
import { collection } from "../../stores/player";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import PetBust from "../PetBust.vue";
import { oddsText, rateOf, topPrize } from "./scratchCards";

const props = defineProps<{ shown: boolean }>();

/** One of the two items changes this often; each changes every other time. */
const TURN_MS = 3500;
const TOP = topPrize("premium");
const fmt = (n: number) => n.toLocaleString("en-US");
const ODDS = { top: oddsText(rateOf("premium", TOP)), skin: oddsText(rateOf("premium", "skin")), big: oddsText(rateOf("premium", "big")) };

/** Skins the client can draw (the server leaves out the ones a client of this version could not show). */
const SKINS = manifest.skins.map((s) => s.name).filter((name) => characters[name]);
const BIGS = manifest.cards.filter((c) => c.tier === "big");
const skinPool = computed(() => {
  const left = SKINS.filter((name) => !ownsCharacter(name, collection.owned));
  return left.length ? left : SKINS;
});
const bigPool = computed(() => {
  const left = BIGS.filter((c) => !(collection.owned[`card:${c.id}`] ?? 0));
  return left.length ? left : BIGS;
});

const start = () => Math.floor(Math.random() * 1000);
const skinAt = ref(start());
const bigAt = ref(start());
const skin = computed(() => skinPool.value[skinAt.value % Math.max(1, skinPool.value.length)] ?? "");
const big = computed(() => bigPool.value[bigAt.value % Math.max(1, bigPool.value.length)] ?? null);
/** The 960px preview: the bust is drawn larger than the 264px face crop is made for. */
const bust = computed(() => (skin.value ? characters[skin.value]?.bgMedium ?? "" : ""));

// ---- turning: only while the shelf is in view, the page is shown and motion is allowed
const active = ref(false);
onMounted(() => (active.value = true));
onActivated(() => (active.value = true));
onDeactivated(() => (active.value = false));
const live = computed(() => active.value && props.shown && !reducedMotion.value);
let timer: ReturnType<typeof setInterval> | undefined;
let turn = 0;
function step() {
  if (turn++ % 2 === 0) {
    if (skinPool.value.length > 1) skinAt.value++;
  } else if (bigPool.value.length > 1) {
    bigAt.value++;
  }
}
watch(live, (on) => {
  clearInterval(timer);
  timer = on ? setInterval(step, TURN_MS) : undefined;
}, { immediate: true });
onBeforeUnmount(() => clearInterval(timer));
</script>

<template>
  <div class="showcase">
    <p class="jackpot">
      <span class="jackpot-plate"><Icon name="shard" :size="22" /><b>{{ fmt(TOP) }}</b></span>
      <small class="odds">{{ ODDS.top }}</small>
    </p>
    <ul class="items">
      <li class="item skin">
        <span class="frame">
          <Transition name="xfade">
            <span v-if="bust" :key="skin" class="art plate" :title="skinTitle(skin)">
              <PetBust class="bust" :src="bust" detail />
            </span>
          </Transition>
        </span>
        <span class="label"><b>皮肤</b><small class="odds">{{ ODDS.skin }}</small></span>
      </li>
      <li class="item big">
        <span class="frame">
          <Transition name="xfade">
            <span v-if="big" :key="big.id" class="art photo" :class="cardFrame(big)" :title="big.name">
              <img :src="assetUrl(big.thumb)" alt="" draggable="false" decoding="async" />
            </span>
          </Transition>
        </span>
        <span class="label"><b>大隐藏</b><small class="odds">{{ ODDS.big }}</small></span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.showcase {
  --card-w: 104px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}
.odds {
  font: 700 var(--fs-strong)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
}

/* The top prize: the amount on a small gold plate, its chance under it. */
.jackpot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  margin: 0;
}
.jackpot-plate {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 8px 16px 8px 12px;
  border-radius: var(--radius-m);
  background: linear-gradient(180deg, #FFFBF1, var(--gold-soft));
  box-shadow: inset 0 0 0 2px var(--gold), 0 6px 12px -8px rgba(var(--gold-rgb), 0.9);
}
.jackpot-plate svg {
  color: var(--gold);
}
.jackpot-plate b {
  font: 800 34px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}

/* The two items: collectibles lying on the page, each a little crooked, the name and chance under it. */
.items {
  display: flex;
  justify-content: center;
  gap: 18px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.frame {
  position: relative;
  display: block;
  container-type: inline-size;
  width: var(--card-w);
  aspect-ratio: 2 / 3;
  rotate: var(--lean);
}
.skin {
  --lean: -4deg;
}
.big {
  --lean: 4deg;
}
.art {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-m);
  box-shadow: 0 0 0 3px #fff, 0 10px 18px -10px rgba(var(--shadow-rgb), 0.5), 0 2px 4px rgba(var(--shadow-rgb), 0.08);
}
/* The skin: its bust standing at the bottom of a plate. */
.plate {
  display: grid;
  place-items: end center;
  overflow: hidden;
  background: linear-gradient(180deg, var(--c-50) 20%, var(--c-300));
}
.bust {
  display: block;
  width: 124%;
  height: 100%;
  filter: var(--contour);
}
/* The big hidden card: the photo in its gold frame, as in the album and on the reveal board. */
.photo {
  border-radius: 5cqw;
  background: var(--frame-fill) var(--frame-at) / var(--frame-size);
}
.photo img {
  position: absolute;
  inset: 4cqw;
  width: calc(100% - 8cqw);
  height: calc(100% - 8cqw);
  border-radius: 3.5cqw;
  object-fit: cover;
}
.label {
  display: flex;
  align-items: baseline;
  gap: 6px;
  white-space: nowrap;
}
.label b {
  font: 800 var(--fs-strong)/1 var(--font);
  color: var(--ink);
}

.xfade-enter-active,
.xfade-leave-active {
  transition: opacity 700ms var(--ease-in-out);
}
.xfade-enter-from,
.xfade-leave-to {
  opacity: 0;
}

/* Under the table: the plate on the left, the two items beside it. */
@container panel (max-width: 760px) {
  .showcase {
    --card-w: 64px;
    flex-direction: row;
    justify-content: flex-start;
    align-items: center;
    gap: 22px;
  }
  .jackpot-plate b {
    font-size: 28px;
  }
  .items {
    gap: 14px;
  }
  .item {
    gap: 8px;
  }
}
/* Short: smaller items, so the column fits beside the ticket. */
@container panel (max-height: 560px) {
  .showcase {
    --card-w: 76px;
    gap: 10px;
  }
  .jackpot-plate {
    padding: 6px 14px 6px 10px;
  }
  .jackpot-plate b {
    font-size: 28px;
  }
}
@container panel (max-width: 760px) and (max-height: 560px) {
  .showcase {
    --card-w: 60px;
  }
}
</style>
