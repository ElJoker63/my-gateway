<template>
  <div>
    <h1>My Account</h1>
    <p class="muted">Your API key, provider pools, and usage.</p>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <div v-if="me" class="card" style="margin-top: 16px">
      <h3>Profile</h3>
      <div class="row"><span class="muted">Name</span><strong>{{ me.name }}</strong></div>
      <div class="row" v-if="me.email"><span class="muted">Email</span>{{ me.email }}</div>
      <div class="row"><span class="muted">API key</span><code class="mono">{{ me.key_display }}</code></div>
      <div class="row"><span class="muted">Key version</span>v{{ me.key_version }}</div>
      <div class="row"><span class="muted">Status</span>
        <StatusBadge :text="me.disabled ? 'disabled' : 'active'" :kind="me.disabled ? 'err' : 'ok'" dot />
      </div>
    </div>

    <div class="card" style="margin-top: 16px" v-if="myKeys">
      <h3>My provider keys</h3>
      <p class="muted" style="font-size: 12.5px">Pools are scoped to your account. Add provider keys that only you use.</p>

      <DataTable :columns="cols" :rows="rows" />

      <form class="form-row" @submit.prevent="add" style="margin-top: 14px">
        <select v-model="form.provider" required>
          <option value="">— provider —</option>
          <option v-for="p in allProviders" :key="p" :value="p">{{ p }}</option>
        </select>
        <input v-model="form.key" type="password" placeholder="API key" required style="font-family: var(--mono)" />
        <AppButton :loading="saving" type="submit">Add</AppButton>
      </form>
      <p v-if="formError" class="error-banner" style="margin-top: 12px">{{ formError }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { api } from "@/api/client";
import { useApi } from "@/api/useApi";
import AppButton from "@/components/AppButton.vue";
import DataTable from "@/components/DataTable.vue";
import StatusBadge from "@/components/StatusBadge.vue";

const cols = [
  { key: "provider", label: "Provider" },
  { key: "keys", label: "Keys" },
  { key: "available", label: "Available" },
  { key: "rpm", label: "RPM/key" },
];

const { data: me, error: e1 } = useApi(() => api.get("/api/me"));
const { data: myKeys, refresh: refreshUsage } = useApi(() => api.get("/api/me/usage"), 15000);
const { data: keysAll } = useApi(() => api.get("/api/keys/status"));

const error = computed(() => e1.value);

const form = ref({ provider: "", key: "" });
const saving = ref(false);
const formError = ref("");

const rows = computed(() =>
  Object.entries(myKeys.value || {}).map(([name, pool]) => ({
    provider: name,
    keys: pool.total_keys,
    available: pool.available_keys,
    rpm: pool.rpm_per_key,
  })),
);

const allProviders = computed(() => {
  const names = Object.keys(keysAll.value || {});
  names.sort();
  return names;
});

async function add() {
  formError.value = "";
  saving.value = true;
  try {
    await api.post(`/api/providers/${encodeURIComponent(form.value.provider)}/keys`, {
      key: form.value.key.trim(),
    });
    form.value.key = "";
    refreshUsage();
  } catch (e) {
    formError.value = e.message;
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.row { display: flex; gap: 14px; padding: 8px 0; font-size: 14px; }
.row .muted { width: 110px; }
</style>
