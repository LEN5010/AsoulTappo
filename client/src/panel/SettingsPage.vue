<script setup lang="ts">
import { ref, watch } from "vue";
import { settings } from "../stores/settings";
import { isTauri } from "../composables/tauri";
import { online, status } from "../stores/player";
import { counter } from "../stores/counter";

const emit = defineEmits<{ resetPet: [] }>();
const serverDraft = ref(settings.serverUrl);
const serverError = ref("");
watch(() => settings.serverUrl, (url) => { serverDraft.value = url; });

function applyServer() {
  try {
    const url = new URL(serverDraft.value.trim());
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new Error("invalid URL");
    }
    settings.serverUrl = url.toString().replace(/\/+$/, "");
    serverDraft.value = settings.serverUrl;
    serverError.value = "";
  } catch {
    serverError.value = "请输入 HTTP 或 HTTPS 服务器地址";
  }
}
</script>

<template>
  <div class="settings">
    <section class="ui-card">
      <h4>我</h4>
      <label class="row">
        <span>昵称</span>
        <input v-model.trim="settings.nick" class="ui-input" maxlength="24" placeholder="匿名小面包" />
      </label>
      <div class="stats">
        <span><b>{{ counter.total.toLocaleString("en-US") }}</b>本机累计敲击</span>
        <span><b>{{ status?.totals.activeMinutes ?? "-" }}</b>活跃分钟</span>
        <span><b>{{ status?.totals.opened ?? "-" }}</b>已开宝箱</span>
        <span><b>{{ status ? `${status.totals.owned}/${status.totals.items}` : "-" }}</b>收藏</span>
      </div>
    </section>

    <section class="ui-card">
      <h4>桌宠</h4>
      <label class="col">
        <span>大小 <b>×{{ settings.scale.toFixed(1) }}</b></span>
        <input v-model.number="settings.scale" class="ui-range" type="range" min="0.5" max="2" step="0.1" />
      </label>
      <label class="col">
        <span>表情停留 <b>{{ (settings.emoteHoldMs / 1000).toFixed(1) }} 秒</b></span>
        <input v-model.number="settings.emoteHoldMs" class="ui-range" type="range" min="1200" max="6000" step="100" />
      </label>
      <label class="row sw"><span>鼠标爪跟随光标</span><input v-model="settings.mouseFollow" class="ui-switch" type="checkbox" /></label>
      <label v-if="settings.mouseFollow" class="col">
        <span>跟随灵敏度 <b>{{ settings.mouseSensitivity.toFixed(2) }}</b></span>
        <input v-model.number="settings.mouseSensitivity" class="ui-range" type="range" min="0.1" max="1" step="0.05" />
      </label>
      <div class="row"><span>找不到桌宠了？</span><button type="button" class="ui-btn small" @click="emit('resetPet')">放回右下角</button></div>
    </section>

    <section v-if="isTauri" class="ui-card">
      <h4>窗口</h4>
      <label class="row sw"><span>桌宠置顶</span><input v-model="settings.alwaysOnTop" class="ui-switch" type="checkbox" /></label>
      <label class="row sw">
        <span>点击穿透<small class="ui-hint">开启后桌宠不再响应鼠标，只能从托盘菜单关闭</small></span>
        <input v-model="settings.clickThrough" class="ui-switch" type="checkbox" />
      </label>
    </section>

    <section class="ui-card">
      <h4>服务器 <span class="state" :class="{ ok: online }">{{ online ? "已连接" : "未连接" }}</span></h4>
      <div class="row">
        <input v-model.trim="serverDraft" class="ui-input grow" spellcheck="false" placeholder="http://localhost:8000" @keydown.enter="applyServer" />
        <button type="button" class="ui-btn" :disabled="serverDraft === settings.serverUrl" @click="applyServer">应用</button>
      </div>
      <small v-if="serverError" class="err" role="alert">{{ serverError }}</small>
      <label class="col">
        <span>点击合并窗口 <b>{{ settings.batchMs }}ms</b></span>
        <input v-model.number="settings.batchMs" class="ui-range" type="range" min="100" max="200" step="10" />
      </label>
    </section>

    <section class="ui-card about">
      <h4>关于</h4>
      <p>AsoulTappo 是非商业的粉丝作品。桌宠代码与素材源自 <b>Evelynall / ASoul-Little-Bun</b>（GPL-2.0），已获原作者许可。</p>
      <p>A-SOUL 角色、表情、装扮与卡牌素材的版权归各自权利人所有，仅限非商业使用。只上传敲击次数，从不上传按了哪个键。</p>
    </section>
  </div>
</template>

<style scoped>
.settings { display: flex; flex-direction: column; gap: 14px; }
section { padding: 14px 18px; display: flex; flex-direction: column; gap: 12px; }
h4 { margin: 0; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.state { font-size: 11px; padding: 1px 8px; border-radius: 999px; background: var(--paper-2); color: var(--ink-3); }
.state.ok { background: rgba(63, 182, 122, 0.15); color: var(--ok); }
.row { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-size: 13px; }
.row .ui-input { width: 240px; }
.row .grow { flex: 1; width: auto; }
.row span { display: flex; flex-direction: column; gap: 2px; }
.col { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; text-align: center; font-size: 11px; color: var(--ink-3); }
.stats b { display: block; font-size: 16px; color: var(--ink); font-variant-numeric: tabular-nums; }
.err { color: var(--bad); font-size: 12px; }
.about p { margin: 0; font-size: 12px; line-height: 1.7; color: var(--ink-2); }
</style>
