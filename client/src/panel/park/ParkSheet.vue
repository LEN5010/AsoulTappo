<script setup lang="ts">
// The park's explanation sheets (the scratch odds, the race rules): one wide dialog whose content is rows on the
// dialog's paper, styled by park-sheet.css. The stylesheet is global so a caller's own rows (its tiles, tokens and
// chips, styled in the caller's scope) take the same look.
import Modal from "../../ui/Modal.vue";
import "./park-sheet.css";

defineProps<{ title: string }>();
defineEmits<{ close: [] }>();
</script>

<template>
  <Modal :title="title" heading wide @close="$emit('close')">
    <div class="park-sheet">
      <slot />
    </div>
  </Modal>
</template>
