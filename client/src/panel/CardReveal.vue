<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { getCard } from "../manifest";
import { assetUrl } from "../asset";
import type { Drop } from "../net/api";
import Modal from "../ui/Modal.vue";

const props = defineProps<{ drops: Drop[]; remaining: number }>();
const emit = defineEmits<{ close: [] }>();
const spotlight = ref(0);
const specials = computed(() => props.drops.filter((d) => d.tier === "big"));
const special = computed(() => specials.value[spotlight.value]);
const cards = computed(() => props.drops.map((d) => ({ ...d, card: getCard(d.item.slice(5))! })));
const shortName = (name: string) =>
  name.replace(/^A-SOUL\s*[·\s]\s*/, "").replace(/收藏集$/, "").split(" · ").at(-1)!.trim() || name;
watch(
  () => props.drops,
  () => (spotlight.value = 0),
);
</script>

<template>
  <Modal :title="special ? '抽中大隐藏！' : '抽卡结果'" wide @close="special ? spotlight++ : emit('close')">
    <template v-if="special" #behind>
      <i :key="spotlight" class="dots" aria-hidden="true"></i>
    </template>
    <template v-if="special" #front>
      <div :key="spotlight" class="burst" aria-hidden="true">
        <i class="flash soft"></i>
        <i class="flash hot"></i>
      </div>
    </template>

    <div v-if="special" :key="spotlight" class="special">
      <span class="ui-tag dark">大隐藏</span>
      <div class="special-frame ui-frame">
        <img class="special-card" :src="assetUrl(getCard(special.item.slice(5))!.thumb)" :alt="getCard(special.item.slice(5))!.name" />
        <i class="foil" aria-hidden="true"></i>
      </div>
      <h3>{{ getCard(special.item.slice(5))!.name }}</h3>
      <small>{{ special.new ? "新获得！" : `已拥有 ×${special.count}` }}</small>
      <button type="button" class="ui-btn primary" @click="spotlight++">查看全部结果</button>
    </div>

    <template v-else>
      <h3 class="heading">本次抽卡获得 {{ drops.length }} 张</h3>
      <div class="results ui-scroll" :class="{ solo: cards.length === 1 }">
        <article
          v-for="(c, i) in cards" :key="i"
          class="drawn" :class="c.tier"
          :style="{ animationDelay: `${Math.min(i, 9) * 55}ms` }"
        >
          <div class="well ui-frame">
            <img :src="assetUrl(c.card.thumb)" :alt="c.card.name" />
            <span v-if="c.new" class="new-tag ui-tag">NEW</span>
            <i v-if="c.tier !== 'normal'" class="tier-tag ui-tag dark">{{ c.tier === "big" ? "大隐藏" : "小隐藏" }}</i>
          </div>
          <b>{{ shortName(c.card.name) }}</b>
          <small>×{{ c.count }}</small>
        </article>
      </div>
      <div class="actions">
        <button type="button" class="ui-btn primary" @click="emit('close')">
          {{ remaining ? `收下并继续抽取（剩余 ${remaining} 次）` : "收下" }}
        </button>
      </div>
    </template>
  </Modal>
</template>

<style scoped>
.heading {
  margin: 0 0 14px;
  text-align: center;
  font: 400 21px/1.1 var(--font-display);
  color: var(--ink);
}
.results {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(88px, 124px));
  justify-content: center;
  gap: 12px 10px;
  max-height: 360px;
  overflow: auto;
  padding: 6px 8px 6px 2px;
}
.results.solo {
  display: flex;
  justify-content: center;
}
.drawn {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  animation: reveal 520ms var(--ease-out) both;
}
.results.solo .drawn {
  width: 156px;
}
.well {
  width: 100%;
  aspect-ratio: 2 / 3;
  background: var(--rar-rare-bg);
}
.drawn.big .well,
.drawn.small .well {
  background: var(--rar-epic-bg);
}
.well img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 16%;
  display: block;
}
.new-tag {
  position: absolute;
  left: 6px;
  top: 5px;
}
.tier-tag {
  position: absolute;
  right: 12px;
  bottom: 6px;
}
.drawn b {
  display: block;
  width: 100%;
  margin-top: 6px;
  font-size: 12px;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.drawn small {
  font: italic 800 13px/1 var(--font-latin);
  color: var(--ink-3);
}
.actions {
  display: flex;
  justify-content: center;
  margin-top: 18px;
}

/* Hidden-card reveal: two slanted bands sweep over everything and the card flips in as they clear,
   while a ring of dots bursts out behind the sheet. */
.burst {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}
.flash {
  position: absolute;
  top: -4%;
  bottom: -4%;
  left: -10%;
  width: 120%;
  transform: translateX(-115%) skewX(var(--skew));
  animation: flash 1200ms cubic-bezier(0.65, 0, 0.35, 1) both;
}
.flash.soft {
  background: var(--accent-soft);
}
.flash.hot {
  background: var(--accent);
  animation-delay: 130ms;
}
.dots {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 760px;
  height: 760px;
  margin: -380px 0 0 -380px;
  background: radial-gradient(var(--accent) 2.4px, transparent 2.8px) 0 0 / 22px 22px;
  mask: radial-gradient(circle, transparent 26%, #000 34%, #000 46%, transparent 64%);
  -webkit-mask: radial-gradient(circle, transparent 26%, #000 34%, #000 46%, transparent 64%);
  opacity: 0;
  animation: dots 1200ms var(--ease-out) 680ms both;
}
@keyframes flash {
  to {
    transform: translateX(115%) skewX(var(--skew));
  }
}
@keyframes dots {
  from {
    opacity: 1;
    transform: scale(0.35);
  }
  60% {
    opacity: 0.9;
  }
  to {
    opacity: 0;
    transform: scale(1.5);
  }
}

.special {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.special-frame {
  --cut: 16px;
  padding: 6px;
  background: var(--accent);
  animation: flip 800ms var(--ease-out) 640ms both;
}
.special-card {
  width: 168px;
  display: block;
}
.foil {
  position: absolute;
  inset: -10%;
  background: linear-gradient(112deg, transparent 38%, rgba(255, 255, 255, 0.6) 48%, rgba(255, 224, 190, 0.35) 54%, transparent 64%);
  transform: translateX(-70%);
  animation: foil 3.6s var(--ease-in-out) 1.5s infinite;
}
@keyframes foil {
  0% {
    transform: translateX(-70%);
  }
  50%, 100% {
    transform: translateX(70%);
  }
}
.special h3 {
  margin: 4px 0 0;
  font: 400 22px/1.1 var(--font-display);
}
.special small {
  color: var(--ink-2);
  font-weight: 700;
}
@keyframes flip {
  from {
    opacity: 0;
    transform: perspective(700px) rotateY(100deg) scale(0.8);
  }
}
@keyframes reveal {
  from {
    opacity: 0;
    transform: perspective(600px) rotateY(70deg) translateY(10px);
  }
}
</style>
