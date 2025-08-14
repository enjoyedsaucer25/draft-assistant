const BASE = import.meta.env.VITE_API_URL || '';
const API  = BASE || '/api';

const join = (base, path) =>
  `${String(base).replace(/\/+$/,'')}/${String(path || '').replace(/^\/+/,'')}`;

async function request(path, { method='GET', body, headers={} } = {}) {
  const url = join(API, path);
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const msg = await res.text().catch(()=> '');
    throw new Error(`HTTP ${res.status} on ${url}: ${msg || res.statusText}`);
  }
  return parseJSON(res);
}
