/* Arranque, identificación, navegación por hash, tema y guía de criterios. */
import { h, toast, initTooltip, mdToHtml, isTyping } from './util.js';
import { api, auth, ApiError } from './api.js';
import { loadCatalog } from './catalog.js';
import { annotateView } from './views/annotate.js';
import { queueView, doneView } from './views/queue.js';
import { reviewList, reviewDetail } from './views/review.js';
import { adminView } from './views/admin.js';

const app = document.getElementById('app');
const ctx = { me: null, catalog: null, go: (hash) => { location.hash = hash; }, openGuide, _queue: null,
  getQueue() { return (this._queue ||= api('/api/my/queue')); },
  invalidateQueue() { this._queue = null; } };
let dispose = null;
let routeSeq = 0;

// ------------------------------------------------------------ tema
function applyTheme(t) { document.documentElement.dataset.theme = t; try { localStorage.setItem('pa.theme', t); } catch { /* */ } }
const toggleTheme = () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');

// ------------------------------------------------------------ guía
async function openGuide() {
  const dlg = document.getElementById('dlg');
  try {
    const g = await api('/api/guide');
    const body = h('div', { class: 'guide' });
    body.innerHTML = mdToHtml(g.markdown); // el texto se escapa dentro de mdToHtml
    dlg.replaceChildren(h('div', { class: 'panel' },
      h('div', { class: 'row' }, h('span', { class: 'badge' }, 'Guía ' + g.version), h('span', { class: 'spacer' }),
        h('button', { class: 'mc-btn small', type: 'button', onClick: () => body.querySelector('[id$="ejemplos"]')?.scrollIntoView() }, 'Ir a los ejemplos'),
        h('button', { class: 'mc-btn small', type: 'button', onClick: () => dlg.close() }, 'Cerrar (Esc)')), body));
    dlg.showModal();
  } catch (e) { toast(e.message, 'error'); }
}

// ------------------------------------------------------------ navegación
function renderChrome() {
  const nav = document.getElementById('nav');
  const mk = (label, hash) => h('a', { class: 'mc-btn small', href: hash, style: { textDecoration: 'none' } }, label);
  nav.replaceChildren(...[mk('Anotar', '#/'), mk('Mis frases', '#/queue'),
    ctx.me.role !== 'annotator' ? mk('Revisión', '#/review') : null,
    ctx.me.role === 'admin' ? mk('Panel', '#/admin') : null,
    h('button', { class: 'mc-btn small', type: 'button', onClick: openGuide }, 'Guía')].filter(Boolean));
  document.getElementById('userbox').replaceChildren(
    h('span', {}, ctx.me.name),
    h('button', { class: 'mc-btn small', type: 'button', 'aria-label': 'Cambiar tema claro u oscuro', onClick: toggleTheme }, '◐'),
    h('button', { class: 'mc-btn small', type: 'button', onClick: () => { auth.clear(); location.hash = ''; location.reload(); } }, 'Salir'));
}

function loginView(msg) {
  document.getElementById('nav').replaceChildren();
  document.getElementById('userbox').replaceChildren();
  const input = h('input', { type: 'text', placeholder: 'Pega aquí tu enlace o tu código', 'aria-label': 'Enlace o código personal' });
  const go = () => {
    let v = input.value.trim();
    const m = /[?&]t=([^&#\s]+)/.exec(v);
    if (m) v = m[1];
    if (!v) return;
    auth.set(v);
    location.hash = '';
    location.reload();
  };
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
  app.replaceChildren(h('div', { class: 'login panel' }, h('h2', {}, 'Entrar'),
    h('p', {}, 'Usa el enlace personal que te dio la persona que coordina el proyecto.'),
    msg ? h('p', { style: { color: 'var(--danger)', fontWeight: 700 } }, msg) : null,
    input, h('button', { class: 'mc-btn primary', type: 'button', onClick: go }, 'Entrar')));
  input.focus();
}

// ------------------------------------------------------------ rutas
async function route() {
  const seq = ++routeSeq;
  if (dispose) { try { dispose(); } catch { /* */ } dispose = null; }
  app.replaceChildren();
  const hash = location.hash || '#/';
  let m;
  try {
    let view;
    if (hash === '#/' || hash === '#') {
      const { next } = await api('/api/my/next');
      if (seq !== routeSeq) return;
      if (next) return ctx.go(`#/annotate/${next}`);
      const q = await ctx.getQueue();
      if (q.items.length) return ctx.go('#/done');
      return ctx.go(ctx.me.role === 'admin' ? '#/admin' : ctx.me.role === 'reviewer' ? '#/review' : '#/queue');
    } else if ((m = /^#\/annotate\/(\d+)$/.exec(hash))) view = (r) => annotateView(r, ctx, +m[1]);
    else if (hash === '#/queue') view = (r) => queueView(r, ctx);
    else if (hash === '#/done') view = (r) => doneView(r, ctx);
    else if (hash === '#/review' && ctx.me.role !== 'annotator') view = (r) => reviewList(r, ctx);
    else if ((m = /^#\/review\/(\d+)$/.exec(hash)) && ctx.me.role !== 'annotator') view = (r) => reviewDetail(r, ctx, +m[1]);
    else if (hash === '#/admin' && ctx.me.role === 'admin') view = (r) => adminView(r, ctx);
    else return ctx.go('#/');
    const holder = h('div', { class: 'view', style: { display: 'contents' } });
    app.append(holder);
    const d = await view(holder);
    if (seq !== routeSeq) { d?.(); return; }
    dispose = d;
  } catch (e) {
    if (seq !== routeSeq || e.status === 401) return;
    app.replaceChildren(h('div', { class: 'login panel' }, h('h2', {}, 'No se pudo abrir'), h('p', {}, e.message),
      h('button', { class: 'mc-btn', type: 'button', onClick: () => ctx.go('#/') }, 'Volver al inicio')));
  }
}

// ------------------------------------------------------------ arranque
async function boot() {
  const url = new URL(location.href);
  const t = url.searchParams.get('t');
  if (t) {
    auth.set(t);
    url.searchParams.delete('t');
    history.replaceState(null, '', url.pathname + (url.search || '') + url.hash);
  }
  window.addEventListener('pa:unauth', () => { auth.clear(); loginView('Tu enlace no es válido o está desactivado.'); });
  if (!auth.token) return loginView();
  try {
    ctx.me = await api('/api/me');
  } catch (e) { return e.status === 401 ? undefined : loginView(e.message); }

  try {
    ctx.catalog = await loadCatalog();
  } catch (e) {
    renderChrome();
    return app.replaceChildren(h('div', { class: 'login panel' }, h('h2', {}, 'Catálogo no disponible'), h('p', {}, e instanceof ApiError ? e.message : String(e))));
  }
  initTooltip((id) => ctx.catalog.get(id), ctx.catalog.groupLabel);
  renderChrome();
  window.addEventListener('hashchange', route);
  document.addEventListener('keydown', (e) => {
    if ((e.key === '?' || e.key === 'F1') && !isTyping(e.target)) { e.preventDefault(); openGuide(); }
  });
  route();
}

boot();
