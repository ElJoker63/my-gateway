import { defineComponent, ref, onMounted, h } from "vue";
import { get } from "../api.js";
import Badge from "../components/Badge.js";

export default defineComponent({
  name: "ProvidersView",
  components: { Badge },
  setup() {
    const rows = ref([]);
    const circuitStates = ref({});
    const error = ref("");

    async function load() {
      try {
        const metrics = await get("/api/metrics");
        circuitStates.value = metrics.circuit_states || {};
        const keyStatus = await get("/api/keys/status");
        rows.value = Object.entries(keyStatus).map(([name, pool]) => ({
          name,
          total: pool.total_keys,
          available: pool.available_keys,
          rpm: pool.rpm_per_key,
          circuit: circuitStates.value[name]?.state || "closed",
          failures: circuitStates.value[name]?.failures || 0,
        }));
        error.value = "";
      } catch (e) {
        error.value = e.message;
      }
    }

    onMounted(load);

    return () => {
      if (error.value) return h("p", { class: "error" }, error.value);
      return h("div", [
        h("h1", "Providers"),
        h("div", { class: "card" }, [
          h("table", [
            h("thead", h("tr", [
              h("th", "Provider"),
              h("th", "Keys"),
              h("th", "Available"),
              h("th", "RPM/key"),
              h("th", "Circuit"),
            ])),
            h("tbody", rows.value.map((r) =>
              h("tr", { key: r.name }, [
                h("td", r.name),
                h("td", String(r.total)),
                h("td", String(r.available)),
                h("td", String(r.rpm)),
                h("td", h(Badge, {
                  text: r.circuit,
                  kind: r.circuit === "closed" ? "ok" : r.circuit === "half_open" ? "warn" : "err",
                })),
              ])
            )),
          ]),
        ]),
      ]);
    };
  },
});
