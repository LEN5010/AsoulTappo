<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getDecor, manifest, resolveAsset } from "../manifest";
import { toHttpBase } from "../net/protocol";
import { settings } from "../stores/settings";
import { chooseDecor, online, refresh, status } from "../stores/player";
import { syncProfile } from "../stores/room";
import { skin } from "../stores/theme";
import SettingsPanel from "./SettingsPanel.vue";
import MemberAvatar from "./MemberAvatar.vue";

const base = computed(() => toHttpBase(settings.serverUrl));
const url = (r: string) => resolveAsset(r, base.value, import.meta.env.BASE_URL);
const showSettings = ref(false);
const unlocked = computed(() => new Set(status.value?.unlocked ?? []));
const frames = computed(() => manifest.decor.filter((d) => d.kind === "frame"));
const badges = computed(() => manifest.decor.filter((d) => d.kind === "badge"));
const seriesName = (id: string) => manifest.series.find((s) => s.id === id)?.name ?? id;

onMounted(refresh);

async function use(kind: "frame" | "badge", id: string) {
  const cur = kind === "frame" ? status.value?.frame : status.value?.badge;
  const next = cur === id ? "" : id; // click again to take off
  await chooseDecor({ [kind]: next });
  syncProfile({ [kind]: next });
}
</script>

<template>
  <div class="me">
    <div class="banner" :style="{ backgroundImage: skin.banner ? `url(${skin.banner})` : undefined }">
      <MemberAvatar :character="settings.character" :frame="status?.frame" :size="40" />
      <div class="who">
        <strong>{{ settings.nick || "匿名小面包" }}</strong>
        <small>{{ settings.character }}<template v-if="getDecor(status?.badge)"> · {{ getDecor(status?.badge)?.name }}</template></small>
      </div>
    </div>

    <div v-if="status" class="stats">
      <span><b>{{ status.totals.taps }}</b>点击</span>
      <span><b>{{ status.totals.activeMinutes }}</b>活跃分钟</span>
      <span><b>{{ status.totals.opened }}</b>已开箱</span>
      <span><b>{{ status.totals.owned }}</b>卡片</span>
    </div>
    <p v-else-if="!online" class="hint">服务器离线:连接后才能同步进度。</p>

    <h4>头像框</h4>
    <div class="decor">
      <button
        v-for="d in frames" :key="d.id" type="button" class="d" :class="{ on: status?.frame === d.id, off: !unlocked.has(d.id) }"
        :disabled="!unlocked.has(d.id)" :title="unlocked.has(d.id) ? d.name : `${d.name}:集齐「${seriesName(d.unlock.series)}」${d.unlock.min} 张卡解锁`"
        :aria-pressed="status?.frame === d.id" @click="use('frame', d.id)"
      ><img :src="url(d.img)" :alt="d.name" /></button>
    </div>
    <h4>徽章</h4>
    <div class="decor">
      <button
        v-for="d in badges" :key="d.id" type="button" class="d" :class="{ on: status?.badge === d.id, off: !unlocked.has(d.id) }"
        :disabled="!unlocked.has(d.id)" :title="unlocked.has(d.id) ? d.name : `${d.name}:获得「${seriesName(d.unlock.series)}」${d.unlock.min} 张卡解锁`"
        :aria-pressed="status?.badge === d.id" @click="use('badge', d.id)"
      ><img :src="url(d.img)" :alt="d.name" /></button>
    </div>

    <button class="toggle" :aria-expanded="showSettings" @click="showSettings = !showSettings">{{ showSettings ? "收起设置" : "设置" }}</button>
    <SettingsPanel v-show="showSettings" />
    <p class="hint credit">素材版权归 A-SOUL / 乐华娱乐及原作者所有,本项目为非商用粉丝作品,详见 ASSETS.md。</p>
  </div>
</template>

<style scoped>
.me { display: flex; flex-direction: column; gap: 6px; }
.banner { display: flex; align-items: center; gap: 8px; padding: 10px; border-radius: 12px; background: rgba(var(--accent-rgb), 0.18) center / cover; color: #222; min-height: 52px; }
.banner .who { display: flex; flex-direction: column; background: rgba(255, 255, 255, 0.65); padding: 2px 8px; border-radius: 8px; min-width: 0; }
.banner small { color: rgba(0, 0, 0, 0.6); }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; font-size: 10px; text-align: center; color: rgba(0, 0, 0, 0.55); }
.stats b { display: block; font-size: 14px; color: var(--accent); }
h4 { margin: 4px 0 0; font-size: 12px; color: rgba(0, 0, 0, 0.5); }
.decor { display: flex; flex-wrap: wrap; gap: 6px; }
.d { width: 46px; height: 46px; padding: 3px; border-radius: 10px; border: 2px solid transparent; background: rgba(255, 255, 255, 0.6); cursor: pointer; }
.d img { width: 100%; height: 100%; object-fit: contain; }
.d.off { cursor: not-allowed; } .d.off img { filter: grayscale(1) opacity(0.35); }
.d.on { border-color: var(--accent); }
.toggle { align-self: flex-start; }
.hint { font-size: 11px; color: rgba(0, 0, 0, 0.5); margin: 0; }
.credit { margin-top: 4px; }
</style>
