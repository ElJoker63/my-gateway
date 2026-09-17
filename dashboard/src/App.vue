<template>
  <div v-if="!isLogin" class="layout">
    <SidebarNav />
    <main class="content">
      <RouterView />
    </main>
  </div>
  <RouterView v-else />
</template>

<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import SidebarNav from "@/components/SidebarNav.vue";

const route = useRoute();
const isLogin = computed(() => route.name === "login");
</script>
