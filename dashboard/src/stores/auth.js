import { reactive } from "vue";

/**
 * Minimal reactive session store — the API key lives in memory + sessionStorage.
 * (Pinia would be overkill for one string.)
 */
export const authState = reactive({
  apiKey: sessionStorage.getItem("gateway_api_key") || "",
});

export function useAuthStore() {
  return {
    get apiKey() {
      return authState.apiKey;
    },
    set(key) {
      authState.apiKey = key;
      sessionStorage.setItem("gateway_api_key", key);
    },
    clear() {
      authState.apiKey = "";
      sessionStorage.removeItem("gateway_api_key");
    },
  };
}
