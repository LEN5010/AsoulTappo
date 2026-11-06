<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { getCharacter } from "../characters";
import { settings } from "../stores/settings";
import { isTauri } from "../composables/tauri";
import { online, status, saveCode, restoreSaveCode, account, setAccount } from "../stores/player";
import { Api, type ServerInfo } from "../net/api";
import { MainAccountApi } from "../net/mainAccount";
import { toHttpBase } from "../net/protocol";
import AccountDialog from "./AccountDialog.vue";
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
// Main-site account: offered when the selected server is linked to the main site.
const info = ref<ServerInfo | null>(null);
async function loadInfo() {
  const server = toHttpBase(settings.serverUrl);
  info.value = null;
  try {
    const result = await new Api(() => server, () => saveCode.value).info();
    if (server === toHttpBase(settings.serverUrl)) info.value = result;
  } catch { /* offline or an older server: guest saves only */ }
}
onMounted(loadInfo);
watch(() => settings.serverUrl, loadInfo);
const signedIn = computed(() => account.value && account.value.server === toHttpBase(settings.serverUrl) ? account.value : null);
const dialog = ref<"login" | "register" | null>(null);
function accountDone(message: string) {
  dialog.value = null;
  saveNotice.value = message;
}
async function signOut() {
  const session = signedIn.value;
  if (!session) return;
  if (info.value?.mainApi) await new MainAccountApi(info.value.mainApi).revoke(session.token).catch(() => {});
  await setAccount(null);
  saveNotice.value = "已退出登录，现在使用这台设备的游客存档";
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
      <div class="ui-group ui-frame saves">
        <div v-if="info?.accountLogin" class="ui-row">
          <span>主站账号</span>
          <div v-if="signedIn" class="who">
            <b>{{ signedIn.user.username }}</b>
            <small v-if="signedIn.user.email">{{ signedIn.user.email }}</small>
          </div>
          <div v-else class="who"><small>未登录</small></div>
          <span v-if="signedIn" class="acts"><button class="ui-btn" type="button" @click="signOut">退出登录</button></span>
          <span v-else class="acts">
            <button class="ui-btn primary" type="button" @click="dialog = 'login'">登录</button>
            <button class="ui-btn" type="button" @click="dialog = 'register'">注册</button>
          </span>
        </div>
        <template v-if="!signedIn">
        <div class="ui-row">
          <span>当前存档码</span>
          <div class="ui-input save-read" role="textbox" aria-readonly="true" aria-label="当前存档码">{{ saveCode }}</div>
          <button class="ui-btn" type="button" @click="copySave">复制</button>
        </div>
        <form class="ui-row" @submit.prevent="restoreSave">
          <span>切换存档码</span>
          <input v-model="saveDraft" class="ui-input" placeholder="粘贴存档码" aria-label="导入存档码" maxlength="128" />
          <button class="ui-btn" type="submit" :disabled="!saveDraft.trim()">切换存档</button>
        </form>
        </template>
        <p v-if="saveNotice" role="status" class="err">{{ saveNotice }}</p>
      </div>
      <AccountDialog v-if="dialog && info?.mainApi" :main-api="info.mainApi" :start="dialog" @close="dialog = null" @done="accountDone" />
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
/* Both code fields share one column. A bare input stays 20 characters wide and clips the token. */
.saves {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
}
.saves > .ui-row {
  display: grid;
  grid-template-columns: subgrid;
  grid-column: 1 / -1;
  align-items: center;
  column-gap: 16px;
}
.saves > .err {
  grid-column: 1 / -1;
}
.saves .ui-input {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
}
.who {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.who b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.who small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.acts {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}
.save-read {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  overflow-x: auto;
  white-space: nowrap;
  font-weight: 700;
  text-align: left;
  user-select: text;
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
  /* 104px disc, 10% larger, grown from the same center (was bottom: -34px). */
  bottom: calc(-34px - 104px * 0.05);
  width: calc(104px * 1.1);
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
  transform: translateX(4px);
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
    bottom: calc(-8px - 72px * 0.05);
    width: calc(72px * 1.1);
  }
  .bust {
    transform: translateX(3px);
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
