<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { manifest } from "../manifest";
import { assetUrl } from "../asset";
import { craftCost, getItem, ownsEmote, type Item } from "../items";
import { boxes, collection, craftItem, error, online, openBoxes, shards, status } from "../stores/player";
import { settings } from "../stores/settings";
import { sendEmote } from "../stores/room";
import { ui } from "../stores/ui";
import type { Drop } from "../net/api";
import RevealModal from "./RevealModal.vue";
import Modal from "../ui/Modal.vue";
import ItemArt from "../ui/ItemArt.vue";
import Icon from "../ui/Icon.vue";
import CharacterAvatar from "../ui/CharacterAvatar.vue";
const character = ref(settings.character);
const query = ref("");
const onlyOwned = ref(false);
const groups = computed(() => manifest.emoteSets.filter((s) => s.character === character.value).map((s) => ({ ...s, emotes: s.emotes.filter((e) => e.name.includes(query.value) && (!onlyOwned.value || ownsEmote(e.key, collection.owned))) })).filter((s) => s.emotes.length));
const favorites = computed(() => Array.from({ length: 8 }, (_, n) => getItem(`emote:${settings.favorites[n]}`)));
const selected = ref<Item | null>(null);
const owned = computed(() => selected.value ? ownsEmote(selected.value.ref, collection.owned) : false);
const cost = computed(() => selected.value ? craftCost(selected.value) : null);
const busy = ref(false);
const drops = ref<Drop[]>([]);
const actionNote = ref("");
watch(() => ui.craftTarget, (id) => { if (id) { selected.value = getItem(id) ?? null; ui.craftTarget = ""; } }, { immediate: true });
async function open(all: boolean) {
  if (busy.value) return;
  busy.value = true;
  const count = all ? boxes.value : 1;
  const results: Drop[] = [];
  let remaining = count;
  while (remaining > 0) {
    const batch = await openBoxes(Math.min(10, remaining));
    if (!batch?.length) break;
    results.push(...batch); remaining -= batch.length;
  }
  drops.value = results;
  busy.value = false;
}
async function craft() {
  if (!selected.value || busy.value) return;
  busy.value = true;
  const item = selected.value;
  if (await craftItem(item.id)) actionNote.value = `已兑换 ${item.name}`;
  busy.value = false;
}
function favorite(item: Item) {
  const at = settings.favorites.indexOf(item.ref);
  if (at >= 0) settings.favorites.splice(at, 1);
  else if (settings.favorites.length < 8) settings.favorites.push(item.ref);
  else actionNote.value = "常用已满，点击上方表情移除一个。";
}
function assign(e: DragEvent, n: number) {
  const key = e.dataTransfer?.getData("text/plain");
  if (!key || !ownsEmote(key, collection.owned)) return;
  const next = settings.favorites.filter((k) => k !== key);
  next.splice(Math.min(n, next.length), 0, key);
  settings.favorites = next.slice(0, 8);
}
function play(item: Item) { sendEmote(item.ref); selected.value = null; }
</script>
<template>
  <div class="emotes-page ui-scroll">
    <section class="box-row">
      <div class="box-title"><span class="box-art"><Icon name="box" :size="30" /></span><div><small>拆开一点小惊喜</small><h2>表情宝箱 <b>{{ boxes }}</b></h2></div></div>
      <div class="progress"><span>敲击 {{ status?.progress.taps ?? 0 }} / {{ status?.progress.tapsPerBox ?? 600 }}</span><div class="ui-bar"><i :style="{ width: `${(status?.progress.taps ?? 0) / (status?.progress.tapsPerBox ?? 600) * 100}%` }"></i></div><small>活跃 {{ status?.progress.minutes ?? 0 }}/{{ status?.progress.minutesPerBox ?? 10 }} 分钟 · 今日 {{ status?.boxesToday ?? 0 }}/{{ status?.dailyCap ?? 10 }} 箱</small></div>
      <div class="buttons"><button class="ui-btn" :disabled="busy || !online || !boxes" @click="open(false)">开一个</button><button class="ui-btn primary" :disabled="busy || !online || !boxes" @click="open(true)">{{ busy ? '开启中…' : '全部打开' }}</button></div>
    </section>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <section class="favorites"><div class="section-heading"><h3>常用表情</h3><small>拖入常用 · 点击移除</small><span><Icon name="shard" :size="14" />{{ shards }} 碎片</span></div><div class="slots"><button v-for="(item, n) in favorites" :key="n" :title="item ? `移除 ${item.name}` : `常用位置 ${n + 1}`" @dragover.prevent @drop.prevent="assign($event, n)" @click="item && favorite(item)"><ItemArt v-if="item" :item="item" :size="50" /><span v-else>＋</span><small>{{ n + 1 }}</small></button></div></section>
    <div class="character-tabs"><button v-for="c in manifest.characters" :key="c.name" :class="{ on: character === c.name }" @click="character = c.name"><CharacterAvatar :character="c.name" :size="28" />{{ c.name }}</button><input v-model="query" class="ui-input" placeholder="搜索表情" aria-label="搜索表情" /><label><input v-model="onlyOwned" type="checkbox" /> 已拥有</label></div>
    <section v-for="s in groups" :key="s.id" class="set"><h3>{{ s.name }}<small>{{ s.emotes.filter((e) => ownsEmote(e.key, collection.owned)).length }} / {{ s.emotes.length }}</small></h3><div class="emote-grid"><button v-for="e in s.emotes" :key="e.key" :class="{ locked: !ownsEmote(e.key, collection.owned), favorite: settings.favorites.includes(e.key) }" :draggable="ownsEmote(e.key, collection.owned)" @dragstart="$event.dataTransfer?.setData('text/plain', e.key)" @click="selected = getItem(`emote:${e.key}`) ?? null; actionNote = ''"><img :src="assetUrl(e.img)" :alt="e.name" loading="lazy" draggable="false" /><span>{{ e.name }}</span><i v-if="settings.favorites.includes(e.key)">✦</i></button></div></section>
    <p v-if="!groups.length" class="empty">还没有匹配的表情。</p>
    <Modal v-if="selected" :title="selected.name" @close="selected = null"><div class="emote-detail"><ItemArt :item="selected" :size="140" /><p>{{ selected.group }}</p><small v-if="actionNote">{{ actionNote }}</small><div v-if="owned" class="buttons"><button class="ui-btn" @click="favorite(selected)">{{ settings.favorites.includes(selected.ref) ? '移出常用' : '加入常用' }}</button><button class="ui-btn primary" @click="play(selected)">发表情</button></div><template v-else><span>宝箱获得 · {{ cost }} 碎片兑换</span><button class="ui-btn primary" :disabled="busy || !online || cost === null || shards < cost" @click="craft">兑换 {{ cost }} 碎片</button></template><p v-if="error" class="error">{{ error }}</p></div></Modal>
    <RevealModal v-if="drops.length" :drops="drops" @close="drops = []" />
  </div>
</template>
<style scoped>
.emotes-page { height: 100%; overflow: auto; box-sizing: border-box; padding: 24px 28px; }
.box-row { display: flex; align-items: center; gap: 24px; padding: 20px; background: #fff5ed; border-top: 2px solid #fc966e; }
.box-title { display: flex; align-items: center; gap: 12px; flex: none; }.box-art { width: 52px; height: 52px; display: grid; place-items: center; color: #b56939; background: #ffdfbd; transform: rotate(-7deg); border-radius: 8px; }
.box-title small { font-size: 10px; color: #a8765d; }h2 { margin: 6px 0 0; font-size: 17px; }h2 b { font-size: 23px; margin-left: 10px; }
.progress { flex: 1; display: flex; flex-direction: column; gap: 6px; font-size: 11px; color: var(--ink-2); }.progress small { font-size: 10px; }
.buttons { display: flex; gap: 8px; justify-content: center; }
.favorites { margin: 24px 0; }.section-heading { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }h3 { margin: 0; font-size: 13px; }.section-heading small { font-size: 10px; color: var(--ink-3); }.section-heading > span { margin-left: auto; display: flex; align-items: center; gap: 5px; font-size: 12px; color: #a15a3e; }
.slots { display: flex; gap: 10px; flex-wrap: wrap; }.slots button { position: relative; width: 64px; height: 64px; display: grid; place-items: center; border: 1px dashed #e8d5c9; background: #fffcf9; border-radius: 5px; cursor: pointer; }.slots button:hover { border-color: var(--accent); }.slots button > span { color: #d0bcad; font-size: 20px; }.slots small { position: absolute; bottom: 2px; right: 4px; font-size: 9px; color: #bc9f8b; }
.character-tabs { display: flex; align-items: center; gap: 8px; padding-bottom: 14px; border-bottom: 1px solid var(--line); flex-wrap: wrap; }.character-tabs button { display: inline-flex; align-items: center; gap: 5px; padding: 4px 8px; background: none; border: 1px solid transparent; border-radius: 5px; cursor: pointer; font: 600 12px var(--font); color: var(--ink-2); }.character-tabs button.on { background: #fff1e8; border-color: #ffd8c3; color: #85492d; }.character-tabs > input { width: 130px; margin-left: auto; }.character-tabs label { font-size: 11px; color: var(--ink-2); display: flex; align-items: center; }
.set { padding: 20px 0 0; }.set h3 { display: flex; gap: 10px; align-items: baseline; margin-bottom: 14px; }.set h3 small { color: var(--ink-3); font-size: 10px; font-weight: 400; }.emote-grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(76px,1fr)); gap: 12px; }.emote-grid button { position: relative; border: 1px solid transparent; border-radius: 5px; padding: 7px 4px; background: transparent; cursor: pointer; color: var(--ink-2); }.emote-grid button:hover { background: #fff6ef; border-color: #f9dfcd; }.emote-grid img { display: block; width: 60px; height: 60px; object-fit: contain; margin: auto; }.emote-grid span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 11px var(--font); margin-top: 7px; }.emote-grid .locked img { opacity: .33; filter: grayscale(.5); }.emote-grid i { position: absolute; top: 3px; right: 5px; color: #e58e65; font-size: 11px; font-style: normal; }
.emote-detail { display: flex; flex-direction: column; align-items: center; gap: 16px; font-size: 12px; }.emote-detail p { margin: 0; color: var(--ink-2); }.emote-detail small { color: #a45b38; }.error { color: var(--bad); font-size: 12px; }.empty { color: var(--ink-3); text-align: center; padding: 24px; font-size: 13px; }
@media (max-width: 700px) { .box-row { flex-wrap: wrap; gap: 14px; }.progress { min-width: 150px; }.box-row .buttons { margin-left: auto; }.emotes-page { padding: 16px; } }
</style>
