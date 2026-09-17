import { defineComponent, ref, onMounted, h } from "vue";
import { get, post, del } from "../api.js";
import Badge from "../components/Badge.js";

const STRATEGIES = ["strict", "round_robin", "least_used", "race"];

export default defineComponent({
  name: "CombosView",
  components: { Badge },
  setup() {
    const combos = ref([]);
    const providers = ref([]);
    const error = ref("");
    const showForm = ref(false);
    const form = ref({ name: "", strategy: "strict", race_size: 2, targets: [{ provider: "", model: "" }] });

    async function load() {
      try {
        const [c, models] = await Promise.all([get("/api/combos"), get("/api/keys/status")]);
        combos.value = c.combos;
        providers.value = Object.keys(models);
        error.value = "";
      } catch (e) {
        error.value = e.message;
      }
    }

    async function save() {
      try {
        const payload = {
          name: form.value.name,
          strategy: form.value.strategy,
          race_size: Number(form.value.race_size),
          targets: form.value.targets
            .filter((t) => t.provider)
            .map((t) => ({ provider: t.provider, model: t.model || null })),
        };
        await post("/api/combos", payload);
        showForm.value = false;
        form.value = { name: "", strategy: "strict", race_size: 2, targets: [{ provider: "", model: "" }] };
        await load();
      } catch (e) {
        error.value = e.message;
      }
    }

    async function remove(name) {
      if (!confirm(`Delete combo "${name}"?`)) return;
      await del(`/api/combos/${encodeURIComponent(name)}`);
      await load();
    }

    function addTarget() {
      form.value.targets.push({ provider: "", model: "" });
    }

    onMounted(load);

    return () => h("div", [
      h("div", { style: "display:flex;justify-content:space-between;align-items:center" }, [
        h("h1", "Combos"),
        h("button", { onClick: () => (showForm.value = !showForm.value) },
          showForm.value ? "Cancel" : "+ New combo"),
      ]),
      error.value ? h("p", { class: "error" }, error.value) : null,

      showForm.value && h("div", { class: "card", style: "margin:16px 0" }, [
        h("h3", "Create combo"),
        h("div", { class: "form-row" }, [
          h("input", {
            placeholder: "name (e.g. fast)",
            value: form.value.name,
            onInput: (e) => (form.value.name = e.target.value),
          }),
          h("select", {
            value: form.value.strategy,
            onChange: (e) => (form.value.strategy = e.target.value),
          }, STRATEGIES.map((s) => h("option", { value: s }, s))),
          form.value.strategy === "race" && h("input", {
            type: "number", min: 2, max: 8,
            value: form.value.race_size,
            onInput: (e) => (form.value.race_size = e.target.value),
            placeholder: "race size",
          }),
        ]),
        form.value.targets.map((t, i) =>
          h("div", { class: "form-row", key: i }, [
            h("select", {
              value: t.provider,
              onChange: (e) => (form.value.targets[i].provider = e.target.value),
            }, [
              h("option", { value: "" }, "— provider —"),
              ...providers.value.map((p) => h("option", { value: p }, p)),
            ]),
            h("input", {
              placeholder: "model (optional)",
              value: t.model,
              onInput: (e) => (form.value.targets[i].model = e.target.value),
            }),
          ])
        ),
        h("div", { style: "display:flex;gap:10px" }, [
          h("button", { class: "ghost", onClick: addTarget }, "+ target"),
          h("button", { onClick: save, disabled: !form.value.name }, "Save"),
        ]),
      ]),

      ...combos.value.map((c) =>
        h("div", { class: "card", style: "margin-bottom:12px" }, [
          h("div", { style: "display:flex;justify-content:space-between;align-items:start" }, [
            h("div", [
              h("h3", `combo:${c.name}`),
              h("div", { class: "muted" }, `strategy: ${c.strategy}${c.strategy === "race" ? `, race_size: ${c.race_size}` : ""}`),
            ]),
            h("button", { class: "danger", onClick: () => remove(c.name) }, "Delete"),
          ]),
          h("ul", c.targets.map((t) =>
            h("li", [h("span", { class: "mono" }, t.provider), t.model ? ` — ${t.model}` : " (default model)"])
          )),
        ])
      ),
    ]);
  },
});
