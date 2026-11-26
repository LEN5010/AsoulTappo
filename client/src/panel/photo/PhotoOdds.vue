<script setup lang="ts">
// The odds of a series' boxes: a row a kind with what one bag gives, what is promised and what a repeat turns into.
import { computed } from "vue";
import { photoItemsOf, photoOdds, type PhotoItemKind } from "../../photocards";
import { photoView } from "../../stores/photocards";
import Icon from "../../ui/Icon.vue";
import Modal from "../../ui/Modal.vue";
import { PHOTO_KIND_LABEL } from "./labels";
import { oddsText } from "./odds";

const props = defineProps<{ series: string; name: string }>();
const emit = defineEmits<{ close: [] }>();

const ORDER: readonly PhotoItemKind[] = ["sign", "group", "duo", "solo"];
const cfg = computed(() => photoView(props.series).cfg);
const odds = computed(() => (cfg.value ? photoOdds(cfg.value) : null));
/** With every signed card there, signed repeats turn into shards like the others. */
const allSigned = computed(() => photoItemsOf(props.series, "sign").every((i) => photoView(props.series).owned.has(i.id)));
const rows = computed(() => ORDER.map((kind) => ({
  kind, label: PHOTO_KIND_LABEL[kind], count: photoItemsOf(props.series, kind).length,
  rate: odds.value ? oddsText(kind === "solo" ? 100 - odds.value.rare : odds.value[kind]) : "",
  traded: kind === "sign" && !allSigned.value,
  shards: cfg.value?.refund[kind === "solo" ? "solo" : "rare"] ?? 0,
})));
</script>

<template>
  <Modal :title="`${name}小卡概率`" heading @close="emit('close')">
    <table v-if="cfg && odds" class="rates">
      <thead><tr><th>类型</th><th>款数</th><th>单张概率</th><th>保底</th><th>重复</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.kind" :class="r.kind">
          <td><span class="kind"><i class="swatch" aria-hidden="true"></i>{{ r.label }}</span></td>
          <td class="num">{{ r.count }}</td>
          <td class="num cur">{{ r.rate }}</td>
          <td class="pity"><span v-if="r.kind === 'sign'" class="pill">{{ cfg.signPity }} 盒</span><template v-else>—</template></td>
          <td class="back">
            <template v-if="r.traded">{{ cfg.swap }} 张换 1 张</template>
            <span v-else class="shards"><Icon name="shard" :size="12" />{{ r.shards }}</span>
          </td>
        </tr>
        <tr class="sum">
          <td><span class="kind"><i class="swatch" aria-hidden="true"></i>稀有合计</span></td>
          <td class="num">{{ rows.reduce((n, r) => n + (r.kind === "solo" ? 0 : r.count), 0) }}</td>
          <td class="num cur">{{ oddsText(odds.rare) }}</td>
          <td class="pity"><span class="pill">每盒 1 张</span></td>
          <td class="back">—</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="wait" role="status">连接服务器后显示</p>
  </Modal>
</template>

<style scoped>
/* The table of the resonance page's odds (ResonancePage.vue). */
.rates {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-body);
}
th {
  padding: 2px 8px 9px;
  border-bottom: 1px solid var(--c-200);
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-3);
  text-align: right;
  white-space: nowrap;
}
th:first-child {
  text-align: left;
}
td {
  padding: 9px 8px;
  border-bottom: 1px solid var(--c-100);
  font-weight: 700;
  color: var(--ink);
  white-space: nowrap;
}
tbody tr:last-child td {
  border-bottom: 0;
}
.kind {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.swatch {
  flex: none;
  width: 4px;
  height: 13px;
  border-radius: 2px;
  background: var(--swatch, var(--c-200));
}
.sign {
  --swatch: var(--grad-gold);
  background: linear-gradient(90deg, color-mix(in oklab, var(--gold-soft) 28%, var(--surface)), transparent 80%);
}
.sign .kind {
  font-weight: 800;
}
.group { --swatch: var(--c-800); }
.duo { --swatch: var(--c-500); }
.solo { --swatch: var(--c-300); }
.sum .kind,
.sum .num {
  color: var(--ink-2);
}
.num {
  text-align: right;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
}
.num.cur {
  color: var(--ink);
}
.pity,
.back {
  text-align: right;
  font: 800 var(--fs-label)/1 var(--font);
  color: var(--ink-3);
}
.back {
  color: var(--ink-2);
}
.shards {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
}
.shards svg {
  color: var(--c-700);
}
.pill {
  display: inline-block;
  padding: 3px 7px;
  border-radius: var(--radius-s);
  background: var(--c-100);
  color: var(--ink-2);
  font: 800 var(--fs-caption)/1 var(--font);
  font-variant-numeric: tabular-nums;
}
.sign .pill {
  background: color-mix(in oklab, var(--gold-soft) 45%, var(--surface));
  color: var(--ink);
}
.wait {
  margin: 0;
  padding: 16px 0 8px;
  text-align: center;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink-3);
}
</style>
