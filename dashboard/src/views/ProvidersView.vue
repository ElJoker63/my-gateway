<template>
  <div>
    <div class="header-row">
      <div>
        <h1>Providers</h1>
        <p class="muted">API keys and health per provider</p>
      </div>
      <AppButton :icon="loading ? null : RefreshIcon" :loading="loading" variant="ghost" small @click="refreshAll">
        Refresh
      </AppButton>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <DataTable
      v-else
      :columns="cols"
      :rows="rows"
      v-slot:status="{ row }"
    >
      <StatusBadge
        :text="row.status"
        :kind="row.available > 0 ? 'ok' : row.total > 0 ? 'warn' : 'dim'"
        dot
      />
    </DataTable>

    <div class="card" style="margin-top:18px">
      <h3>Add API Key</h3>
      <p class="muted" style="font-size: 12.5px">Keys are appended to the provider's pool (stored in Redis; env vars remain the seed).</p>
      <form class="form-row" @submit.prevent="submit" style="margin-top: 4px">
        <select v-model="form.provider" required>
          <option value="" disabled>Select provider</option>
          <option v-for="p in providerNames" :key="p" :value="p">{{ p }}</option>
        </select>
        <input
          v-model="form.key"
          :type="showKey ? 'text' : 'password'"
          placeholder="API key"
          required
          style="font-family: var(--mono)"
        />
        <AppButton variant="ghost" type="button" :icon="showKey ? ViewOffIcon : ViewIcon" @click="showKey = !showKey" />
        <AppButton :loading="saving" type="submit">Add</AppButton>
      </form>
      <p v-if="formError" class="error-banner" style="margin-top: 10px">{{ formError }}</p>
      <p v-if="formOk" class="muted" style="color: var(--ok); margin-top: 6px">Key added.</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { api } from "@/api/client";
import { useApi } from "@/api/useApi";
import { HugeiconsIcon } from "@hugeicons/vue";
import { RefreshIcon, ViewIcon, ViewOffIcon } from "@hugeicons/core-free-icons";
import AppButton from "@/components/AppButton.vue";
import DataTable from "@/components/DataTable.vue";
import StatusBadge from "@/components/StatusBadge.vue";

const cols = [
  { key: "name", label: "Provider" },
  { key: "total", label: "Keys" },
  { key: "available", label: "Available" },
  { key: "rpm", label: "RPM/key" },
  { key: "circuit", label: "Circuit" },
];

const { data: keyStatus, error: e1, loading, refresh: refreshKeys } = useApi(() => api.get("/api/keys/status"), 15000);
const { data: metrics, refresh: refreshMetrics } = useApi(() => api.get("/api/metrics"));

const error = computed(() => e1.value);

const rows = computed(() => {
  const circuits = metrics.value?.circuit_states || {};
  return Object.entries(keyStatus.value || {}).map(([name, pool]) => ({
    name,
    total: pool.total_keys,
    available: pool.available_keys,
    rpm: pool.rpm_per_key,
    circuit: (circuits[name]?.state || "closed"),
  }));
});

const providerNames = computed(() => rows.value.map((r) => r.name).sort());

const form = ref({ provider: "", key: "" });
const saving = ref(false);
const formError = ref("");
const formOk = ref(false);
const showKey = ref(false);

async function submit() {
  formError.value = "";
  formOk.value = false;
  saving.value = true;
  try {
    await api.post(`/api/providers/${encodeURIComponent(form.value.provider)}/keys`, {
      key: form.value.key.trim(),
    });
    form.value.key = "";
    formOk.value = true;
    refreshKeys();
  } catch (e) {
    formError.value = e.message;
  } finally {
    saving.value = false;
  }
}

function refreshAll() {
  refreshKeys();
  refreshMetrics();
}
</script>
