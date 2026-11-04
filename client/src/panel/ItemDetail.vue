<script setup lang="ts">
import { computed } from "vue";
import { craftCost, isOwned, KIND_LABEL, RARITY_LABEL, type Item } from "../items";
import { getCard } from "../manifest";
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

function goCraft() {
  emit("close");
  openPanel("dex", { craftTarget: props.item.id });
}
</script>

<template>
  <Modal :title="item.name" :wide="!!card" @close="emit('close')">
    <div class="detail" :class="`r-${item.rarity ?? 'none'}`">
      <div class="stage ui-frame">
        <template v-if="card && owned">
          <video v-if="card.video" :src="assetUrl(card.video)" :poster="assetUrl(card.thumb)" controls playsinline preload="none"></video>
          <img v-else :src="assetUrl(card.full)" :style="{ backgroundImage: `url(${assetUrl(card.thumb)})` }" :alt="item.name" />
        </template>
        <ItemArt v-else :item="item" :size="180" :locked="!owned" />
      </div>
      <div class="chips">
        <span class="ui-tag">{{ card ? (card.tier === "big" ? "大隐藏" : card.tier === "small" ? "小隐藏" : "普通款") : item.rarity ? RARITY_LABEL[item.rarity] : "初始" }}</span>
        <span class="ui-tag dark">{{ KIND_LABEL[item.kind] }}</span>
        <span v-if="item.characters.length" class="ui-tag dark">{{ item.characters.join(" / ") }}</span>
      </div>
      <h3>{{ item.name }}</h3>
      <p class="ui-muted">{{ item.group }}</p>
      <p v-if="owned" class="state ok">已拥有<template v-if="count > 1"> ×{{ count }}</template></p>
      <template v-else>
        <p v-if="card" class="state">在「{{ item.group }}」卡池中抽取获得</p>
        <p v-else-if="cost !== null" class="state">开宝箱获得，或使用 {{ cost }} 碎片兑换（当前 {{ shards }} 碎片）</p>
        <button v-if="cost !== null" type="button" class="ui-btn primary" @click="goCraft">前往兑换</button>
      </template>
    </div>
  </Modal>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;
}
.stage {
  --cut: 18px;
  width: 100%;
  min-height: 200px;
  display: grid;
  place-items: center;
  background: var(--dots) 0 0 / 10px 10px, var(--accent-tint);
  padding: 12px;
  box-sizing: border-box;
}
.stage video,
.stage img {
  width: 100%;
  max-height: 360px;
  object-fit: contain;
  background: center / contain no-repeat;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 4px;
}
h3 {
  margin: 2px 0 0;
  font: 400 22px/1.1 var(--font-display);
}
p {
  margin: 0;
  font-size: 13px;
}
.state {
  color: var(--ink-2);
  font-weight: 700;
}
.state.ok {
  color: var(--ok);
  font-weight: 800;
}
</style>
