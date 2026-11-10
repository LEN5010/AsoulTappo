<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { MAX_ROOM_SIZE, toHttpBase, type Member } from "../net/protocol";
import { Api, type ServerInfo } from "../net/api";
import { accountLoginTrusted } from "../net/trust";
import { settings } from "../stores/settings";
import { activeAccount, saveCode } from "../stores/player";
import {
  canDuel, conn, createRoom, duelConfig, duelOn, inRoom, inviteDuel, isHost, joinRoom, kickMember, lastError, leaveRoom,
  loadPublicRooms, members, publicRooms, roomId, roomInfo, setRoomPublic, shownNick, youId,
} from "../stores/room";
import { tidyRemotes } from "../stores/desk";
import { characterColor } from "../manifest";
import { reducedMotion, skin } from "../stores/theme";
import CharacterAvatar from "../ui/CharacterAvatar.vue";
import Icon from "../ui/Icon.vue";
import HandImg from "../pet/HandImg.vue";
import Modal from "../ui/Modal.vue";
import StakeKeys from "../pet/StakeKeys.vue";
import RangeInput from "../ui/RangeInput.vue";
import RoomStage from "./RoomStage.vue";
import AccountDialog from "./AccountDialog.vue";

const input = ref(settings.lastRoom);
const busy = ref(false);
const notice = ref("");
const copied = ref(false);
const connText: Record<string, string> = {
  idle: "未加入",
  connecting: "连接中…",
  open: "已加入",
  reconnecting: "重连中…",
};

async function onCreate() {
  busy.value = true;
  notice.value = "";
  try {
    const id = await createRoom();
    input.value = id;
    joinRoom(id);
  } catch (e) {
    notice.value = `创建失败：${e instanceof Error ? e.message : e}`;
  } finally {
    busy.value = false;
  }
}
// The public list is read when the page opens, whenever the room is left and when the server changes.
const listing = ref(false);
async function refreshList() {
  listing.value = true;
  try {
    await loadPublicRooms();
  } finally {
    listing.value = false;
  }
}
watch(() => conn.value === "idle", (idle) => { if (idle) void refreshList(); }, { immediate: true });
watch(() => settings.serverUrl, () => { if (conn.value === "idle") void refreshList(); });
watch(() => activeAccount()?.token, () => { if (conn.value === "idle") void refreshList(); });

// A server with account login lists rooms only for signed-in accounts, and only their rooms go on the list.
const info = ref<ServerInfo | null>(null);
async function loadInfo() {
  const server = toHttpBase(settings.serverUrl);
  info.value = null;
  try {
    const result = await new Api(() => server, () => saveCode.value).info();
    if (server === toHttpBase(settings.serverUrl)) info.value = result;
  } catch { /* an older server without accounts */ }
}
void loadInfo();
watch(() => settings.serverUrl, loadInfo);
/** The account service to sign in with from this page; null when the server or the service is not trusted. */
const mainApi = computed(() => {
  const i = info.value;
  return i?.accountLogin && i.mainApi && accountLoginTrusted(toHttpBase(settings.serverUrl), i.mainApi) ? i.mainApi : null;
});
// A host without an account who took over a listed room still sees the switch, to take the room off the list.
const canPublish = computed(() => isHost.value && (!info.value?.accountLogin || !!activeAccount() || !!roomInfo.value?.public));
const signingIn = ref(false);
const listed = computed(() => (Array.isArray(publicRooms.value) ? publicRooms.value : null));

function joinListed(id: string) {
  input.value = id;
  joinRoom(id);
}
/** The switch follows the server: it moves once the room reports the change. */
function onPublic(e: Event) {
  const box = e.target as HTMLInputElement;
  const want = box.checked;
  box.checked = !!roomInfo.value?.public;
  setRoomPublic(want);
}
// Rock-paper-scissors: the member being invited while the bets are picked.
const picking = ref<Member | null>(null);
function invite(bet: number) {
  if (picking.value) inviteDuel(picking.value.id, bet);
  picking.value = null;
}
watch(inRoom, (v) => { if (!v) picking.value = null; });

async function copy() {
  try {
    await navigator.clipboard.writeText(roomId.value);
    copied.value = true;
    setTimeout(() => (copied.value = false), 1200);
  } catch {
    notice.value = "复制失败";
  }
}
</script>

<template>
  <div class="ui-sections">
    <div class="front">
      <RoomStage />

      <section class="ticket" data-rise>
        <div class="stub">
          <span class="ui-eyebrow">ROOM</span>
          <span class="status">
            <img
              v-if="(conn === 'connecting' || conn === 'reconnecting') && skin.loading && !reducedMotion"
              class="loading" :src="skin.loading" alt=""
            />
            <i v-else class="dot" :class="conn"></i>
            {{ connText[conn] }}
          </span>
        </div>
        <div v-if="conn === 'idle'" class="ticket-body">
          <input v-model="input" class="ui-input" maxlength="64" placeholder="房间号" aria-label="房间号" spellcheck="false" @keydown.enter="joinRoom(input)" />
          <button type="button" class="ui-btn" :disabled="!input.trim()" @click="joinRoom(input)">加入</button>
          <button type="button" class="ui-btn primary" :disabled="busy" @click="onCreate">
            <Icon name="plus" :size="15" />创建房间
          </button>
        </div>
        <div v-else class="ticket-body">
          <b class="code" :title="roomId">{{ roomId }}</b>
          <label v-if="canPublish" class="public">
            <span>公开</span>
            <input class="ui-switch" type="checkbox" :checked="roomInfo?.public" @change="onPublic" />
          </label>
          <button type="button" class="ui-btn" @click="copy">
            <Icon name="copy" :size="14" />{{ copied ? "已复制" : "复制" }}
          </button>
          <button type="button" class="ui-btn" @click="leaveRoom">
            <Icon name="logout" :size="14" />离开
          </button>
        </div>
      </section>
      <p v-if="lastError || notice" class="ui-error err" role="alert">{{ lastError || notice }}</p>
    </div>

    <section v-if="conn === 'idle' && publicRooms === 'signin' && mainApi" data-rise>
      <h4 class="ui-label"><span>公开房间</span></h4>
      <button type="button" class="ui-btn primary signin" @click="signingIn = true">
        <Icon name="lock" :size="14" />登录
      </button>
      <AccountDialog v-if="signingIn" :main-api="mainApi" start="login" @close="signingIn = false" @done="signingIn = false" />
    </section>
    <section v-else-if="conn === 'idle' && listed" data-rise>
      <header class="cap">
        <h4 class="ui-label"><span>公开房间</span></h4>
        <button type="button" class="ui-btn small" :disabled="listing" @click="refreshList">
          <Icon name="refresh" :size="13" />刷新
        </button>
      </header>
      <ul v-if="listed.length" class="members">
        <li v-for="r in listed" :key="r.room" class="member">
          <CharacterAvatar :character="r.host.character" :size="32" />
          <span class="who">
            <b>{{ shownNick(r.host) }}</b>
            <small>{{ r.members }} / {{ r.max }}</small>
          </span>
          <button type="button" class="ui-btn small" :disabled="r.members >= r.max" @click="joinListed(r.room)">加入</button>
        </li>
      </ul>
      <p v-else class="ui-empty">暂无</p>
    </section>

    <section data-rise>
      <h4 class="ui-label"><span>同桌显示</span></h4>
      <div class="ui-group ui-frame">
        <label class="ui-row">
          <span>伙伴桌宠大小</span>
          <span class="ui-ctl">
            <RangeInput v-model="settings.remoteScale" :min="0.4" :max="1.5" :step="0.1" />
            <b class="ui-val">×{{ settings.remoteScale.toFixed(1) }}</b>
          </span>
        </label>
        <label class="ui-row">
          <span>显示伙伴昵称</span>
          <input v-model="settings.showNames" class="ui-switch" type="checkbox" />
        </label>
      </div>
    </section>

    <section v-if="inRoom" data-rise>
      <header class="cap">
        <h4 class="ui-label"><span>房间成员</span><small>{{ members.size }} / {{ MAX_ROOM_SIZE }}</small></h4>
        <button type="button" class="ui-btn small" title="把大家的桌宠重新排到你的桌宠旁边" @click="tidyRemotes">
          <Icon name="refresh" :size="13" />整理位置
        </button>
      </header>
      <ul class="members">
        <li v-for="m in members.values()" :key="m.id" class="member">
          <CharacterAvatar :character="m.character" :size="32" />
          <span class="who">
            <b>
              {{ m.id === youId ? settings.nick.trim() || m.nick : shownNick(m) }}<em v-if="m.id === youId" class="ui-tag">我</em>
              <span v-if="roomInfo?.host === m.id" class="host" title="房主" aria-label="房主"><Icon name="crown" :size="14" /></span>
            </b>
            <small><i :style="{ background: characterColor(m.character) }" aria-hidden="true"></i>{{ m.character }}</small>
          </span>
          <span class="taps">{{ m.taps.toLocaleString("en-US") }}<small>敲击</small></span>
          <!-- Keys acting on one member. -->
          <span v-if="m.id !== youId && (isHost || duelOn)" class="acts">
            <button
              v-if="duelOn" type="button" class="ui-btn small" title="猜拳" aria-label="猜拳" :disabled="!canDuel(m)"
              @click="picking = m"
            >
              <HandImg name="scissors" :size="18" />
            </button>
            <button v-if="isHost" type="button" class="ui-btn small" title="移出房间" aria-label="移出房间" @click="kickMember(m.id)">
              <Icon name="close" :size="13" />
            </button>
          </span>
        </li>
      </ul>
    </section>

    <Modal v-if="picking && duelConfig" :title="`猜拳 ${shownNick(picking)}`" heading @close="picking = null">
      <StakeKeys class="picker" :disabled="!canDuel(picking)" @pick="invite" />
    </Modal>
  </div>
</template>

<style scoped>
.front {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* The room ticket: one sheet of paper, the connection on the left and the room on the right. */
.ticket {
  display: flex;
  align-items: stretch;
  min-height: 68px;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.stub {
  flex: none;
  width: 148px;
  padding: 12px 10px 12px 20px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
}
.stub .ui-eyebrow {
  font-size: 13px;
}
.status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 700;
  color: var(--ink-2);
}
/* The only place green and amber appear: whether the room connection is up. */
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--ink-3);
}
.dot.open {
  background: var(--ok);
}
.dot.connecting,
.dot.reconnecting {
  background: var(--warn);
}
.loading {
  width: 18px;
  height: 18px;
  object-fit: contain;
}
.ticket-body {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px 15px 6px;
}
.ticket-body .ui-input {
  flex: 1;
  min-width: 0;
  background: var(--c-100);
  box-shadow: none;
}
.ticket-body .ui-input:focus {
  box-shadow: 0 0 0 2px var(--ink);
}
.code {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 800 28px/1.1 var(--font-latin);
  letter-spacing: 0.04em;
  user-select: text;
}
.err {
  margin: 0;
}
.public {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--fs-label);
  font-weight: 800;
  color: var(--ink-2);
  cursor: pointer;
}

/* The heading on the left with its count, the tidy key on the right. */
.signin { min-width: 120px; }
.cap {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 10px;
}
.cap .ui-label {
  flex: 1;
  min-width: 0;
  margin: 0;
}
.cap .ui-btn {
  flex: none;
}
.members {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(212px, 1fr));
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.member {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 52px;
  padding: 8px 14px 8px 10px;
  box-sizing: border-box;
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.who {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.who b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--fs-body);
  font-weight: 800;
}
.who em {
  margin-left: 8px;
}
.who .host {
  display: inline-flex;
  margin-left: 6px;
  vertical-align: -2px;
  color: var(--c-700);
}
.who small {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-2);
}
.who small i {
  width: 4px;
  height: 10px;
}
.taps {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.taps small {
  font: 700 var(--fs-caption)/1.2 var(--font);
  color: var(--ink-3);
}
.acts {
  flex: none;
  display: flex;
  gap: 6px;
}
.acts .ui-btn {
  padding: 0 8px;
}
/* The same bets as over a partner's pet on the desk. */
.picker {
  max-width: 260px;
  margin: 0 auto;
}
</style>
