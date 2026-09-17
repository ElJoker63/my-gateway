<template>
  <div>
    <div class="header">
      <h1>Overview</h1>
      <StatusBadge
        v-if="health"
        :text="health.status === 'healthy' ? 'Healthy' : 'Degraded'"
        :kind="health.status === 'healthy' ? 'ok' : 'warn'"
      />
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-else-if="loading" class="spinner">Loading…</div>

    <template v-else>
      <div class="stat-grid">
        <StatCard label="Total Requests" :value="metrics?.total_requests ?? 0"
          :sub="`uptime ${Math.round(metrics?.uptime_seconds ?? 0)}s`" />
        <StatCard label="Error Rate" :value="`${((metrics?.error_rate ?? 0) * 100).toFixed(2)}%`"
          :sub="`${metrics?.total_errors ?? 0} errors`" />
        <StatCard label="Race Wins"
          :value="`${metrics?.race_wins ?? 0}/${metrics?.total_races ?? 0}`"
          sub="parallel races" />
        <StatCard label="Cache Hits" :value="cache?.hits ?? 0"
          :sub="`${cache?.misses ?? 0} misses`" />
      </div>

      <div class="card" v-if="health">
        <h3>Services</h3>
        <DataTable :columns="svcCols" :rows="svcRows" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { api } from "@/api/client";
import { useApi } from "@/api/useApi";
import StatCard from "@/components/StatCard.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import DataTable from "@/components/DataTable.vue";

const { data: metrics, error: e1, loading: l1 } = useApi(() => api.get("/api/metrics"), 5000);
const { data: health } = useApi(() => api.get("/health"));
const { data: cache } = useApi(() => api.get("/api/cache/stats"));

const error = computed(() => e1.value || null);
const loading = computed(() => l1.value && !metrics.value);

const svcCols = [
  { key: "name", label: "Service" },
  { key: "status", label: "Status" },
  { key: "latency", label: "Latency" },
];

const svcRows = computed(() =>
  Object.entries(health.value?.services || {}).map(([name, svc]) => ({
    name,
    status: svc.status,
    latency: svc.latency_ms != null ? `${svc.latency_ms} ms` : "—",
  }))
);
</script>

<style scoped>
.header { display: flex; align-items: center; justify-content: space-between; }
</style>
