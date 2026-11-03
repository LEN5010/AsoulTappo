<script setup lang="ts">
import { computed, reactive } from "vue";
import { manifest, resolveAsset, type ManifestTheme } from "../manifest";
import { toHttpBase } from "../net/protocol";
import { settings } from "../stores/settings";
import { characterColor } from "../manifest";

const base = computed(() => toHttpBase(settings.serverUrl));
const url = (r: string | null) => resolveAsset(r, base.value, import.meta.env.BASE_URL);
const broken = reactive(new Set<string>());
const groups = computed(() =>
  manifest.characters
    .map((c) => ({ c, themes: manifest.themes.filter((t) => t.characters.includes(c.name)) }))
    .filter((g) => g.themes.length),
);
function pick(t: ManifestTheme) {
  settings.theme = t.id;
}
</script>

<template>
  <div class="themes">
    <p class="hint">
      默认主题已内置;其他主题的背景和动画来自服务器素材包(<code>/packs</code>),连接服务器后自动加载,没有时回退为主题色。
    </p>
    <section v-for="g in groups" :key="g.c.id">
      <h4 :style="{ color: g.c.color }">{{ g.c.name }}</h4>
      <div class="row">
        <button
          v-for="t in g.themes" :key="t.id" type="button" class="theme" :class="{ on: settings.theme === t.id }"
          :aria-pressed="settings.theme === t.id" :style="{ '--c': characterColor(g.c.name), '--t': t.colors.accent }" @click="pick(t)"
        >
          <img v-if="!broken.has(t.id)" :src="url(t.cover)" :alt="t.name" loading="lazy" draggable="false" @error="broken.add(t.id)" />
          <span v-else class="ph" :style="{ background: t.colors.tint }"></span>
          <span class="name">{{ t.name }}</span>
          <span class="sw" :style="{ background: t.colors.accent }"></span>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.themes { display: flex; flex-direction: column; gap: 6px; }
.hint { font-size: 11px; color: rgba(0, 0, 0, 0.5); margin: 0; }
h4 { margin: 4px 0 2px; font-size: 12px; }
.row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.theme { position: relative; padding: 0; border: 2px solid transparent; border-radius: 10px; overflow: hidden; background: rgba(255, 255, 255, 0.6); cursor: pointer; text-align: left; font-family: inherit; }
.theme img, .ph { display: block; width: 100%; aspect-ratio: 1 / 1.3; object-fit: cover; }
.name { display: block; padding: 3px 4px; font-size: 10px; line-height: 1.2; min-height: 24px; color: #333; }
.sw { position: absolute; top: 4px; right: 4px; width: 10px; height: 10px; border-radius: 50%; border: 2px solid #fff; }
.theme.on { border-color: var(--t); box-shadow: 0 0 0 2px rgba(var(--accent-rgb), 0.25); }
</style>
