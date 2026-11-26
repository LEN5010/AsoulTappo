<script setup lang="ts">
// macOS: over the pet while the hook has neither Input Monitoring nor Accessibility, so it cannot
// hear other apps. A grant only counts after a restart, so the key turns into one once the settings were opened.
// A grant made for a build signed differently shows as on in the settings and does not count: the entry has to be
// removed and added again. [closable] false: it stays (the run the first-run guide starts in).
import { ref } from "vue";
import { openInputSettings } from "../composables/tauri";
import { useCentredShift, type PetMiddle } from "./centredShift";

const props = withDefaults(defineProps<{ closable?: boolean; middle?: PetMiddle }>(), { closable: true });
const emit = defineEmits<{ close: [] }>();
const paper = ref<HTMLElement>();
const shift = useCentredShift(paper, () => props.middle);
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
    <div ref="paper" class="access" data-hit="keep" data-no-drag role="alert" :style="{ '--shift': `${shift}px` }">
      <p>需要输入监控权限</p>
      <small>已开启仍提示：删除条目后重新添加</small>
      <div class="actions">
        <button v-if="opened" type="button" class="ui-btn small primary" @click="restart">重启</button>
        <button type="button" class="ui-btn small" :class="{ primary: !opened }" @click="open">打开设置</button>
        <button v-if="closable" type="button" class="ui-btn small ghost" aria-label="关闭" title="关闭" @click="emit('close')">×</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.anchor { position: absolute; left: 50%; top: 0; width: 0; height: 0; z-index: 6; }
.access {
  position: absolute; left: 0; bottom: 8px; width: max-content; max-width: 240px; padding: 8px 10px;
  transform: translateX(calc(-50% + var(--shift, 0px))); border-radius: 14px; background: var(--surface);
  box-shadow: 0 6px 16px -6px rgba(var(--shadow-rgb), 0.4); color: var(--ink);
}
/* The point stays on the pet when the paper shifts. */
.access::after {
  content: ""; position: absolute; left: calc(50% - var(--shift, 0px)); top: 100%; translate: -50% 0;
  border: 7px solid transparent; border-top-color: var(--surface); border-bottom: 0;
}
.access p { margin: 0 0 2px; font: 800 var(--fs-label)/1.35 var(--font); }
.access small { display: block; margin: 0 0 6px; font: 700 var(--fs-caption)/1.35 var(--font); color: var(--ink-2); }
.actions { display: flex; align-items: center; gap: 6px; }
.actions .ghost { margin-left: auto; }
</style>
