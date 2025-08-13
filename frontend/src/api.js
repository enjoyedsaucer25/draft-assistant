const API = '/api';

async function get(path)  { const r = await fetch(`${API}${path}`); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function post(path, body) { const r = await fetch(`${API}${path}`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body ?? {}) }); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function del_(path) { const r = await fetch(`${API}${path}`, { method:'DELETE' }); if(!r.ok) throw new Error(await r.text()); return r.json(); }

export const api = {
  health: () => get('/health'),
  teamsInit: () => post('/teams/init'),
  teamsList: () => get('/teams'),
  suggestions: (pos=null) => get(`/suggestions${pos ? `?position=${encodeURIComponent(pos)}`:''}`),
  picksList: () => get('/picks'),
  makePick: (payload) => post('/picks', payload),
  undoPick: (pickId) => del_(`/picks/${pickId}`),
  importDemo: (token) => fetch('/api/admin/import/demo', { method:'POST', headers: token ? { 'x-token': token } : {} }).then(r => r.json()),
};
