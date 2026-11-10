<script setup lang="ts">
// The two Asasfans apps, shown in a dialog opened from About in the settings: the website and the Asasfans Next
// app. Both links open through openAboutLink, so they must stay in ABOUT_LINKS in src-tauri/src/lib.rs, byte for byte.
import { openAboutLink } from "../composables/tauri";
import icon from "../assets/brand/asasfans-icon.webp";

const WEB = "https://len5010.top";
const NEXT = "https://len5010.top/download";
const APPS = [
  { name: "Asasfans Web", note: "动态、二创、小说、小游戏", key: "打开", url: WEB },
  { name: "Asasfans Next", note: "Android · iOS · macOS · Windows", key: "下载", url: NEXT },
];
</script>

<template>
  <ul class="apps">
    <li v-for="app in APPS" :key="app.url" class="app">
      <img class="icon" :src="icon" alt="" draggable="false" />
      <span class="text">
        <b>{{ app.name }}</b>
        <small>{{ app.note }}</small>
      </span>
      <button type="button" class="ui-btn primary" @click="openAboutLink(app.url)">{{ app.key }}</button>
    </li>
  </ul>
</template>

<style scoped>
.apps {
  margin: 0;
  padding: 0;
  list-style: none;
}
.app {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
}
.app:first-child {
  padding-top: 4px;
}
.app:last-child {
  padding-bottom: 0;
}
.app + .app {
  border-top: 1px solid var(--c-100);
}
/* The brand mark keeps its own colours on a white tile. */
.icon {
  flex: none;
  width: 42px;
  height: 42px;
  border-radius: var(--radius-m);
  background: #fff;
  box-shadow: 0 0 0 1px var(--c-100), 0 2px 6px -2px rgba(var(--shadow-rgb), 0.18);
}
.text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.text b {
  font: 800 var(--fs-number)/1.1 var(--font);
  color: var(--ink);
}
.text small {
  font-size: var(--fs-label);
  font-weight: 700;
  line-height: 1.3;
  color: var(--ink-3);
}
.app .ui-btn {
  flex: none;
  min-width: 64px;
}
</style>
