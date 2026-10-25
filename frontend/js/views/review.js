/* Revisión y adjudicación: lista de frases con desacuerdo y comparación lado a lado (referencia dorada). */
import { h, toast, pct, num, dur } from '../util.js';
import { api, imgUrl } from '../api.js';
import { createEditor } from '../editor.js';

const STATES = [['needs', 'Necesitan revisión'], ['waiting', 'Esperando anotaciones'], ['agree', 'Con acuerdo total'], ['gold', 'Con referencia dorada'], ['all', 'Todas']];
const STATE_LABEL = { needs: 'Revisar', waiting: 'Esperando', agree: 'Acuerdo', gold: 'Dorada' };
const STATE_CLS = { needs: 'warn', waiting: 'blind', agree: 'ok', gold: 'ok' };
const PAGE = 100;

export function mini(catalog, it) {
  const p = catalog.get(it.picto_id);
  return h('div', { class: 'mini', dataset: { pid: it.picto_id } },
    h('div', { class: 'pic' }, h('img', { src: imgUrl(it.picto_id), alt: '', loading: 'lazy' })),
    h('span', {}, it.keyword || p?.main || '#' + it.picto_id));
}

export async function reviewList(root, ctx) {
  const st = { filter: 'needs', min: 0, offset: 0 };
  const cards = h('div', { class: 'cards' });
  const table = h('div', { class: 'panel' });
  const pager = h('div', { class: 'row' });
  const sel = h('select', { 'aria-label': 'Filtro', onChange: () => { st.filter = sel.value; st.offset = 0; load(); } },
    STATES.map(([v, l]) => h('option', { value: v }, l)));
  const min = h('input', { type: 'number', min: 0, max: 1, step: 0.05, value: 0, 'aria-label': 'Distancia mínima',
    onChange: () => { st.min = +min.value || 0; st.offset = 0; load(); } });
  const auto = h('button', { class: 'mc-btn', type: 'button', onClick: async () => {
    if (!confirm('Se guardará como referencia dorada toda frase con cobertura completa y acuerdo total. ¿Continuar?')) return;
    try { const r = await api('/api/gold/auto-accept', { method: 'POST' }); toast(`${r.accepted} frases aceptadas`); load(); } catch (e) { toast(e.message, 'error'); }
  } }, 'Aceptar las de acuerdo total');

  async function load() {
    const d = await api(`/api/review/sentences?filter=${st.filter}&min_distance=${st.min}&limit=${PAGE}&offset=${st.offset}`);
    cards.replaceChildren(...STATES.filter(([v]) => v !== 'all').map(([v, l]) =>
      h('div', { class: 'card' }, l, h('b', {}, d.counts[v] || 0))));
    table.replaceChildren(d.items.length ? h('table', { class: 'data' },
      h('thead', {}, h('tr', {}, ['#', 'Frase', 'Anot.', 'Dudosas', 'Distancia', 'Estado'].map((t) => h('th', {}, t)))),
      h('tbody', {}, d.items.map((r) => h('tr', { class: 'click', tabIndex: 0, onClick: () => ctx.go(`#/review/${r.id}`),
        onKeydown: (e) => { if (e.key === 'Enter') ctx.go(`#/review/${r.id}`); } },
      h('td', {}, r.id), h('td', {}, r.text, r.blind ? [' ', h('span', { class: 'badge blind' }, 'ciego')] : null),
      h('td', {}, `${r.n}/${r.target}`), h('td', {}, r.doubtful || ''), h('td', {}, num(r.distance)),
      h('td', {}, h('span', { class: 'badge ' + STATE_CLS[r.state] }, STATE_LABEL[r.state])))))) : h('p', { class: 'muted' }, 'No hay frases en este filtro.'));
    pager.replaceChildren(
      h('button', { class: 'mc-btn small', type: 'button', disabled: st.offset === 0, onClick: () => { st.offset -= PAGE; load(); } }, '◀'),
      h('span', {}, `${d.total ? st.offset + 1 : 0}–${Math.min(st.offset + PAGE, d.total)} de ${d.total}`),
      h('button', { class: 'mc-btn small', type: 'button', disabled: st.offset + PAGE >= d.total, onClick: () => { st.offset += PAGE; load(); } }, '▶'));
  }

  root.append(h('div', { class: 'screen' }, h('div', { class: 'panel' }, h('h2', {}, 'Revisión'), cards),
    h('div', { class: 'row' }, h('label', {}, 'Mostrar ', sel), h('label', {}, 'Distancia mínima ', min), h('span', { class: 'spacer' }), auto),
    table, pager));
  await load();
  return () => {};
}

export async function reviewDetail(root, ctx, sid) {
  const d = await api(`/api/review/${sid}`);
  const cat = ctx.catalog;
  const copyBtn = (it) => h('button', { class: 'mc-btn small', type: 'button', onClick: () => {
    ed.hotbar.replaceAll(it.items.map((x) => ({ picto_id: x.picto_id, keyword: x.keyword, token: x.token ?? null, segment: null, conf: null })));
  } }, 'Copiar');

  const m = d.metrics;
  const metrics = m ? h('div', { class: 'cards' },
    [['Coincidencia exacta', pct(m.exact)], ['Distancia', num(m.distance)], ['Por posición', pct(m.positional)], ['Solape (Jaccard)', pct(m.jaccard)]]
      .map(([l, v]) => h('div', { class: 'card' }, l, h('b', {}, v)))) : h('p', { class: 'muted' }, 'Hace falta más de una anotación para medir el acuerdo.');

  const rows = d.annotations.map((a) => h('div', { class: 'cmp-row' },
    h('div', { class: 'cmp-who' }, a.annotator, h('small', {},
      [{ done: 'Hecha', doubtful: 'Dudosa', skipped: 'Omitida' }[a.status], a.blind ? 'a ciegas' : a.accepted_unchanged ? 'aceptó propuesta' : a.from_suggestion ? 'editó propuesta' : '', dur(a.seconds)].filter(Boolean).join(' · '))),
    h('div', { class: 'cmp-seq' }, a.items.map((it) => mini(cat, it)), a.note ? h('em', { class: 'muted', style: { alignSelf: 'center' } }, `«${a.note}»`) : null),
    a.items.length ? copyBtn(a) : null));
  if (d.gold) rows.push(h('div', { class: 'cmp-row' },
    h('div', { class: 'cmp-who' }, 'Referencia dorada', h('small', {}, `${d.gold.adjudicator || ''} · ${d.gold.updated_at}`)),
    h('div', { class: 'cmp-seq' }, d.gold.items.map((it) => mini(cat, it)), d.gold.note ? h('em', { class: 'muted' }, `«${d.gold.note}»`) : null)));

  const header = h('div', {},
    h('div', { class: 'head-row' }, h('span', { class: 'counter pixel' }, `Frase ${sid}`), h('div', { class: 'sentence' }, d.sentence.text),
      d.sentence.blind ? h('span', { class: 'badge blind' }, 'A ciegas') : null),
    h('div', { style: { marginTop: '8px' } }, metrics),
    h('div', { class: 'compare', style: { marginTop: '8px' } }, rows));

  const note = h('input', { type: 'text', class: 'note', maxLength: 500, value: d.gold?.note || '', placeholder: 'Nota de adjudicación (opcional)', 'aria-label': 'Nota' });
  const next = d.next_needs;
  const save = async () => {
    const items = ed.getItems();
    if (!items.length) return toast('La referencia necesita al menos un pictograma.', 'error');
    try {
      const r = await api(`/api/gold/${sid}`, { method: 'PUT', body: { items, note: note.value.trim() } });
      toast('Referencia guardada');
      ctx.go(r.next ? `#/review/${r.next}` : '#/review');
    } catch (e) { toast(e.message, 'error'); }
  };
  const footer = h('div', { class: 'actions' },
    h('button', { class: 'mc-btn', type: 'button', onClick: () => ctx.go('#/review') }, '◀ Lista'),
    note, h('span', { class: 'spacer' }),
    next ? h('button', { class: 'mc-btn', type: 'button', onClick: () => ctx.go(`#/review/${next}`) }, 'Saltar ▶') : null,
    h('button', { class: 'mc-btn primary', type: 'button', onClick: save }, 'Guardar referencia y siguiente ▶'));

  const ed = createEditor({
    catalog: cat, userId: ctx.me.id, analysis: d.analysis, header, footer,
    items: (d.gold?.items || []).map((x) => ({ picto_id: x.picto_id, keyword: x.keyword, token: null, segment: null, conf: null })),
    onSubmit: save,
  });
  root.append(ed.el);
  return () => ed.destroy();
}
