<template>
  <div>
    <h1>OAuth Connections</h1>
    <p class="muted">
      Connect Google/AWS accounts for OAuth-backed providers (Kiro, Antigravity). Keys never leave
      the gateway — only the issued access tokens are stored.
    </p>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <div v-for="p in pendingFlows" :key="p.provider" class="card" style="margin-top: 16px">
      <h3>{{ p.label }}</h3>
      <p v-if="p.deviceCode" class="muted">
        Go to
        <a :href="p.verificationUri" target="_blank">{{ p.verificationUri }}</a>
        and enter code:
        <code class="mono" style="font-size: 18px">{{ p.userCode }}</code>
      </p>
      <p v-if="p.authUrl">
        <a :href="p.authUrl" target="_blank">Open authorization page</a>
      </p>
      <p class="muted">Waiting for authorization… (this page will update automatically)</p>
    </div>

    <div class="card" style="margin-top: 16px">
      <h3>Connect a provider</h3>
      <div v-for="p in providers" :key="p.name" style="display: flex; align-items: center; gap: 10px; padding: 8px 0">
        <div style="flex: 1">
          <div>{{ p.label }}</div>
          <div class="muted" style="font-size: 12px">{{ p.hint }}</div>
        </div>
        <StatusBadge v-if="p.connected" text="connected" kind="ok" />
        <button v-else @click="connect(p)">Connect</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { api } from "@/api/client";
import { useApi } from "@/api/useApi";
import StatusBadge from "@/components/StatusBadge.vue";

const error = ref("");
const pendingFlows = ref([]);

const { data: status } = useApi(() => api.get("/api/oauth/status"), 4000);

const providers = ref([
  {
    name: "kiro",
    label: "AWS Kiro (CodeWhisperer)",
    hint: "OIDC device code flow — you'll get a short code to enter on Amazon's page",
    get connected() { return status.value?.kiro?.connected; },
  },
  {
    name: "antigravity",
    label: "Google Antigravity (Cloud Code)",
    hint: "OAuth consent flow — consent runs in your browser, callback returns to the gateway",
    get connected() { return status.value?.antigravity?.connected; },
  },
]);

async function connect(p) {
  error.value = "";
  try {
    const res = await api.post(`/api/oauth/${p.name}/start`, {});
    pendingFlows.value = pendingFlows.value.filter((f) => f.provider !== p.name);
    pendingFlows.value.push({ provider: p.name, label: p.label, ...res });
  } catch (e) {
    error.value = e.message;
  }
}
</script>
