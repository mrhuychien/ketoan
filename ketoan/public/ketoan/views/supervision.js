// views/supervision.js — TRANG GIÁM SÁT phòng kế toán (Kế toán trưởng):
// toàn bộ chỉ số các phân hệ + khối giám sát Pricing Rule.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, formatDate } from "../lib/format.js";

const SEV_BADGE = { danger: "red", warning: "yellow", ok: "green" };

export async function render({ container }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div><p>Đang tổng hợp chỉ số giám sát…</p></div>`);
  let d;
  try {
    d = await api.supervision();
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div>
          <div class="kt-view-title"><i class="fas fa-tower-observation"></i> Giám sát phòng kế toán</div>
          <div class="kt-sub">Toàn bộ chỉ số các phân hệ · cập nhật ${formatDate(d.as_of)} · ${d.company}</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <a class="kt-btn kt-btn--outline kt-btn--sm" href="#/dashboard"><i class="fas fa-gauge-high"></i> Dashboard</a>
          <button class="kt-btn kt-btn--outline kt-btn--sm" id="sv-refresh"><i class="fas fa-rotate"></i> Làm mới</button>
        </div>
      </div>

      <div class="kt-ws-sections">
        ${d.sections.map((s) => sectionCard(s))}
        ${pricingCard(d.pricing)}
      </div>
    `
  );

  container.querySelector("#sv-refresh").addEventListener("click", () => render({ container }));
  container.querySelectorAll("[data-go]").forEach((el) =>
    el.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      const go = el.dataset.go;
      if (go.startsWith("/desk/")) window.open(go, "_blank");
      else location.hash = "#" + go;
    })
  );
}

function fmtVal(m) {
  if (m.fmt === "vnd") return formatVND(m.value);
  return String(m.value);
}

const SEV_TEXT = { danger: "xử lý", warning: "chú ý", ok: "✓" };

function metricRow(m) {
  const target = m.route || m.href || "";
  return html`<div class="kt-ws-item ${target ? "kt-row-link" : ""}" ${target ? html`data-go="${target}"` : ""} style="cursor:${target ? "pointer" : "default"}">
    <span class="kt-ws-item-label">${m.label}</span>
    <span style="display:flex;align-items:center;gap:8px;white-space:nowrap">
      <b>${fmtVal(m)}</b>
      ${m.sev ? html`<span class="kt-badge kt-badge--${SEV_BADGE[m.sev] || "gray"}">${SEV_TEXT[m.sev] || m.sev}</span>` : ""}
      ${target ? html`<span class="kt-ws-item-go"><i class="fas ${target.startsWith("/desk/") ? "fa-up-right-from-square" : "fa-chevron-right"}"></i></span>` : ""}
    </span>
  </div>`;
}

function sectionCard(s) {
  return html`
    <div class="kt-card kt-ws-section">
      <div class="kt-card-head"><div class="kt-card-title"><i class="fas ${s.icon}"></i> ${s.title}</div></div>
      <div class="kt-card-body"><div class="kt-ws-items">
        ${s.metrics.map((m) => metricRow(m))}
      </div></div>
    </div>`;
}

/* ---- Khối giám sát Pricing Rule ---- */
function ruleLine(r, extraLabel) {
  return html`<div class="kt-ws-item kt-row-link" data-go="${r.route}" style="cursor:pointer">
    <span class="kt-ws-item-label" style="white-space:normal">
      <b>${r.title}</b> <span class="kt-badge kt-badge--gray">${r.kind}</span>
      ${r.detail ? html`<span class="kt-sub"> · ${r.detail}</span>` : ""}
      ${r.price_list ? html`<span class="kt-sub"> · ${r.price_list}</span>` : ""}
      <br><span class="kt-sub">${r.valid_from || "…"} → ${r.valid_upto || "không hạn"} · dùng ${r.used_30d} lần/30 ngày</span>
    </span>
    <span style="display:flex;align-items:center;gap:8px;white-space:nowrap">
      ${extraLabel}
      <span class="kt-ws-item-go"><i class="fas fa-up-right-from-square"></i></span>
    </span>
  </div>`;
}

function pricingCard(p) {
  if (!p || !p.supported) return "";
  const problems = p.expired_enabled.length + p.expiring_soon.length;
  return html`
    <div class="kt-card kt-ws-section" style="${problems ? "border-left:4px solid var(--kt-danger)" : ""}">
      <div class="kt-card-head">
        <div class="kt-card-title"><i class="fas fa-scale-unbalanced"></i> Giám sát Pricing Rule</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <span class="kt-badge kt-badge--green">${p.active} đang hiệu lực</span>
          <span class="kt-badge kt-badge--gray">${p.disabled} đã tắt</span>
          <a class="kt-btn-icon" target="_blank" href="/desk/pricing-rule" title="Mở danh sách trong Desk"><i class="fas fa-up-right-from-square"></i></a>
        </div>
      </div>
      <div class="kt-card-body"><div class="kt-ws-items">
        ${p.expired_enabled.length
          ? html`<div class="kt-task-group-title" style="margin-top:4px"><i class="fas fa-circle-exclamation" style="color:var(--kt-danger)"></i> Hết hạn mà còn bật (${p.expired_enabled.length}) — tắt hoặc gia hạn</div>
            ${p.expired_enabled.map((r) => ruleLine(r, html`<span class="kt-badge kt-badge--red">hết hạn</span>`))}`
          : ""}
        ${p.expiring_soon.length
          ? html`<div class="kt-task-group-title" style="margin-top:8px"><i class="fas fa-hourglass-half" style="color:var(--kt-warning)"></i> Sắp hết hạn trong 7 ngày (${p.expiring_soon.length})</div>
            ${p.expiring_soon.map((r) => ruleLine(r, html`<span class="kt-badge kt-badge--yellow">đến ${r.valid_upto}</span>`))}`
          : ""}
        ${p.unused_30d.length
          ? html`<div class="kt-task-group-title" style="margin-top:8px"><i class="fas fa-ghost" style="color:var(--kt-muted)"></i> Rule bán đang bật nhưng KHÔNG được dùng 30 ngày (${p.unused_30d.length})</div>
            ${p.unused_30d.map((r) => ruleLine(r, html`<span class="kt-badge kt-badge--gray">0 lần</span>`))}`
          : ""}
        ${p.top_used.length
          ? html`<div class="kt-task-group-title" style="margin-top:8px"><i class="fas fa-fire" style="color:var(--kt-primary)"></i> Dùng nhiều nhất 30 ngày</div>
            ${p.top_used.slice(0, 5).map((r) => ruleLine(r, html`<span class="kt-badge kt-badge--green">${r.used_30d} lần</span>`))}`
          : ""}
        ${!p.expired_enabled.length && !p.expiring_soon.length && !p.unused_30d.length && !p.top_used.length
          ? html`<div class="kt-sub">Chưa có Pricing Rule nào (hoặc chưa phát sinh áp dụng). Vi phạm giá bán không có rule xem ở tab "Giá bán vs bảng giá" từng kênh.</div>`
          : ""}
      </div></div>
    </div>`;
}
