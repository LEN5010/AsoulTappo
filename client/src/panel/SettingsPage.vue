<script setup lang="ts">
import { ref, watch } from "vue";
import { settings } from "../stores/settings";
import { isTauri } from "../composables/tauri";
import { online, status } from "../stores/player";
import { counter } from "../stores/counter";
import { manifest } from "../manifest";
import CharacterAvatar from "../ui/CharacterAvatar.vue";
import RangeInput from "../ui/RangeInput.vue";

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
    <section>
      <h4 class="ui-label">我</h4>
      <div class="group">
        <label class="row">
          <span>昵称</span>
          <input v-model.trim="settings.nick" class="ui-input ctl" maxlength="24" placeholder="匿名小面包" />
        </label>
        <div class="stats">
          <span><b>{{ counter.total.toLocaleString("en-US") }}</b>本机累计敲击</span>
          <span><b>{{ status?.totals.activeMinutes ?? "-" }}</b>活跃分钟</span>
          <span><b>{{ status?.totals.opened ?? "-" }}</b>已开宝箱</span>
          <span><b>{{ status ? `${status.totals.owned}/${status.totals.items}` : "-" }}</b>收藏</span>
        </div>
      </div>
    </section>

    <section>
      <h4 class="ui-label">桌宠</h4>
      <div class="characters"><button v-for="c in manifest.characters" :key="c.name" :class="{ on: settings.character === c.name }" @click="settings.character = c.name"><CharacterAvatar :character="c.name" :size="52" /><span>{{ c.name }}</span></button></div>
      <div class="group">
        <label class="row">
          <span>大小</span>
          <span class="ctl"><RangeInput v-model="settings.scale" :min="0.5" :max="2" :step="0.1" /><b class="val">×{{ settings.scale.toFixed(1) }}</b></span>
        </label>
        <label class="row">
          <span>表情停留</span>
          <span class="ctl"><RangeInput v-model="settings.emoteHoldMs" :min="1200" :max="6000" :step="100" /><b class="val">{{ (settings.emoteHoldMs / 1000).toFixed(1) }} 秒</b></span>
        </label>
        <label class="row"><span>鼠标爪跟随光标</span><input v-model="settings.mouseFollow" class="ui-switch" type="checkbox" /></label>
        <label v-if="settings.mouseFollow" class="row">
          <span>跟随灵敏度</span>
          <span class="ctl"><RangeInput v-model="settings.mouseSensitivity" :min="0.1" :max="1" :step="0.05" /><b class="val">{{ settings.mouseSensitivity.toFixed(2) }}</b></span>
        </label>
        <div class="row"><span>桌宠位置</span><button type="button" class="ui-btn small" @click="emit('resetPet')">放回右下角</button></div>
      </div>
    </section>

    <section v-if="isTauri">
      <h4 class="ui-label">窗口</h4>
      <div class="group">
        <label class="row"><span>桌宠置顶</span><input v-model="settings.alwaysOnTop" class="ui-switch" type="checkbox" /></label>
        <label class="row">
          <span class="two">点击穿透<small>关闭请用托盘菜单</small></span>
          <input v-model="settings.clickThrough" class="ui-switch" type="checkbox" />
        </label>
      </div>
    </section>

    <section>
      <h4 class="ui-label">服务器</h4>
      <div class="group">
        <div class="row">
          <span class="state" :class="{ ok: online }"><i></i>{{ online ? "已连接" : "未连接" }}</span>
          <span class="ctl wide">
            <input v-model.trim="serverDraft" class="ui-input" spellcheck="false" placeholder="http://localhost:8000" @keydown.enter="applyServer" />
            <button type="button" class="ui-btn" :disabled="serverDraft === settings.serverUrl" @click="applyServer">应用</button>
          </span>
        </div>
        <p v-if="serverError" class="err" role="alert">{{ serverError }}</p>
        <label class="row">
          <span>点击合并窗口</span>
          <span class="ctl"><RangeInput v-model="settings.batchMs" :min="100" :max="200" :step="10" /><b class="val">{{ settings.batchMs }}ms</b></span>
        </label>
      </div>
    </section>

    <section>
      <h4 class="ui-label">关于</h4>
      <p class="about">参考原项目 <b>Evelynall / ASoul-Little-Bun</b>（GPL-2.0），感谢原作者。</p>
    </section>
  </div>
</template>

<style scoped>
.characters { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }.characters button { display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 80px; padding: 10px; background: #fff; border: 1px solid var(--line); border-radius: 6px; cursor: pointer; color: var(--ink-2); font: 12px var(--font); }.characters button.on { background: #fff5ed; border-color: var(--accent); color: #985431; }
.settings { display: flex; flex-direction: column; gap: 20px; }
.group { background: #fff; border: 1px solid var(--line); border-radius: var(--r-l); }
.row { display: flex; align-items: center; justify-content: space-between; gap: 16px; min-height: 44px; padding: 6px 14px; box-sizing: border-box; font-size: 13px; }
.group > * + * { border-top: 1px solid var(--line); }
.ctl { width: 280px; flex: none; display: flex; align-items: center; gap: 10px; }
.ctl.wide { width: auto; flex: 1; max-width: 400px; }
.ctl.wide .ui-input { flex: 1; }
.val { width: 48px; flex: none; text-align: right; font-size: 12px; font-weight: 600; color: var(--ink-2); font-variant-numeric: tabular-nums; }
.two { display: flex; flex-direction: column; gap: 2px; }
.two small { font-size: 12px; color: var(--ink-3); }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); }
.stats span { display: flex; flex-direction: column; gap: 2px; padding: 10px 14px; font-size: 12px; color: var(--ink-3); }
.stats span + span { border-left: 1px solid var(--line); }
.stats b { font-size: 17px; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }
.state { display: inline-flex; align-items: center; gap: 6px; color: var(--ink-2); }
.state i { width: 7px; height: 7px; border-radius: 50%; background: var(--ink-3); }
.state.ok i { background: var(--ok); }
.err { margin: 0; padding: 8px 14px; color: var(--bad); font-size: 12px; }
.about { margin: 0; font-size: 12px; line-height: 1.7; color: var(--ink-2); }
</style>
