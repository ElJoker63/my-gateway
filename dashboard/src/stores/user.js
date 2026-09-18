import { reactive, computed } from "vue";

export const userState = reactive({
  user: null,
  isAdmin: false,
});

export async function loadMe(api) {
  try {
    const me = await api.get("/api/me");
    userState.user = me;
    userState.isAdmin = !!me.is_admin;
    return me;
  } catch (e) {
    // non-user key (master) → isAdmin true, no profile
    if (String(e.message).includes("403") || String(e.message).includes("user key")) {
      userState.isAdmin = true;
      return null;
    }
    userState.user = null;
    userState.isAdmin = false;
    return null;
  }
}

export function isAdmin() {
  return computed(() => userState.isAdmin);
}
