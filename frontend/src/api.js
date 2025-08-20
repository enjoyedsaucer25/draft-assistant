// frontend/src/api.js

const BASE = import.meta.env.VITE_API_URL || "";
const API = BASE || "/api";

const join = (base, path) =>
  `${String(base).replace(/\/+$/, "")}/${String(path || "").replace(/^\/+/, "")}`;

async function parseJSON(res) {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`Bad JSON (${res.status} ${res.statusText}): ${text.slice(0, 300)}`);
  }
}

async function request(path, init) {
  const url = join(API, path);
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init && init.headers),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status} ${res.statusText}: ${body}`);
  }
  return parseJSON(res);
}

export const api = {
  health: () => request("/health"),

  meta: {
    playersEnriched: ({ season, position = "", q = "", limit = 300 }) =>
      request(
        `/meta/players_enriched?season=${season}${position ? `&position=${encodeURIComponent(position)}` : ""
        }${q ? `&q=${encodeURIComponent(q)}` : ""}&limit=${limit}`
      ),
  },

  teams: {
    init: () => request(`/teams/init`, { method: "POST" }),
    list: () => request(`/teams/list`),
    upsert: (team) => request(`/teams/upsert`, { method: "POST", body: JSON.stringify(team) }),
  },

  picks: {
    list: () => request(`/picks`),
    create: (payload) => request(`/picks`, { method: "POST", body: JSON.stringify(payload) }),
    delete: (pick_id) => request(`/picks/${pick_id}`, { method: "DELETE" }),
  },

  // --- admin imports ---
  admin: {
    fpEcr: (season) =>
      request(`/admin/import/fp_ecr_via_script${season ? `?season=${season}` : ""}`, {
        method: "POST",
      }),
    runAll: (season) =>
      request(`/admin/import/run_all${season ? `?season=${season}` : ""}`, {
        method: "POST",
      }),
  },
};

export const API_BASE_EFFECTIVE = API;
