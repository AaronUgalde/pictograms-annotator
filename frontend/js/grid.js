/* Cuadrícula virtualizada del catálogo: solo existen en el DOM las casillas visibles (más un margen).
   Las imágenes se piden cuando el scroll se detiene, para no lanzar miles de peticiones al desplazarse rápido. */
import { h, drag } from './util.js';
import { imgUrl } from './api.js';

const GAP = 4;
export const ZOOMS = [48, 64, 80, 96]; // tamaño del pictograma en px

export class VirtualGrid {
  constructor(viewport, { onPick, onHover }) {
    this.vp = viewport;
    this.onPick = onPick;
    this.onHover = onHover;
    this.items = [];
    this.notes = null;
    this.cursor = -1;
    this.focused = false;
    this.cells = new Map();
    this.cols = 1;
    this.rowH = 104;
    this.pitchX = 88;
    this.imgTimer = 0;

    this.spacer = h('div', { class: 'grid-spacer' });
    this.win = h('div', { class: 'grid-window' });
    this.empty = h('div', { class: 'grid-empty hidden' });
    this.spacer.append(this.win);
    viewport.append(this.spacer, this.empty);
    viewport.tabIndex = 0;
    viewport.setAttribute('role', 'listbox');

    this._onScroll = () => { if (!this._raf) this._raf = requestAnimationFrame(() => { this._raf = 0; this.render(); }); };
    viewport.addEventListener('scroll', this._onScroll, { passive: true });
    viewport.addEventListener('click', (e) => this._click(e));
    viewport.addEventListener('mouseover', (e) => {
      const c = e.target.closest('.cell');
      if (c) this.onHover?.(this.items[+c.dataset.idx] ?? null);
    });
    viewport.addEventListener('mouseleave', () => this.onHover?.(null));
    viewport.addEventListener('dragstart', (e) => {
      const c = e.target.closest('.cell');
      if (!c) return;
      drag.current = { kind: 'grid', id: +c.dataset.pid };
      e.dataTransfer.setData('text/plain', c.dataset.pid);
      e.dataTransfer.effectAllowed = 'copy';
    });
    viewport.addEventListener('dragend', () => { drag.current = null; });
    viewport.addEventListener('focus', () => {
      this.focused = true;
      if (this.cursor < 0 && this.items.length) this.cursor = 0;
      this.updateSel();
    });
    viewport.addEventListener('blur', () => { this.focused = false; this.updateSel(); this.onHover?.(null); });
    viewport.addEventListener('keydown', (e) => this._key(e));

    this.ro = new ResizeObserver(() => this.render(true));
    this.ro.observe(viewport);
  }

  focus() { this.vp.focus(); }

  destroy() {
    this.ro.disconnect();
    clearTimeout(this.imgTimer);
    cancelAnimationFrame(this._raf);
  }

  /** items: pictogramas del catálogo. notes: Map id → texto extra para el tooltip. */
  setItems(items, { notes = null, emptyText = '' } = {}) {
    this.items = items;
    this.notes = notes;
    this.cursor = items.length ? 0 : -1;
    this.empty.textContent = emptyText;
    this.empty.classList.toggle('hidden', items.length > 0);
    this.vp.scrollTop = 0;
    this.render(true);
  }

  setZoom(pic) {
    this.vp.style.setProperty('--pic', pic + 'px');
    this.vp.style.setProperty('--cell-w', pic + 20 + 'px');
    this.vp.style.setProperty('--cell-h', pic + 36 + 'px');
    this.render(true);
    if (this.cursor >= 0) this.ensureVisible(this.cursor);
  }

  measure() {
    const cs = getComputedStyle(this.vp);
    const cw = parseFloat(cs.getPropertyValue('--cell-w')) || 84;
    const ch = parseFloat(cs.getPropertyValue('--cell-h')) || 100;
    this.pitchX = cw + GAP;
    this.rowH = ch + GAP;
    this.cols = Math.max(1, Math.floor((this.vp.clientWidth - GAP) / this.pitchX));
  }

  render(force = false) {
    if (force) {
      this.measure();
      for (const el of this.cells.values()) el.remove();
      this.cells.clear();
      const rows = Math.ceil(this.items.length / this.cols);
      this.spacer.style.height = (rows ? rows * this.rowH + GAP : 0) + 'px';
    }
    const total = Math.ceil(this.items.length / this.cols);
    const r0 = Math.max(0, Math.floor(this.vp.scrollTop / this.rowH) - 2);
    const r1 = Math.min(total, Math.ceil((this.vp.scrollTop + this.vp.clientHeight) / this.rowH) + 2);
    const start = r0 * this.cols;
    const end = Math.min(this.items.length, r1 * this.cols);

    for (const [i, el] of this.cells) {
      if (i < start || i >= end) { el.remove(); this.cells.delete(i); }
    }
    const frag = document.createDocumentFragment();
    for (let i = start; i < end; i++) {
      if (this.cells.has(i)) continue;
      const el = this._cell(i);
      this.cells.set(i, el);
      frag.append(el);
    }
    this.win.append(frag);
    this.updateSel();
    this._scheduleImages();
  }

  _cell(i) {
    const p = this.items[i];
    const note = this.notes?.get(p.id);
    const img = h('img', { alt: '', decoding: 'async' });
    img.draggable = false; // se arrastra la casilla, no la imagen
    img.dataset.src = imgUrl(p.id);
    img.addEventListener('error', () => img.replaceWith(h('span', { class: 'noimg' }, 'sin imagen')));
    const dataset = { pid: p.id, idx: i };
    if (note) dataset.note = note;
    return h('div', {
      class: 'slot cell',
      role: 'option',
      id: 'gc' + p.id,
      'aria-label': p.main,
      'aria-selected': 'false',
      draggable: true,
      dataset,
      style: { left: GAP + (i % this.cols) * this.pitchX + 'px', top: GAP + Math.floor(i / this.cols) * this.rowH + 'px' },
    }, h('div', { class: 'pic' }, img), h('div', { class: 'lbl' }, p.main), p.flags ? h('span', { class: 'flag' }, '!') : null);
  }

  _scheduleImages() {
    clearTimeout(this.imgTimer);
    this.imgTimer = setTimeout(() => {
      for (const el of this.cells.values()) {
        const img = el.querySelector('img[data-src]');
        if (img) { img.src = img.dataset.src; img.removeAttribute('data-src'); }
      }
    }, 70);
  }

  updateSel() {
    for (const [i, el] of this.cells) {
      const on = this.focused && i === this.cursor;
      el.classList.toggle('sel', on);
      el.setAttribute('aria-selected', on ? 'true' : 'false');
    }
    const cur = this.cells.get(this.cursor);
    if (cur && this.focused) this.vp.setAttribute('aria-activedescendant', cur.id);
    else this.vp.removeAttribute('aria-activedescendant');
  }

  ensureVisible(i) {
    const top = Math.floor(i / this.cols) * this.rowH;
    if (top < this.vp.scrollTop) this.vp.scrollTop = top;
    else if (top + this.rowH + GAP > this.vp.scrollTop + this.vp.clientHeight) {
      this.vp.scrollTop = top + this.rowH + GAP - this.vp.clientHeight;
    }
    this.render();
  }

  setCursor(i, { scroll = false } = {}) {
    this.cursor = i;
    if (scroll) {
      this.ensureVisible(i);
      this.onHover?.(this.items[i] ?? null);
    }
    this.updateSel();
  }

  _click(e) {
    const c = e.target.closest('.cell');
    if (!c) return;
    const i = +c.dataset.idx;
    this.setCursor(i);
    this.onPick?.(this.items[i], { shift: e.shiftKey });
  }

  _key(e) {
    const n = this.items.length;
    if (!n || e.ctrlKey || e.metaKey || e.altKey) return;
    const page = Math.max(1, Math.floor(this.vp.clientHeight / this.rowH) - 1) * this.cols;
    let c = this.cursor < 0 ? 0 : this.cursor;
    switch (e.key) {
      case 'ArrowRight': c += 1; break;
      case 'ArrowLeft': c -= 1; break;
      case 'ArrowDown': c += this.cols; break;
      case 'ArrowUp': if (c - this.cols >= 0) c -= this.cols; break;
      case 'PageDown': c += page; break;
      case 'PageUp': c -= page; break;
      case 'Home': c = 0; break;
      case 'End': c = n - 1; break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (this.items[c]) this.onPick?.(this.items[c], { shift: e.shiftKey });
        return;
      default: return;
    }
    e.preventDefault();
    this.setCursor(Math.max(0, Math.min(n - 1, c)), { scroll: true });
  }
}
