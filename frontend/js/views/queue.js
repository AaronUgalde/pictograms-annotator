/* Lista de mis frases y pantalla de «has terminado». */
import { h } from '../util.js';

const LABEL = { done: 'Hecha', doubtful: 'Dudosa', skipped: 'Omitida', null: 'Pendiente' };
const CLS = { done: 'ok', doubtful: 'warn', skipped: '', null: 'blind' };

export async function queueView(root, ctx) {
  const { items } = await ctx.getQueue();
  let filter = 'all';
  const count = (s) => items.filter((i) => i.status === s).length;
  const done = items.length - count(null);
  const body = h('div', { class: 'panel' });
  const filters = [['all', 'Todas'], [null, 'Pendientes'], ['doubtful', 'Dudosas'], ['skipped', 'Omitidas'], ['done', 'Hechas']];
  const bar = h('div', { class: 'row' }, filters.map(([f, label]) =>
    h('button', { class: 'mc-btn small', type: 'button', dataset: { f: String(f) }, onClick: () => { filter = f; paint(); } }, label)));

  function paint() {
    for (const b of bar.children) b.classList.toggle('on', b.dataset.f === String(filter));
    const rows = items.filter((i) => filter === 'all' || i.status === filter);
    body.replaceChildren(rows.length ? h('table', { class: 'data' },
      h('thead', {}, h('tr', {}, h('th', {}, '#'), h('th', {}, 'Frase'), h('th', {}, 'Estado'))),
      h('tbody', {}, rows.map((r) => h('tr', { class: 'click', tabIndex: 0, onClick: () => ctx.go(`#/annotate/${r.id}`),
        onKeydown: (e) => { if (e.key === 'Enter') ctx.go(`#/annotate/${r.id}`); } },
      h('td', {}, r.seq), h('td', {}, r.text), h('td', {}, h('span', { class: 'badge ' + CLS[r.status] }, LABEL[r.status])))))) : h('p', { class: 'muted' }, 'No hay frases en este filtro.'));
  }

  root.append(h('div', { class: 'screen' },
    h('div', { class: 'panel' }, h('h2', {}, 'Mis frases'),
      h('div', { class: 'row' }, h('span', {}, `${done} de ${items.length} terminadas`),
        h('div', { class: 'bar', style: { flex: 1, maxWidth: '300px' } }, h('i', { style: { width: (items.length ? 100 * done / items.length : 0) + '%' } })))),
    bar, body));
  paint();
  return () => {};
}

export async function doneView(root, ctx) {
  const { items } = await ctx.getQueue();
  const c = (s) => items.filter((i) => i.status === s).length;
  const pending = c(null);
  root.append(h('div', { class: 'login panel' },
    h('h2', { class: 'pixel' }, pending ? 'Quedan frases' : '¡Listo!'),
    h('p', {}, pending ? `Te quedan ${pending} frases pendientes.` : 'Has terminado todas tus frases asignadas. Gracias.'),
    h('p', { class: 'muted' }, `Hechas: ${c('done')} · Dudosas: ${c('doubtful')} · Omitidas: ${c('skipped')}`),
    h('div', { class: 'row' },
      h('button', { class: 'mc-btn primary', type: 'button', onClick: () => ctx.go('#/queue') }, 'Ver mis frases'),
      pending ? h('button', { class: 'mc-btn', type: 'button', onClick: () => ctx.go('#/') }, 'Seguir anotando') : null)));
  return () => {};
}
