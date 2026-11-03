<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { getCard } from "../manifest";
import { assetUrl } from "../asset";
import type { Drop } from "../net/api";
import Modal from "../ui/Modal.vue";
const props = defineProps<{ drops: Drop[]; remaining: number }>();
const emit = defineEmits<{ close: [] }>();
const spotlight = ref(0);
const specials = computed(() => props.drops.filter((d) => d.tier === 'big'));
const special = computed(() => specials.value[spotlight.value]);
const cards = computed(() => props.drops.map((d) => ({ ...d, card: getCard(d.item.slice(5))! })));
watch(() => props.drops, () => spotlight.value = 0);
</script>
<template>
  <Modal :title="special ? '大隐藏 · 与你相遇' : '收藏揭晓'" wide @close="special ? spotlight++ : emit('close')">
    <div v-if="special" class="special">
      <span class="eyebrow">A LITTLE MIRACLE</span><h2>这一刻，为你闪耀。</h2>
      <img class="special-card" :src="assetUrl(getCard(special.item.slice(5))!.thumb)" :alt="getCard(special.item.slice(5))!.name" />
      <h3>{{ getCard(special.item.slice(5))!.name }}</h3><small>{{ special.new ? '首次收藏' : `已收藏 ×${special.count}` }}</small>
      <button class="ui-btn primary" @click="spotlight++">查看全部</button>
    </div>
    <template v-else>
      <p class="heading">收集了 <b>{{ drops.length }}</b> 个瞬间</p>
      <div class="results ui-scroll" :class="{ solo: cards.length === 1 }">
        <article v-for="(c, i) in cards" :key="i" :class="c.tier" :style="{ animationDelay: `${Math.min(i, 9) * 65}ms` }">
          <div class="art"><img :src="assetUrl(c.card.thumb)" :alt="c.card.name" /><span v-if="c.new">NEW</span><i v-if="c.tier !== 'normal'">{{ c.tier === 'big' ? '大隐藏' : '小隐藏' }}</i></div>
          <b>{{ c.card.name }}</b><small>×{{ c.count }}</small>
        </article>
      </div>
      <div class="actions"><button class="ui-btn primary" @click="emit('close')">{{ remaining ? `收下，继续抽取 ${remaining} 次` : '收下' }}</button></div>
    </template>
  </Modal>
</template>
<style scoped>
.heading { margin: 0 0 20px; text-align: center; font-size: 14px; color: var(--ink-2); }
.results { display: grid; grid-template-columns: repeat(auto-fill, minmax(88px, 1fr)); gap: 18px 12px; max-height: 360px; overflow: auto; padding: 6px; }
.results.solo { display: flex; justify-content: center; }
.results article { min-width: 0; text-align: center; animation: reveal 500ms both; }
.results.solo article { width: 168px; }
.art { position: relative; aspect-ratio: 2/3; }
.art img { width: 100%; height: 100%; object-fit: cover; border-radius: 4px; }
.art > span { position: absolute; left: -3px; top: -4px; background: #fc966e; color: #4c2b20; padding: 3px 5px; font-size: 9px; font-weight: 800; transform: rotate(-5deg); }
.art i { position: absolute; bottom: 0; left: 0; right: 0; padding: 4px; background: #f6db9b; color: #76531e; font-size: 10px; font-style: normal; }
.small .art i { background: #eadbcd; color: #765f4f; }
.big .art { box-shadow: 0 0 0 2px #e3bc61, 0 3px 12px #d8b25766; }
article b { display: block; margin-top: 9px; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
article small { font-size: 10px; color: var(--ink-3); }
.actions { display: flex; justify-content: center; margin-top: 22px; }
.special { display: flex; flex-direction: column; align-items: center; gap: 12px; background: radial-gradient(ellipse at 50% 45%, #fff1cb, transparent 65%); }
.eyebrow { font-size: 9px; letter-spacing: 3px; color: #9f752e; }
h2 { margin: 0 0 8px; font-size: 22px; letter-spacing: 2px; color: #725023; }
.special-card { width: 176px; border: 3px solid #efd18f; border-radius: 5px; animation: reveal 800ms both, glow 2s 800ms ease-in-out 3 alternate; box-shadow: 0 0 30px #d4a53555; }
h3 { margin: 5px 0 0; font-size: 16px; }.special small { color: #99733f; }.special button { margin: 8px 0; }
@keyframes reveal { from { opacity: 0; transform: perspective(600px) rotateY(90deg) translateY(10px); } }
@keyframes glow { to { box-shadow: 0 0 40px #d9a62c99; } }
</style>
