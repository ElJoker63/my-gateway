<template>
  <nav class="sidebar">
    <div class="brand">My <span>Gateway</span> AI</div>
    <RouterLink
      v-for="link in links"
      :key="link.to"
      :to="link.to"
      :class="{ active: route.path === link.to }"
    >
      {{ link.icon }} {{ link.label }}
    </RouterLink>
  </nav>
</template>

<script setup>
import { useRoute } from "vue-router";

const route = useRoute();
const links = [
  { to: "/", label: "Overview", icon: "📊" },
  { to: "/providers", label: "Providers", icon: "🔌" },
  { to: "/keys", label: "API Keys", icon: "🔑" },
  { to: "/combos", label: "Combos", icon: "🎯" },
  { to: "/oauth", label: "OAuth", icon: "🔐" },
  { to: "/metrics", label: "Metrics", icon: "📈" },
  { to: "/settings", label: "Settings", icon: "⚙️" },
];
</script>

<style scoped>
.sidebar {
  background: var(--bg-surface);
  border-right: 1px solid var(--border);
  padding: 20px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.brand {
  padding: 8px 10px 18px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  border-bottom: 1px solid var(--border);
  margin-bottom: 10px;
}
.brand span { color: var(--accent); }
a {
  display: block;
  padding: 9px 12px;
  border-radius: 8px;
  color: var(--text-muted);
  font-weight: 500;
  transition: background 0.15s, color 0.15s;
}
a:hover { background: var(--bg-elevated); color: var(--text); }
a.active { background: var(--bg-elevated); color: var(--accent); }
</style>
