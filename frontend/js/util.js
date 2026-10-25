/* Utilidades compartidas: DOM, normalización, avisos, tooltip, markdown, descargas. */

/** Estado de arrastre compartido (dataTransfer no se puede leer durante dragover). */
export const drag = { current: null };

/** Igual que catalog.norm del backend: minúsculas, sin tildes (conserva ñ), solo letras/dígitos. */
export function norm(s) {
  s = String(s ?? '').toLowerCase().replace(/ñ/g, '\u0000');
  s = s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  s = s.replace(/\u0000/g, 'ñ');
  return s.replace(/[^0-9a-zñ]+/g, ' ').trim();
}

/** Crea un elemento: h('div', {class:'x', onClick: fn}, hijos…). Nunca interpreta HTML. */
export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  let value;
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k === 'value') value = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'for') el.htmlFor = v;
    else if (k in el && typeof v !== 'object') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, kids);
  if (value !== undefined) el.value = value;
  return el;
}

export function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    el.append(k.nodeType ? k : document.createTextNode(String(k)));
  }
  return el;
}

export function debounce(fn, ms) {
  let t;
  const f = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  f.cancel = () => clearTimeout(t);
  return f;
}

export function isTyping(t) {
  return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
}

export const pct = (x, d = 0) => (x == null ? '—' : (x * 100).toFixed(d) + ' %');
export const num = (x, d = 2) => (x == null ? '—' : Number(x).toFixed(d));
export function dur(s) {
  if (s == null) return '—';
  s = Math.round(s);
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s`;
}

// ---------------------------------------------------------------- avisos

let toastTimer;
export function toast(msg, kind = '') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'show' + (kind ? ' ' + kind : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ''; }, kind === 'error' ? 5200 : 2600);
}

// ---------------------------------------------------------------- tooltip

/** Tooltip único por delegación: [data-pid] (pictograma), [data-tip] (texto) y [data-note] (línea extra). */
export function initTooltip(getPicto, groupLabel) {
  const tip = document.getElementById('tip');
  let current = null;

  const hide = () => { tip.style.display = 'none'; current = null; };
  const place = (x, y) => {
    const w = tip.offsetWidth, hh = tip.offsetHeight;
    tip.style.left = Math.max(6, Math.min(x + 16, innerWidth - w - 8)) + 'px';
    tip.style.top = Math.max(6, Math.min(y + 18, innerHeight - hh - 8)) + 'px';
  };

  document.addEventListener('mouseover', (e) => {
    const el = e.target.closest ? e.target.closest('[data-pid],[data-tip]') : null;
    if (!el) return hide();
    if (el === current) return;
    current = el;
    tip.replaceChildren();
    if (el.dataset.pid) {
      const p = getPicto(+el.dataset.pid);
      if (!p) return hide();
      tip.append(h('b', {}, p.main), h('div', { class: 'm' }, `ID ${p.id}`));
      const others = p.kws.filter((k) => k !== p.main);
      if (others.length) tip.append(h('div', { class: 'm' }, 'También: ' + others.slice(0, 8).join(', ')));
      if (p.groups.length) tip.append(h('div', { class: 'm' }, 'Categorías: ' + p.groups.map(groupLabel).join(', ')));
      if (p.flags & 1) tip.append(h('div', {}, '⚠ Marcado por ARASAAC como sexual'));
      if (p.flags & 2) tip.append(h('div', {}, '⚠ Marcado por ARASAAC como violento'));
    } else {
      tip.append(h('div', {}, el.dataset.tip));
    }
    if (el.dataset.note) tip.append(h('div', { class: 'm' }, el.dataset.note));
    tip.style.display = 'block';
    place(e.clientX, e.clientY);
  });
  document.addEventListener('mousemove', (e) => { if (current) place(e.clientX, e.clientY); });
  document.addEventListener('mousedown', hide);
  document.addEventListener('dragstart', hide);
  document.addEventListener('scroll', hide, true);
  document.addEventListener('keydown', hide);
}

// ---------------------------------------------------------------- markdown mínimo (para la guía)

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function inline(s) {
  s = esc(s);
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');
  return s;
}

const slug = (s) => norm(s).replace(/ /g, '-');

/** Convierte el subconjunto de Markdown que usa la guía. Todo el texto se escapa antes. */
export function mdToHtml(md) {
  const lines = String(md || '').replace(/\r/g, '').split('\n');
  const out = [];
  let list = null;
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  const isTableRow = (l) => /^\s*\|.*\|\s*$/.test(l);
  const cells = (l) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let m;
    if (!line.trim()) { closeList(); continue; }

    if ((m = /^(#{1,4})\s+(.*)$/.exec(line))) {
      closeList();
      out.push(`<h${m[1].length} id="g-${slug(m[2])}">${inline(m[2])}</h${m[1].length}>`);
    } else if (isTableRow(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      closeList();
      const head = cells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && isTableRow(lines[i])) rows.push(cells(lines[i++]));
      i--;
      out.push('<table><thead><tr>' + head.map((c) => `<th>${inline(c)}</th>`).join('') + '</tr></thead><tbody>' +
        rows.map((r) => '<tr>' + r.map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') + '</tbody></table>');
    } else if (/^\s*>/.test(line)) {
      closeList();
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ''));
      i--;
      out.push(`<blockquote>${inline(buf.join(' '))}</blockquote>`);
    } else if ((m = /^\s*[-*]\s+(.*)$/.exec(line))) {
      if (list !== 'ul') { closeList(); out.push('<ul>'); list = 'ul'; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = /^\s*\d+\.\s+(.*)$/.exec(line))) {
      if (list !== 'ol') { closeList(); out.push('<ol>'); list = 'ol'; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else {
      closeList();
      const buf = [line.trim()];
      while (i + 1 < lines.length && lines[i + 1].trim() && !/^(\s*[-*>|]|\s*\d+\.\s|#{1,4}\s)/.test(lines[i + 1])) buf.push(lines[++i].trim());
      out.push(`<p>${inline(buf.join(' '))}</p>`);
    }
  }
  closeList();
  return out.join('\n');
}

// ---------------------------------------------------------------- portapapeles y descargas

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = h('textarea', { value: text, style: { position: 'fixed', opacity: 0 } });
    document.body.append(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
  }
  toast('Copiado');
}

export function downloadBlob(filename, blob) {
  const a = h('a', { href: URL.createObjectURL(blob), download: filename });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

/** CSV mínimo con comillas ("" escapa). Devuelve filas de celdas. */
export function parseCSV(text) {
  const rows = [];
  let row = [], cell = '', q = false;
  text = text.replace(/^\uFEFF/, '');
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; }
      else cell += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(cell); cell = '';
      if (row.some((x) => x !== '')) rows.push(row);
      row = [];
    } else cell += c;
  }
  row.push(cell);
  if (row.some((x) => x !== '')) rows.push(row);
  return rows;
}
