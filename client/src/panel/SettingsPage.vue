<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { getCharacter } from "../characters";
import { settings } from "../stores/settings";
import { adminStatus, exportLog, isTauri, openAboutLink, setRunAsAdmin, type AdminStatus } from "../composables/tauri";
import { status, saveCode, account, setAccount, refreshAccount } from "../stores/player";
import { Api, type ServerInfo } from "../net/api";
import { MainAccountApi } from "../net/mainAccount";
import { toHttpBase } from "../net/protocol";
import AccountDialog from "./AccountDialog.vue";
import Modal from "../ui/Modal.vue";
import { checkState, lookForUpdate, openUpdateDialog, updateOffer } from "../stores/update";
import { counter } from "../stores/counter";
import RangeInput from "../ui/RangeInput.vue";
import PetBust from "./PetBust.vue";

const emit = defineEmits<{ resetPet: [] }>();
const notice = ref("");

// The account row is always shown; signing in needs a server connected to the account service.
const info = ref<ServerInfo | null>(null);
async function loadInfo() {
  const server = toHttpBase(settings.serverUrl);
  info.value = null;
  try {
    const result = await new Api(() => server, () => saveCode.value).info();
    if (server === toHttpBase(settings.serverUrl)) info.value = result;
  } catch { /* offline: sign-in shows once the server answers */ }
}
onMounted(() => { void loadInfo(); void refreshAccount(); });
watch(() => settings.serverUrl, loadInfo);
const signedIn = computed(() => account.value && account.value.server === toHttpBase(settings.serverUrl) ? account.value : null);
const dialog = ref<"login" | "register" | null>(null);
function accountDone(message: string) {
  dialog.value = null;
  notice.value = message;
}
async function signOut() {
  const session = signedIn.value;
  if (!session) return;
  if (info.value?.mainApi) await new MainAccountApi(info.value.mainApi).revoke(session.token).catch(() => {});
  await setAccount(null);
  notice.value = "已退出登录";
}

const REPO = "https://github.com/LEN5010/AsoulTappo";
const SPACE = "https://space.bilibili.com/107261543";
const MAIL = "len5010@qq.com";
const contactOpen = ref(false);
const copied = ref(false);
async function copyMail() {
  try { await navigator.clipboard.writeText(MAIL); copied.value = true; } catch { openAboutLink(`mailto:${MAIL}`); }
}
const version = __APP_VERSION__;
const checkNote = computed(() => (checkState.value === "latest" ? "已是最新" : checkState.value === "failed" ? "检查失败" : ""));
const portrait = computed(() => getCharacter(settings.character)?.bg);

// Windows: start as administrator, so games run as administrator still reach the pet.
const admin = ref<AdminStatus | null>(null);
const adminBusy = ref(false);
const adminMsg = ref("");
onMounted(async () => { admin.value = await adminStatus(); });
const adminNote = computed(() => {
  if (adminMsg.value) return adminMsg.value;
  if (admin.value && !admin.value.canElevate && !admin.value.elevated) return "当前账户没有管理员权限，以管理员身份运行的游戏里收不到按键。";
  return "以管理员身份运行的游戏里，打开它才收得到按键。";
});
async function toggleAdmin(e: Event) {
  const input = e.target as HTMLInputElement;
  const want = input.checked;
  adminBusy.value = true;
  adminMsg.value = "";
  try {
    const result = await setRunAsAdmin(want);
    if (result === "restarting") adminMsg.value = "正在以管理员身份重启";
    else if (admin.value) {
      admin.value = { ...admin.value, runAsAdmin: want };
      if (!want && admin.value.elevated) adminMsg.value = "下次启动起按普通权限运行";
    }
  } catch (err) {
    input.checked = !want;
    adminMsg.value = String(err) === "cancelled" ? "已取消" : "没能切换";
  } finally {
    adminBusy.value = false;
  }
}

const logNote = ref("");
const exporting = ref(false);
async function exportLogFile() {
  exporting.value = true;
  logNote.value = "";
  try {
    logNote.value = (await exportLog()).desktop ? "已导出到桌面" : "已导出";
  } catch {
    logNote.value = "导出失败";
  } finally {
    exporting.value = false;
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
      <h4 class="ui-label"><span>账号</span></h4>
      <div class="ui-group ui-frame">
        <div class="ui-row">
          <span>Asasfans 账号</span>
          <span v-if="signedIn" class="who">
            <b>{{ signedIn.user.username }}</b>
            <small v-if="signedIn.user.email">{{ signedIn.user.email }}</small>
          </span>
          <span v-else class="who">
            <small>未登录</small>
            <small v-if="!info?.accountLogin">{{ info ? "当前服务器未开放账号登录" : "连接服务器后可登录" }}</small>
          </span>
          <span v-if="signedIn" class="acts"><button class="ui-btn" type="button" @click="signOut">退出登录</button></span>
          <span v-else-if="info?.accountLogin" class="acts">
            <button class="ui-btn primary" type="button" @click="dialog = 'login'">登录</button>
            <button class="ui-btn" type="button" @click="dialog = 'register'">注册</button>
          </span>
        </div>
        <p v-if="notice" role="status" class="note">{{ notice }}</p>
      </div>
      <AccountDialog v-if="dialog && info?.mainApi" :main-api="info.mainApi" :start="dialog" @close="dialog = null" @done="accountDone" />
    </section>

    <div class="columns">
      <div class="column">
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
            <label class="ui-row" :class="{ off: !settings.mouseFollow }">
              <span>跟随灵敏度</span>
              <span class="ui-ctl">
                <RangeInput v-model="settings.mouseSensitivity" :min="0.1" :max="1" :step="0.05" :disabled="!settings.mouseFollow" />
                <b class="ui-val">{{ settings.mouseSensitivity.toFixed(2) }}</b>
              </span>
            </label>
            <div class="ui-row">
              <span>桌宠位置</span>
              <button type="button" class="ui-btn small" @click="emit('resetPet')">放回右下角</button>
            </div>
            <label class="ui-row" :class="{ off: !settings.showNames }" :title="settings.showNames ? undefined : '联机页关闭了伙伴昵称，铭牌随昵称一起隐藏'">
              <span>显示伙伴铭牌</span>
              <input v-model="settings.showPlates" class="ui-switch" type="checkbox" :disabled="!settings.showNames" />
            </label>
            <label class="ui-row" title="伙伴昵称换成他们桌宠的成员名，直播时用">
              <span>隐藏伙伴 ID</span>
              <input v-model="settings.hideNicks" class="ui-switch" type="checkbox" />
            </label>
          </div>
        </section>
      </div>

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
            <label v-if="admin?.supported" class="ui-row">
              <span>以管理员身份启动</span>
              <input
                class="ui-switch" type="checkbox" :checked="admin.runAsAdmin"
                :disabled="adminBusy || (!admin.canElevate && !admin.elevated)" @change="toggleAdmin"
              />
            </label>
          </div>
          <p v-if="admin?.supported" class="note" role="status">{{ adminNote }}</p>
        </section>

        <section data-rise>
          <h4 class="ui-label"><span>声音</span></h4>
          <div class="ui-group ui-frame">
            <label class="ui-row">
              <span>播放卡面音频</span>
              <input v-model="settings.cardAudio" class="ui-switch" type="checkbox" />
            </label>
            <label class="ui-row">
              <span>界面音效</span>
              <input v-model="settings.sfx" class="ui-switch" type="checkbox" />
            </label>
          </div>
        </section>

        <section data-rise>
          <h4 class="ui-label"><span>关于</span></h4>
          <div class="ui-group ui-frame">
            <div class="ui-row">
              <span>版本</span>
              <span class="version-side">
                <small v-if="checkNote" role="status" class="check-note">{{ checkNote }}</small>
                <b class="version">{{ version }}</b>
                <button v-if="updateOffer" type="button" class="ui-btn small primary" @click="openUpdateDialog">更新</button>
                <button
                  v-else type="button" class="ui-btn small" :disabled="checkState === 'checking'"
                  @click="lookForUpdate(true)"
                >{{ checkState === "checking" ? "检查中" : "检查更新" }}</button>
              </span>
            </div>
            <div v-if="isTauri" class="ui-row">
              <span>运行日志</span>
              <span class="version-side">
                <small v-if="logNote" role="status" class="check-note">{{ logNote }}</small>
                <button type="button" class="ui-btn small" :disabled="exporting" @click="exportLogFile">导出</button>
              </span>
            </div>
            <div class="ui-row">
              <span>项目主页</span>
              <button type="button" class="ui-btn small" @click="openAboutLink(REPO)">GitHub</button>
            </div>
            <div class="ui-row">
              <span>作者</span>
              <button type="button" class="ui-btn small" @click="copied = false; contactOpen = true">联系作者</button>
            </div>
          </div>
        </section>
      </div>
    </div>

    <Modal v-if="contactOpen" title="联系作者" heading @close="contactOpen = false">
      <div class="contact">
        <button type="button" class="way ui-frame" @click="openAboutLink(SPACE)">
          <b>哔哩哔哩</b>
          <span>space.bilibili.com/107261543</span>
          <small>打开个人空间</small>
        </button>
        <button type="button" class="way ui-frame" @click="copyMail">
          <b>QQ 邮箱</b>
          <span>{{ MAIL }}</span>
          <small>{{ copied ? "已复制" : "点击复制" }}</small>
        </button>
      </div>
    </Modal>
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
  flex: none;
  display: flex;
  gap: 6px;
}
.who {
  flex: 1;
}
.version-side {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding-right: 4px;
}
.check-note {
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
  white-space: nowrap;
}
.version {
  flex: none;
  white-space: nowrap;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink-2);
}
.note {
  margin: 0;
  padding: 8px 14px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.contact {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  width: min(420px, 100%);
  margin: 0 auto;
  padding-bottom: 6px;
}
.way {
  --radius: var(--radius-key);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 16px;
  border: 0;
  background: var(--c-100);
  font: inherit;
  text-align: left;
  color: var(--ink);
  cursor: pointer;
  transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast);
}
.way:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 0 2px var(--c-500);
}
.way span {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 700 var(--fs-label)/1.2 var(--font-latin);
}
.way small {
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--c-700);
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
}
.column {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
/* The last group in each column grows so both columns end on the same line. */
.column > section:last-child {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.column > section:last-child > .ui-group {
  flex: 1;
}
.columns .ui-row.off > span:first-child {
  color: var(--ink-3);
}
.columns .ui-range:disabled,
.columns .ui-switch:disabled {
  opacity: 0.45;
  cursor: default;
}
.columns .ui-row {
  gap: 10px;
  min-height: 48px;
  padding: 6px 14px;
}
.columns .ui-ctl {
  width: 172px;
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
