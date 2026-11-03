<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { manifest, type ManifestCard } from "../manifest";
import { assetUrl } from "../asset";
import { getItem, type Item } from "../items";
import { collection, drawCards, error, online, presenceUpdatedAt, status, tickets } from "../stores/player";
import type { Drop } from "../net/api";
import ItemDetail from "./ItemDetail.vue";
import CardReveal from "./CardReveal.vue";
import Icon from "../ui/Icon.vue";
const selected = ref(manifest.series[0]!.id);
const filter = ref("all");
const pool = computed(() => manifest.series.find((p) => p.id === selected.value)!);
const cards = computed(() => manifest.cards.filter((c) => c.series === selected.value));
const ownedCount = (c: ManifestCard) => collection.owned[`card:${c.id}`] ?? 0;
const have = computed(() => cards.value.filter(ownedCount).length);
const visible = computed(() => cards.value.filter((c) => filter.value === "all" || (filter.value === "owned" ? ownedCount(c) : !ownedCount(c))));
const groups = computed(() => [
  { name: "隐藏款", cards: visible.value.filter((c) => c.tier !== "normal").sort((a, b) => Number(b.tier === "big") - Number(a.tier === "big")) },
  { name: "普通款", cards: visible.value.filter((c) => c.tier === "normal") },
]);
const cover = computed(() => cards.value.find((c) => c.tier === "big") ?? cards.value[0]!);
const shortName = (name: string) => name.split(" · ").at(-1)!;
function probability(c: ManifestCard) {
  const mass = { big: 0.5, small: 4.5, normal: 95 }[c.tier];
  return (mass / cards.value.filter((x) => x.tier === c.tier).length).toFixed(2) + "%";
}
const clock = ref(Date.now());
const timer = setInterval(() => clock.value = Date.now(), 1000);
onBeforeUnmount(() => clearInterval(timer));
const remaining = computed(() => {
  const draw = status.value?.draw;
  if (!draw) return 900;
  const elapsed = online.value && presenceUpdatedAt.value ? Math.min(20, Math.max(0, (clock.value - presenceUpdatedAt.value) / 1000)) : 0;
  return Math.max(0, Math.ceil(draw.secondsPerDraw - draw.seconds - elapsed));
});
const countdown = computed(() => `${Math.floor(remaining.value / 60).toString().padStart(2, "0")}:${(remaining.value % 60).toString().padStart(2, "0")}`);
const detail = ref<Item | null>(null);
const drops = ref<Drop[]>([]);
const busy = ref(false);
const pending = ref(0);
async function draw(all: boolean) {
  if (busy.value || !tickets.value) return;
  busy.value = true;
  pending.value = all ? tickets.value : 1;
  await nextBatch();
}
async function nextBatch() {
  const result = await drawCards(selected.value, Math.min(pending.value, 100));
  if (result) { pending.value -= result.length; drops.value = result; }
  else pending.value = 0;
  busy.value = false;
}
async function collect() {
  drops.value = [];
  if (pending.value > 0) { busy.value = true; await nextBatch(); }
}
</script>

<template>
  <div class="collection-page">
    <section class="hero">
      <div class="intro"><small>ASOUL COLLECTION</small><h1>{{ shortName(pool.name) }}<span>✦</span></h1><p>把喜欢的瞬间，收藏在桌边。</p></div>
      <div class="hero-art" aria-hidden="true"><img :src="assetUrl(cover.thumb)" alt="" /><img v-if="cards[1]" :src="assetUrl(cards[1].thumb)" alt="" /></div>
      <span class="hero-number">{{ have.toString().padStart(2, '0') }}<small> / {{ cards.length }}</small></span>
    </section>
    <nav class="pools ui-scroll" aria-label="收藏集"><button v-for="p in manifest.series" :key="p.id" :class="{ on: selected === p.id }" :disabled="busy || drops.length > 0" @click="selected = p.id">{{ shortName(p.name) }}</button></nav>
    <div class="filters"><button v-for="f in [{ id: 'all', label: '全部' }, { id: 'owned', label: '已拥有' }, { id: 'missing', label: '未拥有' }]" :key="f.id" :class="{ on: filter === f.id }" @click="filter = f.id">{{ f.label }}</button><span>已收集 <b>{{ have }}</b> / {{ cards.length }}</span></div>
    <div class="wall ui-scroll">
      <section v-for="group in groups" :key="group.name" class="group">
        <h3 v-if="group.cards.length"><span class="diamond"></span>{{ group.name }}<small>{{ group.cards.length }} 款</small></h3>
        <div class="grid">
          <button v-for="c in group.cards" :key="c.id" class="card" :class="[c.tier, { locked: !ownedCount(c) }]" @click="detail = getItem(`card:${c.id}`) ?? null">
            <span class="face"><img :src="assetUrl(c.thumb)" :alt="c.name" loading="lazy" draggable="false" /><i v-if="c.tier !== 'normal'" class="tier">{{ c.tier === 'big' ? '大隐藏' : '小隐藏' }}</i><b v-if="ownedCount(c)" class="count">×{{ ownedCount(c) }}</b><span v-if="c.video" class="video"><Icon name="play" :size="12" /></span></span>
            <b class="name">{{ c.name }}</b><small class="probability">{{ probability(c) }}</small>
          </button>
        </div>
      </section>
      <p v-if="!visible.length" class="empty">这里还空着，抽一张开启收藏。</p>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <footer class="drawbar">
      <div class="ticket"><Icon name="book" :size="24" /><div><span><b>{{ tickets }}</b> 次抽卡</span><small>{{ online ? `下一抽 ${countdown}` : '连接服务器后开始计时' }}</small></div></div>
      <div class="pity"><span>大隐藏 <b>{{ status?.draw?.pity ?? 0 }}</b> / 400</span><div class="ui-bar"><i :style="{ width: `${(status?.draw?.pity ?? 0) / 4}%` }"></i></div><small>全卡池共用保底 · 大隐藏 0.5% / 小隐藏 4.5%</small></div>
      <div class="draw-actions"><button class="ui-btn" :disabled="busy || !online || !tickets" @click="draw(false)">{{ busy ? '抽取中…' : '抽一次' }}</button><button class="ui-btn primary" :disabled="busy || !online || !tickets" @click="draw(true)">全部抽取 <span v-if="tickets">×{{ tickets }}</span></button></div>
    </footer>
    <ItemDetail v-if="detail" :item="detail" @close="detail = null" />
    <CardReveal v-if="drops.length" :drops="drops" :remaining="pending" @close="collect" />
  </div>
</template>

<style scoped>
.collection-page { height: 100%; display: flex; flex-direction: column; }
.hero { position: relative; display: flex; align-items: center; min-height: 128px; overflow: hidden; background: #fff5ed; border-bottom: 1px solid #f7e8df; }
.hero::before { content: ""; position: absolute; inset: 0; background-image: radial-gradient(#edcdbb 0.7px, transparent 0.7px); background-size: 10px 10px; opacity: .32; }
.intro { position: relative; z-index: 1; margin-left: 28px; }
.intro > small { font-size: 9px; letter-spacing: 3px; color: #a5684b; font-weight: 700; }
h1 { margin: 6px 0 7px; font-size: 27px; letter-spacing: 1px; font-weight: 800; } h1 span { font-size: 16px; color: #fc966e; margin-left: 12px; vertical-align: top; }
.intro p { margin: 0; font-size: 12px; color: #96725f; }
.hero-art { position: absolute; right: 100px; top: -34px; width: 230px; height: 210px; transform: rotate(11deg); }
.hero-art img { position: absolute; height: 205px; border: 5px solid #fff; box-shadow: 0 4px 12px #8e674333; transform: rotate(-19deg); }
.hero-art img + img { left: 110px; transform: rotate(5deg); }
.hero-number { position: relative; margin-left: auto; margin-right: 26px; align-self: flex-end; margin-bottom: 18px; font-size: 28px; font-weight: 800; color: #b77d5e; }
.hero-number small { font-size: 12px; font-weight: 500; }
.pools { display: flex; gap: 4px; padding: 12px 24px 0; overflow-x: auto; flex: none; }
.pools button { flex: none; padding: 8px 13px; border: 1px solid transparent; border-radius: 5px; color: var(--ink-2); background: none; font: 600 12px var(--font); cursor: pointer; }
.pools button.on { color: #844125; background: #fff0e7; border-color: #ffd5c1; }
.pools button:hover { background: #fff5ef; }
.filters { display: flex; align-items: center; gap: 24px; margin: 0 28px; min-height: 44px; flex: none; border-bottom: 1px solid var(--line); font-size: 12px; }
.filters button { align-self: stretch; background: none; border: 0; border-bottom: 2px solid transparent; font: inherit; color: var(--ink-2); cursor: pointer; padding: 0; }
.filters button.on { color: #a85330; border-color: var(--accent); font-weight: 700; }
.filters > span { margin-left: auto; color: var(--ink-2); }
.wall { flex: 1; min-height: 0; overflow: auto; padding: 16px 28px 24px; }
h3 { display: flex; align-items: center; gap: 7px; margin: 0 0 14px; font-size: 13px; } h3 small { font-weight: 400; color: var(--ink-3); margin-left: 3px; font-size: 11px; }
.diamond { width: 6px; height: 6px; background: #fc966e; transform: rotate(45deg); }
.group + .group { margin-top: 24px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 20px 16px; }
.card { min-width: 0; border: 0; background: none; padding: 0; font: inherit; cursor: pointer; text-align: left; color: var(--ink); }
.face { position: relative; display: block; aspect-ratio: 2 / 3; border-radius: 4px; background: #f4efeb; transition: transform 180ms; }
.face img { width: 100%; height: 100%; object-fit: cover; border-radius: 4px; display: block; }
.card:hover .face { transform: translateY(-4px); }
.locked .face img { filter: saturate(.55); opacity: .58; }
.big .face { outline: 1px solid #cf9b45; outline-offset: 2px; }
.small .face { outline: 1px solid #c7ac95; outline-offset: 2px; }
.tier { position: absolute; left: 0; top: 0; padding: 3px 7px; border-radius: 4px 0 4px 0; background: #f1ce8a; color: #694a1d; font-size: 10px; font-style: normal; font-weight: 700; }
.small .tier { background: #e6d8ca; color: #705b49; }
.count { position: absolute; right: -4px; top: -6px; padding: 3px 5px; border-radius: 3px; background: #fff; color: #a95832; border: 1px solid #ecd7c9; font-size: 10px; }
.video { position: absolute; bottom: 5px; right: 5px; display: grid; place-items: center; padding: 4px; background: #42372b99; color: #fff; border-radius: 3px; }
.name { display: block; margin-top: 9px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 600; }
.probability { display: block; color: var(--ink-3); font-size: 11px; margin-top: 3px; }
.big .probability { color: #a37227; }
.drawbar { display: flex; align-items: center; gap: 28px; padding: 16px 24px; background: #fffbf7; border-top: 1px solid #f0e3da; flex: none; }
.ticket { display: flex; align-items: center; gap: 10px; color: #b96541; min-width: 152px; }
.ticket > div { display: flex; flex-direction: column; gap: 4px; }
.ticket span { color: var(--ink-2); font-size: 11px; } .ticket b { font-size: 22px; color: var(--ink); margin-right: 5px; }
.ticket small, .pity small { font-size: 10px; color: var(--ink-2); }
.pity { flex: 1; max-width: 300px; display: flex; flex-direction: column; gap: 5px; font-size: 11px; color: var(--ink-2); }
.pity b { color: var(--ink); } .ui-bar { height: 3px; }
.draw-actions { display: flex; gap: 8px; margin-left: auto; }.draw-actions .ui-btn { height: 38px; }
.empty { color: var(--ink-3); padding: 30px 0; text-align: center; font-size: 13px; }
.error { margin: 0; padding: 6px 24px; color: var(--bad); font-size: 12px; }
@media (max-width: 700px) { .hero-art { right: 10px; opacity: .35; } .hero-number { display: none; } .drawbar { gap: 12px; flex-wrap: wrap; padding: 12px 16px; } .pity { max-width: none; } .pity small { font-size: 9px; } .wall { padding: 16px; } .grid { grid-template-columns: repeat(auto-fill,minmax(94px,1fr)); } }
</style>
