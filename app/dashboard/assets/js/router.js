// Reactive router — hash-based so no server-side rewrites are needed.
import { reactive, readonly } from "vue";

const state = reactive({
  path: window.location.hash.slice(1) || "/",
});

window.addEventListener("hashchange", () => {
  state.path = window.location.hash.slice(1) || "/";
});

export const route = readonly(state);

export function navigate(path) {
  window.location.hash = path;
}
