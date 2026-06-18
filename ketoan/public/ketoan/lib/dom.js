// dom.js — tagged template `html` (auto-escape) + tiện ích DOM nhỏ.
import { escapeHtml } from "./format.js";

// Đánh dấu chuỗi đã an toàn để KHÔNG escape lần nữa (vd HTML con đã build).
class Raw {
  constructor(v) { this.value = v; }
}
export function raw(v) { return new Raw(v == null ? "" : String(v)); }

// html`...${x}...` → escape mọi interpolation trừ Raw/array-of-raw.
export function html(strings, ...values) {
  let out = strings[0];
  for (let i = 0; i < values.length; i++) {
    out += render(values[i]) + strings[i + 1];
  }
  return out;
}

function render(v) {
  if (v == null || v === false) return "";
  if (v instanceof Raw) return v.value;
  if (Array.isArray(v)) return v.map(render).join("");
  return escapeHtml(v);
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// Gắn HTML vào container và trả về container.
export function setHTML(container, htmlStr) {
  container.innerHTML = htmlStr;
  return container;
}

// Ủy quyền sự kiện: on(container, 'click', '.kt-x', handler)
export function on(root, type, selector, handler) {
  root.addEventListener(type, (e) => {
    const target = e.target.closest(selector);
    if (target && root.contains(target)) handler(e, target);
  });
}
