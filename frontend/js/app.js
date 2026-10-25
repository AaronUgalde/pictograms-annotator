/* Arranque, entrada con correo, navegación por hash, tema, progreso y guía de criterios. */
import { h, toast, initTooltip, mdToHtml, isTyping } from './util.js';
import { api, auth, ApiError } from './api.js';
import { loadCatalog } from './catalog.js';
import { annotateView } from './views/annotate.js';
import { queueView, doneView } from './views/queue.js';
import { adminView } from './views/admin.js';

const app = document.getElementById('app');
const ctx = { me: null, catalog: null, go: (hash) => { location.hash = hash; }, openGuide, _queue: null,
  getQueue() { return (this._queue ||= api('/api/my/queue').catch((e) => { this._queue = null; throw e; })); },
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

// ------------------------------------------------------------ barra superior
function renderChrome() {
  const nav = document.getElementById('nav');
  const mk = (label, hash) => h('a', { class: 'mc-btn small', href: hash, style: { textDecoration: 'none' } }, label);
  const isAdmin = ctx.me.role === 'admin';
  nav.replaceChildren(
    ...(isAdmin ? [mk('Panel', '#/admin')] : [mk('Anotar', '#/'), mk('Mis oraciones', '#/queue')]),
    h('button', { class: 'mc-btn small', type: 'button', onClick: openGuide }, 'Guía'));
  document.getElementById('userbox').replaceChildren(...[
    isAdmin ? null : h('span', { id: 'progress', class: 'progress', 'aria-live': 'polite' }),
    h('span', { class: 'muted' }, isAdmin ? 'Administración' : ctx.me.email),
    h('button', { class: 'mc-btn small', type: 'button', 'aria-label': 'Cambiar tema claro u oscuro', onClick: toggleTheme }, '◐'),
    h('button', { class: 'mc-btn small', type: 'button', onClick: () => { auth.clear(); location.hash = ''; location.reload(); } }, 'Salir'),
  ].filter(Boolean));
}

/** «Te faltan 12 de 15» con barra, siempre visible para el alumno. */
async function updateProgress() {
  const el = document.getElementById('progress');
  if (!el || ctx.me.role !== 'annotator') return;
  try {
    const { items } = await ctx.getQueue();
    const total = items.length, left = items.filter((i) => !i.status).length;
    el.replaceChildren(
      h('span', {}, !total ? 'Sin oraciones asignadas' : left ? `Te faltan ${left} de ${total}` : `¡Terminaste! ${total} de ${total}`),
      total ? h('span', { class: 'bar' }, h('i', { style: { width: (100 * (total - left) / total) + '%' } })) : null);
  } catch { /* el progreso es informativo */ }
}

// ------------------------------------------------------------ entrar
function loginView(msg) {
  document.getElementById('nav').replaceChildren();
  document.getElementById('userbox').replaceChildren();
  const err = h('p', { class: 'err', role: 'alert' }, msg || '');
  const finish = (token) => { auth.set(token); location.hash = ''; location.reload(); };
  const attempt = async (path, body, btn) => {
    err.textContent = '';
    btn.disabled = true;
    try { finish((await api(path, { method: 'POST', body })).token); } catch (e) { err.textContent = e.message; btn.disabled = false; }
  };

  const email = h('input', { type: 'email', name: 'email', placeholder: 'tu.correo@ejemplo.com', autocomplete: 'email', required: true, 'aria-label': 'Correo electrónico' });
  const go = h('button', { class: 'mc-btn primary', type: 'submit' }, 'Entrar');
  const form = h('form', { class: 'stack', onSubmit: (e) => { e.preventDefault(); attempt('/api/login', { email: email.value }, go); } },
    h('label', { for: 'login-email' }, 'Tu correo'), email, go);
  email.id = 'login-email';

  const pw = h('input', { type: 'password', name: 'password', autocomplete: 'current-password', 'aria-label': 'Contraseña de administración' });
  const adminGo = h('button', { class: 'mc-btn small', type: 'submit' }, 'Entrar como administrador');
  const adminForm = h('details', { class: 'admin-login' }, h('summary', {}, 'Soy administrador'),
    h('form', { class: 'stack', onSubmit: (e) => { e.preventDefault(); attempt('/api/admin/login', { password: pw.value }, adminGo); } }, pw, adminGo));

  app.replaceChildren(h('div', { class: 'login panel' },
    h('h2', {}, 'Anotador de pictogramas'),
    h('p', {}, 'Escribe tu correo para empezar. Si ya habías empezado, entra con el mismo correo y seguirás donde lo dejaste.'),
    form, err, adminForm));
  email.focus();
}

// ------------------------------------------------------------ rutas
async function route() {
  const seq = ++routeSeq;
  if (dispose) { try { dispose(); } catch { /* */ } dispose = null; }
  app.replaceChildren();
  const hash = location.hash || '#/';
  const isAdmin = ctx.me.role === 'admin';
  let m;
  try {
    let view;
    if (hash === '#/' || hash === '#') {
      if (isAdmin) return ctx.go('#/admin');
      const { next } = await api('/api/my/next');
      if (seq !== routeSeq) return;
      if (next) return ctx.go(`#/annotate/${next}`);
      const q = await ctx.getQueue();
      return ctx.go(q.items.length ? '#/done' : '#/queue');
    } else if (!isAdmin && (m = /^#\/annotate\/(\d+)$/.exec(hash))) view = (r) => annotateView(r, ctx, +m[1]);
    else if (!isAdmin && hash === '#/queue') view = (r) => queueView(r, ctx);
    else if (!isAdmin && hash === '#/done') view = (r) => doneView(r, ctx);
    else if (isAdmin && hash === '#/admin') view = (r) => adminView(r, ctx);
    else return ctx.go('#/');
    const holder = h('div', { class: 'view', style: { display: 'contents' } });
    app.append(holder);
    const d = await view(holder);
    if (seq !== routeSeq) { d?.(); return; }
    dispose = d;
    updateProgress();
  } catch (e) {
    if (seq !== routeSeq || e.status === 401) return;
    app.replaceChildren(h('div', { class: 'login panel' }, h('h2', {}, 'No se pudo abrir'), h('p', {}, e.message),
      h('button', { class: 'mc-btn', type: 'button', onClick: () => ctx.go('#/') }, 'Volver al inicio')));
  }
}

// ------------------------------------------------------------ arranque
async function boot() {
  window.addEventListener('pa:unauth', () => { auth.clear(); loginView('Tu sesión ya no es válida. Vuelve a entrar.'); });
  if (!auth.token) return loginView();
  try {
    ctx.me = await api('/api/me');
  } catch (e) { return e.status === 401 ? undefined : loginView(e.message); }

  if (ctx.me.role === 'annotator') { // el panel de administración no necesita el catálogo
    try {
      ctx.catalog = await loadCatalog();
    } catch (e) {
      renderChrome();
      return app.replaceChildren(h('div', { class: 'login panel' }, h('h2', {}, 'Catálogo no disponible'), h('p', {}, e instanceof ApiError ? e.message : String(e))));
    }
    initTooltip((id) => ctx.catalog.get(id), ctx.catalog.groupLabel);
  }
  renderChrome();
  window.addEventListener('hashchange', route);
  document.addEventListener('keydown', (e) => {
    if ((e.key === '?' || e.key === 'F1') && !isTyping(e.target)) { e.preventDefault(); openGuide(); }
  });
  route();
}

boot();
