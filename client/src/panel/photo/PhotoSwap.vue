<script setup lang="ts">
// Repeat signed cards put by are traded for one the save lacks: one is picked, then it is signed.
import { computed, onMounted, ref } from "vue";
import { characterColor } from "../../manifest";
import { photoItemsOf, type PhotoItem } from "../../photocards";
import { photoError, photoSwapping, photoView, swapPhoto, type PhotocardSettled } from "../../stores/photocards";
import { online } from "../../stores/player";
import Icon from "../../ui/Icon.vue";
import Modal from "../../ui/Modal.vue";
import PhotoThumb from "./PhotoThumb.vue";
import { photoName } from "./labels";

const props = defineProps<{ series: string }>();
const emit = defineEmits<{ close: []; swapped: [item: PhotoItem, settled?: PhotocardSettled] }>();

const view = computed(() => photoView(props.series));
const need = computed(() => view.value.cfg?.swap ?? 0);
const groups = computed(() => {
  const out = new Map<string, PhotoItem[]>();
  for (const item of photoItemsOf(props.series, "sign")) {
    const who = item.characters[0] ?? "";
    out.set(who, [...(out.get(who) ?? []), item]);
  }
  return [...out].map(([who, items]) => ({ who, color: characterColor(who), items }));
});
const picked = ref<PhotoItem | null>(null);
const held = (item: PhotoItem) => view.value.owned.has(item.id);
const can = computed(() => !!picked.value && !held(picked.value) && view.value.canSwap && online.value && !photoSwapping.value);
async function swap() {
  const item = picked.value;
  if (!item || !can.value) return;
  const made = await swapPhoto(item.id);
  if (made) emit("swapped", item, made.settled);
}
onMounted(() => { photoError.value = ""; });
</script>

<template>
  <Modal title="换签名" heading wide :locked="photoSwapping" @close="emit('close')">
    <div class="swap">
      <div class="groups">
        <section v-for="g in groups" :key="g.who" class="group">
          <h4><i :style="{ background: g.color }" aria-hidden="true"></i>{{ g.who }}</h4>
          <div class="cards" role="group" :aria-label="g.who">
            <button
              v-for="item in g.items" :key="item.id" type="button" class="card" :class="{ held: held(item), on: picked?.id === item.id }"
              :disabled="held(item) || photoSwapping" :aria-pressed="picked?.id === item.id" :aria-label="photoName(item)" :title="photoName(item)"
              @click="picked = item"
            >
              <PhotoThumb :item="item" />
              <span v-if="held(item)" class="got"><Icon name="check" :size="12" /></span>
            </button>
          </div>
        </section>
      </div>
      <p v-if="photoError" class="ui-error" role="alert">{{ photoError }}</p>
      <footer class="foot">
        <p class="have">
          <Icon name="swap" :size="16" />重复的签名<b>{{ view.spare }}</b><i>/ {{ need }}</i>
          <span class="cells" aria-hidden="true"><i v-for="k in need" :key="k" :class="{ on: k <= view.spare }"></i></span>
        </p>
        <button type="button" class="ui-btn primary large" :class="{ pulse: can }" :disabled="!can" @click="swap">
          <Icon name="pencil" :size="16" />{{ picked ? `换${photoName(picked)}` : "换签名" }}
        </button>
      </footer>
    </div>
  </Modal>
</template>

<style scoped>
.swap {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.have {
  display: flex;
  align-items: baseline;
  gap: 5px;
  margin: 0;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink-2);
}
.have svg {
  align-self: center;
  color: var(--gold);
}
.have b {
  margin-left: 4px;
  font: 800 20px/1 var(--font-latin);
  color: var(--ink);
}
.have > i {
  font: 800 var(--fs-strong)/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.cells {
  display: flex;
  gap: 3px;
  align-self: center;
  margin-left: 10px;
}
.cells i {
  width: 18px;
  height: 11px;
  border-radius: 2px;
  background: var(--c-100);
}
.cells i.on {
  background: var(--grad-gold);
}
.groups {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(164px, 1fr));
  gap: 12px;
}
.group {
  padding: 12px 14px 16px;
  border-radius: 14px;
  background: var(--c-50);
}
h4 {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 10px;
  font: 800 var(--fs-strong)/1 var(--font);
}
h4 i {
  width: 4px;
  height: 14px;
}
.cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.card {
  position: relative;
  padding: 3px;
  border: 0;
  border-radius: 4px;
  background: linear-gradient(160deg, var(--gold-soft), #fff 34%, var(--gold-soft) 78%, var(--gold));
  box-shadow: 0 6px 14px -8px rgba(var(--shadow-rgb), 0.45);
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base);
}
.card:hover:not(:disabled) {
  transform: translateY(-3px);
}
.card.on {
  transform: translateY(-4px);
  box-shadow: 0 0 0 3px var(--c-500), 0 12px 20px -10px rgba(var(--shadow-rgb), 0.5);
}
.card.held {
  background: var(--c-100);
  box-shadow: none;
  cursor: default;
}
.card.held :deep(img) {
  filter: var(--dim);
}
.got {
  position: absolute;
  inset: auto auto 50% 50%;
  translate: -50% 50%;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--surface);
  color: var(--c-700);
  box-shadow: 0 2px 6px rgba(var(--shadow-rgb), 0.3);
}
.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
</style>
