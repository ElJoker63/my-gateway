<template>
  <div>
    <h1>Settings</h1>

    <div class="card">
      <h3>Session</h3>
      <p class="muted">Your API key is stored in this browser's sessionStorage only.</p>
      <button class="danger" @click="logout">Log out / clear key</button>
    </div>

    <div class="card" style="margin-top: 16px">
      <h3>About</h3>
      <p class="muted">My Gateway AI dashboard — Vue 3 + Vite, served by the gateway itself.</p>
      <p class="muted">End a session by clearing the browser's session storage.</p>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();

function logout() {
  auth.clear();
  router.push("/login");
}
</script>
