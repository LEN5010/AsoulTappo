<script setup lang="ts">
// The reverse of a card, sealed until the draw scene turns it over.
</script>

<template>
  <span class="back" aria-hidden="true">
    <span class="edition">RESONANCE COLLECTION</span>
    <i class="record"></i>
    <i class="mark"></i>
    <span class="signature">此间共鸣</span>
  </span>
</template>

<style scoped>
.back {
  position: absolute;
  inset: 0;
  display: block;
  overflow: hidden;
  border-radius: 5px;
  color: #d9bd88;
  background: repeating-linear-gradient(125deg, transparent 0 13px, rgba(217, 189, 136, .035) 13px 14px), linear-gradient(145deg, #293943, #14212b 64%);
  box-shadow: inset 0 0 0 1px rgba(217, 189, 136, .55), inset 0 0 0 4px #17242e;
}
.back::before { content: ''; position: absolute; inset: 11px; border: 1px solid rgba(217, 189, 136, .3); border-radius: 2px; }
.edition, .signature { position: absolute; left: 12%; right: 12%; text-align: center; }
.edition { top: 10%; font: 800 clamp(7px, 1cqw, 10px)/1.5 var(--font-latin); letter-spacing: .2em; }
.signature { bottom: 12%; font: 500 clamp(10px, 1.4cqw, 14px)/1 var(--font); letter-spacing: .3em; }
.record { position: absolute; width: 76%; aspect-ratio: 1; left: 12%; top: 27%; border: 1px solid rgba(217, 189, 136, .2); border-radius: 50%; box-shadow: 0 0 0 9px rgba(217, 189, 136, .035), inset 0 0 0 9px rgba(217, 189, 136, .035); }
.mark {
  position: absolute;
  left: 23%;
  right: 23%;
  top: 50%;
  aspect-ratio: 3.172;
  background: currentColor;
  transform: translateY(-50%);
  mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
  -webkit-mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
</style>
