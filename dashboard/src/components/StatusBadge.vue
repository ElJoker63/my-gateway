<template>
  <span class="badge" :class="kind">{{ text }}</span>
</template>

<script setup>
defineProps({
  text: { type: String, required: true },
  kind: { type: String, default: "dim" }, // ok | warn | err | dim
});
</script>
