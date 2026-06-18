// views/alerts.js — trung tâm cảnh báo: list rule + mục chi tiết + deep-link Desk.
import { api } from "../lib/api.js";
import { html, setHTML, on } from "../lib/dom.js";
import { formatVND, formatVNDShort, escapeHtml } from "../lib/format.js";

const SEV_LIGHT = { danger: "red", warning: "yellow", info: "green" };
const SEV_BADGE = { danger: "red", warning: "yellow", info: "green" };

export async function render({ container }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let d;
  try {
    d = await api.alerts();
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div class="kt-view-title"><i class="fas fa-triangle-exclamation"></i> Cảnh báo tác nghiệp</div>
        <div class="kt-sub">${d.alerts.length} cảnh báo · ${escapeHtml(d.as_of)}</div>
      </div>
      ${d.alerts.length === 0
        ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có cảnh báo. Mọi thứ ổn 👍</p></div>`
        : d.alerts.map((a) => alertCard(a))}
    `
  );

  // Toggle danh sách mục
  on(container, "click", "[data-toggle]", (e, el) => {
    const body = container.querySelector(`#items-${el.dataset.toggle}`);
    if (body) body.style.display = body.style.display === "none" ? "" : "none";
  });
}

function alertCard(a) {
  const items = a.items || [];
  return html`
    <div class="kt-alert kt-alert--${a.severity}">
      <div class="kt-alert-head">
        <div class="kt-alert-title"><span class="kt-light kt-light--${SEV_LIGHT[a.severity] || "yellow"}"></span> [${a.code}] ${a.title}</div>
        <div style="display:flex;gap:8px;align-items:center">
          <span class="kt-badge kt-badge--${SEV_BADGE[a.severity] || "yellow"}">${a.count} mục · ${formatVNDShort(a.amount)}</span>
          ${items.length ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" data-toggle="${a.code}">Chi tiết</button>` : ""}
          ${a.link ? html`<a class="kt-btn-icon" target="_blank" href="${a.link}"><i class="fas fa-up-right-from-square"></i></a>` : ""}
        </div>
      </div>
      <div class="kt-alert-hint">${a.hint || ""}</div>
      ${items.length
        ? html`<div class="kt-alert-items" id="items-${a.code}" style="display:none">
            ${items.slice(0, 50).map(
              (it) => html`<div class="kt-alert-item">
                <span>${it.label}</span>
                <span style="display:flex;gap:10px;align-items:center">
                  <b class="${it.over != null || it.amount < 0 ? "" : ""}">${formatVND(it.over != null ? it.over : it.amount)}</b>
                  ${it.link ? html`<a class="kt-btn-icon" target="_blank" href="${it.link}"><i class="fas fa-up-right-from-square"></i></a>` : ""}
                </span>
              </div>`
            )}
            ${items.length > 50 ? html`<div class="kt-sub">… và ${items.length - 50} mục khác</div>` : ""}
          </div>`
        : ""}
    </div>`;
}
