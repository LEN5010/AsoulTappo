<script setup lang="ts">
import { ref } from "vue";
import { MAX_ROOM_SIZE } from "../net/protocol";
import { settings } from "../stores/settings";
import {
  conn, createRoom, inRoom, joinRoom, lastError, leaveRoom, members, roomId, sendEmote, youId,
} from "../stores/room";
import EmotePicker from "./EmotePicker.vue";

const input = ref(settings.lastRoom);
const busy = ref(false);
const notice = ref("");
const copied = ref(false);

const connText: Record<string, string> = {
  idle: "未连接",
  connecting: "连接中…",
  open: "已连接",
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
    notice.value = `创建失败:${e instanceof Error ? e.message : e}(检查服务器地址)`;
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
    notice.value = "复制失败,请手动选中房间号";
  }
}
</script>

<template>
  <div class="room">
    <div class="status">
      <span class="dot" :class="conn"></span>{{ connText[conn] }}
      <span v-if="inRoom" class="count">{{ members.size }}/{{ MAX_ROOM_SIZE }} 人</span>
    </div>

    <template v-if="!inRoom && conn === 'idle'">
      <button class="primary" :disabled="busy" @click="onCreate">创建房间</button>
      <div class="row">
        <input v-model="input" placeholder="输入 Room ID" spellcheck="false" @keydown.enter="joinRoom(input)" />
        <button :disabled="!input.trim()" @click="joinRoom(input)">加入</button>
      </div>
    </template>
    <template v-else>
      <div class="row">
        <input :value="roomId" readonly spellcheck="false" @focus="($event.target as HTMLInputElement).select()" />
        <button @click="copy">{{ copied ? "已复制" : "复制" }}</button>
      </div>
      <button @click="leaveRoom">离开房间</button>
    </template>

    <div v-if="lastError || notice" class="err">{{ lastError || notice }}</div>

    <template v-if="inRoom">
      <h4>表情</h4>
      <EmotePicker @pick="sendEmote" />
      <h4>成员</h4>
      <ul class="members">
        <li v-for="m in members.values()" :key="m.id">
          <span class="nick">{{ m.nick }}<em v-if="m.id === youId">(我)</em></span>
          <span class="chr">{{ m.character }}</span>
          <span class="taps">{{ m.taps }}</span>
        </li>
      </ul>
    </template>
    <template v-else>
      <h4>表情(本地预览)</h4>
      <EmotePicker @pick="sendEmote" />
    </template>
  </div>
</template>

<style scoped>
.room { display: flex; flex-direction: column; gap: 8px; }
.status { font-size: 12px; color: #555; display: flex; align-items: center; gap: 6px; }
.count { margin-left: auto; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #aaa; }
.dot.open { background: #3ec46d; }
.dot.connecting, .dot.reconnecting { background: #f0a020; }
.row { display: flex; gap: 6px; }
.row input { flex: 1; min-width: 0; }
input { padding: 5px 8px; border: 1px solid #ccc; border-radius: 6px; font-size: 12px; }
button { padding: 5px 10px; border-radius: 6px; border: 1px solid #ccc; background: #fff; cursor: pointer; font-size: 12px; }
button.primary { background: #ff6b9d; color: #fff; border-color: #ff6b9d; }
button:disabled { opacity: 0.5; cursor: default; }
h4 { margin: 6px 0 0; font-size: 12px; color: #888; font-weight: 600; }
.err { color: #d33; font-size: 12px; }
.members { list-style: none; margin: 0; padding: 0; max-height: 150px; overflow: auto; font-size: 12px; }
.members li { display: flex; gap: 8px; padding: 2px 0; border-bottom: 1px dashed #eee; }
.nick { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nick em { color: #ff6b9d; font-style: normal; margin-left: 2px; }
.chr { color: #999; }
.taps { min-width: 36px; text-align: right; font-variant-numeric: tabular-nums; }
</style>
