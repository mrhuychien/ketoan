// dom.js — tagged template `html` (auto-escape interpolation) + tiện ích DOM nhỏ.
import { escapeHtml } from "./format.js";

// Chuỗi HTML đã an toàn → KHÔNG escape lại khi lồng vào template khác.
// toString() trả về chuỗi để .join("") / nối chuỗi vẫn hoạt động.
class Raw {
  constructor(v) { this.value = v == null ? "" : String(v); }
  toString() { return this.value; }
}
export function raw(v) { return new Raw(v); }

// html`...${x}...` → escape mọi interpolation TRỪ Raw / mảng (đệ quy).
export function html(strings, ...values) {
  let out = strings[0];
  for (let i = 0; i < values.length; i++) {
    out += render(values[i]) + strings[i + 1];
  }
  return new Raw(out); // <- đánh dấu an toàn để lồng không bị escape
}

function render(v) {
  if (v == null || v === false) return "";
  if (v instanceof Raw) return v.value;
  if (Array.isArray(v)) return v.map(render).join("");
  return escapeHtml(v);
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// Gắn HTML vào container (chấp nhận Raw hoặc string) và trả về container.
export function setHTML(container, htmlStr) {
  container.innerHTML = htmlStr instanceof Raw ? htmlStr.value : String(htmlStr == null ? "" : htmlStr);
  return container;
}

// Ủy quyền sự kiện: on(container, 'click', '.kt-x', handler)
export function on(root, type, selector, handler) {
  root.addEventListener(type, (e) => {
    const target = e.target.closest(selector);
    if (target && root.contains(target)) handler(e, target);
  });
}
