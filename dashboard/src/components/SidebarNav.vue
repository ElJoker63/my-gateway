<template>
  <nav class="sidebar">
    <div class="brand">
      <div class="logo-mark">
        <HugeiconsIcon :icon="ApiGatewayIcon" :size="18" :stroke-width="1.8" />
      </div>
      My Gateway
    </div>
    <RouterLink
      v-for="link in links"
      :key="link.to"
      :to="link.to"
      class="nav-item"
      :class="{ active: route.path === link.to }"
    >
      <HugeiconsIcon :icon="link.icon" :size="18" :stroke-width="1.8" />
      {{ link.label }}
    </RouterLink>
  </nav>
</template>

<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import { HugeiconsIcon } from "@hugeicons/vue";
import {
  DashboardSquare01Icon,
  ApiGatewayIcon,
  Key01Icon,
  Layers01Icon,
  ChartUpIcon,
  LockIcon,
  Settings01Icon,
  UserGroupIcon,
  UserCircleIcon,
} from "@hugeicons/core-free-icons";
import { authState } from "@/stores/auth";
import { userState } from "@/stores/user";

const route = useRoute();

const base = [
  { to: "/", label: "Overview", icon: DashboardSquare01Icon },
  { to: "/providers", label: "Providers", icon: ApiGatewayIcon },
  { to: "/keys", label: "API Keys", icon: Key01Icon },
  { to: "/combos", label: "Combos", icon: Layers01Icon },
  { to: "/metrics", label: "Metrics", icon: ChartUpIcon },
  { to: "/oauth", label: "OAuth", icon: LockIcon },
];

const links = computed(() => {
  const list = [...base];
  if (authState.apiKey && !userState.user?.is_admin) {
    // regular users see their own account
    list.push({ to: "/account", label: "My Account", icon: UserCircleIcon });
  }
  if (userState.isAdmin) {
    list.push({ to: "/users", label: "Users", icon: UserGroupIcon });
  }
  list.push({ to: "/settings", label: "Settings", icon: Settings01Icon });
  return list;
});
</script>

<style scoped>
.nav-item.active {
  background: var(--accent-dim);
  color: var(--accent);
}
</style>
