<template>
  <div class="card combo-form">
    <h3>Create combo</h3>
    <div v-if="error" class="error-banner">{{ error }}</div>

    <div class="form-row">
      <input v-model="name" placeholder="name (e.g. fast)" />
      <select v-model="strategy">
        <option v-for="s in strategies" :key="s" :value="s">{{ s }}</option>
      </select>
      <input
        v-if="strategy === 'race'"
        v-model.number="raceSize"
        type="number"
        min="2"
        max="8"
        style="max-width: 100px"
      />
    </div>

    <div v-for="(t, i) in targets" :key="i" class="form-row">
      <select v-model="t.provider">
        <option value="">— provider —</option>
        <option v-for="p in providers" :key="p" :value="p">{{ p }}</option>
      </select>
      <input v-model="t.model" placeholder="model (optional)" />
      <button class="ghost" @click="targets.splice(i, 1)" :disabled="targets.length <= 1">✕</button>
    </div>

    <div style="display: flex; gap: 10px">
      <button class="ghost" @click="targets.push({ provider: '', model: '' })">+ target</button>
      <button @click="save" :disabled="!name || saving">{{ saving ? "Saving…" : "Save" }}</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { api } from "@/api/client";

defineProps({ providers: { type: Array, required: true } });
const emit = defineEmits(["saved", "cancel"]);

const strategies = ["strict", "round_robin", "least_used", "race"];

const name = ref("");
const strategy = ref("strict");
const raceSize = ref(2);
const targets = ref([{ provider: "", model: "" }]);
const error = ref("");
const saving = ref(false);

async function save() {
  error.value = "";
  saving.value = true;
  try {
    await api.post("/api/combos", {
      name: name.value,
      strategy: strategy.value,
      race_size: raceSize.value,
      targets: targets.value
        .filter((t) => t.provider)
        .map((t) => ({ provider: t.provider, model: t.model || null })),
    });
    emit("saved");
  } catch (e) {
    error.value = e.message;
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.combo-form { margin: 16px 0; }
</style>
