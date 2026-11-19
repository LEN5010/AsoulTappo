<script setup lang="ts">
// Emotes at the dou dizhu table: a key in the corner opens the player's favourite emotes (the starter ones without
// any), and a pick plays it on the own pet for the whole room. The table has no other way to talk.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { assetUrl } from "../../asset";
import { starterEmotesOf } from "../../items";
import { getEmote } from "../../manifest";
import { sendEmote } from "../../stores/room";
import { settings } from "../../stores/settings";
import Icon from "../../ui/Icon.vue";

const MAX = 10;
const open = ref(false);
const root = ref<HTMLElement>();
const list = computed(() => (settings.favorites.length ? settings.favorites : starterEmotesOf(settings.character))
  .map((key) => ({ key, e: getEmote(key) })).filter((x) => x.e).slice(0, MAX));
function pick(key: string) {
  open.value = false;
  sendEmote(key);
}
// A press anywhere else puts the tray away.
function away(e: PointerEvent) {
  if (open.value && !root.value?.contains(e.target as Node)) open.value = false;
}
onMounted(() => window.addEventListener("pointerdown", away, true));
onBeforeUnmount(() => window.removeEventListener("pointerdown", away, true));
</script>

<template>
  <div v-if="list.length" ref="root" class="emotes">
    <button type="button" class="ui-btn small ghost" title="表情" aria-label="表情" :aria-expanded="open" @click="open = !open">
      <Icon name="heart" :size="18" />
    </button>
    <Transition name="tray">
      <div v-if="open" class="tray" role="menu" aria-label="表情" :style="{ gridTemplateColumns: `repeat(${Math.min(5, list.length)}, 56px)` }">
        <button v-for="x in list" :key="x.key" type="button" class="ui-btn emo" role="menuitem" :title="x.e!.name" @click="pick(x.key)">
          <img :src="assetUrl(x.e!.thumb ?? x.e!.img)" :alt="x.e!.name" draggable="false" />
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.emotes { position: relative; pointer-events: auto; }
.emotes > .ui-btn { width: 40px; height: 36px; padding: 0; }
/* A sheet of paper under the key, at most five emotes to a row. */
.tray {
  position: absolute;
  right: 0;
  top: 42px;
  display: grid;
  gap: 7px;
  padding: 10px;
  border-radius: 16px;
  background: var(--surface);
  box-shadow: 0 6px 16px -6px rgba(var(--shadow-rgb), 0.4);
}
.emo { width: 56px; height: 56px; padding: 0; }
.emo img { width: 46px; height: 46px; object-fit: contain; pointer-events: none; }
.tray-enter-active { transition: opacity var(--dur-fast), scale var(--dur-fast) var(--ease-pop); transform-origin: 100% 0; }
.tray-enter-from { opacity: 0; scale: 0.85; }
.tray-leave-active { transition: opacity var(--dur-fast) var(--ease-in); }
.tray-leave-to { opacity: 0; }
</style>
