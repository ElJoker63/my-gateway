<template>
  <div class="stat card">
    <div class="label">{{ label }}</div>
    <div class="value">{{ value }}</div>
    <div v-if="sub" class="sub muted">{{ sub }}</div>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], required: true },
  sub: { type: String, default: "" },
});
</script>

<style scoped>
.stat { padding: 16px 18px; }
.label {
  color: var(--text-muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.value {
  font-size: 26px;
  font-weight: 700;
  margin-top: 6px;
  font-variant-numeric: tabular-nums;
}
.sub { font-size: 12px; margin-top: 4px; }
</style>
