<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { characters, getCharacter } from "../characters";
import { settings } from "../stores/settings";
import { isTauri } from "../composables/tauri";
import { online, status } from "../stores/player";
import { counter } from "../stores/counter";
import { THEME_COLORS, themeSwatch } from "../stores/theme";
import { arrowSelect } from "../ui/focus";
import Icon from "../ui/Icon.vue";
import RangeInput from "../ui/RangeInput.vue";
import PetBust from "./PetBust.vue";

const emit = defineEmits<{ resetPet: [] }>();
const swatches = ref<HTMLElement>();
const serverDraft = ref(settings.serverUrl);
const serverError = ref("");
const portrait = computed(() => getCharacter(settings.character)?.bg);
watch(
  () => settings.serverUrl,
  (url) => {
    serverDraft.value = url;
  },
);

function applyServer() {
  try {
    const url = new URL(serverDraft.value.trim());
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new Error("invalid URL");
    }
    settings.serverUrl = url.toString().replace(/\/+$/, "");
    serverDraft.value = settings.serverUrl;
    serverError.value = "";
  } catch {
    serverError.value = "请输入有效的 HTTP 或 HTTPS 地址";
  }
}
</script>

<template>
  <div class="settings">
    <section class="profile ui-frame ui-ring" data-rise>
      <span class="portrait" aria-hidden="true"><PetBust v-if="portrait" class="bust" :src="portrait" /></span>
      <label class="nick">
        <span>昵称</span>
        <input v-model.trim="settings.nick" class="ui-input" maxlength="24" placeholder="匿名小面包" />
      </label>
      <div class="stats">
        <span><b>{{ counter.total.toLocaleString("en-US") }}</b>累计敲击</span>
        <span><b>{{ status?.totals.activeMinutes ?? "-" }}</b>活跃分钟</span>
        <span><b>{{ status?.resonance.total ?? "-" }}</b>已共鸣</span>
        <span><b>{{ status ? `${status.totals.owned}/${status.totals.items}` : "-" }}</b>收集进度</span>
      </div>
    </section>

    <section data-rise>
      <h4 class="ui-label"><span>主题色</span><em>THEME</em></h4>
      <div ref="swatches" class="themes" role="radiogroup" aria-label="主题色" @keydown="arrowSelect($event, swatches)">
        <button
          v-for="t in THEME_COLORS" :key="t.id" type="button" role="radio"
          class="theme" :class="{ on: settings.themeColor === t.id }"
          :aria-checked="settings.themeColor === t.id" @click="settings.themeColor = t.id"
        >
          <span class="theme-art" :style="{ background: themeSwatch(t) }" aria-hidden="true">
            <PetBust v-if="characters[t.name]" class="theme-bust" :src="characters[t.name]!.bg" />
            <i v-else class="theme-logo"></i>
          </span>
          <b>{{ t.name }}</b>
          <span v-if="settings.themeColor === t.id" class="mark" aria-hidden="true"><Icon name="check" :size="11" /></span>
        </button>
      </div>
    </section>

    <div class="columns">
      <section data-rise>
        <h4 class="ui-label"><span>桌宠表现</span><em>PET</em></h4>
        <div class="ui-group ui-frame ui-ring">
          <label class="ui-row">
            <span>桌宠大小</span>
            <span class="ui-ctl">
              <RangeInput v-model="settings.scale" :min="0.5" :max="2" :step="0.1" />
              <b class="ui-val">×{{ settings.scale.toFixed(1) }}</b>
            </span>
          </label>
          <label class="ui-row">
            <span>表情停留时间</span>
            <span class="ui-ctl">
              <RangeInput v-model="settings.emoteHoldMs" :min="1200" :max="6000" :step="100" />
              <b class="ui-val">{{ (settings.emoteHoldMs / 1000).toFixed(1) }} 秒</b>
            </span>
          </label>
          <label class="ui-row">
            <span>鼠标爪跟随光标</span>
            <input v-model="settings.mouseFollow" class="ui-switch" type="checkbox" />
          </label>
          <label v-if="settings.mouseFollow" class="ui-row">
            <span>跟随灵敏度</span>
            <span class="ui-ctl">
              <RangeInput v-model="settings.mouseSensitivity" :min="0.1" :max="1" :step="0.05" />
              <b class="ui-val">{{ settings.mouseSensitivity.toFixed(2) }}</b>
            </span>
          </label>
          <div class="ui-row">
            <span>桌宠位置</span>
            <button type="button" class="ui-btn small" @click="emit('resetPet')">放回右下角</button>
          </div>
        </div>
      </section>

      <div class="column">
        <section v-if="isTauri" data-rise>
          <h4 class="ui-label"><span>窗口设置</span><em>WINDOW</em></h4>
          <div class="ui-group ui-frame ui-ring">
            <label class="ui-row">
              <span>桌宠置顶</span>
              <input v-model="settings.alwaysOnTop" class="ui-switch" type="checkbox" />
            </label>
            <label class="ui-row">
              <span>点击穿透</span>
              <input v-model="settings.clickThrough" class="ui-switch" type="checkbox" />
            </label>
          </div>
        </section>

        <section data-rise>
          <h4 class="ui-label"><span>服务器连接</span><em>SERVER</em></h4>
          <div class="ui-group ui-frame ui-ring">
            <div class="ui-row">
              <span class="state" :class="{ ok: online }"><i></i>{{ online ? "已连接" : "未连接" }}</span>
              <span class="ui-ctl wide">
                <input v-model.trim="serverDraft" class="ui-input" spellcheck="false" placeholder="http://121.36.224.230:8000" @keydown.enter="applyServer" />
                <button type="button" class="ui-btn" :disabled="serverDraft === settings.serverUrl" @click="applyServer">应用</button>
              </span>
            </div>
            <p v-if="serverError" class="ui-error err" role="alert">{{ serverError }}</p>
            <label class="ui-row">
              <span>敲击同步间隔</span>
              <span class="ui-ctl">
                <RangeInput v-model="settings.batchMs" :min="100" :max="200" :step="10" />
                <b class="ui-val">{{ settings.batchMs }}ms</b>
              </span>
            </label>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.settings > * {
  flex: none;
}

.profile {
  --radius: var(--radius-l);
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 92px;
  padding: 0 8px 0 12px;
  box-sizing: border-box;
  background: var(--surface);
}
/* The current pet rises from a disc cut off by the card's bottom edge. */
.portrait {
  position: relative;
  flex: none;
  align-self: flex-end;
  width: 112px;
  height: 84px;
}
.portrait::before {
  content: "";
  position: absolute;
  left: 50%;
  bottom: -34px;
  width: 104px;
  aspect-ratio: 1;
  border-radius: 50%;
  transform: translateX(-50%);
  background: var(--grad-sky);
}
.bust {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  filter: var(--sticker);
}
.nick {
  flex: 0 1 196px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.nick .ui-input {
  width: 100%;
  height: 34px;
  box-sizing: border-box;
  font: 800 var(--fs-number)/1 var(--font);
}
.stats {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.stats span {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 2px 8px 2px 14px;
  border-left: 1.5px solid var(--line);
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-3);
  white-space: nowrap;
}
.stats b {
  overflow: hidden;
  text-overflow: ellipsis;
  font: 800 var(--fs-heading)/1 var(--font-latin);
  color: var(--ink);
}

/* Each theme is picked by its member, on the gradient that theme paints the sidebar with. */
.themes {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}
.theme {
  position: relative;
  min-width: 0;
  padding: 0;
  border: 0;
  border-radius: var(--radius-m);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  box-shadow: inset 0 0 0 1.5px var(--line-2);
  color: var(--ink);
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out), box-shadow var(--dur-fast);
}
.theme:hover {
  transform: translateY(-2px);
}
.theme.on {
  box-shadow: 0 0 0 2px var(--ink);
}
.theme-art {
  position: relative;
  display: block;
  height: 92px;
  overflow: hidden;
}
.theme-bust {
  position: absolute;
  left: 50%;
  bottom: 0;
  width: 108px;
  height: 82px;
  transform: translateX(-50%);
  filter: var(--contour);
  transition: transform var(--dur-base) var(--ease-out);
}
.theme:hover .theme-bust {
  transform: translateX(-50%) scale(1.06);
  transform-origin: 50% 100%;
}
.theme-logo {
  position: absolute;
  inset: 28px 12px;
  background: var(--surface);
  mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
  -webkit-mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
.theme b {
  padding: 5px 2px 6px;
  font-size: var(--fs-body);
  font-weight: 800;
  line-height: 1.2;
}
.mark {
  position: absolute;
  right: 0;
  top: 0;
  width: 22px;
  height: 20px;
  border-radius: 0 0 0 var(--radius-s);
  background: var(--ink);
  color: var(--on-ink);
  display: flex;
  align-items: center;
  justify-content: center;
}

.columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: start;
}
.column {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.columns .ui-row {
  gap: 10px;
  min-height: 48px;
  padding: 6px 14px;
}
.columns .ui-ctl {
  width: 172px;
}
.columns .ui-ctl.wide {
  width: auto;
  flex: 1;
  min-width: 0;
  gap: 6px;
}
.wide .ui-input {
  flex: 1;
  min-width: 0;
}
.state {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--ink-2);
  font-weight: 800;
}
.state i {
  width: 8px;
  height: 14px;
  background: var(--ink-3);
}
.state.ok i {
  background: var(--ok);
}
.err {
  margin: 0;
  padding: 8px 14px;
}

@container panel (max-width: 860px) {
  .columns {
    grid-template-columns: minmax(0, 1fr);
  }
  .profile {
    flex-wrap: wrap;
    gap: 0 12px;
    padding-top: 10px;
  }
  .portrait {
    align-self: flex-start;
    width: 76px;
    height: 58px;
  }
  .portrait::before {
    bottom: -8px;
    width: 72px;
  }
  .nick {
    flex: 1;
  }
  .stats {
    flex: 0 0 100%;
    margin: 8px 0 10px;
  }
  .theme-art {
    height: 52px;
  }
  .theme-bust {
    width: 60px;
    height: 46px;
  }
  .theme-logo {
    inset: 14px 8px;
  }
}
</style>
