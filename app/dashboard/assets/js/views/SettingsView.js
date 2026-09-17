import { defineComponent, h } from "vue";
import { setApiKey } from "../api.js";
import { navigate } from "../router.js";

export default defineComponent({
  name: "SettingsView",
  setup() {
    function logout() {
      setApiKey("");
      navigate("/login");
    }

    return () =>
      h("div", [
        h("h1", "Settings"),
        h("div", { class: "card" }, [
          h("h3", "Session"),
          h("p", { class: "muted" }, "Your API key is stored in this browser's sessionStorage only."),
          h("button", { class: "danger", onClick: logout }, "Log out / clear key"),
        ]),
        h("div", { class: "card", style: "margin-top:16px" }, [
          h("h3", "About"),
          h("p", { class: "muted" }, "My Gateway AI dashboard — data comes from /api/metrics, /api/keys/status, /health."),
          h("p", { class: "muted" }, "Dashboard is a static Vue 3 SPA served by the gateway itself, no build step."),
        ]),
      ]);
  },
});
