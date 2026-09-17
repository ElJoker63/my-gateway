<template>
  <div class="login-wrap">
    <div class="card login-card">
      <h1>🧠 My Gateway AI</h1>
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
import { useAuthStore } from "@/stores/auth";

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
    router.push("/");
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-card {
  width: 360px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.login-card h1 { font-size: 20px; }
</style>
