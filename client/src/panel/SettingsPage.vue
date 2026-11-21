<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { getCharacter } from "../characters";
import { settings } from "../stores/settings";
import { adminStatus, autostartStatus, copyText, exportLog, isTauri, openAboutLink, setHotkey, setAutostart, setRunAsAdmin, type AdminStatus, type AutostartStatus, type HotkeySlot } from "../composables/tauri";
import { emoteKeysLabel, emoteModsOf, setEmoteKeys, shortcutLabel, shortcutOf } from "../desktop/bossKey";
import { status, saveCode, activeAccount, setAccount, refreshAccount } from "../stores/player";
import { Api, type ServerInfo } from "../net/api";
import { MainAccountApi } from "../net/mainAccount";
import { toHttpBase } from "../net/protocol";
import { accountLoginTrusted } from "../net/trust";
import AccountDialog from "./AccountDialog.vue";
import ReminderDialog from "./ReminderDialog.vue";
import Modal from "../ui/Modal.vue";
import { checkState, lookForUpdate, openUpdateDialog, updateOffer } from "../stores/update";
import { counter } from "../stores/counter";
import RangeInput from "../ui/RangeInput.vue";
import Icon from "../ui/Icon.vue";
import PetBust from "./PetBust.vue";
import AsasfansPromo from "./AsasfansPromo.vue";
import FeedbackDialog from "./FeedbackDialog.vue";
import LegalDoc from "./LegalDoc.vue";
import { DOC_TITLES, type DocName } from "../legal";
import { STANDALONE } from "../edition";

const emit = defineEmits<{ resetPet: [] }>();
const notice = ref("");

// The account row is always shown; signing in needs a server connected to the account service.
// A server or account service off the official origin looks like a server without account login.
const info = ref<ServerInfo | null>(null);
async function loadInfo() {
  const server = toHttpBase(settings.serverUrl);
  info.value = null;
  try {
    const result = await new Api(() => server, () => saveCode.value).info();
    if (server !== toHttpBase(settings.serverUrl)) return;
    info.value = accountLoginTrusted(server, result.mainApi) ? result : { ...result, accountLogin: false, mainApi: null };
  } catch { /* offline: sign-in shows once the server answers */ }
}
// The standalone edition has no account row and no server to ask.
onMounted(() => { if (!STANDALONE) { void loadInfo(); void refreshAccount(); } });
watch(() => settings.serverUrl, () => { if (!STANDALONE) void loadInfo(); });
const signedIn = computed(() => activeAccount());
const dialog = ref<"login" | "register" | null>(null);
function accountDone(message: string) {
  dialog.value = null;
  notice.value = message;
}
async function signOut() {
  const session = signedIn.value;
  if (!session) return;
  const mainApi = info.value?.mainApi;
  if (mainApi && accountLoginTrusted(session.server, mainApi)) await new MainAccountApi(mainApi).revoke(session.token).catch(() => {});
  await setAccount(null);
  notice.value = "已退出登录";
}

const REPO = "https://github.com/LEN5010/AsoulTappo";
const SPACE = "https://space.bilibili.com/107261543";
const MAIL = "len5010@qq.com";
const GROUP = "1106311431";
/** The standalone edition's sponsor row; the online edition has it in the promo dialog (AsasfansPromo.vue). Listed in ABOUT_LINKS. */
const SPONSOR = "https://len5010.me/sponsor/";
const contactOpen = ref(false);
const promoOpen = ref(false);
/** The health reminders' own dialog; the row's key says how many are on. */
const tipsOpen = ref(false);
const tipsLabel = computed(() => {
  if (!settings.healthTips) return "已关闭";
  const on = settings.reminders.filter((r) => r.on).length + [settings.tipGreet, settings.tipLunch, settings.tipNight].filter(Boolean).length;
  return `开启 ${on} 项`;
});
function openPromo() {
  promoOpen.value = true;
  settings.promoSeen = true;
}
/** The legal text open for reading again. */
const legalOpen = ref<DocName | null>(null);
/** Which contact was just copied. */
const copied = ref<"" | "mail" | "group">("");
async function copyMail() {
  try { await copyText(MAIL); copied.value = "mail"; } catch { openAboutLink(`mailto:${MAIL}`); }
}
async function copyGroup() {
  try { await copyText(GROUP); copied.value = "group"; } catch { /* the number stays on screen */ }
}
const version = __APP_VERSION__;
const checkNote = computed(() => (checkState.value === "latest" ? "已是最新" : checkState.value === "failed" ? "检查失败" : ""));
const portrait = computed(() => getCharacter(settings.character)?.bg);

// The hide key, the click-through key and the monitor key: a key waits for the next shortcut pressed; Escape leaves it
// as it was.
const IS_MAC = /Mac/i.test(navigator.userAgent);
const HOTKEYS: { slot: HotkeySlot; label: string; key: "bossKey" | "clickThroughKey" | "monitorKey" }[] = [
  { slot: "click-through", label: "点击穿透热键", key: "clickThroughKey" },
  { slot: "hide", label: "隐藏热键", key: "bossKey" },
  { slot: "next-monitor", label: "切换屏幕热键", key: "monitorKey" },
];
// The emote keys are one row: a press on any digit gives their modifiers, and 1 to 8 follow.
const recording = ref<HotkeySlot | "emotes" | null>(null);
const keyNote = ref<Partial<Record<HotkeySlot | "emotes", string>>>({});
const refusal = (e: unknown) => (String(e) === "taken" ? "和另一个热键重复" : "无法使用");
async function saveKey(slot: HotkeySlot, keys: string) {
  recording.value = null;
  const key = HOTKEYS.find((h) => h.slot === slot)!.key;
  try {
    await setHotkey(slot, keys);
    settings[key] = keys;
    keyNote.value = { ...keyNote.value, [slot]: "" };
  } catch (e) {
    keyNote.value = { ...keyNote.value, [slot]: refusal(e) };
    await setHotkey(slot, settings[key]).catch(() => {});
  }
}
async function saveEmoteKey(mods: string) {
  recording.value = null;
  try {
    await setEmoteKeys(mods, setHotkey);
    settings.emoteKey = mods;
    keyNote.value = { ...keyNote.value, emotes: "" };
  } catch (e) {
    keyNote.value = { ...keyNote.value, emotes: refusal(e) };
    await setEmoteKeys(settings.emoteKey, setHotkey).catch(() => {});
  }
}
function onRecordKey(e: KeyboardEvent) {
  e.preventDefault();
  e.stopPropagation();
  const slot = recording.value;
  if (!slot) return;
  if (e.code === "Escape") { recording.value = null; return; }
  if (slot === "emotes") {
    const mods = emoteModsOf(e);
    if (mods) void saveEmoteKey(mods);
    return;
  }
  const keys = shortcutOf(e);
  if (keys) void saveKey(slot, keys);
}
watch(recording, (slot) => {
  window.removeEventListener("keydown", onRecordKey, true);
  if (slot) { keyNote.value = { ...keyNote.value, [slot]: "" }; window.addEventListener("keydown", onRecordKey, true); }
});

// Every row is one height and a group's title with the gap above it takes one row's height too, so the rows of the two
// columns line up, and the groups that start level (窗口设置 and 关于, each under eight rows) keep their titles on one
// line. A setting that only matters with a switch on sits in that switch's row. The columns end where their rows do:
// the right one a few rows sooner. The tomato timer's lengths and switches live on its own page.
type Group = "pet" | "window" | "online" | "sound" | "about";
// The standalone edition has no online group.
const COLUMNS: Group[][] = STANDALONE ? [["pet", "window"], ["sound", "about"]] : [["pet", "window"], ["online", "sound", "about"]];
onBeforeUnmount(() => window.removeEventListener("keydown", onRecordKey, true));

// Start at login. The system holds the state; a failed change shows what the system says now.
const autostart = ref<AutostartStatus | null>(null);
const autostartBusy = ref(false);
const refreshAutostart = async () => { autostart.value = await autostartStatus(); };
// Also read back when the panel comes to the front, after a change in System Settings or Task Manager.
onMounted(() => { void refreshAutostart(); window.addEventListener("focus", refreshAutostart); });
onBeforeUnmount(() => window.removeEventListener("focus", refreshAutostart));
async function toggleAutostart(e: Event) {
  const input = e.target as HTMLInputElement;
  autostartBusy.value = true;
  try {
    autostart.value = await setAutostart(input.checked);
  } catch {
    await refreshAutostart();
    input.checked = autostart.value?.enabled ?? false;
  } finally {
    autostartBusy.value = false;
  }
}

// Windows: start as administrator, so games run as administrator still reach the pet.
const admin = ref<AdminStatus | null>(null);
const adminBusy = ref(false);
onMounted(async () => { admin.value = await adminStatus(); });
// No note under the switch: a cancelled or failed change just flips it back.
async function toggleAdmin(e: Event) {
  const input = e.target as HTMLInputElement;
  const want = input.checked;
  adminBusy.value = true;
  try {
    const result = await setRunAsAdmin(want);
    if (result !== "restarting" && admin.value) admin.value = { ...admin.value, runAsAdmin: want };
  } catch {
    input.checked = !want;
  } finally {
    adminBusy.value = false;
  }
}

/** The feedback dialog, and the row's word once one was sent. */
const feedbackOpen = ref(false);
const feedbackNote = ref("");
function feedbackSent() {
  feedbackOpen.value = false;
  feedbackNote.value = "已发送";
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
        <!-- The standalone edition counts taps on this device only; the rest is the server's. -->
        <span v-if="STANDALONE"><b>{{ counter.today.toLocaleString("en-US") }}</b>今日敲击</span>
        <template v-else>
          <span><b>{{ status?.totals.activeMinutes ?? "-" }}</b>活跃分钟</span>
          <span><b>{{ status?.resonance.total ?? "-" }}</b>已共鸣</span>
          <span><b>{{ status ? `${status.totals.owned}/${status.totals.items}` : "-" }}</b>收集进度</span>
        </template>
      </div>
    </section>

    <section v-if="!STANDALONE" data-rise>
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
      <div v-for="(column, ci) in COLUMNS" :key="ci" class="column">
        <template v-for="group in column" :key="group">
          <section v-if="group === 'pet'" data-rise>
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
              <div class="ui-row">
                <label for="set-follow">鼠标爪跟随光标</label>
                <span class="version-side">
                  <span v-if="settings.mouseFollow" class="ui-ctl beside-switch" title="跟随灵敏度">
                    <RangeInput v-model="settings.mouseSensitivity" :min="0.1" :max="1" :step="0.05" aria-label="跟随灵敏度" />
                    <b class="ui-val">{{ settings.mouseSensitivity.toFixed(2) }}</b>
                  </span>
                  <input id="set-follow" v-model="settings.mouseFollow" class="ui-switch" type="checkbox" />
                </span>
              </div>
              <div class="ui-row">
                <span>桌宠位置</span>
                <button type="button" class="ui-btn small" @click="emit('resetPet')">放回右下角</button>
              </div>
              <label class="ui-row">
                <span>收起任务栏</span>
                <input v-model="settings.barFolded" class="ui-switch" type="checkbox" />
              </label>
              <label v-if="!STANDALONE" class="ui-row">
                <span>显示敲击碎片</span>
                <input v-model="settings.shardPop" class="ui-switch" type="checkbox" />
              </label>
              <div class="ui-row">
                <span>健康提醒</span>
                <button type="button" class="ui-btn small" @click="tipsOpen = true">{{ tipsLabel }}</button>
              </div>
            </div>
          </section>

          <section v-else-if="group === 'window'" data-rise>
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
              <div v-for="h in HOTKEYS" :key="h.slot" class="ui-row">
                <span>{{ h.label }}</span>
                <span class="version-side">
                  <small v-if="keyNote[h.slot]" role="status" class="check-note">{{ keyNote[h.slot] }}</small>
                  <button v-if="settings[h.key] && recording !== h.slot" type="button" class="ui-btn small" @click="saveKey(h.slot, '')">清除</button>
                  <button
                    type="button" class="ui-btn small" :class="{ primary: recording === h.slot }"
                    @click="recording = recording === h.slot ? null : h.slot"
                  >
                    {{ recording === h.slot ? "按下组合键" : settings[h.key] ? shortcutLabel(settings[h.key], IS_MAC) : "未设置" }}
                  </button>
                </span>
              </div>
              <div class="ui-row">
                <span>表情热键</span>
                <span class="version-side">
                  <small v-if="keyNote.emotes" role="status" class="check-note">{{ keyNote.emotes }}</small>
                  <button v-if="settings.emoteKey && recording !== 'emotes'" type="button" class="ui-btn small" @click="saveEmoteKey('')">清除</button>
                  <button
                    type="button" class="ui-btn small" :class="{ primary: recording === 'emotes' }"
                    @click="recording = recording === 'emotes' ? null : 'emotes'"
                  >
                    {{ recording === "emotes" ? "按下组合键加数字" : settings.emoteKey ? emoteKeysLabel(settings.emoteKey, IS_MAC) : "未设置" }}
                  </button>
                </span>
              </div>
              <div class="ui-row">
                <label for="set-capture">采集窗口</label>
                <span class="version-side">
                  <input v-if="settings.captureOpen" v-model="settings.captureBg" class="swatch" type="color" title="采集背景色" aria-label="采集背景色" />
                  <input id="set-capture" v-model="settings.captureOpen" class="ui-switch" type="checkbox" />
                </span>
              </div>
              <label v-if="autostart?.supported" class="ui-row">
                <span>开机自启动</span>
                <span class="version-side">
                  <small v-if="autostart.needsMove" class="check-note">先移到应用程序文件夹</small>
                  <input
                    class="ui-switch" type="checkbox" :checked="autostart.enabled"
                    :disabled="autostartBusy || (autostart.needsMove && !autostart.enabled)" @change="toggleAutostart"
                  />
                </span>
              </label>
              <label v-if="admin?.supported" class="ui-row">
                <span>以管理员身份启动</span>
                <input
                  class="ui-switch" type="checkbox" :checked="admin.runAsAdmin"
                  :disabled="adminBusy || (!admin.canElevate && !admin.elevated)" @change="toggleAdmin"
                />
              </label>
            </div>
          </section>

          <section v-else-if="group === 'online'" data-rise>
            <h4 class="ui-label"><span>联机</span></h4>
            <div class="ui-group ui-frame">
              <label class="ui-row" :class="{ off: !settings.showNames }" :title="settings.showNames ? undefined : '联机页的伙伴名字设为不显示，铭牌一起隐藏'">
                <span>显示伙伴铭牌</span>
                <input v-model="settings.showPlates" class="ui-switch" type="checkbox" :disabled="!settings.showNames" />
              </label>
              <label class="ui-row">
                <span>猜拳免打扰</span>
                <input v-model="settings.duelDnd" class="ui-switch" type="checkbox" />
              </label>
              <label class="ui-row">
                <span>上收藏榜</span>
                <input v-model="settings.onBoard" class="ui-switch" type="checkbox" />
              </label>
            </div>
          </section>

          <section v-else-if="group === 'sound'" data-rise>
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
              <label class="ui-row">
                <span>音量</span>
                <span class="ui-ctl">
                  <RangeInput v-model="settings.volume" :min="0" :max="1" :step="0.05" />
                  <b class="ui-val">{{ Math.round(settings.volume * 100) }}%</b>
                </span>
              </label>
            </div>
          </section>

          <section v-else data-rise>
            <h4 class="ui-label"><span>关于</span></h4>
            <div class="ui-group ui-frame">
              <div class="ui-row">
                <span>版本</span>
                <span class="version-side">
                  <small v-if="checkNote && !STANDALONE" role="status" class="check-note">{{ checkNote }}</small>
                  <b class="version">{{ version }}<template v-if="STANDALONE"> 单机版</template></b>
                  <template v-if="!STANDALONE">
                    <button v-if="updateOffer" type="button" class="ui-btn small about-key primary" @click="openUpdateDialog">更新</button>
                    <button
                      v-else type="button" class="ui-btn small about-key" :disabled="checkState === 'checking'"
                      @click="lookForUpdate(true)"
                    >{{ checkState === "checking" ? "检查中" : "检查更新" }}</button>
                  </template>
                </span>
              </div>
              <div v-if="isTauri" class="ui-row">
                <span>运行日志</span>
                <span class="version-side">
                  <small v-if="logNote" role="status" class="check-note">{{ logNote }}</small>
                  <button type="button" class="ui-btn small about-key" :disabled="exporting" @click="exportLogFile">导出</button>
                </span>
              </div>
              <div v-if="!STANDALONE" class="ui-row">
                <span>意见反馈</span>
                <span class="version-side">
                  <small v-if="feedbackNote" role="status" class="check-note">{{ feedbackNote }}</small>
                  <button type="button" class="ui-btn small about-key" @click="feedbackNote = ''; feedbackOpen = true">写反馈</button>
                </span>
              </div>
              <div class="ui-row">
                <span>项目主页</span>
                <button type="button" class="ui-btn small about-key" @click="openAboutLink(REPO)">GitHub</button>
              </div>
              <div v-if="!STANDALONE" class="ui-row">
                <span>协议与隐私</span>
                <span class="version-side">
                  <button type="button" class="ui-btn small about-key" @click="legalOpen = 'terms'">用户协议</button>
                  <button type="button" class="ui-btn small about-key" @click="legalOpen = 'privacy'">隐私政策</button>
                </span>
              </div>
              <div class="ui-row">
                <span>作者</span>
                <button type="button" class="ui-btn small about-key" @click="copied = ''; contactOpen = true">联系作者</button>
              </div>
              <div v-if="STANDALONE" class="ui-row">
                <span>赞助</span>
                <button type="button" class="ui-btn small" @click="openAboutLink(SPONSOR)">支持</button>
              </div>
              <div v-else class="ui-row promo-row">
                <span>神秘按钮</span>
                <button
                  type="button" class="ui-btn small about-key primary promo-key" :class="{ wiggle: !settings.promoSeen }"
                  @click="openPromo"
                >
                  <Icon name="spark" :size="15" /><span>点我试试</span>
                </button>
              </div>
            </div>
          </section>
        </template>
      </div>
    </div>

    <Modal v-if="legalOpen" :title="DOC_TITLES[legalOpen]" heading wide @close="legalOpen = null">
      <LegalDoc :doc="legalOpen" />
    </Modal>
    <ReminderDialog v-if="tipsOpen" @close="tipsOpen = false" />
    <FeedbackDialog v-if="feedbackOpen" @close="feedbackOpen = false" @sent="feedbackSent" />
    <Modal v-if="promoOpen" title="Asasfans" heading @close="promoOpen = false">
      <AsasfansPromo />
    </Modal>
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
          <small>{{ copied === "mail" ? "已复制" : "点击复制" }}</small>
        </button>
        <button type="button" class="way wide ui-frame" @click="copyGroup">
          <b>QQ 群</b>
          <span>{{ GROUP }}</span>
          <small>{{ copied === "group" ? "已复制" : "点击复制" }}</small>
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
/* The mystery key's row: a faint coral wash sets it apart from the white rows. */
.ui-row.promo-row {
  background: var(--c-50);
}
/* Until it has been opened once, the sparkle twinkles every 8 seconds: it swells with a quarter turn and settles. */
.promo-key.wiggle .icon {
  animation: twinkle 8s ease-in-out 2s infinite;
}
@keyframes twinkle {
  0%, 10%, 100% { scale: 1; rotate: 0deg; }
  3% { scale: 1.35; rotate: 45deg; }
  6% { scale: 0.85; rotate: 80deg; }
  8% { scale: 1.05; rotate: 90deg; }
}
/* Every key in 关于 is as wide as the mystery key (its sparkle and four characters), so their left edges line up. */
.about-key {
  min-width: calc(4em + 45px);
}
.version-side {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
}
/* The colour itself, the size of a switch. */
.swatch {
  appearance: none;
  flex: none;
  width: 42px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 12px;
  background: none;
  overflow: hidden;
  cursor: pointer;
  box-shadow: 0 0 0 2px var(--c-200);
}
.swatch::-webkit-color-swatch-wrapper {
  padding: 0;
}
.swatch::-webkit-color-swatch {
  border: 0;
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
.way.wide {
  grid-column: 1 / -1;
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
/* Both columns end level: the last group of each reaches the column's foot. The rows each platform shows differ
   (start at login and the run log on the desktop, run as administrator on Windows only), so the shorter column's last
   group keeps blank space under its rows. */
.column > section:last-child {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.column > section:last-child > .ui-group {
  flex: 1;
}
/* One grid for both columns: rows are 48px, and a title (24px line, 10px under it) with the 14px gap above it is 48px
   as well, so every row of one column sits level with a row of the other. */
.column > section > .ui-label {
  line-height: 24px;
}
.columns .ui-group > .ui-row {
  height: 48px;
}
.columns .ui-row.off > span:first-child {
  color: var(--ink-3);
}
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
/* A slider with a switch after it: narrower by the switch and the gap, so it starts where the other sliders do. */
.columns .ui-ctl.beside-switch {
  width: calc(172px - 42px - 10px);
  gap: 8px;
}
.columns .ui-ctl.beside-switch .ui-val {
  width: 34px;
}
/* A row's name stays on one line. */
.columns .ui-row > span:first-child,
.columns .ui-row > label:first-child {
  flex: none;
  white-space: nowrap;
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
