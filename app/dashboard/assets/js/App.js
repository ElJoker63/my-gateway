import { computed, defineComponent, h, inject } from "vue";
import { route } from "./router.js";
import Sidebar from "./components/Sidebar.js";
import { hasApiKey } from "./api.js";

export default defineComponent({
  name: "App",
  components: { Sidebar },
  setup() {
    const routes = inject("routes", {});

    const current = computed(() => routes[route.path] || routes["/"] || null);
    const needsLogin = computed(() => route.path !== "/login" && !hasApiKey());

    return () => {
      if (needsLogin.value && route.path !== "/login") {
        // soft redirect to login
        window.location.hash = "#/login";
        return null;
      }
      if (route.path === "/login") return h(current.value);
      return h("div", { class: "layout" }, [
        h(Sidebar),
        h("main", { class: "content" }, [current.value ? h(current.value) : null]),
      ]);
    };
  },
});
