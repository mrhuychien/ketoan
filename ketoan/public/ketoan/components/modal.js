// modal.js — modal overlay tái dùng. openModal trả về {root, close, body}.
import { setHTML } from "../lib/dom.js";

export function openModal({ title = "", body = "", icon = "fa-circle-info", maxWidth = 520 } = {}) {
  const overlay = document.createElement("div");
  overlay.className = "kt-modal-overlay is-show";
  overlay.innerHTML = `
    <div class="kt-modal" style="max-width:${maxWidth}px">
      <div class="kt-modal-head">
        <div class="kt-modal-title"><i class="fas ${icon}"></i> <span></span></div>
        <button class="kt-modal-close" type="button" aria-label="Đóng"><i class="fas fa-times"></i></button>
      </div>
      <div class="kt-modal-body"></div>
    </div>`;
  overlay.querySelector(".kt-modal-title span").textContent = title;
  const bodyEl = overlay.querySelector(".kt-modal-body");
  setHTML(bodyEl, body);

  function close() {
    overlay.classList.remove("is-show");
    setTimeout(() => overlay.remove(), 180);
  }
  overlay.querySelector(".kt-modal-close").addEventListener("click", close);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
  });

  document.body.appendChild(overlay);
  return { root: overlay, body: bodyEl, close };
}
