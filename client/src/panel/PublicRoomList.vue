<script setup lang="ts">
// Public rooms of the server, one card each. The room this desk is in, when listed, is tagged and has no join key.
import type { PublicRoom } from "../net/protocol";
import { settings } from "../stores/settings";
import { shownNick } from "../stores/room";
import CharacterAvatar from "../ui/CharacterAvatar.vue";

defineProps<{ rooms: PublicRoom[]; current?: string }>();
defineEmits<{ join: [room: PublicRoom] }>();

// Hidden nicknames hide room names too: both are what players typed.
const listedName = (r: PublicRoom) => (settings.hideNicks ? "" : r.name ?? "");
</script>

<template>
  <ul v-if="rooms.length" class="rooms">
    <li v-for="r in rooms" :key="r.room" class="room">
      <CharacterAvatar :character="r.host.character" :size="32" />
      <span class="who">
        <b>{{ listedName(r) || shownNick(r.host) }}</b>
        <small>
          <template v-if="listedName(r)">{{ shownNick(r.host) }} · </template>{{ r.members }} / {{ r.max }}
        </small>
      </span>
      <em v-if="current && r.room === current" class="ui-tag">当前</em>
      <button v-else type="button" class="ui-btn small" :disabled="r.members >= r.max" @click="$emit('join', r)">加入</button>
    </li>
  </ul>
  <p v-else class="ui-empty">暂无</p>
</template>

<style scoped>
.rooms {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(212px, 1fr));
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.room {
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
.room > .ui-tag {
  flex: none;
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
.who small {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-2);
}
</style>
