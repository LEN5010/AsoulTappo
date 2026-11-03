<script setup lang="ts">
import { ref, watch } from "vue";
import { characterNames } from "../characters";
import { settings } from "../stores/settings";
import { isTauri } from "../composables/tauri";

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
    <label>昵称
      <input v-model.trim="settings.nick" maxlength="24" placeholder="匿名小面包" />
    </label>
    <label>角色
      <select v-model="settings.character">
        <option v-for="n in characterNames" :key="n" :value="n">{{ n }}</option>
      </select>
    </label>
    <label>服务器地址
      <input v-model.trim="serverDraft" spellcheck="false" placeholder="http://localhost:8000" @keydown.enter="applyServer" />
      <button type="button" :disabled="serverDraft === settings.serverUrl" @click="applyServer">应用服务器</button>
      <small v-if="serverError" role="alert">{{ serverError }}</small>
    </label>
    <label>桌宠大小 ×{{ settings.scale.toFixed(1) }}
      <input v-model.number="settings.scale" type="range" min="0.5" max="2" step="0.1" />
    </label>
    <label class="check"><input v-model="settings.mouseFollow" type="checkbox" /> 鼠标层跟随光标</label>
    <label v-if="settings.mouseFollow">跟随灵敏度 {{ settings.mouseSensitivity.toFixed(2) }}
      <input v-model.number="settings.mouseSensitivity" type="range" min="0.1" max="1" step="0.05" />
    </label>
    <label>点击合并窗口 {{ settings.batchMs }}ms
      <input v-model.number="settings.batchMs" type="range" min="100" max="200" step="10" />
    </label>
    <template v-if="isTauri">
      <label class="check"><input v-model="settings.alwaysOnTop" type="checkbox" /> 窗口置顶</label>
      <label class="check"><input v-model="settings.clickThrough" type="checkbox" /> 点击穿透(开启后只能从托盘菜单恢复)</label>
    </template>
  </div>
</template>

<style scoped>
.settings { display: flex; flex-direction: column; gap: 8px; font-size: 12px; }
label { display: flex; flex-direction: column; gap: 3px; color: rgba(0, 0, 0, 0.65); }
label.check { flex-direction: row; align-items: center; gap: 6px; }
small { color: rgba(0, 0, 0, 0.45); }
.hint { color: rgba(0, 0, 0, 0.45); margin: 4px 0 0; }
</style>
