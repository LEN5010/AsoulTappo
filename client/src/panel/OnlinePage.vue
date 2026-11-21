<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { MAX_ROOM_SIZE, ROOM_NAME_MAX, toHttpBase, type Member, type PublicRoom } from "../net/protocol";
import { Api, type ServerInfo } from "../net/api";
import { accountLoginTrusted } from "../net/trust";
import { partnerNames, setPartnerNames, settings, type PartnerNames } from "../stores/settings";
import { activeAccount, saveCode, status } from "../stores/player";
import {
  betsNeedAccount, canDuel, cheer, cheerDone, cheerOn, conn, createRoom, duelConfig, duelOn, inRoom, inviteDuel, isHost, joinRoom, kickMember,
  lastError, leaveRoom, loadPublicRooms, members, nameOn, publicRooms, roomId, roomInfo, setRoomName, setRoomPublic, shownNick,
  youId,
} from "../stores/room";
import { tidyRemotes } from "../stores/desk";
import { copyText } from "../composables/tauri";
import { characterColor, skinTitle } from "../manifest";
import { reducedMotion, skin } from "../stores/theme";
import CharacterAvatar from "../ui/CharacterAvatar.vue";
import Icon from "../ui/Icon.vue";
import HandImg from "../pet/HandImg.vue";
import Modal from "../ui/Modal.vue";
import StakeKeys from "../pet/StakeKeys.vue";
import RangeInput from "../ui/RangeInput.vue";
import StatusKeys from "../ui/StatusKeys.vue";
import { roomStatus } from "../roomStatus";
import RoomStage from "./RoomStage.vue";
import ProfileDialog from "./ProfileDialog.vue";
import { ui } from "../stores/ui";
import AccountDialog from "./AccountDialog.vue";
import PublicRoomList from "./PublicRoomList.vue";
import RecentRoomList from "./RecentRoomList.vue";
import { dropRoom } from "../recentRooms";
import SegTabs from "../ui/SegTabs.vue";
import { ddzCanWatch, ddzLive, ddzOn, ddzPlaying, ddzQueueOn, ddzWatchSeat, watchDdz } from "../stores/ddz";
import DdzBanner from "./ddz/DdzBanner.vue";

const input = ref(settings.lastRoom);
/** The own status keys: none, then the list. */
// The own status: one row that unfolds the status keys under it.
const myStatus = computed(() => roomStatus(settings.status));
const statusOpen = ref(false);
function pickStatus(id: string) {
  settings.status = id;
  statusOpen.value = false;
}
function closeStatus(e: Event) {
  if (e instanceof KeyboardEvent ? e.key === "Escape" : !(e.target as HTMLElement | null)?.closest?.(".status-pick, .status-keys")) {
    statusOpen.value = false;
  }
}
onMounted(() => {
  window.addEventListener("pointerdown", closeStatus, true);
  window.addEventListener("keydown", closeStatus);
});
onBeforeUnmount(() => {
  window.removeEventListener("pointerdown", closeStatus, true);
  window.removeEventListener("keydown", closeStatus);
});
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
watch(() => settings.serverUrl, () => { if (conn.value === "idle" || roomsOpen.value) void refreshList(); });
watch(() => activeAccount()?.token, () => { if (conn.value === "idle" || roomsOpen.value) void refreshList(); });

// In a room the public list opens in a dialog from the ticket; joining another room there asks first, then switches
// rooms directly. One dialog at a time: the question takes the list's place, and signing in closes it.
const roomsOpen = ref(false);
const switchTo = ref<PublicRoom | null>(null);
/** The sign-in dialog was opened from the room list, which comes back once signed in. */
let listAfterSignin = false;
function openRooms() {
  switchTo.value = null;
  roomsOpen.value = true;
  void refreshList();
}
function closeRooms() {
  roomsOpen.value = false;
  switchTo.value = null;
}
function signinFromRooms() {
  closeRooms();
  listAfterSignin = true;
  signingIn.value = true;
}
function cancelSignin() {
  signingIn.value = false;
  listAfterSignin = false;
}
function signedIn() {
  signingIn.value = false;
  if (listAfterSignin && conn.value !== "idle") openRooms();
  listAfterSignin = false;
}
function switchRoom() {
  const target = switchTo.value;
  closeRooms();
  if (target) joinListed(target.room);
}
watch(() => conn.value === "idle", (idle) => { if (idle) closeRooms(); });

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
/** Bets need an account here and none is signed in: the duel and dou dizhu keys say so. */
const needAccount = computed(() => betsNeedAccount(info.value?.accountLogin));
// A host without an account who took over a listed room still sees the switch, to take the room off the list.
const canPublish = computed(() => isHost.value && (!info.value?.accountLogin || !!activeAccount() || !!roomInfo.value?.public));
const signingIn = ref(false);
const LAYOUTS = [
  { id: "free" as const, label: "自由" }, { id: "row" as const, label: "一排" }, { id: "formation" as const, label: "方阵" },
];
const NAMES: { id: PartnerNames; label: string }[] = [{ id: "nick", label: "昵称" }, { id: "member", label: "成员名" }, { id: "off", label: "不显示" }];
const names = computed({ get: () => partnerNames(settings), set: (v: PartnerNames) => setPartnerNames(settings, v) });
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
/** The partner whose profile is on screen; the own seat opens the 排行 page instead. */
const profileOf = ref<string | null>(null);
function openProfile(id: string | null) {
  if (id) profileOf.value = id;
  else ui.page = "cheer";
}
/** A partner's pet asked for its profile (`profile:<member id>`, src/pet/duelPick.ts). */
function openTarget(target: string) {
  if (!target.startsWith("profile:")) return;
  ui.craftTarget = "";
  profileOf.value = target.slice(8) || null;
}
openTarget(ui.craftTarget);
watch(() => ui.craftTarget, openTarget, { flush: "post" });
function invite(bet: number) {
  if (picking.value) inviteDuel(picking.value.id, bet);
  picking.value = null;
}
// 合力应援 tells as much as it can without words. The bar is one cell per cheering save (the target grows by a cell
// each), filled one cell after another, in the style of the pity bars. The faces before it are the saves cheering:
// the own one first, grey until its taps go on the bar, then the others, and an empty ring for each that left but
// still counts. The prize at the end is what each gets when the bar is full, or that today's cheer is used up; a
// full bar flashes as the pets show their shards. Words are left for what holds the bar up: too few taps in all to
// take part, or too few saves in the room. The progress is in numbers by the title; who put in how much is on the
// faces.
const cheerCells = computed(() => {
  const c = cheer.value;
  if (!c) return [];
  const cells = Math.max(2, c.count);
  const per = c.target / cells;
  return Array.from({ length: cells }, (_, i) => Math.min(1, Math.max(0, (c.total - i * per) / per)));
});
const cheerFaces = computed(() => {
  const c = cheer.value;
  const me = members.get(youId.value) ?? null;
  if (!c) return { me, on: false, others: [] as Member[], gone: 0 };
  // A share goes on the bar once it reaches minShare (server/app/rooms.py). Two seats of one save show one face.
  const on = (c.shares[youId.value] ?? 0) >= c.minShare;
  const seen = new Set([me?.uid ?? youId.value]);
  const others: Member[] = [];
  for (const m of members.values()) {
    const key = m.uid ?? m.id;
    if (m.id === youId.value || seen.has(key) || (c.shares[m.id] ?? 0) < c.minShare) continue;
    seen.add(key);
    others.push(m);
  }
  return { me, on, others, gone: Math.max(0, c.count - others.length - (on ? 1 : 0)) };
});
const cheerCapped = computed(() => {
  const own = status.value?.cheer;
  return !!own && own.got >= own.cap;
});
const cheerNote = computed(() => {
  const own = status.value?.cheer;
  if (own && (status.value?.totals.taps ?? 0) < own.minTaps) {
    const need = own.minTaps % 10000 === 0 ? `${own.minTaps / 10000} 万` : own.minTaps.toLocaleString("en-US");
    return `累计敲击满 ${need} 下后加入应援`;
  }
  if ([...members.values()].filter((m) => m.uid).length < 2) return "两位有存档的伙伴在房间里时开始累计";
  return "";
});
const cheerFlash = ref(false);
let flashTimer: ReturnType<typeof setTimeout> | undefined;
watch(() => cheerDone.value?.round, (round) => {
  if (!round) return;
  cheerFlash.value = true;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => (cheerFlash.value = false), 1200);
});
/** A face's tooltip: whose it is and the taps it put in this round. */
const faceTitle = (m: Member) =>
  `${m.id === youId.value ? "我" : shownNick(m)} ${(cheer.value?.shares[m.id] ?? 0).toLocaleString("en-US")}`;

// Removing a member asks first; the question goes away with the member or the room.
/** The game member [m] plays in the room, when this client can watch it. */
const gameOf = (m: Member) => (ddzCanWatch.value ? Object.keys(ddzLive.value).find((id) => ddzLive.value[id]!.includes(m.id)) : undefined);
/** Watch member [m]'s game from its seat. */
function watchMember(m: Member) {
  const table = gameOf(m);
  if (table) watchDdz(table, ddzWatchSeat(table, m.id));
}

const kicking = ref<Member | null>(null);
function kick() {
  if (kicking.value) kickMember(kicking.value.id);
  kicking.value = null;
}
watch(inRoom, (v) => { if (!v) { picking.value = null; kicking.value = null; } });
watch(() => kicking.value && !members.has(kicking.value.id), (gone) => { if (gone) kicking.value = null; });

// The room's name: big on the ticket with the room id under it. Hidden nicknames hide room names too: both are what
// players typed.
const roomName = computed(() => (settings.hideNicks ? "" : roomInfo.value?.name ?? ""));
const canName = computed(() => isHost.value && nameOn.value);
const naming = ref(false);
const nameDraft = ref("");
const nameBox = ref<HTMLInputElement>();
async function startNaming() {
  nameDraft.value = roomInfo.value?.name ?? "";
  naming.value = true;
  await nextTick();
  nameBox.value?.select();
}
/** Enter or leaving the box sends the name; Escape drops it. */
function saveName() {
  if (!naming.value) return;
  naming.value = false;
  const name = nameDraft.value.trim();
  if (name !== (roomInfo.value?.name ?? "")) setRoomName(name);
}
watch(canName, (can) => { if (!can) naming.value = false; });

async function copy() {
  try {
    await copyText(roomId.value);
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
      <RoomStage @profile="openProfile" />

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
          <input
            v-if="naming" ref="nameBox" v-model="nameDraft" class="ui-input" :maxlength="ROOM_NAME_MAX" placeholder="房间名"
            aria-label="房间名" spellcheck="false" @keydown.enter="saveName" @keydown.esc="naming = false" @blur="saveName"
          />
          <div v-else class="room-id">
            <b v-if="roomName" class="name" :title="roomName">{{ roomName }}</b>
            <b class="code" :class="{ under: !!roomName }" :title="roomId">{{ roomId }}</b>
          </div>
          <button v-if="canName && !naming" type="button" class="ui-btn small ghost rename" aria-label="房间名" title="房间名" @click="startNaming">
            <Icon name="pencil" :size="15" />
          </button>
          <label v-if="canPublish" class="public">
            <span>公开</span>
            <input class="ui-switch" type="checkbox" :checked="roomInfo?.public" @change="onPublic" />
          </label>
          <button type="button" class="ui-btn small ghost rooms-key" aria-label="公开房间" title="公开房间" @click="openRooms">
            <Icon name="search" :size="15" />
          </button>
          <button type="button" class="ui-btn" @click="copy">
            <Icon name="copy" :size="14" />{{ copied ? "已复制" : "复制" }}
          </button>
          <button type="button" class="ui-btn" @click="leaveRoom">
            <Icon name="logout" :size="14" />离开
          </button>
        </div>
      </section>
      <p v-if="lastError || notice" class="ui-error err" role="alert">{{ lastError || notice }}</p>
      <DdzBanner v-if="ddzOn || ddzQueueOn" :need-account="needAccount" />
    </div>

    <section v-if="conn === 'idle' && settings.recentRooms.length" data-rise>
      <h4 class="ui-label"><span>加入过</span></h4>
      <RecentRoomList
        :rooms="settings.recentRooms" @join="(id) => { input = id; joinRoom(id); }"
        @forget="(id) => (settings.recentRooms = dropRoom(settings.recentRooms, id))"
      />
    </section>

    <section v-if="conn === 'idle' && publicRooms === 'signin' && mainApi" data-rise>
      <h4 class="ui-label"><span>公开房间</span></h4>
      <button type="button" class="ui-btn primary signin" @click="signingIn = true">
        <Icon name="lock" :size="14" />登录
      </button>
    </section>
    <section v-else-if="conn === 'idle' && listed" data-rise>
      <header class="cap">
        <h4 class="ui-label"><span>公开房间</span></h4>
        <button type="button" class="ui-btn small" :disabled="listing" @click="refreshList">
          <Icon name="refresh" :size="13" />刷新
        </button>
      </header>
      <PublicRoomList :rooms="listed" @join="(r) => joinListed(r.room)" />
    </section>

    <section data-rise>
      <h4 class="ui-label"><span>同桌显示</span></h4>
      <div class="ui-group ui-frame">
        <div class="ui-row">
          <span>我的状态</span>
          <button type="button" class="ui-btn small status-pick" :aria-expanded="statusOpen" @click="statusOpen = !statusOpen">
            <Icon :name="myStatus?.icon ?? 'off'" :size="15" />
            <span class="label">{{ myStatus?.label ?? "不显示" }}</span>
            <Icon class="chev" name="down" :size="14" />
          </button>
        </div>
        <div v-if="statusOpen" class="status-keys">
          <StatusKeys row :model-value="settings.status" @update:model-value="pickStatus" />
        </div>
        <label class="ui-row">
          <span>显示伙伴桌宠</span>
          <input v-model="settings.showPartners" class="ui-switch" type="checkbox" />
        </label>
        <label class="ui-row">
          <span>伙伴桌宠大小</span>
          <span class="ui-ctl">
            <RangeInput v-model="settings.remoteScale" :min="0.4" :max="1.5" :step="0.1" />
            <b class="ui-val">×{{ settings.remoteScale.toFixed(1) }}</b>
          </span>
        </label>
        <div class="ui-row">
          <span>排列</span>
          <SegTabs v-model="settings.partnerLayout" :tabs="LAYOUTS" label="排列" />
        </div>
        <label v-if="settings.partnerLayout === 'formation'" class="ui-row">
          <span>列数</span>
          <span class="ui-ctl">
            <RangeInput v-model="settings.formationCols" :min="1" :max="10" :step="1" />
            <b class="ui-val">{{ settings.formationCols }}</b>
          </span>
        </label>
        <div class="ui-row">
          <span>伙伴名字</span>
          <SegTabs v-model="names" :tabs="NAMES" label="伙伴名字" />
        </div>
      </div>
    </section>

    <section v-if="inRoom && cheerOn && cheer" data-rise>
      <h4 class="ui-label">
        <span>合力应援</span><small>{{ cheer.total.toLocaleString("en-US") }} / {{ cheer.target.toLocaleString("en-US") }}</small>
      </h4>
      <div class="cheer ui-frame">
        <div class="cheer-track">
          <span class="cheer-faces">
            <CharacterAvatar
              v-if="cheerFaces.me" :character="cheerFaces.me.character" :size="26" class="me" :class="{ off: !cheerFaces.on }"
              :title="faceTitle(cheerFaces.me)"
            />
            <CharacterAvatar
              v-for="m in cheerFaces.others" :key="m.id" :character="m.character" :size="26" :title="faceTitle(m)"
            />
            <i v-for="n in cheerFaces.gone" :key="`gone-${n}`" class="gone" aria-hidden="true"></i>
          </span>
          <span
            class="cheer-bar" :class="{ flash: cheerFlash }" role="progressbar" aria-label="合力应援"
            :aria-valuenow="cheer.total" :aria-valuemax="cheer.target"
          >
            <span v-for="(fill, i) in cheerCells" :key="i" class="ui-bar"><i :style="{ width: `${fill * 100}%` }"></i></span>
          </span>
          <span class="cheer-prize" :class="{ off: cheerCapped }">
            <template v-if="cheerCapped">今日已满</template>
            <template v-else><Icon name="shard" :size="18" />+{{ cheer.reward }}</template>
          </span>
        </div>
        <p v-if="cheerNote" class="cheer-note">{{ cheerNote }}</p>
      </div>
    </section>

    <section v-if="inRoom" data-rise>
      <header class="cap">
        <h4 class="ui-label"><span>房间成员</span><small>{{ members.size }} / {{ MAX_ROOM_SIZE }}</small></h4>
        <button type="button" class="ui-btn small" @click="tidyRemotes">
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
              <em v-if="ddzPlaying.has(m.id)" class="ui-tag at-table">牌局中</em>
            </b>
            <small>
              <i :style="{ background: characterColor(m.character) }" aria-hidden="true"></i>{{ skinTitle(m.character) }}
              <span v-if="roomStatus(m.status)" class="status"><Icon :name="roomStatus(m.status)!.icon" :size="12" />{{ roomStatus(m.status)!.label }}</span>
            </small>
          </span>
          <span class="taps">{{ m.taps.toLocaleString("en-US") }}<small>敲击</small></span>
          <!-- Keys acting on one member. -->
          <span v-if="m.id !== youId && (isHost || duelOn || gameOf(m))" class="acts">
            <button v-if="gameOf(m)" type="button" class="ui-btn small" title="观战" aria-label="观战" @click="watchMember(m)">
              <Icon name="eye" :size="16" />
            </button>
            <button
              v-if="duelOn" type="button" class="ui-btn small" title="猜拳" aria-label="猜拳" :disabled="!canDuel(m)"
              @click="picking = m"
            >
              <HandImg name="scissors" :size="18" />
            </button>
            <button v-if="isHost" type="button" class="ui-btn small" title="移出房间" aria-label="移出房间" @click="kicking = m">
              <Icon name="close" :size="13" />
            </button>
          </span>
        </li>
      </ul>
    </section>

    <ProfileDialog v-if="profileOf" :id="profileOf" :key="profileOf" @close="profileOf = null" />
    <AccountDialog v-if="signingIn && mainApi" :main-api="mainApi" start="login" @close="cancelSignin" @done="signedIn" />
    <Modal v-if="roomsOpen && switchTo" title="离开当前房间并加入？" heading @close="closeRooms">
      <div class="confirm">
        <button type="button" class="ui-btn" @click="switchTo = null">取消</button>
        <button type="button" class="ui-btn primary" @click="switchRoom">加入</button>
      </div>
    </Modal>
    <Modal v-else-if="roomsOpen" title="公开房间" heading wide @close="closeRooms">
      <template v-if="publicRooms === 'signin'">
        <button v-if="mainApi" type="button" class="ui-btn primary signin" @click="signinFromRooms">
          <Icon name="lock" :size="14" />登录
        </button>
        <p v-else class="ui-empty">暂无</p>
      </template>
      <template v-else>
        <div class="list-keys">
          <button type="button" class="ui-btn small" :disabled="listing" @click="refreshList">
            <Icon name="refresh" :size="13" />刷新
          </button>
        </div>
        <PublicRoomList :rooms="listed ?? []" :current="roomId" @join="(r) => (switchTo = r)" />
      </template>
    </Modal>
    <Modal v-if="kicking" :title="`把${shownNick(kicking)}移出房间？`" heading @close="kicking = null">
      <div class="confirm">
        <button type="button" class="ui-btn" @click="kicking = null">取消</button>
        <button type="button" class="ui-btn primary" @click="kick">移出</button>
      </div>
    </Modal>
    <Modal v-if="picking && duelConfig" :title="`猜拳 ${shownNick(picking)}`" heading @close="picking = null">
      <p v-if="needAccount" class="picker picker-note">登录 Asasfans 账号后才能猜拳</p>
      <StakeKeys v-else class="picker" :disabled="!canDuel(picking)" @pick="invite" />
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
.room-id {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.code {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 800 28px/1.1 var(--font-latin);
  letter-spacing: 0.04em;
  user-select: text;
}
/* With a name the id steps back under it. */
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 800 22px/1.2 var(--font);
}
.code.under {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--ink-3);
}
.rename,
.rooms-key {
  flex: none;
  padding: 0 6px;
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
/* The refresh key over the list in the room list dialog. */
.list-keys {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}
/* The kick question's keys, as the update dialog's. */
.confirm {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.confirm .primary {
  min-width: 96px;
}
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
.who .at-table {
  --tag-bg: var(--c-100);
  --tag-fg: var(--c-700);
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
.who small .status {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: 4px;
  color: var(--c-700);
  font-weight: 800;
}
/* The own status keys; the bottom padding makes room for their lip. */
.status-pick {
  gap: 5px;
  padding: 0 8px 0 10px;
}
/* The font's ink sits below the middle of its line box; lifted, the label lines up with the icon. */
.status-pick .label {
  position: relative;
  top: -0.03em;
}
.status-pick .chev {
  color: var(--ink-2);
  transition: rotate var(--dur-fast) var(--ease-out);
}
.status-pick[aria-expanded="true"] .chev {
  rotate: 180deg;
}
.status-keys {
  padding: 8px 18px;
  animation: status-in var(--dur-base) var(--ease-out);
}
@keyframes status-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
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
/* 合力应援: the faces cheering, the bar in cells, one per cheering save, and the prize at its end. */
.cheer {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
}
.cheer-track {
  display: flex;
  align-items: center;
  gap: 14px;
}
.cheer-faces {
  flex: none;
  display: flex;
  align-items: center;
  padding-left: 8px;
}
.cheer-faces > * {
  margin-left: -8px;
  border-radius: 50%;
  box-shadow: 0 0 0 2px var(--surface);
}
.cheer-faces > .off {
  filter: grayscale(1);
  opacity: 0.45;
}
/* The own face pops once its taps go on the bar. */
.cheer-faces > .me:not(.off) {
  animation: face-pop 0.45s var(--ease-out);
}
@keyframes face-pop {
  40% { transform: scale(1.25); }
}
/* A save that left but still counts for a while. */
.cheer-faces > .gone {
  box-sizing: border-box;
  width: 26px;
  height: 26px;
  border: 2px dashed var(--c-300);
  background: var(--surface);
}
.cheer-bar {
  flex: 1;
  display: flex;
  gap: 4px;
  min-width: 0;
}
.cheer-bar > .ui-bar {
  position: relative;
  flex: 1;
  min-width: 0;
}
/* A full bar lights up once before it starts over. */
.cheer-bar.flash > .ui-bar::after {
  content: "";
  position: absolute;
  inset: 0;
  background: var(--c-500);
  animation: cheer-full 1.2s var(--ease-out) forwards;
}
@keyframes cheer-full {
  from { opacity: 1; }
  to { opacity: 0; }
}
.cheer-prize {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--c-700);
  font: 800 20px/1 var(--font-latin);
}
.cheer-prize.off {
  color: var(--ink-3);
  font: 700 var(--fs-label)/1.2 var(--font);
}
.cheer-note {
  margin: 0;
  font: 700 var(--fs-label)/1.4 var(--font);
  color: var(--ink-2);
}
.acts .ui-btn {
  padding: 0 8px;
}
/* The same bets as over a partner's pet on the desk. */
.picker {
  max-width: 260px;
  margin: 0 auto;
}
/* In place of the bets while they need an account: as the dou dizhu sheet says what holds a game up. */
.picker-note {
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-key);
  background: var(--c-50);
  font: 800 var(--fs-body)/1.3 var(--font);
  color: var(--ink-2);
  text-align: center;
}
</style>
