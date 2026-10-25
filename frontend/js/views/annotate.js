/* Pantalla de anotación: una frase, secuencia propuesta, guardar y pasar a la siguiente. */
import { h, toast } from '../util.js';
import { api } from '../api.js';
import { createEditor } from '../editor.js';

export async function annotateView(root, ctx, sid) {
  const [data, queue] = await Promise.all([api(`/api/annotate/${sid}`), ctx.getQueue()]);
  const { sentence, annotation, analysis } = data;
  const blind = sentence.blind;
  const proposalIds = blind ? [] : analysis.sequence.map((x) => x.picto_id);

  const proposalItems = () => analysis.sequence.map((x) => ({
    picto_id: x.picto_id, keyword: x.keyword, token: x.token, segment: x.segment,
    conf: analysis.segments[x.segment]?.confidence === 'low' ? 'low' : null,
  }));

  function initialItems() {
    if (annotation) {
      const used = new Set();
      return annotation.items.map((it) => {
        let segment = null;
        const s = it.token ? analysis.segments.find((x) => x.key === it.token && !used.has(x.index)) : null;
        if (s) { segment = s.index; used.add(s.index); }
        return { picto_id: it.picto_id, keyword: it.keyword, token: it.token, segment, conf: null };
      });
    }
    return blind ? [] : proposalItems();
  }

  let mode = annotation?.status === 'doubtful' ? 'doubtful' : annotation?.status === 'skipped' ? 'skipped' : null;
  let saving = false;
  let ed = null;

  const noteInput = h('input', {
    type: 'text', class: 'note', maxLength: 500, value: annotation?.note || '',
    placeholder: 'Nota (obligatoria si marcas dudosa u omitida)', 'aria-label': 'Nota',
  });
  const snapshot = () => JSON.stringify([ed ? ed.getItems().map((i) => i.picto_id) : null, mode, noteInput.value.trim()]);

  // ---- cabecera y pie
  const btnDoubt = h('button', { class: 'mc-btn', type: 'button', onClick: () => toggle('doubtful') }, 'Dudosa');
  const btnSkip = h('button', { class: 'mc-btn', type: 'button', onClick: () => toggle('skipped') }, 'Omitir');
  const header = h('div', { class: 'head-row' },
    h('span', { class: 'counter pixel' }, `Frase ${sentence.pos} de ${sentence.total}`),
    h('div', { class: 'sentence' }, sentence.text),
    blind ? h('span', { class: 'badge blind', 'data-tip': 'Modo ciego: sin propuesta del sistema' }, 'A ciegas') : null,
    annotation ? h('span', { class: 'badge ' + (annotation.status === 'done' ? 'ok' : 'warn') },
      { done: 'Hecha', doubtful: 'Dudosa', skipped: 'Omitida' }[annotation.status]) : null,
    btnDoubt, btnSkip);

  const prevIdx = queue.items.findIndex((q) => q.id === sentence.id) - 1;
  const btnPrev = h('button', { class: 'mc-btn', type: 'button', disabled: prevIdx < 0, onClick: goPrev }, '◀ Anterior');
  const btnRestore = h('button', { class: 'mc-btn', type: 'button', onClick: restore, 'data-tip': 'Vuelve a la propuesta del sistema' }, '↺ Propuesta');
  const btnAccept = h('button', { class: 'mc-btn', type: 'button', onClick: acceptAll }, 'Aceptar propuesta ✓');
  const btnSave = h('button', { class: 'mc-btn primary', type: 'button', onClick: save }, 'Guardar y siguiente ▶');
  const footer = h('div', {},
    h('div', { class: 'actions' }, btnPrev, noteInput,
      blind || !proposalIds.length ? null : [btnRestore, btnAccept], h('span', { class: 'spacer' }), btnSave),
    h('div', { class: 'hint', style: { marginTop: '6px' } },
      h('kbd', {}, '1'), '–', h('kbd', {}, '9'), ' casilla · ', h('kbd', {}, 'Mayús'), '+clic añade al final · ',
      h('kbd', {}, 'Supr'), ' quita · ', h('kbd', {}, 'Ctrl'), '+', h('kbd', {}, 'Z'), ' deshace · ',
      h('kbd', {}, '/'), ' busca · ', h('kbd', {}, 'Ctrl'), '+', h('kbd', {}, 'Intro'), ' guarda · ', h('kbd', {}, '?'), ' guía'));

  ed = createEditor({
    catalog: ctx.catalog, userId: ctx.me.id, analysis, items: initialItems(), header, footer, blind,
    onSubmit: () => save(),
  });
  root.append(ed.el);
  const initial = snapshot();
  const isDirty = () => snapshot() !== initial;
  paintMode();

  // ---- tiempo dedicado (solo cuenta con la pestaña visible y actividad reciente)
  let seconds = 0, lastAct = Date.now();
  const act = () => { lastAct = Date.now(); };
  document.addEventListener('pointermove', act);
  document.addEventListener('keydown', act);
  const tick = setInterval(() => { if (!document.hidden && Date.now() - lastAct < 60000) seconds += 1; }, 1000);
  const warn = (e) => { if (isDirty()) { e.preventDefault(); e.returnValue = ''; } };
  window.addEventListener('beforeunload', warn);

  // ---- acciones
  function paintMode() {
    btnDoubt.classList.toggle('on', mode === 'doubtful');
    btnSkip.classList.toggle('on', mode === 'skipped');
  }
  function toggle(m) { mode = mode === m ? null : m; paintMode(); if (mode) noteInput.focus(); }

  function restore() {
    ed.hotbar.replaceAll(proposalItems());
    ed.refreshTokens();
  }

  async function acceptAll() {
    const cur = ed.getItems().map((i) => i.picto_id);
    if (cur.length && JSON.stringify(cur) !== JSON.stringify(proposalIds)
      && !confirm('Se reemplazará tu secuencia por la propuesta del sistema. ¿Continuar?')) return;
    mode = null; paintMode();
    restore();
    await save();
  }

  async function save() {
    if (saving) return;
    const items = ed.getItems();
    const note = noteInput.value.trim();
    const status = mode || 'done';
    if (status === 'done' && !items.length) return toast('Añade al menos un pictograma, o márcala como omitida.', 'error');
    if (status === 'doubtful' && !items.length) return toast('Una frase dudosa necesita al menos un pictograma.', 'error');
    if (status !== 'done' && !note) { noteInput.focus(); return toast('Escribe una nota breve que explique la duda.', 'error'); }
    saving = true; btnSave.disabled = true;
    try {
      const res = await api(`/api/annotations/${sid}`, { method: 'PUT', body: { status, items, note, seconds } });
      ctx.invalidateQueue();
      window.removeEventListener('beforeunload', warn);
      ctx.go(res.next ? `#/annotate/${res.next}` : '#/done');
    } catch (e) {
      saving = false; btnSave.disabled = false;
      toast(e.message, 'error');
    }
  }

  function goPrev() {
    if (isDirty() && !confirm('Hay cambios sin guardar. ¿Descartarlos?')) return;
    window.removeEventListener('beforeunload', warn);
    ctx.go(`#/annotate/${queue.items[prevIdx].id}`);
  }

  return () => {
    window.removeEventListener('beforeunload', warn);
    clearInterval(tick);
    document.removeEventListener('pointermove', act);
    document.removeEventListener('keydown', act);
    ed.destroy();
  };
}
