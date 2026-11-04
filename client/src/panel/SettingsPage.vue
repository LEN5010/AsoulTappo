<script setup lang="ts">
import { ref, watch } from "vue";
import { settings } from "../stores/settings";
import { isTauri } from "../composables/tauri";
import { online, status } from "../stores/player";
import { counter } from "../stores/counter";
import RangeInput from "../ui/RangeInput.vue";

const emit = defineEmits<{ resetPet: [] }>();
const serverDraft = ref(settings.serverUrl);
const serverError = ref("");
watch(
  () => settings.serverUrl,
  (url) => {
    serverDraft.value = url;
  },
);

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
    serverError.value = "请输入有效的 HTTP 或 HTTPS 地址";
  }
}
</script>

<template>
  <div class="settings">
    <section data-rise>
      <h4 class="ui-label">个人资料</h4>
      <div class="group ui-frame ui-ring">
        <label class="row">
          <span>昵称</span>
          <input v-model.trim="settings.nick" class="ui-input ctl" maxlength="24" placeholder="匿名小面包" />
        </label>
        <div class="stats">
          <span><b>{{ counter.total.toLocaleString("en-US") }}</b>累计敲击</span>
          <span><b>{{ status?.totals.activeMinutes ?? "-" }}</b>活跃分钟</span>
          <span><b>{{ status?.totals.opened ?? "-" }}</b>已开宝箱</span>
          <span><b>{{ status ? `${status.totals.owned}/${status.totals.items}` : "-" }}</b>收集进度</span>
        </div>
      </div>
    </section>

    <section data-rise>
      <h4 class="ui-label">桌宠表现</h4>
      <div class="group ui-frame ui-ring">
        <label class="row">
          <span>桌宠大小</span>
          <span class="ctl">
            <RangeInput v-model="settings.scale" :min="0.5" :max="2" :step="0.1" />
            <b class="val">×{{ settings.scale.toFixed(1) }}</b>
          </span>
        </label>
        <label class="row">
          <span>表情停留时间</span>
          <span class="ctl">
            <RangeInput v-model="settings.emoteHoldMs" :min="1200" :max="6000" :step="100" />
            <b class="val">{{ (settings.emoteHoldMs / 1000).toFixed(1) }} 秒</b>
          </span>
        </label>
        <label class="row">
          <span>鼠标爪跟随光标</span>
          <input v-model="settings.mouseFollow" class="ui-switch" type="checkbox" />
        </label>
        <label v-if="settings.mouseFollow" class="row">
          <span>跟随灵敏度</span>
          <span class="ctl">
            <RangeInput v-model="settings.mouseSensitivity" :min="0.1" :max="1" :step="0.05" />
            <b class="val">{{ settings.mouseSensitivity.toFixed(2) }}</b>
          </span>
        </label>
        <div class="row">
          <span>桌宠位置</span>
          <button type="button" class="ui-btn small" @click="emit('resetPet')">放回右下角</button>
        </div>
      </div>
    </section>

    <section v-if="isTauri" data-rise>
      <h4 class="ui-label">窗口设置</h4>
      <div class="group ui-frame ui-ring">
        <label class="row">
          <span>桌宠置顶</span>
          <input v-model="settings.alwaysOnTop" class="ui-switch" type="checkbox" />
        </label>
        <label class="row">
          <span>点击穿透</span>
          <input v-model="settings.clickThrough" class="ui-switch" type="checkbox" />
        </label>
      </div>
    </section>

    <section data-rise>
      <h4 class="ui-label">服务器连接</h4>
      <div class="group ui-frame ui-ring">
        <div class="row">
          <span class="state" :class="{ ok: online }"><i></i>{{ online ? "已连接" : "未连接" }}</span>
          <span class="ctl wide">
            <input v-model.trim="serverDraft" class="ui-input" spellcheck="false" placeholder="http://localhost:8000" @keydown.enter="applyServer" />
            <button type="button" class="ui-btn" :disabled="serverDraft === settings.serverUrl" @click="applyServer">应用</button>
          </span>
        </div>
        <p v-if="serverError" class="ui-error err" role="alert">{{ serverError }}</p>
        <label class="row">
          <span>敲击同步间隔</span>
          <span class="ctl">
            <RangeInput v-model="settings.batchMs" :min="100" :max="200" :step="10" />
            <b class="val">{{ settings.batchMs }}ms</b>
          </span>
        </label>
      </div>
    </section>
  </div>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.group {
  --cut: 16px;
  background: var(--surface);
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 48px;
  padding: 8px 18px;
  box-sizing: border-box;
  font-size: 13px;
  font-weight: 700;
}
.group > * + * {
  border-top: 1.5px solid var(--line);
}
.ctl {
  width: 280px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
}
.ctl.wide {
  width: auto;
  flex: 1;
  max-width: 400px;
}
.ctl.wide .ui-input {
  flex: 1;
}
.val {
  width: 52px;
  flex: none;
  text-align: right;
  font: italic 800 16px/1 var(--font-latin);
  color: var(--ink-2);
}
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
}
.stats span {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 18px 12px;
  font-size: 12px;
  font-weight: 700;
  color: var(--ink-3);
}
.stats span + span {
  border-left: 1.5px solid var(--line);
}
.stats b {
  font: italic 800 30px/1 var(--font-latin);
  color: var(--accent-deep);
}
.state {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ink-2);
  font-weight: 800;
}
.state i {
  width: 8px;
  height: 14px;
  background: var(--ink-3);
  transform: skewX(var(--skew));
}
.state.ok i {
  background: var(--ok);
}
.err {
  margin: 0;
  padding: 8px 18px;
}
</style>
