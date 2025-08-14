// frontend/src/api.js

// If VITE_API_URL is set, we call that directly.
// If it's empty/undefined, we use the Vite dev proxy at "/api".
const BASE = import.meta.env.VITE_API_URL || "";
const API = BASE || "/api";

// Normalize base + path so we never emit "//" or miss a slash.
const join = (base, path) =>
  `${String(base).replace(/\/+$/, "")}/${String(path || "").replace(/^\/+/, "")}`;

// Safe JSON parser: returns {} for empty; throws with context on bad JSON
async function parseJSON(res) {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(
      `Bad JSON from ${res.url} (status ${res.status}): ${text.slice(0, 200)}`
    );
  }
}

// Pull admin token from env and prepare default headers
const ADMIN_TOKEN = import.meta.env.VITE_ADMIN_TOKEN;
const ADMIN_HEADERS = ADMIN_TOKEN ? { "x-token": ADMIN_TOKEN } : {};

// Core request helper with good errors
async function request(path, { method = "GET", body, headers = {} } = {}) {
  const url = join(API, path);
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    // Try to surface useful text from the response
    let msg = "";
    try {
      msg = await res.text();
    } catch (_) {}
    throw new Error(`HTTP ${res.status} on ${url}: ${msg || res.statusText}`);
  }

  return parseJSON(res);
}

// Public API
export const api = {
  health: () => request("/health"),

  // Teams
  teamsInit: () => request("/teams/init", { method: "POST" }),
  teamsList: () => request("/teams"),
  teamUpsert: (payload) =>
    request("/teams/upsert", { method: "POST", body: payload }),

  // Picks
  picksList: () => request("/picks"),
  makePick: (payload) => request("/picks", { method: "POST", body: payload }),
  undoPick: (pickId) => request(`/picks/${pickId}`, { method: "DELETE" }),

  // Suggestions
  suggestions: (pos = null, opts = {}) => {
    const q = pos ? `?position=${encodeURIComponent(pos)}` : "";
    return request(`/suggestions${q}`, opts);
  },

  // Admin (now auto-sends x-token if present)
  importDemo: () =>
    request("/admin/import/demo", { method: "POST", headers: ADMIN_HEADERS }),

  importCsv: (absPath) =>
    request(`/admin/import/csv?path=${encodeURIComponent(absPath)}`, {
      method: "POST",
      headers: ADMIN_HEADERS,
    }),
};

// Optional: export the effective base for quick debugging in UI header
export const API_BASE_EFFECTIVE = API;
