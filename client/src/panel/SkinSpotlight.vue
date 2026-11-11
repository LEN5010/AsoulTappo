<script setup lang="ts">
// The launch spotlight (stores/spotlight.ts): the release's new skins, once per device.
import Modal from "../ui/Modal.vue";
import Icon from "../ui/Icon.vue";
import SkinArt from "./SkinArt.vue";
import { characterColor, memberOf, skinTitle } from "../manifest";
import { readSpotlight, spotlight, spotlightShown } from "../stores/spotlight";
import { ui } from "../stores/ui";

const TILTS = [-3, 2.2, -1.4, 3.2];
function resonate() {
  ui.page = "resonance";
  readSpotlight();
}
</script>

<template>
  <Modal v-if="spotlight && spotlightShown" :key="spotlight.id" :title="spotlight.title" heading wide @close="readSpotlight">
    <span class="ui-tag gold">新皮肤</span>
    <ul class="lineup">
      <li v-for="(name, i) in spotlight.skins" :key="name" :style="{ '--tilt': `${TILTS[i % TILTS.length]}deg`, '--i': i }">
        <SkinArt :name="name" owned />
        <b>{{ skinTitle(name) }}</b>
        <small><i :style="{ background: characterColor(name) }" aria-hidden="true"></i>{{ memberOf(name) }}</small>
      </li>
    </ul>
    <div class="acts">
      <button type="button" class="ui-btn primary" @click="resonate"><Icon name="spark" :size="15" />去共鸣</button>
    </div>
  </Modal>
</template>

<style scoped>
.lineup {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 18px;
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
}
.lineup li {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  animation: deal var(--dur-slow) var(--ease-out) both;
  animation-delay: calc(var(--i) * 90ms + 120ms);
}
.lineup li :deep(.skin-art) { transform: rotate(var(--tilt)); }
.lineup b { margin-top: 8px; font-size: var(--fs-strong); font-weight: 800; }
.lineup small { display: flex; align-items: center; gap: 5px; color: var(--ink-2); font-size: var(--fs-label); }
.lineup small i { width: 3px; height: 10px; }
@keyframes deal {
  from { opacity: 0; transform: translateY(18px); }
}
@media (prefers-reduced-motion: reduce) {
  .lineup li { animation: none; }
}
.acts {
  display: flex;
  justify-content: flex-end;
  margin-top: 22px;
}
.acts .primary {
  min-width: 96px;
}
</style>
