<script setup lang="ts">
import { ref } from "vue";
import { MAX_ROOM_SIZE } from "../net/protocol";
import { settings } from "../stores/settings";
import { conn, createRoom, inRoom, joinRoom, lastError, leaveRoom, members, roomId, youId } from "../stores/room";
import { tidyRemotes } from "../stores/desk";
import { characterColor } from "../manifest";
import { reducedMotion, skin } from "../stores/theme";
import CharacterAvatar from "../ui/CharacterAvatar.vue";
import Icon from "../ui/Icon.vue";
import RangeInput from "../ui/RangeInput.vue";
import RoomStage from "./RoomStage.vue";

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

      <section class="ticket ui-frame ui-ring" data-rise>
        <div class="stub ui-plate">
          <span class="stub-mark">ROOM</span>
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
          <input v-model="input" class="ui-input" placeholder="房间号" aria-label="房间号" spellcheck="false" @keydown.enter="joinRoom(input)" />
          <button type="button" class="ui-btn" :disabled="!input.trim()" @click="joinRoom(input)">加入</button>
          <button type="button" class="ui-btn primary" :disabled="busy" @click="onCreate">
            <Icon name="plus" :size="15" />创建房间
          </button>
        </div>
        <div v-else class="ticket-body">
          <b class="code" :title="roomId">{{ roomId }}</b>
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

    <section data-rise>
      <h4 class="ui-label"><span>同桌显示</span><em>TOGETHER</em></h4>
      <div class="ui-group ui-frame ui-ring">
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
        <h4 class="ui-label"><span>房间成员</span><em>MEMBERS</em><small>{{ members.size }} / {{ MAX_ROOM_SIZE }}</small></h4>
        <button type="button" class="ui-btn small" title="把大家的桌宠重新排到你的桌宠旁边" @click="tidyRemotes">
          <Icon name="refresh" :size="13" />整理位置
        </button>
      </header>
      <ul class="members">
        <li v-for="m in members.values()" :key="m.id" class="member ui-frame ui-ring">
          <CharacterAvatar :character="m.character" :size="32" />
          <span class="who">
            <b>{{ m.nick }}<em v-if="m.id === youId" class="ui-tag">我</em></b>
            <small><i :style="{ background: characterColor(m.character) }" aria-hidden="true"></i>{{ m.character }}</small>
          </span>
          <span class="taps">{{ m.taps.toLocaleString("en-US") }}<small>敲击</small></span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.front {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ticket {
  --radius: var(--radius-m);
  display: flex;
  align-items: stretch;
  min-height: 64px;
  background: var(--surface);
}
.stub {
  --plate-bg: var(--grad-sky);
  flex: none;
  width: 156px;
  margin-left: -8px;
  padding: 8px 14px 8px 24px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
  color: var(--on-accent);
}
.stub::after {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  right: -7px;
  border-right: 2px dashed var(--line-2);
}
.stub-mark {
  font: 800 var(--fs-heading)/1 var(--font-latin);
  letter-spacing: 0.08em;
}
.status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-label);
  font-weight: 700;
}
.dot {
  width: 6px;
  height: 12px;
  background: var(--surface);
}
.dot.open,
.dot.connecting,
.dot.reconnecting {
  box-shadow: 0 0 0 1.5px var(--surface);
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
  padding: 10px 18px 10px 22px;
}
.ticket-body .ui-input {
  flex: 1;
  min-width: 0;
}
.code {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 800 var(--fs-section)/1.2 var(--font-latin);
  letter-spacing: 0.03em;
  user-select: text;
}
.err {
  margin: 0;
}

.cap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.cap .ui-label {
  margin: 0;
}
.members {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(212px, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.member {
  --radius: var(--radius-s);
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 52px;
  padding: 7px 14px 7px 10px;
  box-sizing: border-box;
  background: var(--surface);
}
.who {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
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
.who small {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-2);
}
.who small i {
  width: 3px;
  height: 9px;
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
</style>
