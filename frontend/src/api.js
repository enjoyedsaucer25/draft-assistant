// frontend/src/api.js
const BASE = import.meta.env.VITE_API_URL || '';   // If '', we expect a dev proxy at /api
const API  = BASE ? BASE : '/api';

// Safe JSON parser: returns {} for empty; throws with context on bad JSON
async function parseJSON(res) {
  const text = await res.text();             // don't call res.json() directly
  if (!text) return {};                      // handle 204/empty bodies safely
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`Bad JSON from ${res.url} (status ${res.status}): ${text.slice(0,200)}`);
  }
}

async function request(path, { method='GET', body, headers={} } = {}) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const msg = await res.text().catch(()=>'');
    throw new Error(`HTTP ${res.status} on ${path}: ${msg || res.statusText}`);
  }
  return parseJSON(res);
}

export const api = {
  health: () => request('/health'),
  teamsInit: () => request('/teams/init', { method: 'POST' }),
  teamsList: () => request('/teams'),
  suggestions: (pos=null) => request(`/suggestions${pos ? `?position=${encodeURIComponent(pos)}` : ''}`),
  picksList: () => request('/picks'),
  makePick: (payload) => request('/picks', { method: 'POST', body: payload }),
  undoPick: (pickId) => request(`/picks/${pickId}`, { method: 'DELETE' }),
  importDemo: () => request('/admin/import/demo', { method: 'POST' }),
};
