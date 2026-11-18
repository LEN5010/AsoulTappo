<script setup lang="ts">
// The health reminders' settings: all of them on or off, then one row per reminder with its minutes and seconds; a
// row unfolds to its lines. A built-in reminder can be set back to how it ships, a player's own taken off. Under them
// the once-a-day ones. Every edit goes straight to the settings.
import { computed, nextTick, ref } from "vue";
import {
  EVERY_MIN, LINE_MAX, LINES_MAX, NAME_MAX, REMINDERS_MAX, SHOW_SEC, newReminder, presetOf, type Reminder,
} from "../reminders";
import { tryReminder } from "../stores/nudge";
import { settings } from "../stores/settings";
import Icon from "../ui/Icon.vue";
import Modal from "../ui/Modal.vue";

defineEmits<{ close: [] }>();

const list = ref<HTMLElement>();
/** The reminder whose lines are unfolded. */
const open = ref<string | null>(null);
const full = computed(() => settings.reminders.length >= REMINDERS_MAX);
const builtIn = (r: Reminder) => !!presetOf(r.id);

/** A number field left: what was typed, brought into range; anything else puts the old number back. */
function setNumber(r: Reminder, key: "everyMin" | "showSec", e: Event) {
  const field = e.target as HTMLInputElement;
  const range = key === "everyMin" ? EVERY_MIN : SHOW_SEC;
  const n = Math.round(Number(field.value));
  if (field.value.trim() && Number.isFinite(n)) r[key] = Math.min(range.max, Math.max(range.min, n));
  field.value = String(r[key]);
}

function nameLeft(r: Reminder) {
  r.name = r.name.trim() || "我的提醒";
}

async function focusLast(id: string, selector: string) {
  await nextTick();
  const fields = list.value?.querySelectorAll<HTMLInputElement>(`[data-tip="${id}"] ${selector}`);
  fields?.[fields.length - 1]?.focus();
}

function add() {
  const r = newReminder(settings.reminders);
  settings.reminders.push(r);
  open.value = r.id;
  void focusLast(r.id, ".tip-name");
}

function remove(r: Reminder) {
  settings.reminders.splice(settings.reminders.indexOf(r), 1);
}

function reset(r: Reminder) {
  Object.assign(r, presetOf(r.id), { on: r.on });
}

function addLine(r: Reminder) {
  r.lines.push("");
  void focusLast(r.id, ".line .ui-input");
}

function dropLine(r: Reminder, i: number) {
  r.lines.splice(i, 1);
}
</script>

<template>
  <Modal title="健康提醒" heading wide @close="$emit('close')">
    <div class="ui-sections">
      <div class="ui-group ui-frame">
        <label class="ui-row">
          <span>健康提醒</span>
          <input v-model="settings.healthTips" class="ui-switch" type="checkbox" />
        </label>
      </div>

      <section :class="{ dim: !settings.healthTips }" :inert="!settings.healthTips">
        <ul ref="list" class="ui-group ui-frame">
          <li v-for="r in settings.reminders" :key="r.id" :data-tip="r.id">
            <div class="ui-row head">
              <input v-model="r.on" class="ui-switch" type="checkbox" :aria-label="r.name" />
              <button type="button" class="name" :aria-expanded="open === r.id" @click="open = open === r.id ? null : r.id">
                <span>{{ r.name }}</span>
                <Icon name="down" :size="14" />
              </button>
              <label class="num">
                <span>每</span>
                <input
                  class="ui-input" type="text" inputmode="numeric" maxlength="3" :value="r.everyMin" :aria-label="`${r.name}间隔分钟`"
                  @change="setNumber(r, 'everyMin', $event)" @focus="($event.target as HTMLInputElement).select()"
                />
                <span>分钟</span>
              </label>
              <label class="num">
                <span>停留</span>
                <input
                  class="ui-input" type="text" inputmode="numeric" maxlength="3" :value="r.showSec" :aria-label="`${r.name}停留秒数`"
                  @change="setNumber(r, 'showSec', $event)" @focus="($event.target as HTMLInputElement).select()"
                />
                <span>秒</span>
              </label>
            </div>
            <div v-if="open === r.id" class="edit">
              <input
                v-if="!builtIn(r)" v-model="r.name" class="ui-input tip-name" :maxlength="NAME_MAX" placeholder="名称" aria-label="名称"
                @change="nameLeft(r)"
              />
              <div v-for="(_, i) in r.lines" :key="i" class="line">
                <input v-model="r.lines[i]" class="ui-input" :maxlength="LINE_MAX" placeholder="提示内容" :aria-label="`第 ${i + 1} 句`" />
                <button type="button" class="ui-btn small ghost drop" aria-label="删掉这句" :disabled="r.lines.length < 2" @click="dropLine(r, i)">
                  <Icon name="close" :size="14" />
                </button>
              </div>
              <div class="acts">
                <button type="button" class="ui-btn small" :disabled="r.lines.length >= LINES_MAX" @click="addLine(r)">
                  <Icon name="plus" :size="14" />加一句
                </button>
                <button type="button" class="ui-btn small" @click="tryReminder(r)">试一下</button>
                <button v-if="builtIn(r)" type="button" class="ui-btn small ghost" @click="reset(r)">恢复默认</button>
                <button v-else type="button" class="ui-btn small ghost" @click="remove(r)">删除</button>
              </div>
            </div>
          </li>
        </ul>
        <button type="button" class="ui-btn add" :disabled="full" @click="add"><Icon name="plus" :size="14" />加一个提醒</button>
      </section>

      <section :class="{ dim: !settings.healthTips }" :inert="!settings.healthTips">
        <h4 class="ui-label"><span>每天一次</span></h4>
        <div class="ui-group ui-frame">
          <label class="ui-row">
            <span>问好</span>
            <input v-model="settings.tipGreet" class="ui-switch" type="checkbox" />
          </label>
          <label class="ui-row">
            <span>午饭</span>
            <input v-model="settings.tipLunch" class="ui-switch" type="checkbox" />
          </label>
          <label class="ui-row">
            <span>晚安</span>
            <input v-model="settings.tipNight" class="ui-switch" type="checkbox" />
          </label>
        </div>
      </section>
    </div>
  </Modal>
</template>

<style scoped>
.dim {
  opacity: 0.5;
}
section {
  display: flex;
  flex-direction: column;
  transition: opacity var(--dur-fast);
}
/* One reminder: its switch, its name (the key that unfolds its lines), then the two numbers. */
.head {
  justify-content: flex-start;
  gap: 12px;
}
.name {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--ink);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.name span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.name :deep(svg) {
  flex: none;
  color: var(--ink-3);
  transition: rotate var(--dur-fast), color var(--dur-fast);
}
.name:hover :deep(svg) {
  color: var(--ink);
}
.name[aria-expanded="true"] :deep(svg) {
  rotate: 180deg;
}
.num {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--ink-2);
  font-size: var(--fs-label);
  white-space: nowrap;
}
.num .ui-input {
  width: 48px;
  height: 28px;
  padding: 0 4px;
  border-radius: var(--radius-key-s);
  font: 800 var(--fs-body)/1 var(--font-latin);
  text-align: center;
}
/* The lines sit under the name, past the switch. */
.edit {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 18px 14px 72px;
  border-top: 0;
}
.line {
  display: flex;
  align-items: center;
  gap: 8px;
}
.line .ui-input {
  flex: 1;
}
.drop {
  flex: none;
  width: 28px;
  padding: 0;
}
.acts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 2px;
}
.add {
  align-self: flex-start;
  margin-top: 14px;
}
@container panel (max-width: 620px) {
  .head {
    flex-wrap: wrap;
    row-gap: 6px;
  }
  .edit {
    padding-left: 18px;
  }
}
</style>
