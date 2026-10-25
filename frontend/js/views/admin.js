/* Panel de administración: cargar oraciones, ajustes, progreso de cada alumno y descarga de resultados. */
import { h, toast, downloadBlob, parseCSV, pct } from '../util.js';
import { api } from '../api.js';

const section = (title, ...kids) => h('div', { class: 'panel' }, h('h2', {}, title), ...kids);
const cards = (pairs) => h('div', { class: 'cards' }, pairs.map(([l, v]) => h('div', { class: 'card' }, l, h('b', {}, v ?? '—'))));
const when = (iso) => (iso ? new Date(iso).toLocaleString('es', { dateStyle: 'short', timeStyle: 'short' }) : '—');

/** Lee un .txt (una oración por línea) o un .csv (columna «oracion», «frase» o «text»; si no, la primera). */
async function readSentences(file) {
  const text = (await file.text()).replace(/^\uFEFF/, '');
  if (!file.name.toLowerCase().endsWith('.csv')) return text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const rows = parseCSV(text);
  const head = (rows[0] || []).map((c) => c.trim().toLowerCase());
  const col = head.findIndex((c) => ['oracion', 'oración', 'frase', 'text', 'texto'].includes(c));
  const body = col >= 0 ? rows.slice(1) : rows;
  return body.map((r) => (r[Math.max(col, 0)] || '').trim()).filter(Boolean);
}

function statusBadge(s) {
  if (!s.assigned) return h('span', { class: 'badge' }, 'Sin oraciones');
  if (!s.remaining) return h('span', { class: 'badge ok' }, 'Terminó');
  if (!s.finished) return h('span', { class: 'badge blind' }, 'Sin empezar');
  return h('span', { class: 'badge warn' }, 'En curso');
}

export async function adminView(root, ctx) {
  const wrap = h('div', { class: 'screen' });
  root.append(wrap);
  let filterText = '';

  // ---- carga de oraciones
  function sentencesBox(total) {
    let lines = [];
    const info = h('span', { class: 'muted' }, 'Elige un archivo .txt (una oración por línea) o .csv (columna «oracion»).');
    const send = h('button', { class: 'mc-btn primary', type: 'button', disabled: true, onClick: async () => {
      send.disabled = true;
      try {
        const r = await api('/api/admin/sentences', { method: 'POST', body: { lines } });
        toast(`${r.added} oraciones nuevas${r.duplicates ? `, ${r.duplicates} repetidas ignoradas` : ''}`);
        load();
      } catch (e) { toast(e.message, 'error'); send.disabled = false; }
    } }, 'Cargar oraciones');
    const file = h('input', { type: 'file', accept: '.txt,.csv,text/plain,text/csv', 'aria-label': 'Archivo de oraciones', onChange: async () => {
      const f = file.files[0];
      if (!f) return;
      lines = await readSentences(f);
      info.textContent = lines.length ? `${lines.length} oraciones detectadas. Ejemplo: «${lines[0].slice(0, 70)}»` : 'No encontré oraciones en ese archivo.';
      send.disabled = !lines.length;
    } });
    const del = h('button', { class: 'mc-btn small danger', type: 'button', disabled: !total, onClick: async () => {
      if (!confirm('Se borrarán las oraciones que nadie ha anotado todavía (y sus asignaciones). Las ya anotadas se conservan. ¿Continuar?')) return;
      try { toast(`${(await api('/api/admin/sentences/unannotated', { method: 'DELETE' })).deleted} oraciones borradas`); load(); } catch (e) { toast(e.message, 'error'); }
    } }, 'Borrar las que nadie ha anotado');
    return section('Oraciones',
      h('div', { class: 'row' }, file, send), h('p', {}, info),
      h('p', { class: 'hint' }, 'Puedes subir más archivos cuando quieras: las oraciones repetidas se ignoran y los alumnos nuevos las recibirán automáticamente.'),
      h('div', { class: 'row' }, del));
  }

  // ---- ajustes
  function settingsBox(s) {
    const n = h('input', { type: 'number', min: 1, max: 500, value: s.sentences_per_student, 'aria-label': 'Oraciones por alumno', style: { width: '90px' } });
    const save = h('button', { class: 'mc-btn', type: 'button', onClick: async () => {
      try { await api('/api/admin/settings', { method: 'PUT', body: { sentences_per_student: +n.value } }); toast('Guardado'); load(); } catch (e) { toast(e.message, 'error'); }
    } }, 'Guardar');
    const open = h('input', { type: 'checkbox', checked: s.registration_open, onChange: async () => {
      try { await api('/api/admin/settings', { method: 'PUT', body: { registration_open: open.checked } }); toast(open.checked ? 'Registro abierto' : 'Registro cerrado'); }
      catch (e) { toast(e.message, 'error'); open.checked = !open.checked; }
    } });
    return section('Ajustes',
      h('div', { class: 'row' }, h('label', {}, 'Oraciones por alumno ', n), save),
      h('p', { class: 'hint' }, 'Cada alumno recibe este número de oraciones, empezando por las que tienen menos alumnos asignados. Si lo subes, los alumnos existentes reciben las que les falten la próxima vez que entren; si lo bajas, nadie pierde oraciones.'),
      h('div', { class: 'row' }, h('label', {}, open, 'Permitir que se creen cuentas nuevas')),
      h('p', { class: 'hint' }, s.allowed_domains.length
        ? `Solo pueden crear cuenta correos de: @${s.allowed_domains.join(', @')}. Quienes ya tienen cuenta siempre pueden entrar.`
        : 'Cualquier correo puede crear cuenta. Cierra el registro cuando ya estén todos tus alumnos.'));
  }

  // ---- tabla de alumnos
  function studentsBox(students) {
    const tbody = h('tbody');
    const paint = () => {
      const q = filterText.trim().toLowerCase();
      const rows = students.filter((s) => s.email.includes(q));
      tbody.replaceChildren(...rows.map((s) => {
        const p = s.assigned ? s.finished / s.assigned : 0;
        return h('tr', {},
          h('td', {}, s.email),
          h('td', {}, s.assigned), h('td', {}, s.finished), h('td', {}, h('b', {}, s.remaining)),
          h('td', {}, h('div', { class: 'row', style: { flexWrap: 'nowrap' } },
            h('div', { class: 'bar', role: 'progressbar', 'aria-valuenow': Math.round(p * 100), 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-label': `Progreso de ${s.email}` },
              h('i', { style: { width: p * 100 + '%' } })), h('span', {}, pct(p)))),
          h('td', {}, statusBadge(s)), h('td', {}, when(s.last_activity)));
      }));
      if (!rows.length) tbody.append(h('tr', {}, h('td', { colspan: 7, class: 'muted' }, students.length ? 'Ningún correo coincide.' : 'Todavía no hay alumnos. Comparte el enlace de la aplicación.')));
    };
    const search = h('input', { type: 'search', placeholder: 'Buscar correo…', value: filterText, 'aria-label': 'Buscar correo', onInput: () => { filterText = search.value; paint(); } });
    paint();
    return section('Alumnos', h('div', { class: 'row', style: { marginBottom: '8px' } }, search),
      h('table', { class: 'data' },
        h('thead', {}, h('tr', {}, ['Correo', 'Asignadas', 'Hechas', 'Faltan', 'Progreso', 'Estado', 'Última actividad'].map((t) => h('th', {}, t)))), tbody));
  }

  // ---- descargas
  function dataBox() {
    const dl = (fmt) => async () => {
      try { downloadBlob(`pictogramas.${fmt}`, await (await api(`/api/admin/export?format=${fmt}`, { raw: true })).blob()); } catch (e) { toast(e.message, 'error'); }
    };
    return section('Resultados',
      h('div', { class: 'row' },
        h('button', { class: 'mc-btn', type: 'button', onClick: dl('csv') }, 'Descargar CSV (Excel)'),
        h('button', { class: 'mc-btn', type: 'button', onClick: dl('jsonl') }, 'Descargar JSONL'),
        h('button', { class: 'mc-btn', type: 'button', onClick: async () => {
          try { downloadBlob('annotator-backup.db', await (await api('/api/admin/backup', { raw: true })).blob()); } catch (e) { toast(e.message, 'error'); }
        } }, 'Copia de seguridad (.db)')),
      h('p', { class: 'hint' }, 'Cada fila es la respuesta de un alumno a una oración. Descarga una copia de vez en cuando, sobre todo antes de cambiar el servidor.'));
  }

  async function load() {
    const d = await api('/api/admin/dashboard');
    const t = d.totals, c = t.coverage;
    wrap.replaceChildren(
      section('Resumen',
        cards([['Alumnos', t.students], ['Ya terminaron', `${t.students_finished} de ${t.students}`], ['Oraciones cargadas', t.sentences], ['Respuestas guardadas', t.annotations]]),
        h('p', { class: 'muted', style: { marginTop: '10px' } },
          `Oraciones con ninguna respuesta: ${c['0']} · con una: ${c['1']} · con dos o más: ${c['2+']}`)),
      sentencesBox(t.sentences), settingsBox(d.settings), studentsBox(d.students), dataBox());
  }

  await load();
  return () => {};
}
