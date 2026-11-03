<script setup lang="ts">
// 联机: create / join a room by ID; members' pets appear on your desk and can be dragged anywhere.
import { ref } from "vue";
import { MAX_ROOM_SIZE } from "../net/protocol";
import { settings } from "../stores/settings";
import { conn, createRoom, inRoom, joinRoom, lastError, leaveRoom, members, roomId, youId } from "../stores/room";
import { tidyRemotes } from "../stores/desk";
import { getDecor, characterColor } from "../manifest";
import { assetUrl } from "../asset";
import { reducedMotion, skin } from "../stores/theme";
import CharacterAvatar from "../ui/CharacterAvatar.vue";
import Icon from "../ui/Icon.vue";

const input = ref(settings.lastRoom);
const busy = ref(false);
const notice = ref("");
const copied = ref(false);
const connText: Record<string, string> = { idle: "未连接", connecting: "连接中…", open: "已连接", reconnecting: "重连中…" };

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
const badgeImg = (id?: string | null) => assetUrl(getDecor(id)?.img);
</script>

<template>
  <div class="room">
    <section class="ui-card hero">
      <div class="status">
        <img v-if="(conn === 'connecting' || conn === 'reconnecting') && skin.loading && !reducedMotion" class="loading" :src="skin.loading" alt="" />
        <span v-else class="dot" :class="conn"></span>
        <b>{{ connText[conn] }}</b>
        <span v-if="inRoom" class="ui-muted">· {{ members.size }}/{{ MAX_ROOM_SIZE }} 人</span>
      </div>

      <template v-if="!inRoom && conn === 'idle'">
        <div class="join">
          <input v-model="input" class="ui-input" placeholder="输入房间号" spellcheck="false" @keydown.enter="joinRoom(input)" />
          <button type="button" class="ui-btn" :disabled="!input.trim()" @click="joinRoom(input)">加入</button>
          <span class="or">或</span>
          <button type="button" class="ui-btn primary" :disabled="busy" @click="onCreate"><Icon name="plus" :size="16" />创建房间</button>
        </div>
      </template>
      <template v-else>
        <div class="join">
          <label class="rid"><Icon name="link" :size="16" /><input :value="roomId" class="ui-input" readonly spellcheck="false" @focus="($event.target as HTMLInputElement).select()" /></label>
          <button type="button" class="ui-btn" @click="copy"><Icon name="copy" :size="15" />{{ copied ? "已复制" : "复制房间号" }}</button>
          <button type="button" class="ui-btn ghost" @click="leaveRoom"><Icon name="logout" :size="15" />离开</button>
        </div>
      </template>
      <p v-if="lastError || notice" class="err">{{ lastError || notice }}</p>
    </section>

    <section v-if="inRoom" class="ui-card members">
      <header>
        <b>成员</b>
        <button type="button" class="ui-btn small" title="把大家的桌宠重新排到你的桌宠旁边" @click="tidyRemotes"><Icon name="refresh" :size="14" />整理桌面</button>
      </header>
      <ul>
        <li v-for="m in members.values()" :key="m.id">
          <CharacterAvatar :character="m.character" :frame="m.frame" :size="34" />
          <span class="nick">{{ m.nick }}<em v-if="m.id === youId">我</em></span>
          <img v-if="badgeImg(m.badge)" class="badge" :src="badgeImg(m.badge)" :title="getDecor(m.badge)?.name" alt="" />
          <span class="chr" :style="{ color: characterColor(m.character) }">{{ m.character }}</span>
          <span class="taps">{{ m.taps.toLocaleString("en-US") }}</span>
        </li>
      </ul>
    </section>

    <section class="ui-card opts">
      <label class="line">
        <span>同桌桌宠大小 <b>×{{ settings.remoteScale.toFixed(1) }}</b></span>
        <input v-model.number="settings.remoteScale" class="ui-range" type="range" min="0.4" max="1.5" step="0.1" />
      </label>
      <label class="line sw">
        <span>显示同桌名字</span>
        <input v-model="settings.showNames" class="ui-switch" type="checkbox" />
      </label>
    </section>
  </div>
</template>

<style scoped>
.room { display: flex; flex-direction: column; gap: 14px; }
.hero { padding: 18px; display: flex; flex-direction: column; gap: 12px; background: linear-gradient(160deg, rgba(var(--accent-rgb), 0.1), #fff 60%); }
.status { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.dot { width: 10px; height: 10px; border-radius: 50%; background: var(--ink-3); }
.dot.open { background: var(--ok); box-shadow: 0 0 0 4px rgba(63, 182, 122, 0.18); }
.dot.connecting, .dot.reconnecting { background: var(--warn); }
.loading { width: 24px; height: 24px; object-fit: contain; }
.join { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.join > .ui-input { flex: 1; min-width: 160px; }
.rid { flex: 1; min-width: 200px; display: flex; align-items: center; gap: 6px; color: var(--ink-3); }
.rid .ui-input { flex: 1; font-family: ui-monospace, monospace; font-size: 12px; }
.or { color: var(--ink-3); font-size: 12px; }
.err { margin: 0; color: var(--bad); font-size: 12px; }
.members { padding: 14px 16px; }
.members header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
li { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px dashed var(--line); font-size: 13px; }
li:last-child { border-bottom: none; }
.nick { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
.nick em { margin-left: 6px; font-style: normal; font-size: 11px; padding: 1px 6px; border-radius: 999px; background: var(--accent); color: var(--on-accent); }
.badge { height: 20px; width: auto; }
.chr { font-size: 12px; font-weight: 700; }
.taps { min-width: 56px; text-align: right; font-variant-numeric: tabular-nums; color: var(--ink-2); }
.opts { padding: 14px 16px; display: flex; flex-direction: column; gap: 12px; }
.line { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
.line.sw { flex-direction: row; align-items: center; justify-content: space-between; }
</style>
