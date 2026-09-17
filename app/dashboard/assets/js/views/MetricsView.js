import { defineComponent, ref, onMounted, onUnmounted, computed, h } from "vue";
import { get } from "../api.js";
import StatCard from "../components/StatCard.js";

export default defineComponent({
  name: "MetricsView",
  components: { StatCard },
  setup() {
    const data = ref(null);
    const error = ref("");
    let timer = null;

    async function load() {
      try {
        data.value = await get("/api/metrics");
        error.value = "";
      } catch (e) {
        error.value = e.message;
      }
    }

    onMounted(() => {
      load();
      timer = setInterval(load, 5000);
    });
    onUnmounted(() => clearInterval(timer));

    const latencyRows = computed(() => {
      if (!data.value) return [];
      return Object.entries(data.value.latency || {})
        .map(([key, v]) => ({ key, ...v }))
        .sort((a, b) => (b.count || 0) - (a.count || 0));
    });

    const maxP95 = computed(() =>
      Math.max(1, ...latencyRows.value.map((r) => r.p95_ms || 0))
    );

    return () => {
      if (error.value) return h("p", { class: "error" }, error.value);
      const d = data.value;
      if (!d) return h("p", { class: "muted" }, "Loading…");

      return h("div", [
        h("h1", "Metrics"),
        h("div", { class: "stat-grid" }, [
          h(StatCard, { label: "Requests", value: d.total_requests }),
          h(StatCard, { label: "Errors", value: d.total_errors, sub: `${(d.error_rate * 100).toFixed(2)}% rate` }),
          h(StatCard, { label: "Races", value: d.total_races, sub: `${(d.race_win_rate * 100).toFixed(1)}% first-target wins` }),
          h(StatCard, { label: "Providers active", value: Object.keys(d.providers || {}).length }),
        ]),
        h("div", { class: "card" }, [
          h("h3", "Latency percentiles (rolling window)"),
          h("div", latencyRows.value.map((r) =>
            h("div", { class: "bar-row", key: r.key }, [
              h("span", { class: "mono" }, r.key),
              h("div", { class: "bar-track" },
                h("div", {
                  class: "bar-fill",
                  style: `width:${((r.p95_ms || 0) / maxP95.value * 100).toFixed(1)}%`,
                })
              ),
              h("span", { class: "muted" },
                r.p95_ms != null ? `p95 ${r.p95_ms}ms · n=${r.count}` : "—"),
            ])
          )),
        ]),
        h("div", { class: "card", style: "margin-top:16px" }, [
          h("h3", "Providers"),
          h("table", [
            h("thead", h("tr", [
              h("th", "Provider"), h("th", "Requests"), h("th", "Errors"), h("th", "Tokens"), h("th", "Models"),
            ])),
            h("tbody", Object.entries(d.providers || {}).map(([name, p]) =>
              h("tr", { key: name }, [
                h("td", name),
                h("td", String(p.requests)),
                h("td", String(p.errors)),
                h("td", String(p.tokens)),
                h("td", { class: "muted" }, (p.models || []).join(", ") || "—"),
              ])
            )),
          ]),
        ]),
      ]);
    };
  },
});
