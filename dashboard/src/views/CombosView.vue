<template>
  <div>
    <div class="header">
      <h1>Combos</h1>
      <button @click="showForm = !showForm">{{ showForm ? "Cancel" : "+ New combo" }}</button>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <ComboForm v-if="showForm" :providers="providerNames" @saved="onSaved" @cancel="showForm = false" />

    <div v-if="loading" class="spinner">Loading…</div>
    <div v-for="c in combos" :key="c.name" class="card" style="margin-bottom: 12px">
      <div class="header">
        <div>
          <h3 class="mono">combo:{{ c.name }}</h3>
          <div class="muted">
            strategy: {{ c.strategy }}<template v-if="c.strategy === 'race'">, race_size: {{ c.race_size }}</template>
          </div>
        </div>
        <button class="danger" @click="remove(c.name)">Delete</button>
      </div>
      <ul>
        <li v-for="(t, i) in c.targets" :key="i">
          <span class="mono">{{ t.provider }}</span>
          {{ t.model ? ` — ${t.model}` : " (default model)" }}
          <StatusBadge v-if="t.weight > 1" :text="`w${t.weight}`" kind="dim" />
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { api } from "@/api/client";
import { useApi } from "@/api/useApi";
import StatusBadge from "@/components/StatusBadge.vue";
import ComboForm from "@/components/ComboForm.vue";

const { data: comboData, error: e1, loading, refresh } = useApi(() => api.get("/api/combos"));
const { data: keyStatus } = useApi(() => api.get("/api/keys/status"));

const showForm = ref(false);
const error = computed(() => e1.value);

const combos = computed(() => comboData.value?.combos || []);
const providerNames = computed(() => Object.keys(keyStatus.value || {}));

function onSaved() {
  showForm.value = false;
  refresh();
}

async function remove(name) {
  if (!confirm(`Delete combo "${name}"?`)) return;
  await api.del(`/api/combos/${encodeURIComponent(name)}`);
  refresh();
}
</script>

<style scoped>
.header { display: flex; justify-content: space-between; align-items: center; }
</style>
