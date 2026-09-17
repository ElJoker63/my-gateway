<template>
  <div>
    <h1>Providers</h1>
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="spinner">Loading…</div>
    <div class="card">
      <DataTable :columns="cols" :rows="rows" />
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { api } from "@/api/client";
import { useApi } from "@/api/useApi";
import DataTable from "@/components/DataTable.vue";

const cols = [
  { key: "name", label: "Provider" },
  { key: "total", label: "Keys" },
  { key: "available", label: "Available" },
  { key: "rpm", label: "RPM/key" },
  { key: "circuit", label: "Circuit" },
];

const { data: keyStatus, error: e1, loading: l1 } = useApi(() => api.get("/api/keys/status"));
const { data: metrics } = useApi(() => api.get("/api/metrics"));

const rows = computed(() => {
  const circuits = metrics.value?.circuit_states || {};
  return Object.entries(keyStatus.value || {}).map(([name, pool]) => ({
    name,
    total: pool.total_keys,
    available: pool.available_keys,
    rpm: pool.rpm_per_key,
    circuit: circuits[name]?.state || "closed",
  }));
});

const error = computed(() => e1.value);
const loading = computed(() => l1.value && !keyStatus.value);
</script>
