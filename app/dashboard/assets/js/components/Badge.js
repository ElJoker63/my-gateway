import { defineComponent, h } from "vue";

// Badge with state-aware color ("ok" | "warn" | "err" | "dim")
export default defineComponent({
  name: "Badge",
  props: {
    text: { type: String, required: true },
    kind: { type: String, default: "dim" },
  },
  setup(props) {
    return () => h("span", { class: `badge ${props.kind}` }, props.text);
  },
});
