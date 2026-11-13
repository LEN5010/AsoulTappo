<script setup lang="ts">
// Over the pet: the park's big wins anywhere on the server (status `park.news`), each shown once, one at a time.
// While [paused] or the cooldown bubble is up (they hold the spot) the queue waits; nothing is marked seen before it
// shows.
import { onBeforeUnmount, ref, watch } from "vue";
import { newsLine, type NewsLine } from "../parkNews";
import { markNewsSeen, unseenParkNews } from "../stores/park";
import { tapCooldown } from "../stores/pet";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ paused?: boolean }>();

const SHOW_MS = 5000;
const GAP_MS = 600;

const line = ref<NewsLine | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;

function next() {
  if (line.value || timer || props.paused) return;
  const cooling = tapCooldown.value - Date.now();
  if (cooling > 0) {
    if (unseenParkNews.value.length) timer = setTimeout(() => { timer = undefined; next(); }, cooling + GAP_MS);
    return;
  }
  for (const n of unseenParkNews.value) {
    markNewsSeen([n.id]);
    const shown = newsLine(n);
    if (!shown) continue;
    line.value = shown;
    timer = setTimeout(() => {
      line.value = null;
      timer = setTimeout(() => { timer = undefined; next(); }, GAP_MS);
    }, SHOW_MS);
    return;
  }
}
watch(() => [unseenParkNews.value.length, props.paused], next, { immediate: true });
onBeforeUnmount(() => clearTimeout(timer));

const fmt = (n: number) => n.toLocaleString("en-US");
</script>

<template>
  <div class="anchor" role="status">
    <Transition name="news">
      <p v-if="line" class="news">
        <b v-if="line.nick" class="nick">{{ line.nick }}</b>
        <span>{{ line.text }}</span>
        <span v-if="line.shards" class="amount"><Icon name="shard" :size="13" />{{ fmt(line.shards) }}</span>
      </p>
    </Transition>
  </div>
</template>

<style scoped>
.anchor { position: absolute; left: 50%; top: 0; width: 0; height: 0; pointer-events: none; z-index: 5; }
.news {
  position: absolute; left: 0; bottom: 8px; margin: 0; padding: 6px 12px; transform: translateX(-50%);
  display: flex; align-items: center; gap: 5px; max-width: 320px; box-sizing: border-box;
  border-radius: 14px; background: var(--surface); box-shadow: 0 6px 16px -6px rgba(var(--shadow-rgb), 0.4);
  font: 700 var(--fs-body)/1.3 var(--font); color: var(--ink); white-space: nowrap;
}
.news::after {
  content: ""; position: absolute; left: 50%; top: 100%; translate: -50% 0;
  border: 7px solid transparent; border-top-color: var(--surface); border-bottom: 0;
}
.nick { min-width: 0; max-width: 140px; overflow: hidden; text-overflow: ellipsis; font-weight: 800; color: var(--c-700); }
.amount { display: inline-flex; align-items: center; gap: 2px; font: 800 var(--fs-number)/1 var(--font-latin); }
.amount svg { color: var(--c-600); }
.news-enter-active { transition: opacity var(--dur-fast), transform var(--dur-fast) var(--ease-pop); }
.news-enter-from { opacity: 0; transform: translate(-50%, 8px) scale(0.8); }
.news-leave-active { transition: opacity var(--dur-base) var(--ease-in); }
.news-leave-to { opacity: 0; }
</style>
