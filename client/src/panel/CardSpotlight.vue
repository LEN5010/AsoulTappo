<script setup lang="ts">
// One card's entrance. A normal card flips, a small hidden card cuts in over ink, a big hidden
// card gets gold rays and a title card. `settled` holds the final frame; a hidden card's video starts there.
import { computed } from "vue";
import { assetUrl } from "../asset";
import { cardLabel, TIER_LABEL } from "../cards";
import { characterColor, type ManifestCard } from "../manifest";
import type { Drop } from "../net/api";
import { reducedMotion } from "../stores/theme";

const props = defineProps<{ drop: Drop; card: ManifestCard; art: string; settled: boolean }>();
defineEmits<{ done: [] }>();

const label = computed(() => cardLabel(props.card));
const hidden = computed(() => props.card.tier !== "normal");
</script>

<template>
  <div class="spot" :class="[card.tier, { settled }]">
    <i v-if="card.tier === 'big'" class="rays" aria-hidden="true"></i>
    <i v-else class="stripe" aria-hidden="true"></i>

    <div class="row">
      <div class="flip" @animationend.self="$emit('done')">
        <div class="art ui-frame">
          <video
            v-if="settled && hidden && card.video && !reducedMotion" class="media"
            :src="assetUrl(card.video)" :poster="art" autoplay loop muted playsinline
          ></video>
          <img v-else class="media" :src="art" :alt="card.name" draggable="false" />
          <i v-if="hidden" class="foil" aria-hidden="true"></i>
        </div>
      </div>

      <div class="facts">
        <span class="ui-tag" :class="{ gold: card.tier === 'big', dark: card.tier === 'normal' }">{{ TIER_LABEL[card.tier] }}</span>
        <h3>{{ label.title }}</h3>
        <p><i :style="{ background: characterColor(card.characters[0] ?? '') }" aria-hidden="true"></i>{{ label.who }}</p>
        <span v-if="drop.new" class="state fresh">NEW</span>
        <span v-else class="state">已拥有 ×{{ drop.count }}</span>
      </div>
    </div>

    <template v-if="hidden && !settled">
      <i class="cut one" aria-hidden="true"></i>
      <i class="cut two" aria-hidden="true"></i>
      <strong class="title">{{ TIER_LABEL[card.tier] }}</strong>
    </template>
  </div>
</template>

<style scoped>
.spot {
  --flip-at: 0ms;
  --flip-ms: 520ms;
  --frame: var(--surface);
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: var(--accent);
  color: var(--on-accent);
}
.small {
  --flip-at: 620ms;
  --flip-ms: 560ms;
  --frame: var(--accent);
  background: var(--ink);
  color: var(--on-ink);
}
.big {
  --flip-at: 1280ms;
  --flip-ms: 640ms;
  --frame: var(--gold);
  background: var(--ink);
  color: var(--on-ink);
}

.stripe {
  position: absolute;
  top: -10px;
  bottom: -10px;
  right: 16%;
  width: 22%;
  background: rgba(255, 255, 255, 0.14);
  transform: skewX(var(--skew));
}
.small .stripe {
  background: var(--accent);
  opacity: 0.22;
}
.rays {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 150cqw;
  aspect-ratio: 1;
  margin: -75cqw 0 0 -75cqw;
  background: repeating-conic-gradient(rgba(var(--gold-rgb), 0) 0deg 9deg, rgba(var(--gold-rgb), 0.22) 9deg 18deg);
  mask: radial-gradient(closest-side, #000 30%, transparent 78%);
  -webkit-mask: radial-gradient(closest-side, #000 30%, transparent 78%);
  animation: spin 26s linear infinite;
}

.row {
  position: relative;
  z-index: 1;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 44px;
  padding: 0 40px;
  box-sizing: border-box;
}
.flip {
  flex: none;
  animation: flip var(--flip-ms) var(--ease-out) var(--flip-at) backwards;
}
.art {
  --cut: var(--cut-l);
  height: min(480px, 74cqh);
  aspect-ratio: 2 / 3;
  padding: 5px;
  box-sizing: border-box;
  background: var(--frame);
}
.media {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
  background: var(--accent-soft);
}
.foil {
  position: absolute;
  inset: -10%;
  background: linear-gradient(112deg, transparent 38%, rgba(255, 255, 255, 0.46) 48%, rgba(255, 224, 190, 0.28) 54%, transparent 64%);
  transform: translateX(-70%);
  pointer-events: none;
}
.settled .foil {
  animation: foil 4.2s var(--ease-in-out) infinite;
}

.facts {
  flex: 0 1 260px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  animation: facts var(--dur-slow) var(--ease-out) calc(var(--flip-at) + var(--flip-ms) - 160ms) backwards;
}
h3 {
  margin: 6px 0 0;
  font: 400 var(--fs-display)/1.15 var(--font-display);
}
.facts p {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: var(--fs-strong);
  font-weight: 800;
}
.facts p i {
  width: 5px;
  height: 13px;
  transform: skewX(var(--skew));
}
.state {
  margin-top: 10px;
  font-size: var(--fs-body);
  font-weight: 800;
}
.state.fresh {
  font: italic 800 var(--fs-title)/1 var(--font-latin);
  letter-spacing: 0.06em;
}
.big .state.fresh {
  color: var(--gold-soft);
}

.settled .flip,
.settled .facts {
  animation: none;
}

/* Two bands wipe across, the tier name rides between them, then the card flips in. */
.cut {
  position: absolute;
  inset: -2px -14%;
  z-index: 2;
  transform: skewX(var(--skew)) translateX(-112%);
  animation: cut 620ms var(--ease-in-out) both;
}
.cut.one {
  background: var(--accent);
}
.cut.two {
  background: var(--surface);
  animation-delay: 70ms;
}
.big .cut {
  animation-duration: 1280ms;
}
.big .cut.one {
  background: var(--gold);
}
.big .cut.two {
  background: var(--gold-soft);
}
.title {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 3;
  font: 400 var(--fs-burst)/1 var(--font-display);
  color: var(--ink);
  white-space: nowrap;
  transform: translate(-50%, -50%);
  animation: title 620ms var(--ease-in-out) both;
}
.big .title {
  animation: slam 1280ms var(--ease-out) both;
}

@keyframes flip {
  from {
    opacity: 0;
    transform: perspective(900px) rotateY(96deg) scale(0.82);
  }
}
@keyframes facts {
  from {
    opacity: 0;
    transform: translate(-14px, 10px);
  }
}
@keyframes cut {
  45%, 55% {
    transform: skewX(var(--skew)) translateX(0);
  }
  to {
    transform: skewX(var(--skew)) translateX(112%);
  }
}
@keyframes title {
  0% {
    opacity: 0;
    transform: translate(calc(-50% - 90px), -50%);
  }
  40%, 60% {
    opacity: 1;
    transform: translate(-50%, -50%);
  }
  100% {
    opacity: 0;
    transform: translate(calc(-50% + 90px), -50%);
  }
}
@keyframes slam {
  0%, 16% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(2.1);
  }
  30%, 68% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  100% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(1.12);
  }
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@keyframes foil {
  0%, 12% {
    transform: translateX(-70%);
  }
  55%, 100% {
    transform: translateX(70%);
  }
}

@container panel (max-height: 560px) {
  .row {
    gap: 28px;
  }
  h3 {
    font-size: var(--fs-title);
  }
}
</style>
