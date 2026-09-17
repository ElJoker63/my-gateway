<template>
  <div class="callback-wrap">
    <div class="card" style="width: 420px">
      <h1>Connecting…</h1>
      <p class="muted">{{ message }}</p>
      <p v-if="error" class="error-banner">{{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";

const router = useRouter();
const route = useRoute();
const message = ref("Finishing OAuth handshake…");
const error = ref("");

onMounted(async () => {
  try {
    const params = new URLSearchParams(window.location.search);
    const provider = params.get("state") || "";
    const code = params.get("code") || "";
    if (!code) throw new Error("Missing authorization code");

    const authKey = sessionStorage.getItem("gateway_api_key") || "";
    const res = await fetch(`/api/oauth/${encodeURIComponent(provider)}/callback?code=${encodeURIComponent(code)}`, {
      headers: { Authorization: `Bearer ${authKey}` },
    });
    if (!res.ok) throw new Error(`Callback rejected (HTTP ${res.status})`);

    message.value = "Connected! Redirecting…";
    setTimeout(() => router.push("/oauth"), 1000);
  } catch (e) {
    error.value = e.message;
  }
});
</script>

<style scoped>
.callback-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
