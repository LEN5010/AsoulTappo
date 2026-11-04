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

const input = ref(settings.lastRoom);
const busy = ref(false);
const notice = ref("");
const copied = ref(false);
const connText: Record<string, string> = {
  idle: "未加入房间",
  connecting: "连接中…",
  open: "已在房间中",
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
  <div class="room">
    <section data-rise>
      <h4 class="ui-label"><span>联机房间</span><em>ROOM</em></h4>
      <div class="group ui-frame ui-ring">
        <div class="row">
          <span class="status">
            <img
              v-if="(conn === 'connecting' || conn === 'reconnecting') && skin.loading && !reducedMotion"
              class="loading" :src="skin.loading" alt=""
            />
            <i v-else class="dot" :class="conn"></i>
            {{ connText[conn] }}
            <span v-if="inRoom" class="ui-tag">{{ members.size }} / {{ MAX_ROOM_SIZE }} 人</span>
          </span>
        </div>
        <div v-if="!inRoom && conn === 'idle'" class="row join">
          <input v-model="input" class="ui-input" placeholder="输入房间号加入朋友的桌面" spellcheck="false" @keydown.enter="joinRoom(input)" />
          <button type="button" class="ui-btn" :disabled="!input.trim()" @click="joinRoom(input)">加入</button>
          <button type="button" class="ui-btn primary" :disabled="busy" @click="onCreate">
            <Icon name="plus" :size="15" />创建房间
          </button>
        </div>
        <div v-else class="row join">
          <input :value="roomId" class="ui-input mono" readonly spellcheck="false" @focus="($event.target as HTMLInputElement).select()" />
          <button type="button" class="ui-btn" @click="copy">
            <Icon name="copy" :size="14" />{{ copied ? "已复制" : "复制房间号" }}
          </button>
          <button type="button" class="ui-btn" @click="leaveRoom">
            <Icon name="logout" :size="14" />离开
          </button>
        </div>
        <p v-if="lastError || notice" class="ui-error err">{{ lastError || notice }}</p>
      </div>
    </section>

    <section v-if="inRoom" data-rise>
      <header class="cap">
        <h4 class="ui-label"><span>房间成员</span><em>MEMBERS</em></h4>
        <button type="button" class="ui-btn small" title="把大家的桌宠重新排到你的桌宠旁边" @click="tidyRemotes">
          <Icon name="refresh" :size="13" />整理位置
        </button>
      </header>
      <ul class="group ui-frame ui-ring">
        <li v-for="m in members.values()" :key="m.id" class="row">
          <CharacterAvatar :character="m.character" :size="32" />
          <span class="nick">{{ m.nick }}<em v-if="m.id === youId" class="ui-tag">我</em></span>
          <span class="ui-chip chr"><i :style="{ background: characterColor(m.character) }" aria-hidden="true"></i>{{ m.character }}</span>
          <span class="taps">{{ m.taps.toLocaleString("en-US") }} <small>敲击</small></span>
        </li>
      </ul>
    </section>

    <section data-rise>
      <h4 class="ui-label"><span>同桌显示</span><em>TOGETHER</em></h4>
      <div class="group ui-frame ui-ring">
        <label class="row">
          <span>伙伴桌宠大小</span>
          <span class="ctl">
            <RangeInput v-model="settings.remoteScale" :min="0.4" :max="1.5" :step="0.1" />
            <b class="val">×{{ settings.remoteScale.toFixed(1) }}</b>
          </span>
        </label>
        <label class="row">
          <span>显示伙伴昵称</span>
          <input v-model="settings.showNames" class="ui-switch" type="checkbox" />
        </label>
      </div>
    </section>
  </div>
</template>

<style scoped>
.room {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.group {
  --cut: 16px;
  margin: 0;
  padding: 0;
  list-style: none;
  background: var(--surface);
}
.group > * + * {
  border-top: 1.5px solid var(--line);
}
.row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 48px;
  padding: 8px 18px;
  box-sizing: border-box;
  font-size: 13px;
  font-weight: 700;
}
label.row {
  justify-content: space-between;
}
.status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 800;
}
.dot {
  width: 8px;
  height: 14px;
  background: var(--ink-3);
  transform: skewX(var(--skew));
}
.dot.open {
  background: var(--ok);
}
.dot.connecting,
.dot.reconnecting {
  background: var(--warn);
}
.loading {
  width: 22px;
  height: 22px;
  object-fit: contain;
}
.join .ui-input {
  flex: 1;
}
.mono {
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  font-size: 12px;
  color: var(--ink-2);
}
.err {
  margin: 0;
  padding: 8px 18px;
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
.nick {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 800;
}
.nick em {
  margin-left: 8px;
}
.chr {
  cursor: default;
  height: 22px;
  color: var(--ink);
}
.chr:hover::before {
  background: var(--surface);
}
.taps {
  min-width: 72px;
  text-align: right;
  font: italic 800 17px/1 var(--font-latin);
  color: var(--ink);
}
.taps small {
  font: 600 11px var(--font);
  color: var(--ink-3);
}
.ctl {
  width: 280px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
}
.val {
  width: 52px;
  flex: none;
  text-align: right;
  font: italic 800 16px/1 var(--font-latin);
  color: var(--ink-2);
}
</style>
