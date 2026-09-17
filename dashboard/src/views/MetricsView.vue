<template>
  <div>
    <h1>Metrics</h1>
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="spinner">Loading…</div>
    <template v-else>
      <div class="stat-grid">
        <StatCard label="Requests" :value="data?.total_requests ?? 0" />
        <StatCard label="Errors" :value="data?.total_errors ?? 0"
          :sub="`${((data?.error_rate ?? 0) * 100).toFixed(2)}% rate`" />
        <StatCard label="Races" :value="data?.total_races ?? 0"
          :sub="`${((data?.race_win_rate ?? 0) * 100).toFixed(1)}% first-target wins`" />
        <StatCard label="Providers active" :value="Object.keys(data?.providers || {}).length" />
      </div>

      <div class="card">
        <h3>Latency percentiles (rolling window)</h3>
        <LatencyBar
          v-for="row in latencyRows"
          :key="row.key"
          :label="row.key"
          :value="row.p95_ms"
          :max="maxP95"
        />
      </div>

      <div class="card" style="margin-top: 16px">
        <h3>Providers</h3>
        <DataTable :columns="provCols" :rows="provRows" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { api } from "@/api/client";
import { useApi } from "@/api/useApi";
import StatCard from "@/components/StatCard.vue";
import LatencyBar from "@/components/LatencyBar.vue";
import DataTable from "@/components/DataTable.vue";

const { data, error, loading } = useApi(() => api.get("/api/metrics"), 5000);

const latencyRows = computed(() =>
  Object.entries(data.value?.latency || {})
    .map(([key, v]) => ({ key, ...v }))
    .sort((a, b) => (b.count || 0) - (a.count || 0))
);

const maxP95 = computed(() => Math.max(1, ...latencyRows.value.map((r) => r.p95_ms || 0)));

const provCols = [
  { key: "name", label: "Provider" },
  { key: "requests", label: "Requests" },
  { key: "errors", label: "Errors" },
  { key: "tokens", label: "Tokens" },
  { key: "models", label: "Models" },
];

const provRows = computed(() =>
  Object.entries(data.value?.providers || {}).map(([name, p]) => ({
    name,
    requests: p.requests,
    errors: p.errors,
    tokens: p.tokens,
    models: (p.models || []).join(", ") || "—",
  }))
);
</script>
