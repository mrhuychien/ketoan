// views/workspace.js — trang THAM KHẢO của 1 nghiệp vụ (/vt/:key):
// Hướng dẫn nghiệp vụ + lối tắt (Thực hiện / Báo cáo / Công cụ).
// Làm việc thật diễn ra ở trang `home` của workspace — có nút vào thẳng.
import { html, setHTML } from "../lib/dom.js";
import { getWorkspace, workHome } from "../lib/workspaces.js";

export async function render({ container, params }) {
  const ws = getWorkspace(params.key);
  if (!ws) {
    setHTML(container, html`<div class="kt-empty"><i class="fas fa-compass"></i><p>Không có nghiệp vụ này. <a href="#/">Về trang chủ</a></p></div>`);
    return;
  }

  const actions = ws.sections.find((s) => s.title === "Thực hiện");
  const others = ws.sections.filter((s) => s.title !== "Thực hiện");

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div>
          <div class="kt-view-title"><i class="fas ${ws.icon}"></i> ${ws.label} — hướng dẫn &amp; lối tắt</div>
          <div class="kt-sub">${ws.desc}</div>
        </div>
        <a class="kt-btn kt-btn--primary kt-btn--sm" href="#${workHome(ws)}"><i class="fas fa-arrow-right"></i> Vào trang làm việc</a>
      </div>

      ${ws.guide && ws.guide.length
        ? html`<div class="kt-card kt-guide kt-mb">
            <div class="kt-card-head kt-guide-head" id="ws-guide-toggle">
              <div class="kt-card-title"><i class="fas fa-book-open"></i> Hướng dẫn nghiệp vụ</div>
              <span class="kt-btn-icon"><i class="fas fa-chevron-down" id="ws-guide-chev"></i></span>
            </div>
            <div class="kt-card-body" id="ws-guide-body">
              <ol class="kt-guide-steps">
                ${ws.guide.map((g) => html`<li>${g}</li>`)}
              </ol>
            </div>
          </div>`
        : ""}

      ${actions
        ? html`<div class="kt-card kt-mb">
            <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-bolt"></i> Thực hiện</div></div>
            <div class="kt-card-body"><div class="kt-ws-actions">
              ${actions.items.map((it) => actionBtn(it))}
            </div></div>
          </div>`
        : ""}

      <div class="kt-ws-sections">
        ${others.map((sec) => sectionCard(sec))}
      </div>
    `
  );

  // Thu gọn/mở hướng dẫn (nhớ trạng thái theo nghiệp vụ).
  const gBody = container.querySelector("#ws-guide-body");
  const gChev = container.querySelector("#ws-guide-chev");
  const gKey = "kt-guide-" + ws.key;
  const applyGuide = (open) => {
    if (!gBody) return;
    gBody.style.display = open ? "" : "none";
    if (gChev) gChev.className = "fas " + (open ? "fa-chevron-up" : "fa-chevron-down");
  };
  if (gBody) {
    applyGuide(localStorage.getItem(gKey) !== "closed");
    container.querySelector("#ws-guide-toggle").addEventListener("click", () => {
      const open = gBody.style.display === "none";
      applyGuide(open);
      try { localStorage.setItem(gKey, open ? "open" : "closed"); } catch (_) {}
    });
  }
}

function actionBtn(it) {
  const isDesk = it.type === "desk";
  const href = isDesk ? it.href : "#" + it.route;
  return html`<a class="kt-ws-action" href="${href}" target="${isDesk ? "_blank" : ""}">
    <i class="fas ${it.icon || "fa-bolt"}"></i><span>${it.label}</span>
    ${isDesk ? html`<i class="fas fa-up-right-from-square kt-ws-action-ext"></i>` : ""}
  </a>`;
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
