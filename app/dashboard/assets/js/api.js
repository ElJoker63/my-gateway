// Tiny API client: attaches the gateway API key as Bearer token.
// The key is stored in sessionStorage after the user enters it once.

const BASE = ""; // same origin

export function getApiKey() {
  return sessionStorage.getItem("gateway_api_key") || "";
}

export function setApiKey(key) {
  if (key) sessionStorage.setItem("gateway_api_key", key);
  else sessionStorage.removeItem("gateway_api_key");
}

export function hasApiKey() {
  return !!getApiKey();
}

export async function api(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  const key = getApiKey();
  if (key) headers["Authorization"] = `Bearer ${key}`;
  if (options.body && typeof options.body !== "string") {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    setApiKey("");
    window.location.hash = "#/login";
    throw new Error("unauthorized");
  }

  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail || data.error || detail;
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }

  return res.json();
}

export const get = (path) => api(path);
export const post = (path, body) => api(path, { method: "POST", body });
export const del = (path) => api(path, { method: "DELETE" });
