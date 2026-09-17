import { defineComponent, h } from "vue";

export default defineComponent({
  name: "StatCard",
  props: {
    label: { type: String, required: true },
    value: { type: [String, Number], required: true },
    sub: { type: String, default: "" },
  },
  setup(props) {
    return () =>
      h("div", { class: "stat" }, [
        h("div", { class: "label" }, props.label),
        h("div", { class: "value" }, String(props.value)),
        props.sub ? h("div", { class: "sub" }, props.sub) : null,
      ]);
  },
});
