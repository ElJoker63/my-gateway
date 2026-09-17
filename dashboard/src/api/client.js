/**
 * API client — attaches the gateway key as Bearer, handles 401 → login redirect.
 */
import { useAuthStore } from "@/stores/auth";

const BASE = "";

async function request(path, options = {}) {
  const auth = useAuthStore();
  const headers = { Accept: "application/json", ...(options.headers || {}) };

  if (auth.apiKey) headers.Authorization = `Bearer ${auth.apiKey}`;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    auth.clear();
    throw new Error("unauthorized");
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail || data.error || detail;
    } catch { /* body wasn't JSON */ }
    throw new Error(detail);
  }

  return res.status === 204 ? null : res.json();
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body }),
  del: (path) => request(path, { method: "DELETE" }),
};
