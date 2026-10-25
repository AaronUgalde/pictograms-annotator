/* Panel de coordinación: progreso, personas y enlaces, importación y reparto, acuerdo, sesgo y exportación. */
import { h, toast, pct, num, dur, copyText, downloadBlob, parseCSV } from '../util.js';
import { api } from '../api.js';

const link = (token) => `${location.origin}/?t=${token}`;
const ROLE = { annotator: 'Anotador', reviewer: 'Revisor', admin: 'Admin' };

function section(title, ...kids) { return h('div', { class: 'panel' }, h('h2', {}, title), ...kids); }
function cards(pairs) { return h('div', { class: 'cards' }, pairs.map(([l, v]) => h('div', { class: 'card' }, l, h('b', {}, v ?? '—')))); }
const table = (head, rows) => h('table', { class: 'data' }, h('thead', {}, h('tr', {}, head.map((t) => h('th', {}, t)))),
  h('tbody', {}, rows.map((r) => h('tr', {}, r.map((c) => h('td', {}, c))))));

export async function adminView(root, ctx) {
  const wrap = h('div', { class: 'screen' });
  root.append(wrap);

  async function load() {
    const [dash, users] = await Promise.all([api('/api/admin/dashboard'), api('/api/admin/users')]);
    const tokens = new Map(users.items.map((u) => [u.id, u.token]));
    const t = dash.totals, ann = t.annotations, ag = dash.agreement;
    wrap.replaceChildren(
      section('Resumen', cards([
        ['Frases', t.sentences], ['Asignaciones', t.assignments], ['Hechas', ann.done || 0], ['Dudosas', ann.doubtful || 0],
        ['Omitidas', ann.skipped || 0], ['Por revisar', t.states.needs || 0], ['Con referencia', t.states.gold || 0]]),
      h('p', { class: 'muted' }, `Catálogo ${t.catalog.version || 'sin cargar'} (${t.catalog.count} pictogramas, ${t.catalog.frozen ? 'congelado' : 'SIN congelar'}) · guía ${t.guide_version}`)),

      section('Personas', usersTable(dash.users, tokens), addUserForm()),
      section('Frases y reparto', importForm(), assignForm()),
      section('Acuerdo entre anotadores', agreement(dash)),
      section('Sistema', systemBox(t.catalog)));
  }

  function usersTable(list, tokens) {
    return table(['Persona', 'Rol', 'Asignadas', 'Hechas', 'Dud.', 'Omit.', 'Progreso', 'Tiempo medio', 'Propuesta sin cambios', 'Dist. a otros', ''],
      list.map((u) => [
        u.name + (u.active ? '' : ' (inactiva)'), ROLE[u.role], u.assigned, u.done, u.doubtful, u.skipped,
        h('div', { class: 'bar' }, h('i', { style: { width: (u.assigned ? 100 * (u.done + u.doubtful + u.skipped) / u.assigned : 0) + '%' } })),
        dur(u.avg_seconds), pct(u.unchanged_rate), num(u.mean_distance_to_others),
        h('span', { class: 'row' },
          h('button', { class: 'mc-btn small', type: 'button', onClick: () => copyText(link(tokens.get(u.id))) }, 'Copiar enlace'),
          h('button', { class: 'mc-btn small', type: 'button', onClick: async () => {
            if (!confirm(`Se invalidará el enlace actual de ${u.name}. ¿Continuar?`)) return;
            const r = await api(`/api/admin/users/${u.id}/regen-token`, { method: 'POST' });
            copyText(link(r.token)); load();
          } }, 'Nuevo enlace'),
          h('button', { class: 'mc-btn small', type: 'button', onClick: async () => {
            try { await api(`/api/admin/users/${u.id}`, { method: 'PATCH', body: { active: !u.active } }); load(); } catch (e) { toast(e.message, 'error'); }
          } }, u.active ? 'Desactivar' : 'Activar'))]));
  }

  function addUserForm() {
    const name = h('input', { type: 'text', placeholder: 'Nombre', 'aria-label': 'Nombre' });
    const role = h('select', { 'aria-label': 'Rol' }, Object.entries(ROLE).map(([v, l]) => h('option', { value: v }, l)));
    const out = h('div', { class: 'muted' });
    return h('div', { class: 'row', style: { marginTop: '10px' } }, name, role,
      h('button', { class: 'mc-btn', type: 'button', onClick: async () => {
        try {
          const u = await api('/api/admin/users', { method: 'POST', body: { name: name.value, role: role.value } });
          copyText(link(u.token));
          toast(`${u.name} creada; enlace copiado`);
          load();
        } catch (e) { toast(e.message, 'error'); }
      } }, 'Añadir persona'), out);
  }

  function importForm() {
    const ta = h('textarea', { class: 'big', placeholder: 'Una frase por línea (o carga un .txt / .csv)', 'aria-label': 'Frases' });
    const batch = h('input', { type: 'text', placeholder: 'Lote (opcional)', 'aria-label': 'Lote' });
    const pilot = h('input', { type: 'checkbox' });
    const file = h('input', { type: 'file', accept: '.txt,.csv', onChange: async () => {
      const f = file.files[0]; if (!f) return;
      const text = await f.text();
      if (f.name.toLowerCase().endsWith('.csv')) {
        const rows = parseCSV(text);
        const head = rows[0]?.map((c) => c.trim().toLowerCase()) || [];
        const col = Math.max(head.indexOf('text'), head.indexOf('frase'));
        ta.value = (col >= 0 ? rows.slice(1).map((r) => r[col]) : rows.map((r) => r[0])).filter(Boolean).join('\n');
      } else ta.value = text;
    } });
    return h('div', {}, h('h3', {}, 'Importar frases'), ta,
      h('div', { class: 'row', style: { marginTop: '8px' } }, file, batch, h('label', {}, pilot, 'Piloto'),
        h('button', { class: 'mc-btn', type: 'button', onClick: async () => {
          const lines = ta.value.split('\n').map((l) => l.trim()).filter(Boolean);
          if (!lines.length) return toast('No hay frases', 'error');
          const r = await api('/api/admin/sentences', { method: 'POST', body: { lines, batch: batch.value.trim(), pilot: pilot.checked } });
          toast(`${r.added} añadidas, ${r.duplicates} repetidas`); ta.value = ''; load();
        } }, 'Importar')));
  }

  function assignForm() {
    const f = (label, props) => { const i = h('input', { type: 'number', ...props }); return [h('label', {}, label, i), i]; };
    const [l1, cov] = f('Cobertura ', { min: 1, max: 5, value: 2 });
    const [l2, tri] = f('% con 3 anotadores ', { min: 0, max: 100, value: 10 });
    const [l3, bli] = f('% a ciegas ', { min: 0, max: 100, value: 10 });
    const [l4, seed] = f('Semilla ', { value: 1 });
    const batch = h('input', { type: 'text', placeholder: 'Lote (todos si vacío)', 'aria-label': 'Lote a repartir' });
    const rev = h('input', { type: 'checkbox' });
    const out = h('pre', { class: 'muted' });
    return h('div', { style: { marginTop: '14px' } }, h('h3', {}, 'Repartir entre anotadores'),
      h('div', { class: 'row' }, l1, l2, l3, l4, batch, h('label', {}, rev, 'Incluir revisores'),
        h('button', { class: 'mc-btn primary', type: 'button', onClick: async () => {
          try {
            const r = await api('/api/admin/assign', { method: 'POST', body: {
              coverage: +cov.value, triple_fraction: +tri.value / 100, blind_fraction: +bli.value / 100,
              seed: seed.value === '' ? null : +seed.value, batch: batch.value.trim() || null, include_reviewers: rev.checked } });
            out.textContent = `Frases repartidas: ${r.sentences_assigned} · asignaciones: ${r.assignments_created} · triples: ${r.triple} · a ciegas: ${r.blind}`;
            load();
          } catch (e) { toast(e.message, 'error'); }
        } }, 'Repartir')), out,
      h('p', { class: 'hint' }, 'Solo se reparten las frases aún sin asignar; repartir otra vez no duplica nada.'));
  }

  function agreement(d) {
    const ag = d.agreement;
    const bias = d.bias, bm = bias.by_mode;
    return h('div', {},
      ag ? cards([['Parejas evaluadas', ag.pairs_evaluated], ['Coincidencia exacta', pct(ag.exact)], ['Distancia media', num(ag.distance)],
        ['Por posición', pct(ag.positional)], ['Jaccard', pct(ag.jaccard)]]) : h('p', { class: 'muted' }, 'Aún no hay frases con dos o más anotaciones.'),
      h('h3', {}, 'Sesgo de las sugerencias'),
      table(['Modo', 'Anotaciones', 'Tiempo medio', 'Propuesta aceptada sin cambios', 'Distancia entre anotadores'], [
        ['Con sugerencias', bm.with_suggestions?.n ?? 0, dur(bm.with_suggestions?.avg_seconds), pct(bm.with_suggestions?.accepted_unchanged_rate), num(bias.agreement_with_suggestions?.distance)],
        ['A ciegas', bm.blind?.n ?? 0, dur(bm.blind?.avg_seconds), '—', num(bias.agreement_blind?.distance)]]),
      d.pairs.length ? [h('h3', {}, 'Parejas con más desacuerdo'),
        table(['A', 'B', 'Frases', 'Exacta', 'Distancia'], d.pairs.slice(0, 10).map((p) => [p.a, p.b, p.n, pct(p.exact), num(p.distance)]))] : null,
      d.worst_sentences.length ? [h('h3', {}, 'Frases más conflictivas'),
        table(['#', 'Frase', 'Distancia', ''], d.worst_sentences.slice(0, 10).map((s) => [s.sentence_id, s.text, num(s.distance),
          h('button', { class: 'mc-btn small', type: 'button', onClick: () => ctx.go(`#/review/${s.sentence_id}`) }, 'Revisar')]))] : null);
  }

  function systemBox(cat) {
    const exp = (fmt) => async () => {
      const res = await api(`/api/admin/export?format=${fmt}`, { raw: true });
      downloadBlob(`pictogramas.${fmt}`, await res.blob());
    };
    return h('div', { class: 'row' },
      h('button', { class: 'mc-btn', type: 'button', onClick: exp('jsonl') }, 'Exportar JSONL'),
      h('button', { class: 'mc-btn', type: 'button', onClick: exp('csv') }, 'Exportar CSV'),
      h('button', { class: 'mc-btn', type: 'button', onClick: async () => { const r = await api('/api/admin/backup', { method: 'POST' }); toast('Copia creada: ' + r.path); } }, 'Copia de seguridad ahora'),
      cat.frozen ? h('span', { class: 'badge ok' }, 'Catálogo congelado') : h('button', { class: 'mc-btn danger', type: 'button', onClick: async () => {
        if (!confirm('Congelar el catálogo impide cambiarlo sin forzarlo. Hazlo antes de empezar a anotar. ¿Continuar?')) return;
        try { await api('/api/admin/catalog/freeze', { method: 'POST' }); load(); } catch (e) { toast(e.message, 'error'); }
      } }, 'Congelar catálogo'));
  }

  await load();
  return () => {};
}
