<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { getCharacter } from "../characters";
import { settings } from "../stores/settings";
import { isTauri } from "../composables/tauri";
import { online, status, saveCode, restoreSaveCode } from "../stores/player";
import { counter } from "../stores/counter";
import RangeInput from "../ui/RangeInput.vue";
import PetBust from "./PetBust.vue";

const emit = defineEmits<{ resetPet: [] }>();
const serverDraft = ref(settings.serverUrl);
const serverError = ref("");
const saveDraft = ref("");
const saveNotice = ref("");
async function copySave() {
  try { await navigator.clipboard.writeText(saveCode.value); saveNotice.value = "存档码已复制"; }
  catch { saveNotice.value = "复制失败，请手动复制存档码"; }
}
async function restoreSave() {
  try { await restoreSaveCode(saveDraft.value); saveDraft.value = ""; saveNotice.value = "已切换存档"; }
  catch (error) { saveNotice.value = error instanceof Error ? error.message : "切换存档失败"; }
}
const portrait = computed(() => getCharacter(settings.character)?.bg);
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
    <section class="profile ui-frame" data-rise>
      <span class="portrait" aria-hidden="true"><PetBust v-if="portrait" class="bust" :src="portrait" /></span>
      <label class="nick">
        <span>昵称</span>
        <input v-model.trim="settings.nick" class="ui-input" maxlength="24" placeholder="匿名小面包" />
      </label>
      <div class="stats">
        <span><b>{{ counter.total.toLocaleString("en-US") }}</b>累计敲击</span>
        <span><b>{{ status?.totals.activeMinutes ?? "-" }}</b>活跃分钟</span>
        <span><b>{{ status?.resonance.total ?? "-" }}</b>已共鸣</span>
        <span><b>{{ status ? `${status.totals.owned}/${status.totals.items}` : "-" }}</b>收集进度</span>
      </div>
    </section>

    <section data-rise>
      <h4 class="ui-label"><span>存档</span></h4>
      <div class="ui-group ui-frame">
        <div class="ui-row"><span>当前存档码</span><input class="ui-input" readonly :value="saveCode" aria-label="当前存档码" /><button class="ui-btn" type="button" @click="copySave">复制</button></div>
        <form class="ui-row" @submit.prevent="restoreSave"><input v-model="saveDraft" class="ui-input" placeholder="粘贴存档码" aria-label="导入存档码" maxlength="128" /><button class="ui-btn" type="submit" :disabled="!saveDraft.trim()">切换存档</button></form>
        <p v-if="saveNotice" role="status" class="err">{{ saveNotice }}</p>
      </div>
    </section>

    <div class="columns">
      <section data-rise>
        <h4 class="ui-label"><span>桌宠表现</span></h4>
        <div class="ui-group ui-frame">
          <label class="ui-row">
            <span>桌宠大小</span>
            <span class="ui-ctl">
              <RangeInput v-model="settings.scale" :min="0.5" :max="2" :step="0.1" />
              <b class="ui-val">×{{ settings.scale.toFixed(1) }}</b>
            </span>
          </label>
          <label class="ui-row">
            <span>表情停留时间</span>
            <span class="ui-ctl">
              <RangeInput v-model="settings.emoteHoldMs" :min="1200" :max="6000" :step="100" />
              <b class="ui-val">{{ (settings.emoteHoldMs / 1000).toFixed(1) }} 秒</b>
            </span>
          </label>
          <label class="ui-row">
            <span>鼠标爪跟随光标</span>
            <input v-model="settings.mouseFollow" class="ui-switch" type="checkbox" />
          </label>
          <label v-if="settings.mouseFollow" class="ui-row">
            <span>跟随灵敏度</span>
            <span class="ui-ctl">
              <RangeInput v-model="settings.mouseSensitivity" :min="0.1" :max="1" :step="0.05" />
              <b class="ui-val">{{ settings.mouseSensitivity.toFixed(2) }}</b>
            </span>
          </label>
          <div class="ui-row">
            <span>桌宠位置</span>
            <button type="button" class="ui-btn small" @click="emit('resetPet')">放回右下角</button>
          </div>
        </div>
      </section>

      <div class="column">
        <section v-if="isTauri" data-rise>
          <h4 class="ui-label"><span>窗口设置</span></h4>
          <div class="ui-group ui-frame">
            <label class="ui-row">
              <span>桌宠置顶</span>
              <input v-model="settings.alwaysOnTop" class="ui-switch" type="checkbox" />
            </label>
            <label class="ui-row">
              <span>点击穿透</span>
              <input v-model="settings.clickThrough" class="ui-switch" type="checkbox" />
            </label>
          </div>
        </section>

        <section data-rise>
          <h4 class="ui-label"><span>服务器连接</span></h4>
          <div class="ui-group ui-frame">
            <div class="ui-row">
              <span class="state" :class="{ ok: online }"><i></i>{{ online ? "已连接" : "未连接" }}</span>
              <span class="ui-ctl wide">
                <input v-model.trim="serverDraft" class="ui-input" spellcheck="false" placeholder="http://121.36.224.230:8000" @keydown.enter="applyServer" />
                <button type="button" class="ui-btn" :disabled="serverDraft === settings.serverUrl" @click="applyServer">应用</button>
              </span>
            </div>
            <p v-if="serverError" class="ui-error err" role="alert">{{ serverError }}</p>
            <label class="ui-row">
              <span>敲击同步间隔</span>
              <span class="ui-ctl">
                <RangeInput v-model="settings.batchMs" :min="100" :max="200" :step="10" />
                <b class="ui-val">{{ settings.batchMs }}ms</b>
              </span>
            </label>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.settings > * {
  flex: none;
}

.profile {
  --radius: var(--radius-l);
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 92px;
  padding: 0 8px 0 12px;
  box-sizing: border-box;
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
/* The current pet rises from a coral disc cut off by the card's bottom edge. */
.portrait {
  position: relative;
  flex: none;
  align-self: flex-end;
  width: 112px;
  height: 84px;
}
.portrait::before {
  content: "";
  position: absolute;
  left: 50%;
  bottom: -34px;
  width: 104px;
  aspect-ratio: 1;
  border-radius: 50%;
  transform: translateX(-50%);
  background: var(--c-500);
}
.bust {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  filter: var(--sticker);
}
.nick {
  flex: 0 1 196px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.nick .ui-input {
  width: 100%;
  height: 34px;
  box-sizing: border-box;
  font: 800 var(--fs-number)/1 var(--font);
}
.stats {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.stats span {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 2px 8px 2px 14px;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-3);
  white-space: nowrap;
}
.stats b {
  overflow: hidden;
  text-overflow: ellipsis;
  font: 800 var(--fs-heading)/1 var(--font-latin);
  color: var(--ink);
}

.columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: start;
}
.column {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.columns .ui-row {
  gap: 10px;
  min-height: 48px;
  padding: 6px 14px;
}
.columns .ui-ctl {
  width: 172px;
}
.columns .ui-ctl.wide {
  width: auto;
  flex: 1;
  min-width: 0;
  gap: 6px;
}
.wide .ui-input {
  flex: 1;
  min-width: 0;
}
.state {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--ink-2);
  font-weight: 800;
}
.state i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ink-3);
}
.state.ok i {
  background: var(--ok);
}
.err {
  margin: 0;
  padding: 8px 14px;
}

@container panel (max-width: 860px) {
  .columns {
    grid-template-columns: minmax(0, 1fr);
  }
  .profile {
    flex-wrap: wrap;
    gap: 0 12px;
    padding-top: 10px;
  }
  .portrait {
    align-self: flex-start;
    width: 76px;
    height: 58px;
  }
  .portrait::before {
    bottom: -8px;
    width: 72px;
  }
  .nick {
    flex: 1;
  }
  .stats {
    flex: 0 0 100%;
    margin: 8px 0 10px;
  }
}
</style>
