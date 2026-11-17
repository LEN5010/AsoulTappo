<script setup lang="ts">
// The park's explanation and history sheets (scratch odds, race rules, coin and scratch ledgers): one wide dialog whose
// content sits on the dialog's paper, styled by park-sheet.css. The stylesheet is global so a caller's own rows (its
// tiles, tokens and chips, styled in the caller's scope) take the same look.
import { reducedMotion } from "../../stores/theme";
import Modal from "../../ui/Modal.vue";
import "./park-sheet.css";

defineProps<{ title: string }>();
defineEmits<{ close: [] }>();
</script>

<template>
  <Modal :title="title" heading wide @close="$emit('close')">
    <div class="park-sheet" :class="{ calm: reducedMotion }">
      <slot />
    </div>
  </Modal>
</template>
