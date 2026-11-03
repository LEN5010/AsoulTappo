<script setup lang="ts">
import { watch } from "vue";
import { characterNames } from "../characters";
import { settings } from "../stores/settings";
import { setBatchMs, syncProfile } from "../stores/room";
import { isTauri } from "../composables/tauri";

watch(() => settings.character, (character) => syncProfile({ character }));
watch(() => settings.nick, (nick) => nick.trim() && syncProfile({ nick: nick.trim() }));
watch(() => settings.batchMs, (ms) => setBatchMs(ms));
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
      <input v-model.trim="settings.serverUrl" spellcheck="false" placeholder="http://localhost:8000" />
      <small>修改后重新加入房间生效</small>
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
    <p class="hint">隐私:仅上传点击次数,不上传按键内容。</p>
  </div>
</template>

<style scoped>
.settings { display: flex; flex-direction: column; gap: 8px; font-size: 12px; }
label { display: flex; flex-direction: column; gap: 3px; color: #555; }
label.check { flex-direction: row; align-items: center; gap: 6px; }
input:not([type="checkbox"]):not([type="range"]), select { padding: 5px 8px; border: 1px solid #ccc; border-radius: 6px; font-size: 12px; }
small { color: #999; }
.hint { color: #999; margin: 4px 0 0; }
</style>
