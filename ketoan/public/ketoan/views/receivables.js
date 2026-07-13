// views/receivables.js — bảng kê công nợ theo khách + tuổi nợ, tìm kiếm, vào 360°.
import { api } from "../lib/api.js";
import { html, setHTML, on } from "../lib/dom.js";
import { formatVND, formatVNDShort, escapeHtml } from "../lib/format.js";
import { navigate } from "../lib/router.js";

const CHANNEL_LABEL = { npp: "kênh NPP", mt: "kênh MT", khac: "kênh Du lịch, Khác", "tat-ca": "toàn bộ" };

export async function render({ container, params }) {
  const channel = (params && params.channel) || "tat-ca";
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let summary, aging;
  try {
    [summary, aging] = await Promise.all([api.arSummary(channel), api.aging(channel)]);
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  const rows = summary.rows;
  const maxAging = Math.max(1, ...aging.buckets.map((b) => b.amount));

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div class="kt-view-title"><i class="fas fa-file-invoice-dollar"></i> Công nợ phải thu — ${CHANNEL_LABEL[channel] || channel}</div>
        <div class="kt-sub">${summary.count} khách · tổng ${formatVND(summary.total)}</div>
      </div>

      <div class="kt-card kt-mb">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-layer-group"></i> Tuổi nợ</div></div>
        <div class="kt-card-body"><div class="kt-aging">
          ${aging.buckets.map(
            (b) => html`<div class="kt-aging-row"><span>${b.label}</span>
              <div class="kt-aging-track"><div class="kt-aging-fill" style="width:${Math.round((b.amount / maxAging) * 100)}%;background:${b.key === "over" ? "var(--kt-danger)" : b.key === "current" ? "var(--kt-success)" : "var(--kt-warning)"}"></div></div>
              <span class="kt-aging-amt">${formatVNDShort(b.amount)}</span></div>`
          )}
        </div></div>
      </div>

      <div class="kt-card">
        <div class="kt-card-head">
          <div class="kt-card-title"><i class="fas fa-users"></i> Bảng kê theo khách</div>
          <div class="kt-search"><i class="fas fa-search"></i><input class="kt-input" id="kt-ar-search" placeholder="Tìm khách..."></div>
        </div>
        <div class="kt-card-body">
          <div class="kt-table-wrap">
            <table class="kt-table">
              <thead><tr><th>Khách hàng</th><th>Nhóm</th><th class="num">Công nợ</th><th class="num">Quá hạn</th><th></th></tr></thead>
              <tbody id="kt-ar-body">
                ${rows.map((r) => rowHtml(r))}
              </tbody>
            </table>
          </div>
          ${rows.length === 0 ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có công nợ</p></div>` : ""}
        </div>
      </div>
    `
  );

  // Tìm kiếm client-side
  const search = container.querySelector("#kt-ar-search");
  const body = container.querySelector("#kt-ar-body");
  search.addEventListener("input", () => {
    const q = search.value.toLowerCase().trim();
    const filtered = !q ? rows : rows.filter((r) => (r.customer_name || r.customer || "").toLowerCase().includes(q));
    setHTML(body, filtered.map((r) => rowHtml(r)).join(""));
  });

  // Click hàng → 360°
  on(container, "click", "[data-customer]", (e, el) => {
    navigate("/khach/" + encodeURIComponent(el.dataset.customer));
  });
}

function rowHtml(r) {
  const overdue = r.days_overdue > 0;
  return html`
    <tr class="kt-row-link" data-customer="${r.customer}">
      <td>${r.customer_name || r.customer}</td>
      <td>${r.customer_group ? html`<span class="kt-badge kt-badge--gray">${r.customer_group}</span>` : "—"}</td>
      <td class="num">${formatVND(r.outstanding)}</td>
      <td class="num ${overdue ? "danger" : "pos"}">${overdue ? "quá " + r.days_overdue + " ngày" : "trong hạn"}</td>
      <td class="num"><span class="kt-btn-icon"><i class="fas fa-chevron-right"></i></span></td>
    </tr>`;
}
