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
    throw new Error(
      `Bad JSON from ${res.url} (status ${res.status}): ${text.slice(0, 200)}`
    );
  }
}

const ADMIN_TOKEN = import.meta.env.VITE_ADMIN_TOKEN;
const ADMIN_HEADERS = ADMIN_TOKEN ? { "x-token": ADMIN_TOKEN } : {};

async function request(path, { method = "GET", body, headers = {} } = {}) {
  const url = join(API, path);
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = "";
    try { msg = await res.text(); } catch { }
    throw new Error(`HTTP ${res.status} on ${url}: ${msg || res.statusText}`);
  }
  return parseJSON(res);
}

export const api = {
  health: () => request("/health"),

  teamsInit: () => request("/teams/init", { method: "POST" }),
  teamsList: () => request("/teams"),
  teamUpsert: (payload) => request("/teams/upsert", { method: "POST", body: payload }),

  picksList: () => request("/picks"),
  makePick: (payload) => request("/picks", { method: "POST", body: payload }),
  undoPick: (pickId) => request(`/picks/${pickId}`, { method: "DELETE" }),

  suggestions: (pos = null, opts = {}) => {
    const q = pos ? `?position=${encodeURIComponent(pos)}` : "";
    return request(`/suggestions${q}`, opts);
  },

  importDemo: () => request("/admin/import/demo", { method: "POST", headers: ADMIN_HEADERS }),
  importCsv: (absPath) =>
    request(`/admin/import/csv?path=${encodeURIComponent(absPath)}`, {
      method: "POST",
      headers: ADMIN_HEADERS,
    }),
  importSleeperPlayers: (season) =>
    request(`/admin/import/sleeper_players?season=${season}`, {
      method: "POST",
      headers: ADMIN_HEADERS,
    }),
  importInjuriesCBS: (season) =>
    request(`/admin/import/injuries_cbs?season=${season}`, {
      method: "POST",
      headers: ADMIN_HEADERS,
    }),

  // Optional FantasyPros endpoints (backend gated by DA_ENABLE_FP_IMPORTS)
  importFPECRCsv: (season, path) =>
    request(
      `/admin/import/fp_ecr_csv?season=${season}&path=${encodeURIComponent(path)}`,
      { method: "POST", headers: ADMIN_HEADERS }
    ),
  importFPECRHtml: (season, url) =>
    request(
      `/admin/import/fp_ecr_html?season=${season}&url=${encodeURIComponent(url)}`,
      { method: "POST", headers: ADMIN_HEADERS }
    ),
  importFPADPCsv: (season, path, source = "fp_composite") =>
    request(
      `/admin/import/fp_adp_csv?season=${season}&path=${encodeURIComponent(
        path
      )}&source=${encodeURIComponent(source)}`,
      { method: "POST", headers: ADMIN_HEADERS }
    ),

  playersEnriched: (season, position = "") =>
    request(
      `/meta/players_enriched?season=${season}${position ? `&position=${encodeURIComponent(position)}` : ""
      }`
    ),

  setTier: (player_id, tier) =>
    request(`/edits/tier/${encodeURIComponent(player_id)}?tier=${tier ?? ""}`, {
      method: "POST",
    }),
  addNote: (player_id, text, team_slot_id = null) =>
    request(
      `/edits/notes?player_id=${encodeURIComponent(
        player_id
      )}&text=${encodeURIComponent(text)}${team_slot_id ? `&team_slot_id=${team_slot_id}` : ""
      }`,
      { method: "POST" }
    ),
  listNotes: (player_id) =>
    request(`/edits/notes?player_id=${encodeURIComponent(player_id)}`),
};

export const API_BASE_EFFECTIVE = API;
