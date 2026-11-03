<script setup lang="ts">
import { computed } from "vue";
import { craftCost, isOwned, KIND_LABEL, RARITY_LABEL, type Item } from "../items";
import { getCard, manifest } from "../manifest";
import { assetUrl } from "../asset";
import { collection, shards, unlocked } from "../stores/player";
import { openPanel } from "../stores/ui";
import Modal from "../ui/Modal.vue";
import ItemArt from "../ui/ItemArt.vue";

const props = defineProps<{ item: Item }>();
const emit = defineEmits<{ close: [] }>();
const owned = computed(() => isOwned(props.item, { owned: collection.owned, unlocked: unlocked.value }));
const count = computed(() => collection.owned[props.item.id] ?? 0);
const card = computed(() => (props.item.kind === "card" ? getCard(props.item.ref) : undefined));
const cost = computed(() => craftCost(props.item));
const unlockText = computed(() => {
  const d = manifest.decor.find((x) => x.id === props.item.ref);
  return d ? `收集「${props.item.group}」${d.unlock.min} 张卡牌后解锁` : "";
});
function goCraft() {
  emit("close");
  openPanel("craft", { craftTarget: props.item.id });
}
</script>

<template>
  <Modal :title="item.name" :wide="!!card" @close="emit('close')">
    <div class="detail" :class="`r-${item.rarity ?? 'none'}`">
      <div class="stage">
        <template v-if="card && owned">
          <video v-if="card.video" :src="assetUrl(card.video)" :poster="assetUrl(card.thumb)" controls playsinline preload="none"></video>
          <img v-else :src="assetUrl(card.full)" :style="{ backgroundImage: `url(${assetUrl(card.thumb)})` }" :alt="item.name" />
        </template>
        <ItemArt v-else :item="item" :size="168" :locked="!owned" />
      </div>
      <div class="chips">
        <span class="chip rar">{{ item.rarity ? RARITY_LABEL[item.rarity] : item.starter ? "初始" : "解锁" }}</span>
        <span class="chip">{{ KIND_LABEL[item.kind] }}</span>
        <span v-if="item.characters.length" class="chip">{{ item.characters.join(" / ") }}</span>
      </div>
      <h3>{{ owned ? item.name : "未获得" }}</h3>
      <p class="ui-muted">{{ item.group }}</p>
      <p v-if="owned" class="state ok">已拥有<template v-if="count > 1"> ×{{ count }}</template></p>
      <template v-else>
        <p v-if="unlockText" class="state">{{ unlockText }}</p>
        <p v-else-if="cost !== null" class="state">开宝箱获得，或用 {{ cost }} 碎片合成（现有 {{ shards }}）</p>
        <button v-if="cost !== null" type="button" class="ui-btn primary" @click="goCraft">去合成</button>
      </template>
    </div>
  </Modal>
</template>

<style scoped>
.detail { display: flex; flex-direction: column; align-items: center; gap: 8px; text-align: center; }
.stage { width: 100%; min-height: 190px; display: grid; place-items: center; border-radius: var(--r-l); background: var(--rar-none-bg); padding: 12px; box-sizing: border-box; }
.r-common .stage { background: var(--rar-common-bg); } .r-rare .stage { background: var(--rar-rare-bg); }
.r-epic .stage { background: var(--rar-epic-bg); } .r-legendary .stage { background: var(--rar-legendary-bg); }
.stage video, .stage img { width: 100%; max-height: 360px; object-fit: contain; border-radius: var(--r-m); background: center / contain no-repeat; }
.chips { display: flex; flex-wrap: wrap; gap: 4px; justify-content: center; }
.chip { font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: var(--r-s); background: var(--paper-2); color: var(--ink-2); }
.chip.rar { background: rgba(var(--accent-rgb), 0.14); color: var(--ink); }
h3 { margin: 2px 0 0; font-size: 16px; font-weight: 700; }
p { margin: 0; font-size: 13px; }
.state { color: var(--ink-2); }
.state.ok { color: var(--ok); font-weight: 600; }
</style>
