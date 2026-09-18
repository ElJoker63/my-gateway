<template>
  <div class="login-wrap">
    <div class="card login-card">
      <div class="login-head">
        <div class="logo-mark">
          <HugeiconsIcon :icon="ApiGatewayIcon" :size="26" :stroke-width="1.6" />
        </div>
        <div>
          <h1>My Gateway AI</h1>
          <p class="muted">LLM Gateway Admin</p>
        </div>
      </div>

      <p class="muted">Enter your gateway API key to continue.</p>

      <input
        v-model="key"
        type="password"
        placeholder="GATEWAY_API_KEY"
        @keyup.enter="submit"
        autofocus
      />
      <p v-if="error" class="error-banner">{{ error }}</p>
      <button :disabled="loading || !key.trim()" @click="submit">
        {{ loading ? "Checking…" : "Connect" }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { HugeiconsIcon } from "@hugeicons/vue";
import { ApiGatewayIcon } from "@hugeicons/core-free-icons";
import { useAuthStore } from "@/stores/auth";
import { loadMe } from "@/stores/user";
import { api } from "@/api/client";

const key = ref("");
const error = ref("");
const loading = ref(false);
const auth = useAuthStore();
const router = useRouter();

async function submit() {
  error.value = "";
  loading.value = true;
  try {
    const res = await fetch("/api/metrics", {
      headers: { Authorization: `Bearer ${key.value.trim()}` },
    });
    if (res.status === 401) throw new Error("Invalid API key");
    if (!res.ok) throw new Error(`Server error (${res.status})`);
    auth.set(key.value.trim());
    // Load identity so the sidebar knows if we're admin or a user
    await loadMe(api);
    router.push("/");
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-head { display: flex; gap: 14px; align-items: center; }
.login-head h1 { margin: 0; font-size: 22px; }
.login-head p { margin: 0; font-size: 12.5px; }
</style>
