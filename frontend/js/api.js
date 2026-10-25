/* Cliente de la API: identificación por token y manejo uniforme de errores. */

const KEY = 'pa.token';

export const auth = {
  get token() { try { return localStorage.getItem(KEY) || ''; } catch { return ''; } },
  set(t) { try { localStorage.setItem(KEY, t); } catch { /* sin almacenamiento */ } },
  clear() { try { localStorage.removeItem(KEY); } catch { /* idem */ } },
};

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

function detailText(d, fallback) {
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || '').filter(Boolean).join('; ') || fallback;
  return fallback;
}

export async function api(path, { method = 'GET', body, raw = false } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: { 'x-token': auth.token, ...(body !== undefined ? { 'content-type': 'application/json' } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, 'No se pudo conectar con el servidor');
  }
  if (res.status === 401) {
    window.dispatchEvent(new Event('pa:unauth'));
    throw new ApiError(401, 'Identificación no válida');
  }
  if (!res.ok) {
    let msg = res.statusText || 'Error';
    try { msg = detailText((await res.json()).detail, msg); } catch { /* cuerpo no JSON */ }
    throw new ApiError(res.status, msg);
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

export const imgUrl = (id) => `/img/${id}.png`;
