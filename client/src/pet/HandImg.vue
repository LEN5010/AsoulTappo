<script setup lang="ts">
// A rock-paper-scissors hand as a picture (Fluent Emoji, flat).
import paper from "../assets/duel/paper.svg";
import rock from "../assets/duel/rock.svg";
import scissors from "../assets/duel/scissors.svg";

const SRC: Record<string, string> = { rock, scissors, paper };
defineProps<{ name: string; size?: number }>();
</script>

<template>
  <img :src="SRC[name]" :width="size ?? 24" :height="size ?? 24" draggable="false" alt="" />
</template>
