/* Lista de mis oraciones y pantalla de «has terminado». */
import { h } from '../util.js';

const LABEL = { done: 'Hecha', doubtful: 'Dudosa', skipped: 'Omitida', null: 'Pendiente' };
const CLS = { done: 'ok', doubtful: 'warn', skipped: '', null: 'blind' };

export async function queueView(root, ctx) {
  const { items } = await ctx.getQueue();
  if (!items.length) {
    root.append(h('div', { class: 'login panel' },
      h('h2', {}, 'Todavía no tienes oraciones'),
      h('p', {}, 'Aún no hay oraciones cargadas. Cuando tu docente las suba, vuelve a entrar con tu correo y te aparecerán aquí.'),
      h('button', { class: 'mc-btn', type: 'button', onClick: () => location.reload() }, 'Comprobar de nuevo')));
    return () => {};
  }
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
      h('thead', {}, h('tr', {}, h('th', {}, '#'), h('th', {}, 'Oración'), h('th', {}, 'Estado'))),
      h('tbody', {}, rows.map((r) => h('tr', { class: 'click', tabIndex: 0, onClick: () => ctx.go(`#/annotate/${r.id}`),
        onKeydown: (e) => { if (e.key === 'Enter') ctx.go(`#/annotate/${r.id}`); } },
      h('td', {}, r.seq), h('td', {}, r.text), h('td', {}, h('span', { class: 'badge ' + CLS[r.status] }, LABEL[r.status])))))) : h('p', { class: 'muted' }, 'No hay oraciones en este filtro.'));
  }

  root.append(h('div', { class: 'screen' },
    h('div', { class: 'panel' }, h('h2', {}, 'Mis oraciones'),
      h('div', { class: 'row' }, h('span', {}, `${done} de ${items.length} terminadas · te faltan ${items.length - done}`),
        h('div', { class: 'bar', style: { flex: 1, maxWidth: '300px' } }, h('i', { style: { width: (100 * done / items.length) + '%' } })))),
    bar, body));
  paint();
  return () => {};
}

export async function doneView(root, ctx) {
  const { items } = await ctx.getQueue();
  const c = (s) => items.filter((i) => i.status === s).length;
  const pending = c(null);
  root.append(h('div', { class: 'login panel' },
    h('h2', { class: 'pixel' }, pending ? 'Quedan oraciones' : '¡Listo!'),
    h('p', {}, pending ? `Te faltan ${pending} oraciones.` : 'Terminaste todas tus oraciones. ¡Gracias por tu ayuda!'),
    h('p', { class: 'muted' }, `Hechas: ${c('done')} · Dudosas: ${c('doubtful')} · Omitidas: ${c('skipped')}`),
    h('div', { class: 'row' },
      h('button', { class: 'mc-btn primary', type: 'button', onClick: () => ctx.go('#/queue') }, 'Ver mis oraciones'),
      pending ? h('button', { class: 'mc-btn', type: 'button', onClick: () => ctx.go('#/') }, 'Seguir anotando') : null)));
  return () => {};
}
