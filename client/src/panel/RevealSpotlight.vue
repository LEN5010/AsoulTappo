<script setup lang="ts">
import { computed, watch } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { assetUrl } from "../asset";
import { getCharacter, skinSeries } from "../characters";
import { cardLabel, TIER_LABEL } from "../cards";
import { getItem, RARITY_LABEL } from "../items";
import { characterColor, memberOf, type ManifestCard, type Rarity } from "../manifest";
import type { Drop } from "../net/api";
import { reducedMotion } from "../stores/theme";
import { isRevealHighlight } from "../reveal";

const pageActive = usePageActive();
const props = defineProps<{ drop: Drop; card?: ManifestCard; art?: string; settled: boolean }>();
const emit = defineEmits<{ done: [] }>();
const item = computed(() => getItem(props.drop.item)!);
const skin = computed(() => props.drop.rarity === "skin");
const special = computed(() => isRevealHighlight(props.drop) || props.card?.tier === "small");
const label = computed(() => props.card ? cardLabel(props.card) : {
  title: item.value.name,
  who: skin.value ? memberOf(item.value.ref) : item.value.group,
});
const tier = computed(() => skin.value ? "桌宠皮肤" : props.card && props.card.tier !== "normal"
  ? TIER_LABEL[props.card.tier] : `${RARITY_LABEL[props.drop.rarity as Rarity]}${props.card ? '卡片' : '表情'}`);
const duration = computed(() => special.value ? "1400ms" : props.drop.rarity === "common" ? "620ms" : "860ms");
watch(reducedMotion, (value) => { if (value) emit("done"); });
</script>

<template>
  <div class="reveal-spotlight" :class="[`rarity-${drop.rarity}`, { special, skin, settled: settled || reducedMotion }]" :style="{ '--reveal-ms': duration }">
    <div class="reveal-layout">
      <div class="display">
        <i class="ground" aria-hidden="true"></i>
        <i v-if="special" class="edge-flash" aria-hidden="true"></i>
        <div v-if="special && !settled && !reducedMotion" class="particles" aria-hidden="true">
          <i v-for="n in 12" :key="n" :style="{ '--angle': `${n * 30}deg`, '--reach': `${100 + n % 3 * 34}px`, '--delay': `${450 + n % 4 * 35}ms` }"></i>
        </div>
        <div class="reveal-object" @animationend.self="emit('done')">
          <div class="front" :class="{ illustration: !!card }">
            <template v-if="card">
              <video v-if="settled && card.video && !reducedMotion && pageActive" class="card-image" :src="assetUrl(card.video)" :poster="art" autoplay loop muted playsinline></video>
              <img v-else class="card-image" :src="art" :alt="card.name" draggable="false" />
            </template>
            <template v-else>
              <span class="artifact-type">A-SOUL <i></i> {{ skin ? 'DESKTOP PET' : 'STICKER' }}</span>
              <img class="artifact-image" :src="skin ? getCharacter(item.ref)?.bg : assetUrl(item.art)" :alt="item.name" draggable="false" />
              <span class="artifact-caption">{{ skin ? skinSeries(item.ref) : item.characters.join(' · ') }}</span>
            </template>
            <i v-if="special" class="foil" aria-hidden="true"></i>
          </div>
        </div>
      </div>
      <div class="reveal-facts">
        <span class="reveal-tier"><i></i>{{ tier }}</span>
        <h3>{{ label.title }}</h3>
        <p class="member"><i :style="{ background: characterColor(item.characters[0] ?? '') }"></i>{{ label.who }}</p>
        <div class="ownership">
          <span v-if="drop.new" class="new-label">首次获得</span>
          <span v-else>已拥有 <b>×{{ drop.count }}</b></span>
          <small v-if="drop.shards">重复返还 {{ drop.shards }} 碎片</small>
        </div>
        <p v-if="skin" class="skin-hint">在背包中装备，换上新的桌宠形象</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.reveal-spotlight { position: absolute; inset: 0; overflow: hidden; color: var(--draw-white); --reveal-ms: 620ms; }
.reveal-layout { position: relative; z-index: 1; height: 100%; max-width: 880px; margin: auto; padding: 80px 64px 96px; box-sizing: border-box; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, .8fr); align-items: center; gap: 52px; }
.display { position: relative; display: grid; place-items: center; height: min(420px, 65cqh); perspective: 1400px; }
.ground { position: absolute; width: 86%; height: 20px; bottom: -22px; border-radius: 50%; background: rgba(0, 0, 0, .34); filter: blur(10px); }
.reveal-object { position: relative; height: 100%; aspect-ratio: 2 / 3; transform-style: preserve-3d; animation: reveal-turn var(--reveal-ms) cubic-bezier(.2,.7,.16,1) both; }
.special .reveal-object { animation-name: reveal-special; }
.front { position: absolute; inset: 0; border-radius: 6px; backface-visibility: hidden; animation: front-visible var(--reveal-ms) step-end both; }
.special .front { animation-name: special-front-visible; }
.front { display: flex; flex-direction: column; align-items: center; justify-content: space-between; padding: 22px 16px 18px; box-sizing: border-box; overflow: hidden; background: var(--draw-paper); color: #23313a; box-shadow: 0 12px 32px -12px rgba(0,0,0,.5), 0 0 0 1px rgba(255,255,255,.4); }
.special .front { box-shadow: 0 16px 40px -16px rgba(0,0,0,.6), 0 0 0 1px var(--draw-tone); }
.front.illustration { padding: 3px; background: #c8c9c0; }
.special .front.illustration { background: var(--draw-tone); }
.card-image { display: block; width: 100%; height: 100%; object-fit: cover; border-radius: 3px; }
.artifact-type { display: flex; align-items: center; gap: 8px; font: 800 10px/1.4 var(--font-latin); letter-spacing: .15em; color: #69747a; }
.artifact-type i { width: 2px; height: 2px; background: currentColor; }
.artifact-image { display: block; width: 94%; height: 68%; object-fit: contain; }
.artifact-caption { font: 500 var(--fs-label)/1.3 var(--font); color: #69747a; letter-spacing: .12em; }
.skin .reveal-object { width: 100%; height: 86%; aspect-ratio: auto; }
.skin .artifact-image { width: 100%; height: 72%; }
.foil { position: absolute; inset: -20%; background: linear-gradient(115deg, transparent 42%, rgba(255,255,255,.34) 49%, rgba(255,255,255,.08) 53%, transparent 60%); transform: translateX(-120%); animation: reveal-foil 500ms var(--ease-out) 850ms both; pointer-events: none; }
.edge-flash { position: absolute; left: 50%; top: -8%; width: 2px; height: 116%; background: var(--draw-tone); box-shadow: 0 0 14px 2px color-mix(in srgb, var(--draw-tone) 36%, transparent); animation: reveal-edge 1200ms var(--ease-out) both; }
.particles { position: absolute; left: 50%; top: 50%; pointer-events: none; }
.particles i { position: absolute; width: 3px; height: 3px; background: var(--draw-tone); animation: reveal-particle 650ms var(--ease-out) var(--delay) both; }
.reveal-facts { min-width: 0; animation: reveal-facts 450ms var(--ease-out) calc(var(--reveal-ms) - 220ms) both; }
.reveal-tier { display: flex; align-items: center; gap: 8px; color: var(--draw-tone); font: 500 var(--fs-body)/1.4 var(--font); letter-spacing: .12em; }
.reveal-tier i { width: 18px; height: 1px; background: currentColor; }
h3 { margin: 18px 0 16px; font: 800 clamp(24px, 4.5cqw, 42px)/1.3 var(--font); letter-spacing: -.025em; text-wrap: balance; }
.member { display: flex; align-items: center; gap: 8px; margin: 0; font: 500 var(--fs-body)/1.7 var(--font); color: var(--draw-muted); }
.member i { flex: none; width: 3px; height: 12px; }
.ownership { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; margin-top: 30px; padding-top: 20px; border-top: 1px solid var(--draw-line); color: var(--draw-muted); font-size: var(--fs-body); }
.ownership b { margin-left: 6px; color: var(--draw-white); font-weight: 500; }
.ownership small { font-size: var(--fs-label); }
.new-label { border: 1px solid color-mix(in srgb, var(--draw-tone) 45%, transparent); border-radius: 3px; padding: 5px 10px; color: var(--draw-tone); font-size: var(--fs-label); }
.skin-hint { margin: 20px 0 0; color: var(--draw-muted); font-size: var(--fs-label); line-height: 1.7; }
.settled .reveal-object, .settled .reveal-facts { animation: none; }
.settled .front { animation: none; visibility: visible; }
.settled .edge-flash, .settled .particles { display: none; }
.settled .foil { animation: none; transform: translateX(120%); }
@keyframes reveal-turn { 0% { opacity: 0; transform: translate(-20px, 24px) rotateY(160deg) rotateZ(-4deg) scale(.94); } 18% { opacity: 1; } 48% { transform: translate(0, -6px) rotateY(86deg) rotateZ(-1deg); } 100% { opacity: 1; transform: none; } }
@keyframes reveal-special { 0% { opacity: 0; transform: translateY(24px) rotateY(180deg) scale(.94); } 16%, 36% { opacity: 1; transform: rotateY(180deg) scale(.97); } 55% { transform: translateY(-8px) rotateY(90deg); } 78% { transform: rotateY(-3deg) scale(1.015); } 100% { opacity: 1; transform: none; } }
@keyframes front-visible { 0% { visibility: hidden; } 48%, 100% { visibility: visible; } }
@keyframes special-front-visible { 0% { visibility: hidden; } 55%, 100% { visibility: visible; } }
@keyframes reveal-facts { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }
@keyframes reveal-foil { to { transform: translateX(120%); } }
@keyframes reveal-edge { 0%, 24% { opacity: 0; transform: scaleY(.05); } 42% { opacity: .95; transform: scaleY(1); } 70%, 100% { opacity: 0; transform: scaleY(1.08); } }
@keyframes reveal-particle { 0% { opacity: 0; transform: rotate(var(--angle)) translateX(35px) scale(.5); } 20% { opacity: .8; } 100% { opacity: 0; transform: rotate(var(--angle)) translateX(var(--reach)) scale(0); } }
@container cinema (max-width: 660px) { .reveal-layout { padding: 76px 28px 88px; gap: 24px; grid-template-columns: minmax(0, 1fr) minmax(0, .85fr); } .display { height: min(340px, 54cqh); } .artifact-type { font-size: 8px; gap: 4px; letter-spacing: .06em; } .front { padding: 16px 10px; } h3 { font-size: 24px; } }
@container cinema (max-width: 480px) { .reveal-layout { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(0, 1fr) auto; gap: 22px; padding: 70px 24px 88px; } .display { height: min(290px, 42cqh); } .reveal-facts { text-align: center; } .reveal-tier, .member { justify-content: center; } h3 { margin: 10px 0 8px; font-size: 23px; } .ownership { align-items: center; flex-direction: row; justify-content: center; margin-top: 14px; padding-top: 12px; } .skin-hint { margin-top: 10px; } }
@container cinema (max-height: 540px) { .reveal-layout { padding-top: 64px; padding-bottom: 72px; } .display { height: 64cqh; } h3 { font-size: 26px; margin: 12px 0; } .ownership { margin-top: 18px; padding-top: 14px; } }
@container cinema (max-width: 480px) and (max-height: 540px) { .reveal-layout { padding: 60px 20px 72px; gap: 12px; } .display { height: 32cqh; } h3 { margin: 8px 0; font-size: 21px; } .ownership { margin-top: 10px; padding-top: 10px; } }
</style>
