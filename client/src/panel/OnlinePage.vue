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
    <section>
      <h4 class="ui-label">联机房间</h4>
      <div class="group">
        <div class="row">
          <span class="status">
            <img
              v-if="(conn === 'connecting' || conn === 'reconnecting') && skin.loading && !reducedMotion"
              class="loading" :src="skin.loading" alt=""
            />
            <i v-else class="dot" :class="conn"></i>
            {{ connText[conn] }}
            <span v-if="inRoom" class="count-pill">{{ members.size }} / {{ MAX_ROOM_SIZE }} 人</span>
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
        <p v-if="lastError || notice" class="err">{{ lastError || notice }}</p>
      </div>
    </section>

    <section v-if="inRoom">
      <header class="cap">
        <h4 class="ui-label">房间成员</h4>
        <button type="button" class="ui-btn small" title="把大家的桌宠重新排到你的桌宠旁边" @click="tidyRemotes">
          <Icon name="refresh" :size="13" />整理位置
        </button>
      </header>
      <ul class="group">
        <li v-for="m in members.values()" :key="m.id" class="row">
          <CharacterAvatar :character="m.character" :size="32" />
          <span class="nick">{{ m.nick }}<em v-if="m.id === youId">我</em></span>
          <span class="chr" :style="{ color: characterColor(m.character) }">{{ m.character }}</span>
          <span class="taps">{{ m.taps.toLocaleString("en-US") }} <small>敲击</small></span>
        </li>
      </ul>
    </section>

    <section>
      <h4 class="ui-label">同桌显示</h4>
      <div class="group">
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
  gap: 20px;
}
.group {
  margin: 0;
  padding: 4px 0;
  list-style: none;
  background: var(--card);
  border: 2px solid var(--tile-border);
  border-radius: 22px;
  box-shadow: 0 3px 0 var(--tile-lip);
  overflow: hidden;
}
.group > * + * {
  border-top: 1.5px dashed var(--line);
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
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
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--ink-3);
}
.dot.open {
  background: var(--ok);
  box-shadow: 0 0 0 3px rgba(70, 168, 114, 0.2);
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
.count-pill {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--paper-2);
  color: var(--ink-2);
  font-size: 11px;
  font-weight: 700;
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
  color: var(--bad);
  font-size: 12px;
  font-weight: 700;
}
.cap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
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
  margin-left: 6px;
  font-style: normal;
  font-size: 11px;
  font-weight: 800;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--on-accent);
}
.chr {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--paper);
  font-size: 12px;
  font-weight: 800;
}
.taps {
  min-width: 72px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
  font-weight: 800;
}
.taps small {
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-3);
}
.ctl {
  width: 280px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
}
.val {
  width: 52px;
  flex: none;
  text-align: right;
  font-size: 12px;
  font-weight: 800;
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}
</style>
