<template>
  <div class="bar-row">
    <span class="mono">{{ label }}</span>
    <div class="bar-track">
      <div class="bar-fill" :style="{ width: `${pct}%` }" />
    </div>
    <span class="muted">{{ display }}</span>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  label: { type: String, required: true },
  value: { type: Number, default: null },
  max: { type: Number, required: true },
});

const pct = computed(() => {
  if (!props.value || !props.max) return 0;
  return Math.min(100, (props.value / props.max) * 100).toFixed(1);
});

const display = computed(() => (props.value != null ? `${props.value} ms` : "—"));
</script>
