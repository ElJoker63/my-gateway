<template>
  <button :class="cls" :disabled="disabled || loading" @click="$emit('click', $event)">
    <span v-if="loading" class="spinner-ring" />
    <HugeiconsIcon v-else-if="icon" :icon="icon" :size="16" :stroke-width="1.8" />
    <slot />
  </button>
</template>

<script setup>
import { computed } from "vue";
import { HugeiconsIcon } from "@hugeicons/vue";

const props = defineProps({
  icon: { type: [Array, Object], default: null },
  variant: { type: String, default: "primary" }, // primary | ghost | danger
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  small: { type: Boolean, default: false },
});

defineEmits(["click"]);

const cls = computed(() => ({
  ghost: props.variant === "ghost",
  danger: props.variant === "danger",
  small: props.small,
}));
</script>

<style scoped>
.spinner-ring {
  width: 13px;
  height: 13px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
