import { defineComponent, ref, onMounted, h } from "vue";
import { get } from "../api.js";
import Badge from "../components/Badge.js";

export default defineComponent({
  name: "KeysView",
  components: { Badge },
  setup() {
    const pools = ref({});
    const error = ref("");

    async function load() {
      try {
        pools.value = await get("/api/keys/status");
        error.value = "";
      } catch (e) {
        error.value = e.message;
      }
    }

    onMounted(load);

    return () => {
      if (error.value) return h("p", { class: "error" }, error.value);

      const sections = Object.entries(pools.value).map(([provider, pool]) =>
        h("div", { class: "card", style: "margin-bottom:16px" }, [
          h("h3", `${provider} (${pool.available_keys}/${pool.total_keys} available)`),
          h("table", [
            h("thead", h("tr", [
              h("th", "Key"), h("th", "Used"), h("th", "Limit"), h("th", "Status"), h("th", "Retry in"),
            ])),
            h("tbody", pool.keys.map((k) =>
              h("tr", { key: k.id }, [
                h("td", { class: "mono" }, k.display),
                h("td", String(k.requests_used)),
                h("td", String(k.requests_limit)),
                h("td", h(Badge, {
                  text: k.status,
                  kind: k.status === "active" ? "ok" : k.status === "rate_limited" ? "warn" : "err",
                })),
                h("td", k.retry_after_seconds ? `${k.retry_after_seconds}s` : "—"),
              ])
            )),
          ]),
        ])
      );

      return h("div", [h("h1", "API Key Pools"), ...sections]);
    };
  },
});
