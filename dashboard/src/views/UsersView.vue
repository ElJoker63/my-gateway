<template>
  <div>
    <div class="header-row">
      <div>
        <h1>Users</h1>
        <p class="muted">Create per-user API keys — each user gets isolated key pools</p>
      </div>
      <AppButton :icon="PlusSignIcon" @click="showForm = !showForm">{{ showForm ? "Cancel" : "New user" }}</AppButton>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <div v-if="showForm" class="card" style="margin-bottom: 20px">
      <h3>Create user</h3>
      <div class="form-row">
        <input v-model="form.name" placeholder="Name" />
        <input v-model="form.email" placeholder="Email (optional)" type="email" />
        <label style="display:flex;align-items:center;gap:8px">
          <input v-model="form.admin" type="checkbox" style="width:auto" /> Admin
        </label>
      </div>
      <div class="form-row">
        <AppButton :loading="creating" @click="create">Create</AppButton>
      </div>
    </div>

    <div v-if="newKey" class="card" style="margin-bottom: 20px; border-color: rgba(10,132,255,0.4)">
      <h3>New API key — show once, then it can't be retrieved again</h3>
      <p class="muted" style="font-size: 12px">For user <strong>{{ newKey.user }}</strong></p>
      <div style="display:flex;align-items:center;gap:8px;margin-top:8px">
        <code class="mono" style="word-break:break-all;flex:1">{{ newKey.value }}</code>
        <AppButton :icon="Copy01Icon" variant="ghost" small @click="copyKey">Copy</AppButton>
      </div>
      <AppButton class="ghost" small style="margin-top:14px" @click="newKey = null">Done</AppButton>
    </div>

    <DataTable :columns="cols" :rows="rows">
      <template #is_admin="{ row }">
        <StatusBadge v-if="row.is_admin" text="admin" kind="info" dot />
        <span v-else class="muted">—</span>
      </template>
      <template #disabled="{ row }">
        <StatusBadge :text="row.disabled ? 'disabled' : 'active'" :kind="row.disabled ? 'err' : 'ok'" dot />
      </template>
      <template #actions="{ row }">
        <div style="display:flex;gap:6px">
          <AppButton :icon="Rotate01Icon" variant="ghost" small @click="rotate(row.id)">Rotate</AppButton>
          <AppButton :icon="Delete02Icon" variant="danger" small @click="disable(row.id)" :disabled="row.is_admin">Disable</AppButton>
        </div>
      </template>
    </DataTable>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { HugeiconsIcon } from "@hugeicons/vue";
import { PlusSignIcon, Copy01Icon, Rotate01Icon, Delete02Icon } from "@hugeicons/core-free-icons";
import { api } from "@/api/client";
import { useApi } from "@/api/useApi";
import AppButton from "@/components/AppButton.vue";
import DataTable from "@/components/DataTable.vue";
import StatusBadge from "@/components/StatusBadge.vue";

const cols = [
  { key: "name", label: "Name" },
  { key: "email", label: "Email" },
  { key: "key_display", label: "Key" },
  { key: "is_admin", label: "Admin" },
  { key: "disabled", label: "Status" },
  { key: "actions", label: "" },
];

const { data, error, refresh } = useApi(() => api.get("/api/admin/users"), 15000);
const showForm = ref(false);
const creating = ref(false);
const newKey = ref(null);

const form = ref({ name: "", email: "", admin: false });

const rows = computed(() => data.value?.users || []);

async function create() {
  error.value = "";
  creating.value = true;
  try {
    const res = await api.post("/api/admin/users", {
      name: form.value.name,
      email: form.value.email,
      is_admin: form.value.admin,
    });
    newKey.value = { user: res.user.name, value: res.api_key };
    form.value = { name: "", email: "", admin: false };
    showForm.value = false;
    refresh();
  } catch (e) {
    error.value = e.message;
  } finally {
    creating.value = false;
  }
}

async function rotate(id) {
  if (!confirm("Rotate key — the old one stops working immediately. Continue?")) return;
  try {
    await api.post(`/api/admin/users/${encodeURIComponent(id)}/rotate`, {});
    refresh();
  } catch (e) {
    error.value = e.message;
  }
}

async function disable(id) {
  try {
    await api.del(`/api/admin/users/${encodeURIComponent(id)}`);
    refresh();
  } catch (e) {
    error.value = e.message;
  }
}

async function copyKey() {
  if (!newKey.value) return;
  try {
    await navigator.clipboard.writeText(newKey.value.value);
  } catch {
    /* clipboard may be blocked by the browser — user can select+copy manually */
  }
}
</script>
