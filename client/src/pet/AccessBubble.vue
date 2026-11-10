<script setup lang="ts">
// macOS: over the pet while the hook has neither Input Monitoring nor Accessibility, so it cannot
// hear other apps. A grant only counts after a restart, so the key turns into one once the settings were opened.
import { ref } from "vue";
import { openInputSettings } from "../composables/tauri";

const emit = defineEmits<{ close: [] }>();
const opened = ref(false);
function open() {
  void openInputSettings();
  opened.value = true;
}
async function restart() {
  const { relaunch } = await import("@tauri-apps/plugin-process");
  await relaunch();
}
</script>

<template>
  <div class="anchor">
    <div class="access" data-hit data-no-drag role="alert">
      <p>需要输入监控权限</p>
      <div class="actions">
        <button v-if="opened" type="button" class="ui-btn small primary" @click="restart">重启</button>
        <button type="button" class="ui-btn small" :class="{ primary: !opened }" @click="open">打开设置</button>
        <button type="button" class="ui-btn small ghost" aria-label="关闭" title="关闭" @click="emit('close')">×</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.anchor { position: absolute; left: 50%; top: 0; width: 0; height: 0; z-index: 6; }
.access {
  position: absolute; left: 0; bottom: 8px; width: max-content; max-width: 240px; padding: 8px 10px;
  transform: translateX(-50%); border-radius: 14px; background: var(--surface);
  box-shadow: 0 6px 16px -6px rgba(var(--shadow-rgb), 0.4); color: var(--ink);
}
.access::after {
  content: ""; position: absolute; left: 50%; top: 100%; translate: -50% 0;
  border: 7px solid transparent; border-top-color: var(--surface); border-bottom: 0;
}
.access p { margin: 0 0 6px; font: 800 var(--fs-label)/1.35 var(--font); }
.actions { display: flex; align-items: center; gap: 6px; }
.actions .ghost { margin-left: auto; }
</style>
