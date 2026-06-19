// views/utilities.js — tiện ích nhanh: tìm khách → 360°, nhập sổ quỹ, lối tắt báo cáo Desk.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, escapeHtml } from "../lib/format.js";
import { navigate } from "../lib/router.js";
import { openCashbook } from "../components/cashbook.js";

const CAN_CASHBOOK = !!(window.KETOAN_CONTEXT || {}).canUseCashbook;

export async function render({ container }) {
  setHTML(
    container,
    html`
      <div class="kt-view-head"><div class="kt-view-title"><i class="fas fa-bolt"></i> Tiện ích nhanh</div></div>

      <div class="${CAN_CASHBOOK ? "kt-grid-2" : ""} kt-mb">
        <div class="kt-card">
          <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-magnifying-glass"></i> Tìm khách → 360° công nợ</div></div>
          <div class="kt-card-body">
            <div class="kt-search kt-mb"><i class="fas fa-search"></i><input class="kt-input" id="ut-search" placeholder="Gõ tên/mã khách (≥2 ký tự)..."></div>
            <div id="ut-results"></div>
          </div>
        </div>

        ${CAN_CASHBOOK
          ? html`<div class="kt-card">
              <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-money-bill-wave"></i> Nhập sổ quỹ</div></div>
              <div class="kt-card-body">
                <p class="kt-sub kt-mb">Tạo nhanh phiếu thu/chi tiền mặt (Journal Entry nháp) — kèm QR VietQR. Người duyệt &amp; ghi sổ trong Desk.</p>
                <button class="kt-btn kt-btn--success" id="ut-cashbook"><i class="fas fa-plus"></i> Mở phiếu sổ quỹ</button>
              </div>
            </div>`
          : ""}
      </div>

      <div class="kt-card">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-file-export"></i> Lối tắt báo cáo (ERPNext)</div></div>
        <div class="kt-card-body" style="display:flex;gap:10px;flex-wrap:wrap">
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/app/accounts-receivable"><i class="fas fa-file-invoice-dollar"></i> Bảng kê công nợ phải thu</a>
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/app/accounts-receivable-summary"><i class="fas fa-layer-group"></i> Tổng hợp công nợ</a>
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/app/general-ledger"><i class="fas fa-book"></i> Sổ cái</a>
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/app/cash-flow"><i class="fas fa-chart-line"></i> Lưu chuyển tiền tệ</a>
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/app/journal-entry/new"><i class="fas fa-pen"></i> Bút toán mới</a>
        </div>
      </div>
    `
  );

  const cbBtn = container.querySelector("#ut-cashbook");
  if (cbBtn) cbBtn.addEventListener("click", () => openCashbook());

  // Tìm khách: dùng frappe.client.get_list qua method API (search_link tương đương).
  const search = container.querySelector("#ut-search");
  const results = container.querySelector("#ut-results");
  let timer = null;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    const q = search.value.trim();
    if (q.length < 2) { results.innerHTML = ""; return; }
    timer = setTimeout(() => doSearch(q, results), 250);
  });
}

async function doSearch(q, results) {
  results.innerHTML = '<div class="kt-spinner" style="width:24px;height:24px"></div>';
  try {
    const res = await api.call("frappe.client.get_list", {
      doctype: "Customer",
      filters: [["customer_name", "like", "%" + q + "%"]],
      fields: ["name", "customer_name", "customer_group"],
      limit_page_length: 15,
      order_by: "customer_name asc",
    });
    if (!res || !res.length) { results.innerHTML = '<div class="kt-empty"><i class="fas fa-user-slash"></i><p>Không thấy khách</p></div>'; return; }
    setHTML(
      results,
      html`<div class="kt-table-wrap"><table class="kt-table"><tbody>
        ${res.map(
          (c) => html`<tr class="kt-row-link" data-c="${c.name}"><td>${c.customer_name || c.name}</td>
            <td>${c.customer_group ? html`<span class="kt-badge kt-badge--gray">${c.customer_group}</span>` : ""}</td>
            <td class="num"><span class="kt-btn-icon"><i class="fas fa-chevron-right"></i></span></td></tr>`
        )}
      </tbody></table></div>`
    );
    results.querySelectorAll("[data-c]").forEach((el) =>
      el.addEventListener("click", () => navigate("/khach/" + encodeURIComponent(el.dataset.c)))
    );
  } catch (e) {
    results.innerHTML = `<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`;
  }
}
