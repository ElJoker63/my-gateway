import { ref, onMounted, onUnmounted } from "vue";

/**
 * Composable for dashboard data fetching with optional polling.
 * Usage:
 *   const { data, error, loading, refresh } = useApi(() => api.get("/api/metrics"), 5000);
 */
export function useApi(fetcher, pollMs = 0, { immediate = true } = {}) {
  const data = ref(null);
  const error = ref("");
  const loading = ref(true);
  let timer = null;

  async function refresh() {
    try {
      data.value = await fetcher();
      error.value = "";
    } catch (e) {
      error.value = e.message;
    } finally {
      loading.value = false;
    }
  }

  onMounted(() => {
    if (immediate) refresh();
    if (pollMs > 0) timer = setInterval(refresh, pollMs);
  });

  onUnmounted(() => {
    if (timer) clearInterval(timer);
  });

  return { data, error, loading, refresh };
}
