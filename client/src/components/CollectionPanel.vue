<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RARITY_ORDER, getCard, manifest, resolveAsset, type ManifestCard, type Rarity } from "../manifest";
import { seriesProgress } from "../net/api";
import { toHttpBase } from "../net/protocol";
import { settings } from "../stores/settings";
import { boxes, collection, lastOpened, online, openBox, refresh, status, error } from "../stores/player";
import { reducedMotion, skin } from "../stores/theme";

const base = computed(() => toHttpBase(settings.serverUrl));
const url = (r: string | null) => resolveAsset(r, base.value, import.meta.env.BASE_URL);
const filter = ref<string>("all");
const detail = ref<ManifestCard | null>(null);
const opening = ref(false);
const reveal = ref<ManifestCard | null>(null);

const owned = computed(() => collection.owned);
const have = (id: string) => (owned.value[id] ?? 0) > 0;
const progress = computed(() => seriesProgress(owned.value));
const totalOwned = computed(() => manifest.cards.filter((c) => have(c.id)).length);
const rarityName = (r: Rarity) => manifest.rarities[r].name;
const shown = computed(() =>
  manifest.cards
    .filter((c) => filter.value === "all" || c.series === filter.value)
    .slice()
    .sort((a, b) => RARITY_ORDER.indexOf(b.rarity) - RARITY_ORDER.indexOf(a.rarity)),
);
const prog = computed(() => status.value?.progress);
const pct = (v: number, max?: number) => (max ? Math.min(100, Math.round((v / max) * 100)) : 0);
const seriesName = (id: string) => manifest.series.find((s) => s.id === id)?.name ?? id;

onMounted(refresh);

async function open() {
  opening.value = true;
  const r = await openBox();
  if (r) {
    const c = getCard(r.card) ?? null;
    if (!reducedMotion.value) await new Promise((res) => setTimeout(res, 700));
    reveal.value = c;
  }
  opening.value = false;
}
function show(c: ManifestCard) {
  if (have(c.id)) detail.value = c;
}
</script>

<template>
  <div class="col">
    <template v-if="!reveal && !detail">
    <section class="box glass">
      <div class="box-head">
        <strong>宝箱 ×{{ boxes }}</strong>
        <span class="muted">今日 {{ status?.boxesToday ?? 0 }}/{{ status?.dailyCap ?? "-" }}</span>
      </div>
      <div class="bar" title="点击进度"><i :style="{ width: pct(prog?.taps ?? 0, prog?.tapsPerBox) + '%' }"></i></div>
      <div class="bar" title="活跃分钟进度"><i class="alt" :style="{ width: pct(prog?.minutes ?? 0, prog?.minutesPerBox) + '%' }"></i></div>
      <small class="muted">
        每 {{ prog?.tapsPerBox ?? 600 }} 次点击或 {{ prog?.minutesPerBox ?? 10 }} 个活跃分钟获得一个宝箱
      </small>
      <button class="primary" :disabled="!boxes || opening || !online" @click="open">
        <img v-if="opening && skin.loading && !reducedMotion" class="spin" :src="skin.loading" alt="" />
        {{ opening ? "开启中…" : online ? "开宝箱" : "服务器离线" }}
      </button>
      <div v-if="error && !online" class="err">{{ error }}</div>
    </section>

    <div class="summary">
      <span>图鉴 {{ totalOwned }}/{{ manifest.cards.length }}</span>
      <select v-model="filter" aria-label="按系列筛选">
        <option value="all">全部系列</option>
        <option v-for="s in progress" :key="s.id" :value="s.id">{{ s.name }} ({{ s.have }}/{{ s.total }})</option>
      </select>
    </div>

    <div class="grid">
      <button
        v-for="c in shown" :key="c.id" type="button" class="card" :class="[c.rarity, { locked: !have(c.id) }]"
        :aria-label="have(c.id) ? c.name : '未获得的卡片'" :disabled="!have(c.id)" @click="show(c)"
      >
        <img :src="url(c.thumb)" :alt="have(c.id) ? c.name : ''" loading="lazy" draggable="false" />
        <span v-if="have(c.id) && (owned[c.id] ?? 0) > 1" class="dup">×{{ owned[c.id] }}</span>
        <span v-if="!have(c.id)" class="q">?</span>
        <span v-else-if="c.video" class="vid" aria-hidden="true">▶</span>
      </button>
    </div>

    </template>

    <!-- newly opened card -->
    <div v-if="reveal" class="overlay" role="dialog" aria-modal="true" aria-label="获得新卡片" @click.self="reveal = null">
      <div class="modal glass" :class="reveal.rarity">
        <div class="tag">{{ rarityName(reveal.rarity) }}<template v-if="lastOpened?.new"> · NEW</template></div>
        <img class="big" :src="url(reveal.thumb)" :alt="reveal.name" />
        <strong>{{ reveal.name }}</strong>
        <small class="muted">{{ seriesName(reveal.series) }}</small>
        <div class="actions">
          <button @click="detail = reveal; reveal = null">查看详情</button>
          <button class="primary" autofocus @click="reveal = null">好的</button>
        </div>
      </div>
    </div>

    <!-- card detail with video -->
    <div v-if="detail" class="overlay" role="dialog" aria-modal="true" :aria-label="detail.name" @click.self="detail = null">
      <div class="modal glass wide" :class="detail.rarity">
        <div class="tag">{{ rarityName(detail.rarity) }} · {{ seriesName(detail.series) }}</div>
        <video
          v-if="detail.video" :src="url(detail.video)" :poster="url(detail.thumb)" controls playsinline preload="none"
          class="big"
        ></video>
        <img v-else class="big" :src="url(detail.full)" :style="{ backgroundImage: `url(${url(detail.thumb)})` }" :alt="detail.name" />
        <strong>{{ detail.name }}</strong>
        <small class="muted">{{ detail.characters.join(" / ") }}<template v-if="detail.sub"> · {{ detail.sub }}</template></small>
        <small v-if="detail.video" class="muted">视频由服务器素材包提供,首次播放时加载</small>
        <button class="primary" autofocus @click="detail = null">关闭</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.col { display: flex; flex-direction: column; gap: 8px; position: relative; }
.glass { background: rgba(255, 255, 255, 0.55); border: 1px solid rgba(255, 255, 255, 0.7); border-radius: 12px; backdrop-filter: blur(6px); }
.box { padding: 8px; display: flex; flex-direction: column; gap: 5px; }
.box-head { display: flex; justify-content: space-between; align-items: baseline; }
.muted { color: rgba(0, 0, 0, 0.5); font-size: 11px; }
.bar { height: 6px; border-radius: 3px; background: rgba(0, 0, 0, 0.1); overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--accent); transition: width 300ms; }
.bar i.alt { background: var(--char); }
.spin { width: 16px; height: 16px; vertical-align: -3px; margin-right: 4px; }
.summary { display: flex; align-items: center; justify-content: space-between; gap: 6px; font-size: 12px; }
.summary select { max-width: 170px; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.card { position: relative; padding: 0; border: 2px solid transparent; border-radius: 8px; overflow: hidden; background: rgba(255, 255, 255, 0.6); cursor: pointer; aspect-ratio: 414 / 621; }
.card img { width: 100%; height: 100%; object-fit: cover; display: block; }
.card.locked { cursor: default; background: rgba(0, 0, 0, 0.12); }
.card.locked img { filter: brightness(0) opacity(0.3); } /* silhouette */
.card.rare { border-color: #5aa0e6; } .card.epic { border-color: #a65be0; } .card.legendary { border-color: #f0b030; box-shadow: 0 0 8px rgba(240, 176, 48, 0.7); }
.card:not(.locked):hover { transform: translateY(-2px); }
.q { position: absolute; inset: 0; display: grid; place-items: center; font-size: 22px; color: rgba(0, 0, 0, 0.35); font-weight: 700; }
.dup, .vid { position: absolute; font-size: 10px; background: rgba(0, 0, 0, 0.6); color: #fff; border-radius: 6px; padding: 0 4px; }
.dup { right: 3px; bottom: 3px; } .vid { left: 3px; bottom: 3px; }
.overlay { display: grid; place-items: center; padding: 2px 0; }
.modal { width: 100%; box-sizing: border-box; max-height: 92vh; overflow: auto; background: rgba(255, 255, 255, 0.92); padding: 10px; display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center; animation: pop 220ms ease-out; }
.modal.legendary { box-shadow: 0 0 22px rgba(240, 176, 48, 0.8); } .modal.epic { box-shadow: 0 0 16px rgba(166, 91, 224, 0.6); } .modal.rare { box-shadow: 0 0 12px rgba(90, 160, 230, 0.6); }
.tag { font-size: 11px; font-weight: 700; color: var(--accent); }
.big { width: 100%; max-height: 360px; object-fit: contain; border-radius: 8px; background: rgba(0, 0, 0, 0.06) center / contain no-repeat; }
.actions { display: flex; gap: 6px; }
.err { color: #c33; font-size: 12px; }
@keyframes pop { from { opacity: 0; transform: scale(0.85); } to { opacity: 1; transform: none; } }
</style>
