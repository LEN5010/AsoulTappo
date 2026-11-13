<script setup lang="ts">
// Redeem codes (protocol/PROTOCOL.md 游乐园): the redeem work fills this in.
import Modal from "../../ui/Modal.vue";

const emit = defineEmits<{ close: [] }>();
</script>

<template>
  <Modal title="兑换码" heading @close="emit('close')"></Modal>
</template>
