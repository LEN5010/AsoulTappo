<script setup lang="ts">
// The premium card's prize showcase beside the table: the top shard prize on a gold plate, and under it the two items
// the card gives as collectibles, a skin bust and a big hidden card, tilted on a recessed display mat. The art is one
// the save does not own yet (what the card would give, park_scratch.py ParkScratch._items); with all of them owned the
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
const calm = computed(() => reducedMotion.value);

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
const live = computed(() => active.value && props.shown && !calm.value);
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
  <div class="showcase" :class="{ calm }">
    <div class="jackpot">
      <div class="jackpot-plate frame-gold">
        <span class="jackpot-head">
          <span class="tier-word">头奖</span>
          <small class="odds-pill">{{ ODDS.top }}</small>
        </span>
        <b class="jackpot-amount"><Icon name="shard" :size="22" />{{ fmt(TOP) }}</b>
      </div>
    </div>

    <div class="pedestal">
      <ul class="items">
        <li class="item skin">
          <span class="frame">
            <Transition name="xfade" :css="!calm">
              <span v-if="bust" :key="skin" class="art plate" :title="skinTitle(skin)">
                <PetBust class="bust" :src="bust" detail />
              </span>
            </Transition>
          </span>
          <span class="label"><b>皮肤</b><small class="odds">{{ ODDS.skin }}</small></span>
        </li>
        <li class="item big">
          <span class="frame">
            <Transition name="xfade" :css="!calm">
              <span v-if="big" :key="big.id" class="art photo" :class="cardFrame(big)" :title="big.name">
                <img :src="assetUrl(big.thumb)" alt="" draggable="false" decoding="async" />
              </span>
            </Transition>
          </span>
          <span class="label"><b>大隐藏</b><small class="odds">{{ ODDS.big }}</small></span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.showcase {
  --card-w: 98px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
}
.odds {
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
}

/* Sunlit gold-foil plaque framed by .frame-gold, matching LotteryPrizes. */
.jackpot {
  display: flex;
  flex-direction: column;
}
.jackpot-plate {
  --plaque-face: linear-gradient(
    180deg,
    color-mix(in oklab, var(--gold-soft) 24%, #fff) 0%,
    var(--gold-soft) 56%,
    color-mix(in oklab, var(--gold-soft) 72%, var(--gold)) 100%
  );
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 9px 12px 10px 13px;
  box-sizing: border-box;
  border: 2.5px solid transparent;
  border-radius: var(--radius-l);
  background: var(--plaque-face) padding-box, var(--frame-fill) var(--frame-at) / var(--frame-size) border-box;
  box-shadow:
    inset 0 1.5px 0 rgba(255, 255, 255, 0.9),
    0 8px 18px -12px rgba(var(--gold-rgb), 0.6),
    0 2px 4px rgba(var(--shadow-rgb), 0.06);
}
.jackpot-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.tier-word {
  font: 800 var(--fs-label)/1 var(--font);
  color: var(--ink);
}
.odds-pill {
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  font: 800 var(--fs-caption)/1.2 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
}
.jackpot-amount {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font: 800 34px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.8);
}
.jackpot-amount svg {
  color: color-mix(in oklab, var(--gold) 70%, var(--c-700));
  filter: drop-shadow(0 1px 0 rgba(255, 255, 255, 0.8));
}

/* Recessed tonal display stand holding the two collectible prizes. */
.pedestal {
  padding: 14px 10px 11px;
  border-radius: var(--radius-l);
  background: var(--c-100);
  box-shadow: inset 0 2px 4px rgba(var(--c-900-rgb), 0.06);
}
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
  gap: 9px;
}
.frame {
  position: relative;
  display: block;
  container-type: inline-size;
  width: var(--card-w);
  aspect-ratio: 2 / 3;
  rotate: var(--lean);
  transition: rotate var(--dur-base) var(--ease-out), translate var(--dur-base) var(--ease-out);
}
.skin {
  --lean: -4deg;
}
.big {
  --lean: 4deg;
}
.item:hover .frame {
  rotate: 0deg;
  translate: 0 -4px;
}
.calm .frame {
  transition: none;
}
.calm .item:hover .frame {
  rotate: var(--lean);
  translate: none;
}
.art {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-m);
  box-shadow: 0 0 0 2.5px #fff, 0 10px 18px -10px rgba(var(--shadow-rgb), 0.45), 0 2px 4px rgba(var(--shadow-rgb), 0.08);
}
/* The skin: its bust standing at the bottom of a warm coral plate. */
.plate {
  display: grid;
  place-items: end center;
  overflow: hidden;
  background: linear-gradient(180deg, var(--c-50) 18%, var(--c-300));
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
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  white-space: nowrap;
}
.label b {
  font: 800 var(--fs-label)/1.2 var(--font);
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

/* Compact panel heights (e.g. 920×620 where panel height is 600px): scale items so the shelf stays crisp beside deck. */
@container panel (max-height: 640px) {
  .showcase {
    --card-w: 80px;
    gap: 8px;
  }
  .jackpot-plate {
    padding: 7px 11px 8px 12px;
  }
  .jackpot-amount {
    font-size: 28px;
  }
  .pedestal {
    padding: 10px 8px 8px;
  }
}

/* Under the table: the plate on the left, the two items beside it. */
@container panel (max-width: 760px) {
  .showcase {
    --card-w: 62px;
    flex-direction: row;
    justify-content: flex-start;
    align-items: stretch;
    gap: 12px;
  }
  .jackpot {
    justify-content: center;
  }
  .jackpot-plate {
    justify-content: center;
    min-width: 128px;
  }
  .jackpot-amount {
    font-size: 26px;
  }
  .pedestal {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px 10px;
  }
  .items {
    gap: 14px;
  }
  .item {
    gap: 6px;
  }
}

@container panel (max-height: 560px) {
  .showcase {
    --card-w: 68px;
    gap: 6px;
  }
  .jackpot-amount {
    font-size: 24px;
  }
  .pedestal {
    padding: 8px 8px 6px;
  }
}

@container panel (max-width: 760px) and (max-height: 560px) {
  .showcase {
    --card-w: 56px;
  }
}
</style>
