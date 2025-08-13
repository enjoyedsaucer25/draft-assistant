const API = import.meta.env.VITE_API_URL;

async function get(path) {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function post(path, body = undefined) {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: body ? JSON.stringify(body) : null
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function del(path) {
  const r = await fetch(`${API}${path}`, { method: "DELETE" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export const api = {
  health: () => get("/health"),
  teamsInit: () => post("/teams/init"),
  teamsList: () => get("/teams"),
  suggestions: (position = null) =>
    get(`/suggestions${position ? `?position=${encodeURIComponent(position)}` : ""}`),
  picksList: () => get("/picks"),
  makePick: (payload) => post("/picks", payload),
  undoPick: (pickId) => del(`/picks/${pickId}`),
  importDemo: () => post("/admin/import/demo"), // handy if you need to reseed
};
