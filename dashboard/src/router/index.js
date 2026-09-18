import { createRouter, createWebHistory } from "vue-router";
import { authState } from "@/stores/auth";

const routes = [
  {
    path: "/login",
    name: "login",
    component: () => import("@/views/LoginView.vue"),
    meta: { public: true },
  },
  { path: "/", name: "overview", component: () => import("@/views/OverviewView.vue") },
  { path: "/providers", name: "providers", component: () => import("@/views/ProvidersView.vue") },
  { path: "/keys", name: "keys", component: () => import("@/views/KeysView.vue") },
  { path: "/combos", name: "combos", component: () => import("@/views/CombosView.vue") },
  { path: "/metrics", name: "metrics", component: () => import("@/views/MetricsView.vue") },
  { path: "/oauth", name: "oauth", component: () => import("@/views/OAuthView.vue") },
  { path: "/oauth/callback", name: "oauth-callback", component: () => import("@/views/OAuthCallbackView.vue"), meta: { public: true } },
  { path: "/users", name: "users", component: () => import("@/views/UsersView.vue") },
  { path: "/account", name: "account", component: () => import("@/views/MyAccountView.vue") },
  { path: "/settings", name: "settings", component: () => import("@/views/SettingsView.vue") },
];

const router = createRouter({
  history: createWebHistory("/dashboard/"),
  routes,
});

router.beforeEach((to) => {
  if (to.meta.public) return true;
  if (!authState.apiKey) return { name: "login" };
  return true;
});

export default router;
