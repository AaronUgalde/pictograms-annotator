/* Secuencia de la frase («barra rápida»): casillas, casilla activa, arrastrar/soltar, papelera, deshacer y rehacer.
   Cada elemento: { picto_id, keyword, token, segment, conf }. `segment` y `conf` son solo de interfaz. */
import { h, drag } from './util.js';
import { imgUrl } from './api.js';

const MAX_HISTORY = 200;
const clone = (seq) => seq.map((x) => ({ ...x }));

export function makeItem(p, { keyword, token, segment } = {}) {
  return { picto_id: p.id, keyword: keyword || p.main, token: token ?? null, segment: segment ?? null, conf: null };
}

export class Hotbar {
  constructor(bar, trash, { catalog, onChange, onSelect, onEnter, onDropFromGrid }) {
    this.bar = bar;
    this.trash = trash;
    this.catalog = catalog;
    this.onChange = onChange;
    this.onSelect = onSelect;
    this.onEnter = onEnter;
    this.onDropFromGrid = onDropFromGrid;
    this.seq = [];
    this.active = 0;
    this.preview = null;
    this.undoStack = [];
    this.redoStack = [];
    this.slots = [];

    bar.setAttribute('role', 'listbox');
    bar.setAttribute('aria-label', 'Secuencia de pictogramas de la frase');
    bar.addEventListener('click', (e) => {
      const i = this._index(e);
      if (i >= 0) this.select(i);
    });
    bar.addEventListener('keydown', (e) => this._key(e));
    bar.addEventListener('dragstart', (e) => {
      const i = this._index(e);
      if (i < 0 || i >= this.seq.length) return e.preventDefault();
      drag.current = { kind: 'slot', index: i };
      e.dataTransfer.setData('text/plain', String(this.seq[i].picto_id));
      e.dataTransfer.effectAllowed = 'move';
    });
    bar.addEventListener('dragover', (e) => {
      const i = this._index(e);
      if (i < 0 || !drag.current) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = drag.current.kind === 'slot' ? 'move' : 'copy';
      this.slots.forEach((s, k) => s.classList.toggle('dragover', k === i));
    });
    bar.addEventListener('dragleave', (e) => {
      if (!bar.contains(e.relatedTarget)) this.slots.forEach((s) => s.classList.remove('dragover'));
    });
    bar.addEventListener('drop', (e) => {
      const i = this._index(e);
      const d = drag.current;
      this.slots.forEach((s) => s.classList.remove('dragover'));
      if (i < 0 || !d) return;
      e.preventDefault();
      if (d.kind === 'slot') this.move(d.index, i);
      else {
        const p = this.catalog.get(d.id);
        if (p) (this.onDropFromGrid ? this.onDropFromGrid(i, p) : this.placeAt(i, p));
      }
    });
    bar.addEventListener('dragend', () => {
      drag.current = null;
      this.slots.forEach((s) => s.classList.remove('dragover'));
    });

    trash.setAttribute('role', 'button');
    trash.tabIndex = 0;
    trash.setAttribute('aria-label', 'Papelera: quitar el pictograma de la casilla activa');
    trash.addEventListener('dragover', (e) => {
      if (drag.current?.kind !== 'slot') return;
      e.preventDefault();
      trash.classList.add('dragover');
    });
    trash.addEventListener('dragleave', () => trash.classList.remove('dragover'));
    trash.addEventListener('drop', (e) => {
      trash.classList.remove('dragover');
      if (drag.current?.kind !== 'slot') return;
      e.preventDefault();
      this.remove(drag.current.index);
    });
    const trashAct = () => this.remove(this.active);
    trash.addEventListener('click', trashAct);
    trash.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); trashAct(); }
    });

    this.render();
  }

  // ------------------------------------------------------------ lectura

  items() { return clone(this.seq); }
  get canUndo() { return this.undoStack.length > 0; }
  get canRedo() { return this.redoStack.length > 0; }
  indexOfSegment(segment) { return this.seq.findIndex((x) => x.segment === segment); }

  // ------------------------------------------------------------ mutaciones (con historial)

  _snap() { return { seq: clone(this.seq), active: this.active }; }

  _commit(fn) {
    this.undoStack.push(this._snap());
    if (this.undoStack.length > MAX_HISTORY) this.undoStack.shift();
    this.redoStack = [];
    fn();
    this.render();
    this.onChange?.(this.items());
    this._notifySelect();
  }

  _notifySelect() { this.onSelect?.(this.active, this.seq[this.active] ?? null); }

  /** Sustituye la secuencia entera sin historial (carga inicial). */
  set(seq, { active } = {}) {
    this.seq = clone(seq);
    this.active = active ?? this.seq.length;
    this.undoStack = [];
    this.redoStack = [];
    this.preview = null;
    this.render();
  }

  /** Sustituye la secuencia entera, deshacible (restaurar propuesta, copiar una anotación). */
  replaceAll(seq) {
    this._commit(() => { this.seq = clone(seq); this.active = this.seq.length; });
  }

  /** Clic en el catálogo: reemplaza la casilla activa (o añade si es la vacía) y avanza. */
  place(p, { append = false, keyword, token, segment } = {}) {
    this._commit(() => {
      const item = makeItem(p, { keyword, token, segment });
      if (append) {
        const atEnd = this.active >= this.seq.length;
        this.seq.push(item);
        if (atEnd) this.active = this.seq.length;
        return;
      }
      const replaced = this.seq[this.active];
      if (replaced && item.token == null) { item.token = replaced.token; item.segment = replaced.segment; }
      if (this.active >= this.seq.length) this.seq.push(item);
      else this.seq[this.active] = item;
      this.active = Math.min(this.active + 1, this.seq.length);
    });
  }

  /** Arrastrar desde el catálogo a una casilla concreta. */
  placeAt(i, p, opts = {}) {
    this._commit(() => {
      const item = makeItem(p, opts);
      if (i >= this.seq.length) this.seq.push(item);
      else {
        const replaced = this.seq[i];
        if (item.token == null) { item.token = replaced.token; item.segment = replaced.segment; }
        this.seq[i] = item;
      }
      this.active = Math.min(i + 1, this.seq.length);
    });
  }

  remove(i) {
    if (i < 0 || i >= this.seq.length) return;
    this._commit(() => {
      this.seq.splice(i, 1);
      if (this.active > i) this.active -= 1;
      this.active = Math.min(this.active, this.seq.length);
    });
  }

  move(from, to) {
    if (from < 0 || from >= this.seq.length) return;
    to = Math.min(to, this.seq.length - 1);
    if (from === to) return;
    this._commit(() => {
      const [it] = this.seq.splice(from, 1);
      this.seq.splice(to, 0, it);
      this.active = to;
    });
  }

  undo() { this._travel(this.undoStack, this.redoStack); }
  redo() { this._travel(this.redoStack, this.undoStack); }

  _travel(from, to) {
    const snap = from.pop();
    if (!snap) return;
    to.push(this._snap());
    this.seq = clone(snap.seq);
    this.active = snap.active;
    this.render();
    this.onChange?.(this.items());
    this._notifySelect();
  }

  // ------------------------------------------------------------ selección y vista previa

  select(i, { focus = false } = {}) {
    this.active = Math.max(0, Math.min(i, this.seq.length));
    this.render();
    if (focus) this.focusActive();
    this._notifySelect();
  }

  focusActive() { this.slots[this.active]?.focus(); }

  setPreview(p) {
    if ((this.preview?.id ?? null) === (p?.id ?? null)) return;
    this.preview = p || null;
    this._patch(this.active);
  }

  // ------------------------------------------------------------ teclado

  _index(e) {
    const s = e.target.closest ? e.target.closest('.slot') : null;
    return s && this.bar.contains(s) ? this.slots.indexOf(s) : -1;
  }

  _key(e) {
    if (e.ctrlKey || e.metaKey) return;
    const n = this.seq.length;
    switch (e.key) {
      case 'ArrowLeft':
      case 'ArrowRight': {
        const to = this.active + (e.key === 'ArrowLeft' ? -1 : 1);
        if (to < 0 || to > n) break;
        if (e.altKey) { if (to < n) this.move(this.active, to); this.focusActive(); }
        else this.select(to, { focus: true });
        break;
      }
      case 'Home': this.select(0, { focus: true }); break;
      case 'End': this.select(n, { focus: true }); break;
      case 'Delete':
      case 'Backspace': this.remove(this.active); this.focusActive(); break;
      case 'Enter':
      case ' ': this.onEnter?.(); break;
      default: return;
    }
    e.preventDefault();
  }

  // ------------------------------------------------------------ dibujo (reutiliza los elementos)

  render() {
    const n = this.seq.length + 1; // siempre hay una casilla vacía al final
    while (this.slots.length < n) {
      const el = this._makeSlot();
      this.slots.push(el);
      this.bar.append(el);
    }
    while (this.slots.length > n) this.slots.pop().remove();
    for (let i = 0; i < n; i++) this._patch(i);
  }

  _makeSlot() {
    const el = h('div', { class: 'slot', role: 'option', tabIndex: -1 });
    el._num = h('span', { class: 'num' });
    el._conf = h('span', { class: 'conf' }, '?');
    el._img = h('img', { alt: '' });
    el._img.draggable = false;
    el._plus = h('span', { class: 'noimg' }, '+');
    el._lbl = h('div', { class: 'lbl' });
    el._pid = 0;
    el.append(el._num, el._conf, h('div', { class: 'pic' }, el._img, el._plus), el._lbl);
    return el;
  }

  _patch(i) {
    const el = this.slots[i];
    if (!el) return;
    const item = this.seq[i];
    const isActive = i === this.active;
    const ghost = isActive && this.preview ? this.preview : null;
    const shown = ghost ? ghost.id : item ? item.picto_id : 0;
    const label = ghost ? ghost.main : item ? item.keyword || this.catalog.get(item.picto_id)?.main || '#' + item.picto_id : '';

    el.className = 'slot' + (item ? '' : ' empty') + (isActive ? ' active' : '') + (ghost ? ' ghost' : '');
    el.tabIndex = isActive ? 0 : -1;
    el.draggable = !!item;
    el.setAttribute('aria-selected', isActive ? 'true' : 'false');
    el.setAttribute('aria-label', item ? `Casilla ${i + 1}: ${label}` : `Casilla ${i + 1} vacía`);
    el._num.textContent = i + 1;

    if (item) { el.dataset.pid = item.picto_id; } else { delete el.dataset.pid; }
    const low = item?.conf === 'low' && !ghost;
    el._conf.style.display = low ? '' : 'none';
    if (low) el.dataset.note = 'Propuesta con confianza baja: revísala.'; else delete el.dataset.note;

    if (shown) {
      if (el._pid !== shown) { el._img.src = imgUrl(shown); el._pid = shown; }
      el._img.style.display = '';
      el._plus.style.display = 'none';
    } else {
      el._pid = 0;
      el._img.removeAttribute('src');
      el._img.style.display = 'none';
      el._plus.style.display = '';
    }
    el._lbl.textContent = label;
  }
}
