/* Editor de inventario: palabras de la frase + pestañas/buscador + cuadrícula + secuencia (hotbar) + atajos.
   Lo usan la anotación y la adjudicación. Las vistas aportan la cabecera y el pie (botones de guardar). */
import { h, isTyping, debounce } from './util.js';
import { VirtualGrid, ZOOMS } from './grid.js';
import { Hotbar } from './hotbar.js';

const REC_MAX = 60;

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* sin almacenamiento */ } },
};

export const toPayload = (items) => items.map(({ picto_id, keyword, token }) => ({ picto_id, keyword, token }));

/**
 * @param {object} o
 * @param {Catalog} o.catalog
 * @param {number} o.userId        para las «Recientes» de cada persona
 * @param {object|null} o.analysis respuesta de analyze_sentence (tokens, segments, memory…)
 * @param {Array} o.items          secuencia inicial (con segment/conf opcionales)
 * @param {Node} o.header          contenido de la cabecera (frase, botones)
 * @param {Node} o.footer          contenido bajo la barra (acciones)
 * @param {boolean} o.blind        modo ciego: sin pestaña de sugeridos
 */
export function createEditor({ catalog, userId, analysis = null, items = [], header = null, footer = null, blind = false, onChange, onSubmit }) {
  const hasSug = !blind && !!analysis && analysis.segments.length > 0;
  const state = { tab: null, prevTab: null, query: '', focus: null };
  let sugMap = new Map(); // id → {segment, key, keyword} de la lista de sugeridos que se está viendo

  // ------------------------------------------------------------ DOM
  const tokensEl = h('div', { class: 'tokens', 'aria-label': 'Palabras de la frase' });
  const tabsEl = h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Pestañas del catálogo' });
  const searchInput = h('input', {
    type: 'search', placeholder: 'Buscar nombre o nº…  ( / )', autocomplete: 'off', spellcheck: false,
    'aria-label': 'Buscar pictograma por nombre o número',
  });
  const info = h('span', { class: 'info', 'aria-live': 'polite' });
  const zoomMinus = h('button', { class: 'mc-btn small', type: 'button', 'aria-label': 'Casillas más pequeñas', onClick: () => setZoom(zoomIdx - 1) }, '−');
  const zoomPlus = h('button', { class: 'mc-btn small', type: 'button', 'aria-label': 'Casillas más grandes', onClick: () => setZoom(zoomIdx + 1) }, '+');
  const viewport = h('div', { class: 'grid-viewport', 'aria-label': 'Catálogo de pictogramas' });
  const barEl = h('div', { class: 'hotbar' });
  const trashEl = h('div', { class: 'slot trash' }, h('span', { 'aria-hidden': 'true' }, '🗑'), h('small', {}, 'Quitar'));

  const root = h('div', { class: 'editor' },
    h('div', { class: 'panel' }, header, tokensEl),
    h('div', { class: 'tabs-row' }, tabsEl, h('div', { class: 'search' }, searchInput)),
    h('div', { class: 'grid-wrap' }, h('div', { class: 'panel' },
      h('div', { class: 'grid-info' }, info, h('span', { class: 'zoom' }, 'Tamaño ', zoomMinus, zoomPlus)), viewport)),
    h('div', { class: 'panel hotbar-wrap' }, h('div', { class: 'hotbar-row' }, barEl, trashEl), footer));

  // ------------------------------------------------------------ componentes
  const grid = new VirtualGrid(viewport, {
    onPick: (p, o) => pick(p, o),
    onHover: (p) => hotbar.setPreview(p),
  });

  const hotbar = new Hotbar(barEl, trashEl, {
    catalog,
    onChange: (seq) => { renderTokens(); updateCounts(); onChange?.(seq); },
    onSelect: (i, item) => handleSelect(item),
    onEnter: () => grid.focus(),
    onDropFromGrid: (i, p) => {
      const o = placementFor(p);
      hotbar.placeAt(i, p, o);
      pushRecent(p.id);
    },
  });
  hotbar.set(items, { active: items.length });

  // ------------------------------------------------------------ listas de cada pestaña
  const readRecent = () => store.get('pa.recent.' + userId, []);
  function pushRecent(id) {
    store.set('pa.recent.' + userId, [id, ...readRecent().filter((x) => x !== id)].slice(0, REC_MAX));
    updateCounts();
  }

  function sugList() {
    const f = state.focus?.segment;
    const segs = f != null && analysis.segments[f] ? [analysis.segments[f]] : analysis.segments;
    const out = [], notes = new Map(), map = new Map();
    for (const s of segs) {
      for (const c of s.candidates) {
        const p = catalog.get(c.id);
        if (!p || map.has(c.id)) continue;
        out.push(p);
        notes.set(c.id, `Sugerido para «${s.text}»`);
        map.set(c.id, { segment: s.index, key: s.key, keyword: c.keyword });
      }
    }
    return {
      items: out, notes, map,
      text: segs.length === 1 && f != null ? `Alternativas para «${segs[0].text}»` : 'Sugerencias para toda la frase',
      empty: 'No hay sugerencias. Usa el buscador o las categorías.',
    };
  }

  function memList() {
    const best = new Map();
    for (const [key, arr] of Object.entries(analysis?.memory || {})) {
      for (const m of arr) {
        const cur = best.get(m.id);
        if (!cur || m.count > cur.count) best.set(m.id, { count: m.count, key });
      }
    }
    const out = [], notes = new Map();
    for (const [id, m] of [...best].sort((a, b) => b[1].count - a[1].count)) {
      const p = catalog.get(id);
      if (!p) continue;
      out.push(p);
      notes.set(id, `Elegido ${m.count} ${m.count === 1 ? 'vez' : 'veces'} para «${m.key}»`);
    }
    return { items: out, notes, text: 'Lo que elegiste antes para las palabras de esta frase', empty: 'Todavía no has elegido pictogramas para las palabras de esta frase.' };
  }

  const recList = () => ({
    items: readRecent().map((id) => catalog.get(id)).filter(Boolean),
    text: 'Los últimos que elegiste', empty: 'Aún no has elegido ningún pictograma.',
  });

  const searchList = () => {
    const res = state.query.trim() ? catalog.search(state.query) : [];
    return {
      items: res,
      text: state.query.trim() ? `${res.length} resultado${res.length === 1 ? '' : 's'} para «${state.query.trim()}»` : 'Escribe un nombre o el número de un pictograma',
      empty: state.query.trim() ? 'Sin resultados. Prueba con otra forma de la palabra (singular, infinitivo…).' : 'Escribe en el buscador de arriba.',
    };
  };

  function listFor(tab) {
    if (tab === 'sug') return sugList();
    if (tab === 'mem') return memList();
    if (tab === 'rec') return recList();
    if (tab === 'search') return searchList();
    if (tab === 'all') return { items: catalog.sorted, text: `Todo el catálogo: ${catalog.all.length} pictogramas`, empty: '' };
    const gi = +tab.slice(1);
    return { items: catalog.groupLists[gi], text: `${catalog.groups[gi].label}: ${catalog.groupLists[gi].length} pictogramas`, empty: 'Sin pictogramas en esta categoría.' };
  }

  // ------------------------------------------------------------ pestañas
  const tabDefs = [];
  if (hasSug) tabDefs.push({ id: 'sug', label: 'Sugeridos' });
  tabDefs.push({ id: 'mem', label: 'Usados antes' }, { id: 'rec', label: 'Recientes' }, { id: 'search', label: 'Buscar' });
  catalog.groups.forEach((g, i) => tabDefs.push({ id: 'g' + i, label: g.label }));
  tabDefs.push({ id: 'all', label: 'Todos' });
  for (const t of tabDefs) {
    t.n = h('span', { class: 'n' });
    t.el = h('button', {
      class: 'tab', type: 'button', role: 'tab', 'aria-selected': 'false', tabIndex: -1,
      onClick: () => { selectTab(t.id); if (t.id === 'search') searchInput.focus(); },
    }, t.label, ' ', t.n);
    tabsEl.append(t.el);
  }
  tabsEl.addEventListener('keydown', (e) => {
    const i = tabDefs.findIndex((t) => t.id === state.tab);
    let to = i;
    if (e.key === 'ArrowRight') to = Math.min(tabDefs.length - 1, i + 1);
    else if (e.key === 'ArrowLeft') to = Math.max(0, i - 1);
    else if (e.key === 'Home') to = 0;
    else if (e.key === 'End') to = tabDefs.length - 1;
    else return;
    e.preventDefault();
    selectTab(tabDefs[to].id);
    tabDefs[to].el.focus();
  });

  function updateCounts() {
    for (const t of tabDefs) {
      let n = '';
      if (t.id === 'sug') n = sugCount();
      else if (t.id === 'mem') n = memList().items.length;
      else if (t.id === 'rec') n = readRecent().length;
      else if (t.id === 'search') n = state.query.trim() ? catalog.search(state.query).length : '';
      else if (t.id === 'all') n = '';
      else n = catalog.groupLists[+t.id.slice(1)].length;
      t.n.textContent = n === '' || n === 0 ? '' : n;
    }
  }
  const sugCount = () => new Set(analysis.segments.flatMap((s) => s.candidates.map((c) => c.id))).size;

  const defaultTab = () => (hasSug ? 'sug' : memList().items.length ? 'mem' : 'g0');

  function selectTab(id) {
    state.tab = id;
    for (const t of tabDefs) {
      const on = t.id === id;
      t.el.setAttribute('aria-selected', on ? 'true' : 'false');
      t.el.tabIndex = on ? 0 : -1;
    }
    refreshList();
    tabDefs.find((t) => t.id === id)?.el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }

  function refreshList() {
    const l = listFor(state.tab);
    sugMap = l.map || new Map();
    grid.setItems(l.items, { notes: l.notes || null, emptyText: l.empty });
    info.textContent = l.text;
    updateCounts();
  }

  // ------------------------------------------------------------ elegir un pictograma
  /** Decide a qué palabra de la frase se atribuye la elección (alimenta la «memoria»). */
  function placementFor(p) {
    const o = {};
    const s = state.tab === 'sug' ? sugMap.get(p.id) : null;
    if (s) { o.token = s.key; o.segment = s.segment; o.keyword = s.keyword; }
    else if (state.focus) { o.token = state.focus.key; o.segment = state.focus.segment; }
    return o;
  }

  function pick(p, { shift = false } = {}) {
    hotbar.place(p, { ...placementFor(p), append: shift });
    pushRecent(p.id);
  }

  // ------------------------------------------------------------ palabras de la frase
  function handleSelect(item) {
    const had = state.focus;
    if (item && item.segment != null && analysis?.segments[item.segment]) {
      const seg = analysis.segments[item.segment];
      state.focus = { tokenIdx: analysis.tokens.findIndex((t) => t.segment === item.segment), key: seg.key, segment: item.segment };
      if (state.tab === 'sug' && had?.segment !== item.segment) refreshList();
    } else {
      state.focus = null;
      if (had && state.tab === 'sug') refreshList();
    }
    renderTokens();
  }

  function renderTokens() {
    tokensEl.replaceChildren();
    if (!analysis) return;
    analysis.tokens.forEach((t, idx) => {
      if (t.pos === 'PUNCT' || t.pos === 'SPACE') return;
      const used = t.segment != null && hotbar.seq.some((it) => it.segment === t.segment);
      const nomatch = t.segment == null && !t.skip;
      const cls = 'chip' + (t.skip ? ' skip' : '') + (nomatch ? ' nomatch' : '') + (used ? ' used' : '')
        + (state.focus?.tokenIdx === idx ? ' active' : '');
      const tip = t.skip ? 'Palabra vacía: normalmente se omite (ver la guía)'
        : nomatch ? 'Sin sugerencia: pulsa para buscarla' : `Lema: ${t.lemma}`;
      tokensEl.append(h('button', { class: cls, type: 'button', 'data-tip': tip, onClick: () => onChip(t, idx) }, t.text));
    });
  }

  function onChip(t, idx) {
    if (t.segment != null) {
      const seg = analysis.segments[t.segment];
      state.focus = { tokenIdx: idx, key: seg.key, segment: t.segment };
      const slot = hotbar.indexOfSegment(t.segment);
      if (slot >= 0) hotbar.select(slot); // handleSelect fija el mismo foco
      if (hasSug) selectTab('sug');
    } else {
      state.focus = { tokenIdx: idx, key: t.key, segment: null };
      searchInput.value = t.key;
      applyQuery(t.key);
      grid.focus();
    }
    renderTokens();
  }

  // ------------------------------------------------------------ buscador
  function applyQuery(q) {
    state.query = q;
    if (q.trim()) {
      if (state.tab !== 'search') state.prevTab = state.tab;
      selectTab('search');
    } else if (state.tab === 'search') {
      selectTab(state.prevTab || defaultTab());
    }
  }
  const onInput = debounce(() => applyQuery(searchInput.value), 90);
  searchInput.addEventListener('input', onInput);
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      onInput.cancel();
      applyQuery(searchInput.value);
      const first = state.tab === 'search' ? grid.items[0] : null;
      if (first) {
        pick(first, { shift: e.shiftKey });
        searchInput.value = '';
        applyQuery('');
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      grid.focus();
    } else if (e.key === 'Escape') {
      searchInput.value = '';
      applyQuery('');
      searchInput.blur();
    }
  });

  // ------------------------------------------------------------ tamaño de casillas
  let zoomIdx = Math.max(0, Math.min(ZOOMS.length - 1, store.get('pa.zoom', 1)));
  function setZoom(i) {
    zoomIdx = Math.max(0, Math.min(ZOOMS.length - 1, i));
    store.set('pa.zoom', zoomIdx);
    zoomMinus.disabled = zoomIdx === 0;
    zoomPlus.disabled = zoomIdx === ZOOMS.length - 1;
    grid.setZoom(ZOOMS[zoomIdx]);
  }

  // ------------------------------------------------------------ atajos globales
  function onKey(e) {
    if (e.defaultPrevented || document.querySelector('dialog[open]')) return;
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key === 'Enter') { e.preventDefault(); onSubmit?.(); return; }
    if (isTyping(e.target)) return;
    const k = e.key.toLowerCase();
    if (mod && k === 'z' && !e.shiftKey) { e.preventDefault(); hotbar.undo(); return; }
    if (mod && (k === 'y' || (k === 'z' && e.shiftKey))) { e.preventDefault(); hotbar.redo(); return; }
    if (mod || e.altKey) return;
    if (/^[1-9]$/.test(e.key)) {
      const i = +e.key - 1;
      if (i <= hotbar.seq.length) { e.preventDefault(); hotbar.select(i); }
    } else if (e.key === '/') {
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
    } else if (e.key === 'Delete') {
      e.preventDefault();
      hotbar.remove(hotbar.active);
    }
  }
  document.addEventListener('keydown', onKey);

  // ------------------------------------------------------------ arranque
  setZoom(zoomIdx);
  renderTokens();
  state.prevTab = defaultTab();
  selectTab(state.prevTab);

  return {
    el: root,
    hotbar,
    grid,
    getItems: () => toPayload(hotbar.items()),
    focusSearch: () => searchInput.focus(),
    refreshTokens: renderTokens,
    destroy() {
      document.removeEventListener('keydown', onKey);
      onInput.cancel();
      grid.destroy();
    },
  };
}
