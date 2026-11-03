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
const shortName = (name: string) => name.split(" · ").at(-1)!;
watch(
  () => props.drops,
  () => (spotlight.value = 0),
);
</script>

<template>
  <Modal :title="special ? '抽中大隐藏！' : '抽卡结果'" wide @close="special ? spotlight++ : emit('close')">
    <div v-if="special" class="special">
      <span class="tag-pill">大隐藏</span>
      <div class="special-frame">
        <img class="special-card" :src="assetUrl(getCard(special.item.slice(5))!.thumb)" :alt="getCard(special.item.slice(5))!.name" />
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
          class="sq-card" :class="c.tier"
          :style="{ animationDelay: `${Math.min(i, 9) * 55}ms` }"
        >
          <div class="well">
            <img :src="assetUrl(c.card.thumb)" :alt="c.card.name" />
            <span v-if="c.new" class="new-pill">NEW</span>
            <i v-if="c.tier !== 'normal'" class="tier-pill">{{ c.tier === "big" ? "大隐藏" : "小隐藏" }}</i>
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
  font-size: 16px;
  font-weight: 800;
  color: var(--ink);
}
.results {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
  gap: 12px;
  max-height: 360px;
  overflow: auto;
  padding: 6px;
}
.results.solo {
  display: flex;
  justify-content: center;
}
.sq-card {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 6px 8px;
  border-radius: 20px;
  background: var(--tile-frame);
  border: 2px solid var(--tile-border);
  box-shadow: 0 3px 0 var(--tile-lip);
  text-align: center;
  animation: reveal 420ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
.results.solo .sq-card {
  width: 172px;
}
.sq-card.big {
  border-color: var(--accent);
  box-shadow: 0 3px 0 var(--accent-deep), 0 0 14px rgba(var(--accent-rgb), 0.5);
}
.well {
  position: relative;
  width: 100%;
  aspect-ratio: 1 / 1.08;
  border-radius: 14px;
  overflow: hidden;
  background: var(--rar-rare-bg);
}
.sq-card.big .well,
.sq-card.small .well {
  background: var(--rar-epic-bg);
}
.well img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 16%;
  display: block;
}
.new-pill {
  position: absolute;
  left: 4px;
  top: 4px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--accent);
  color: var(--on-accent);
  font-size: 9px;
  font-weight: 900;
}
.tier-pill {
  position: absolute;
  right: 4px;
  bottom: 4px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(255, 246, 236, 0.92);
  color: var(--on-accent);
  font-size: 10px;
  font-style: normal;
  font-weight: 800;
}
.sq-card b {
  display: block;
  width: 100%;
  margin-top: 6px;
  font-size: 12px;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sq-card small {
  font-size: 10px;
  font-weight: 700;
  color: var(--ink-3);
}
.actions {
  display: flex;
  justify-content: center;
  margin-top: 18px;
}

.special {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.tag-pill {
  padding: 3px 12px;
  border-radius: 999px;
  background: linear-gradient(180deg, #FFB596, var(--accent));
  border: 1.5px solid var(--accent-deep);
  color: var(--on-accent);
  font-size: 12px;
  font-weight: 900;
}
.special-frame {
  padding: 8px;
  border-radius: 24px;
  background: #FFF6EC;
  border: 3px solid var(--accent);
  box-shadow: 0 4px 0 var(--accent-deep), 0 0 24px rgba(var(--accent-rgb), 0.48);
  animation: reveal 550ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
.special-card {
  width: 168px;
  border-radius: 16px;
  display: block;
}
h3 {
  margin: 4px 0 0;
  font-size: 17px;
  font-weight: 800;
}
.special small {
  color: var(--ink-2);
  font-weight: 700;
}
@keyframes reveal {
  from {
    opacity: 0;
    transform: perspective(600px) rotateY(80deg) scale(0.92);
  }
}
</style>
