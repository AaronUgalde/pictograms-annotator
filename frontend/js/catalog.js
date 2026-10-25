/* Catálogo de ARASAAC en el navegador: índices por categoría y búsqueda tolerante a tildes y a coincidencias parciales. */
import { api } from './api.js';
import { norm } from './util.js';

const collator = new Intl.Collator('es', { sensitivity: 'base' });

export class Catalog {
  /** payload: { version, groups:[{id,label}], items:[[id, principal, palabras, grupos, flags]] } */
  constructor(payload) {
    this.version = payload.version;
    this.groups = payload.groups;
    this.byId = new Map();
    this.all = [];
    this.groupLists = this.groups.map(() => []);
    for (const [id, main, kws, gi, flags] of payload.items) {
      const p = { id, main, kws, groups: gi, flags, keys: kws.map(norm) };
      this.byId.set(id, p);
      this.all.push(p);
      for (const g of gi) this.groupLists[g].push(p);
    }
    const byName = (a, b) => collator.compare(a.main, b.main) || a.id - b.id;
    this.sorted = [...this.all].sort(byName);
    for (const l of this.groupLists) l.sort(byName);
  }

  get(id) { return this.byId.get(id); }

  groupLabel = (i) => this.groups[i]?.label ?? '';

  /**
   * Búsqueda: «agua», «hambre», «lavar manos» o un ID numérico. El ID exacto sale primero; después,
   * palabra clave exacta > empieza por > palabra que empieza por > contiene > todas las palabras.
   */
  search(query, limit = 800) {
    const q = norm(query);
    if (!q) return [];
    const words = q.split(' ');
    const head = [];
    if (/^\d+$/.test(q)) {
      const exact = this.byId.get(+q);
      if (exact) head.push(exact);
    }
    const scored = [];
    for (const p of this.all) {
      if (head[0] === p) continue;
      let best = Infinity;
      for (let i = 0; i < p.keys.length; i++) {
        const k = p.keys[i];
        let tier;
        if (k === q) tier = 0;
        else if (k.startsWith(q)) tier = 1;
        else if ((' ' + k).includes(' ' + q)) tier = 2;
        else if (k.includes(q)) tier = 3;
        else if (words.length > 1 && words.every((w) => (' ' + k).includes(' ' + w))) tier = 4;
        else continue;
        best = Math.min(best, tier * 1e6 + Math.min(i, 99) * 1e4 + k.length);
      }
      if (best < Infinity) scored.push([best, p]);
    }
    scored.sort((a, b) => a[0] - b[0] || collator.compare(a[1].main, b[1].main) || a[1].id - b[1].id);
    return head.concat(scored.slice(0, limit - head.length).map((s) => s[1]));
  }
}

export async function loadCatalog() {
  return new Catalog(await api('/api/catalog'));
}
