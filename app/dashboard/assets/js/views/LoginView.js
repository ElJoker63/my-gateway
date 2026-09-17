import { defineComponent, ref, h } from "vue";
import { setApiKey } from "../api.js";
import { navigate } from "../router.js";

export default defineComponent({
  name: "LoginView",
  setup() {
    const key = ref("");
    const error = ref("");
    const loading = ref(false);

    async function submit() {
      error.value = "";
      loading.value = true;
      try {
        setApiKey(key.value.trim());
        // verify against a protected endpoint
        const res = await fetch("/api/metrics", {
          headers: { Authorization: `Bearer ${key.value.trim()}` },
        });
        if (res.status === 401) throw new Error("Invalid key");
        if (!res.ok) throw new Error(`Server error (${res.status})`);
        navigate("/");
      } catch (e) {
        setApiKey("");
        error.value = e.message === "Invalid key" ? "Invalid API key" : e.message;
      } finally {
        loading.value = false;
      }
    }

    return () =>
      h("div", { class: "login-wrap" }, [
        h("div", { class: "card login-card" }, [
          h("h1", ["🧠 My Gateway AI"]),
          h("p", { class: "muted" }, "Enter your gateway API key to continue."),
          h("input", {
            type: "password",
            placeholder: "GATEWAY_API_KEY",
            value: key.value,
            onInput: (e) => (key.value = e.target.value),
            onKeydown: (e) => e.key === "Enter" && submit(),
          }),
          error.value ? h("p", { class: "error" }, error.value) : null,
          h("button", { onClick: submit, disabled: loading.value || !key.value.trim() },
            loading.value ? "Checking…" : "Connect"),
        ]),
      ]);
  },
});
