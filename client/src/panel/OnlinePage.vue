<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { MAX_ROOM_SIZE, toHttpBase, type Member } from "../net/protocol";
import { Api, type ServerInfo } from "../net/api";
import { accountLoginTrusted } from "../net/trust";
import { settings } from "../stores/settings";
import { activeAccount, saveCode, status } from "../stores/player";
import {
  canDuel, cheer, cheerDone, cheerOn, conn, createRoom, duelConfig, duelOn, inRoom, inviteDuel, isHost, joinRoom, kickMember,
  lastError, leaveRoom, loadPublicRooms, members, publicRooms, roomId, roomInfo, setRoomPublic, shownNick, youId,
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
import ProfileDialog from "./ProfileDialog.vue";
import { ui } from "../stores/ui";
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
const kicking = ref<Member | null>(null);
function kick() {
  if (kicking.value) kickMember(kicking.value.id);
  kicking.value = null;
}
watch(inRoom, (v) => { if (!v) { picking.value = null; kicking.value = null; } });
watch(() => kicking.value && !members.has(kicking.value.id), (gone) => { if (gone) kicking.value = null; });

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
        <label class="ui-row">
          <span>显示伙伴昵称</span>
          <input v-model="settings.showNames" class="ui-switch" type="checkbox" />
        </label>
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
            <button v-if="isHost" type="button" class="ui-btn small" title="移出房间" aria-label="移出房间" @click="kicking = m">
              <Icon name="close" :size="13" />
            </button>
          </span>
        </li>
      </ul>
    </section>

    <ProfileDialog v-if="profileOf" :id="profileOf" :key="profileOf" @close="profileOf = null" />
    <Modal v-if="kicking" :title="`把${shownNick(kicking)}移出房间？`" heading @close="kicking = null">
      <div class="confirm">
        <button type="button" class="ui-btn" @click="kicking = null">取消</button>
        <button type="button" class="ui-btn primary" @click="kick">移出</button>
      </div>
    </Modal>
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
@media (prefers-reduced-motion: reduce) {
  .cheer-faces > .me:not(.off) { animation: none; }
  .cheer-bar.flash > .ui-bar::after { display: none; }
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
</style>
