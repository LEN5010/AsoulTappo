<script setup lang="ts">
// Over the pet once an elevated program (a game run as administrator) has stayed in front: the pet cannot hear
// its keys and clicks unless it runs as administrator too. Stays until closed or acted on.
import { computed, ref } from "vue";
import { setRunAsAdmin, type InputBlocked } from "../composables/tauri";

const props = defineProps<{ hint: InputBlocked }>();
const emit = defineEmits<{ close: [] }>();
const name = computed(() => (props.hint.by ?? "").replace(/\.exe$/i, ""));
const busy = ref(false);
const note = ref("");

async function restart() {
  busy.value = true;
  note.value = "";
  try {
    if ((await setRunAsAdmin(true)) === "restarting") note.value = "正在重启";
    else emit("close");
  } catch (e) {
    note.value = String(e) === "cancelled" ? "已取消" : "没能重启";
    busy.value = false;
  }
}
</script>

<template>
  <div class="anchor">
    <div class="admin" data-hit data-no-drag role="alert">
      <p>{{ name }} 以管理员身份运行，桌宠收不到按键</p>
      <div class="actions">
        <button v-if="hint.canElevate" type="button" class="ui-btn small primary" :disabled="busy" @click="restart">以管理员身份重启</button>
        <small v-else>当前账户没有管理员权限</small>
        <small v-if="note" role="status">{{ note }}</small>
        <button type="button" class="ui-btn small ghost" aria-label="关闭" title="关闭" @click="emit('close')">×</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.anchor { position: absolute; left: 50%; top: 0; width: 0; height: 0; z-index: 6; }
.admin {
  position: absolute; left: 0; bottom: 8px; width: max-content; max-width: 240px; padding: 8px 10px;
  transform: translateX(-50%); border-radius: 14px; background: var(--surface);
  box-shadow: 0 6px 16px -6px rgba(var(--shadow-rgb), 0.4); color: var(--ink);
}
.admin::after {
  content: ""; position: absolute; left: 50%; top: 100%; translate: -50% 0;
  border: 7px solid transparent; border-top-color: var(--surface); border-bottom: 0;
}
.admin p { margin: 0 0 6px; font: 800 var(--fs-label)/1.35 var(--font); }
.actions { display: flex; align-items: center; gap: 6px; }
.actions small { font: 700 var(--fs-label)/1.3 var(--font); color: var(--ink-2); }
.actions .ghost { margin-left: auto; }
</style>
