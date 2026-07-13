// views/workspace.js — landing 1 vai trò: 3 mục Tác nghiệp / Báo cáo / Công cụ.
import { html, setHTML } from "../lib/dom.js";
import { getWorkspace } from "../lib/workspaces.js";

export async function render({ container, params }) {
  const ws = getWorkspace(params.key);
  if (!ws) {
    setHTML(container, html`<div class="kt-empty"><i class="fas fa-compass"></i><p>Không có bàn làm việc này. <a href="#/">Về trang chủ</a></p></div>`);
    return;
  }

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div class="kt-view-title"><i class="fas ${ws.icon}"></i> ${ws.label}</div>
        <div class="kt-sub">${ws.desc}</div>
      </div>
      <div class="kt-ws-sections">
        ${ws.sections.map((sec) => sectionCard(sec))}
      </div>
    `
  );
}

function sectionCard(sec) {
  return html`
    <div class="kt-card kt-ws-section">
      <div class="kt-card-head"><div class="kt-card-title"><i class="fas ${sec.icon}"></i> ${sec.title}</div></div>
      <div class="kt-card-body">
        <div class="kt-ws-items">
          ${sec.items.length ? sec.items.map((it) => itemLink(it)) : html`<div class="kt-sub">Sắp có…</div>`}
        </div>
      </div>
    </div>`;
}

function itemLink(it) {
  const isDesk = it.type === "desk";
  const href = isDesk ? it.href : "#" + it.route;
  const target = isDesk ? "_blank" : "";
  return html`<a class="kt-ws-item" href="${href}" target="${target}">
    <span class="kt-ws-item-ico"><i class="fas ${it.icon || "fa-arrow-right"}"></i></span>
    <span class="kt-ws-item-label">${it.label}</span>
    <span class="kt-ws-item-go"><i class="fas ${isDesk ? "fa-up-right-from-square" : "fa-chevron-right"}"></i></span>
  </a>`;
}
