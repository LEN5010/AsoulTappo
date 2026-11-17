<script setup lang="ts">
// The rooms this desk joined lately (recentRooms.ts), one card each as the public rooms are: the room's name or its
// number, the day it was last joined, a key to join again and one to forget it.
import { roomDay, type RecentRoom } from "../recentRooms";
import { settings } from "../stores/settings";
import Icon from "../ui/Icon.vue";

defineProps<{ rooms: RecentRoom[] }>();
defineEmits<{ join: [room: string]; forget: [room: string] }>();

// Hidden nicknames hide room names too: both are what players typed.
const shownName = (r: RecentRoom) => (settings.hideNicks ? "" : r.name ?? "");
</script>

<template>
  <ul class="rooms">
    <li v-for="r in rooms" :key="r.room" class="room">
      <span class="mark" aria-hidden="true"><Icon name="clock" :size="16" /></span>
      <span class="who">
        <b :title="r.room">{{ shownName(r) || r.room }}</b>
        <small><template v-if="shownName(r)">{{ r.room }} · </template>{{ roomDay(r.at) }}</small>
      </span>
      <button type="button" class="ui-btn small ghost forget" aria-label="移除" @click="$emit('forget', r.room)">
        <Icon name="close" :size="13" />
      </button>
      <button type="button" class="ui-btn small" @click="$emit('join', r.room)">加入</button>
    </li>
  </ul>
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
  position: relative;
}
.mark {
  flex: none;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--c-100);
  color: var(--c-700);
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-2);
}
/* A small key on the card's corner, quiet until the card is pointed at: the join key stays the card's one key. */
.forget {
  position: absolute;
  top: -7px;
  right: -7px;
  width: 22px;
  min-width: 0;
  height: 22px;
  padding: 0;
  border-radius: 50%;
  background: var(--surface);
  box-shadow: var(--shadow-key);
  opacity: 0;
  transition: opacity var(--dur-fast);
}
.room:hover .forget,
.forget:focus-visible {
  opacity: 1;
}
</style>
