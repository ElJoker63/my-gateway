import { defineComponent, h } from "vue";
import { route, navigate } from "../router.js";

const LINKS = [
  { path: "/", label: "Overview", icon: "📊" },
  { path: "/providers", label: "Providers", icon: "🔌" },
  { path: "/keys", label: "API Keys", icon: "🔑" },
  { path: "/combos", label: "Combos", icon: "🎯" },
  { path: "/metrics", label: "Metrics", icon: "📈" },
  { path: "/settings", label: "Settings", icon: "⚙️" },
];

export default defineComponent({
  name: "Sidebar",
  setup() {
    return () =>
      h("nav", { class: "sidebar" }, [
        h("div", { class: "brand" }, [
          "My ",
          h("span", "Gateway"),
          " AI",
        ]),
        LINKS.map((l) =>
          h(
            "a",
            {
              class: { active: route.path === l.path },
              href: `#${l.path}`,
              onClick: (e) => {
                e.preventDefault();
                navigate(l.path);
              },
            },
            `${l.icon}  ${l.label}`
          )
        ),
      ]);
  },
});
