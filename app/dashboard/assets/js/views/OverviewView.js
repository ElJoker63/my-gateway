import { defineComponent, ref, onMounted, onUnmounted, h } from "vue";
import { get } from "../api.js";
import StatCard from "../components/StatCard.js";
import Badge from "../components/Badge.js";

export default defineComponent({
  name: "OverviewView",
  components: { StatCard, Badge },
  setup() {
    const metrics = ref(null);
    const health = ref(null);
    const cache = ref(null);
    const error = ref("");
    let timer = null;

    async function load() {
      try {
        [metrics.value, health.value, cache.value] = await Promise.all([
          get("/api/metrics"),
          get("/health"),
          get("/api/cache/stats"),
        ]);
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

    const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));

    return () => {
      if (error.value) return h("div", { class: "card" }, [h("p", { class: "error" }, error.value)]);
      const m = metrics.value;
      const hc = health.value;

      return h("div", [
        h("div", { style: "display:flex;align-items:center;justify-content:space-between" }, [
          h("h1", "Overview"),
          hc && h(Badge, {
            text: hc.status === "healthy" ? "Healthy" : "Degraded",
            kind: hc.status === "healthy" ? "ok" : "warn",
          }),
        ]),
        h("div", { class: "stat-grid" }, [
          h(StatCard, { label: "Total Requests", value: m?.total_requests ?? "—", sub: `uptime ${fmt(m?.uptime_seconds, 0)}s` }),
          h(StatCard, { label: "Error Rate", value: m ? `${(m.error_rate * 100).toFixed(2)}%` : "—", sub: `${m?.total_errors ?? 0} errors` }),
          h(StatCard, { label: "Race Wins", value: m ? `${m.race_wins}/${m.total_races}` : "—", sub: "parallel races" }),
          h(StatCard, { label: "Cache Hits", value: cache.value?.hits ?? "—", sub: `${cache.value?.misses ?? 0} misses` }),
        ]),
        hc && h("div", { class: "card" }, [
          h("h3", "Services"),
          h("table", [
            h("thead", h("tr", [h("th", "Service"), h("th", "Status"), h("th", "Latency")])),
            h("tbody", Object.entries(hc.services).map(([name, svc]) =>
              h("tr", { key: name }, [
                h("td", name),
                h("td", h(Badge, { text: svc.status, kind: svc.status === "healthy" ? "ok" : "err" })),
                h("td", svc.latency_ms != null ? `${svc.latency_ms} ms` : "—"),
              ])
            )),
          ]),
        ]),
      ]);
    };
  },
});
