<template>
  <span class="badge" :class="kind">
    <span v-if="dot" class="dot" />
    {{ text }}
  </span>
</template>

<script setup>
defineProps({
  text: { type: String, required: true },
  kind: { type: String, default: "dim" }, // ok | warn | err | dim | info
  dot: { type: Boolean, default: false },
});
</script>

<style scoped>
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
</style>
