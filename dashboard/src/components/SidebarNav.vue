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
} from "@hugeicons/core-free-icons";

const route = useRoute();

const links = [
  { to: "/", label: "Overview", icon: DashboardSquare01Icon },
  { to: "/providers", label: "Providers", icon: ApiGatewayIcon },
  { to: "/keys", label: "API Keys", icon: Key01Icon },
  { to: "/combos", label: "Combos", icon: Layers01Icon },
  { to: "/metrics", label: "Metrics", icon: ChartUpIcon },
  { to: "/oauth", label: "OAuth", icon: LockIcon },
  { to: "/settings", label: "Settings", icon: Settings01Icon },
];
</script>
