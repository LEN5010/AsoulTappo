<script setup lang="ts">
// What opens over the photocards' page: its dialogs, a card looked at, and the table a box is opened on.
import { computed } from "vue";
import { manifest } from "../../manifest";
import type { PhotoItem } from "../../photocards";
import type { PhotocardSettled } from "../../stores/photocards";
import PhotoOdds from "./PhotoOdds.vue";
import PhotoOpening from "./PhotoOpening.vue";
import PhotoSwap from "./PhotoSwap.vue";
import PhotoViewer from "./PhotoViewer.vue";
import { photoOver, photoRun, shopSeries } from "./shop";

const name = computed(() => manifest.photocards.find((s) => s.id === shopSeries.value)?.name ?? "");
/** The card just traded for, signed as it opens. */
function signed(item: PhotoItem, settled?: PhotocardSettled) {
  photoOver.value = { kind: "card", item, list: [item], write: true, settled };
}
function step(item: PhotoItem) {
  const over = photoOver.value;
  if (over?.kind === "card") photoOver.value = { kind: "card", item, list: over.list };
}
</script>

<template>
  <PhotoOdds v-if="photoOver?.kind === 'odds'" :series="shopSeries" :name="name" @close="photoOver = null" />
  <PhotoSwap v-else-if="photoOver?.kind === 'swap'" :series="shopSeries" @close="photoOver = null" @swapped="signed" />
  <PhotoViewer
    v-else-if="photoOver?.kind === 'card'" :item="photoOver.item" :list="photoOver.list" :from="photoOver.from"
    :write="photoOver.write" :settled="photoOver.settled" @step="step" @close="photoOver = null"
  />
  <PhotoOpening v-if="photoRun" :run="photoRun" />
</template>
