<template>
  <div>
    <h1>API Key Pools</h1>
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="spinner">Loading…</div>
    <div v-for="pool in pools" :key="pool.name" class="card" style="margin-bottom: 16px">
      <h3>{{ pool.name }} — {{ pool.available }}/{{ pool.total }} available</h3>
      <DataTable :columns="cols" :rows="pool.keys" />
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { api } from "@/api/client";
import { useApi } from "@/api/useApi";
import DataTable from "@/components/DataTable.vue";

const cols = [
  { key: "display", label: "Key" },
  { key: "used", label: "Used" },
  { key: "limit", label: "Limit" },
  { key: "status", label: "Status" },
  { key: "retry", label: "Retry in" },
];

const { data, error, loading } = useApi(() => api.get("/api/keys/status"), 10000);

const pools = computed(() =>
  Object.entries(data.value || {}).map(([name, pool]) => ({
    name,
    available: pool.available_keys,
    total: pool.total_keys,
    keys: pool.keys.map((k) => ({
      display: k.display,
      used: k.requests_used,
      limit: k.requests_limit,
      status: k.status,
      retry: k.retry_after_seconds ? `${k.retry_after_seconds}s` : "—",
    })),
  }))
);
</script>
