<script setup lang="ts">
// One of the legal texts as plain text blocks; the dialog around it shows the title.
import { computed } from "vue";
import { DOCS, parseDoc, type DocName } from "../legal";

const props = defineProps<{ doc: DocName }>();
const blocks = computed(() => parseDoc(DOCS[props.doc]).blocks);
</script>

<template>
  <article class="doc">
    <template v-for="(block, i) in blocks" :key="i">
      <h4 v-if="block.kind === 'heading'">{{ block.text }}</h4>
      <ul v-else-if="block.kind === 'list'">
        <li v-for="(item, j) in block.items" :key="j">{{ item }}</li>
      </ul>
      <p v-else>{{ block.text }}</p>
    </template>
  </article>
</template>

<style scoped>
.doc {
  font: 400 var(--fs-body)/1.75 var(--font);
  color: var(--ink-2);
  user-select: text;
  -webkit-user-select: text;
}
h4 {
  margin: 18px 0 6px;
  font: 800 var(--fs-strong)/1.4 var(--font);
  color: var(--ink);
}
p {
  margin: 0 0 8px;
}
ul {
  margin: 0 0 8px;
  padding-left: 18px;
}
li {
  margin-bottom: 4px;
}
li::marker {
  color: var(--c-500);
}
</style>
