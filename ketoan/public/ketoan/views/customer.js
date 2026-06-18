// views/customer.js — 360° công nợ 1 khách: hóa đơn outstanding + hạn mức + deep-link Desk.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, formatDate, escapeHtml } from "../lib/format.js";

const isManager = (window.KETOAN_CONTEXT || {}).isManager;
const q = encodeURIComponent;

export async function render({ container, params }) {
  const customer = params.id;
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let d;
  try {
    d = await api.customerDetail(customer);
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div class="kt-view-title"><i class="fas fa-id-card-clip"></i> ${d.customer_name || d.customer}</div>
        <a class="kt-btn kt-btn--outline kt-btn--sm" href="#/cong-no"><i class="fas fa-arrow-left"></i> Công nợ</a>
      </div>

      <div class="kt-stats">
        <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-file-invoice-dollar"></i> Tổng công nợ</div>
          <div class="kt-stat-value is-grad">${formatVND(d.outstanding)}</div>
          ${d.customer_group ? html`<div class="kt-stat-sub">${d.customer_group}${d.territory ? " · " + d.territory : ""}</div>` : ""}
        </div>
        ${isManager
          ? html`<div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-user-shield"></i> Hạn mức tín dụng</div>
              <div class="kt-stat-value ${d.over_limit ? "neg" : ""}">${d.credit_limit ? formatVND(d.credit_limit) : "—"}</div>
              ${d.over_limit ? html`<div class="kt-stat-sub" style="color:var(--kt-danger)">Vượt ${formatVND(d.outstanding - d.credit_limit)}</div>` : ""}
            </div>`
          : ""}
        <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-link-slash"></i> Khoản thu treo</div>
          <div class="kt-stat-value ${d.unallocated_payment > 0 ? "warn" : ""}">${formatVND(d.unallocated_payment)}</div>
        </div>
      </div>

      <div class="kt-card kt-mb">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-bolt"></i> Thao tác trong ERPNext</div></div>
        <div class="kt-card-body" style="display:flex;gap:10px;flex-wrap:wrap">
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/app/customer/${q(d.customer)}"><i class="fas fa-up-right-from-square"></i> Mở khách</a>
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/app/general-ledger?party_type=Customer&party=${q(d.customer)}"><i class="fas fa-book"></i> Sổ cái</a>
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/app/payment-entry?party=${q(d.customer)}"><i class="fas fa-money-bill-wave"></i> Phiếu thu</a>
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/app/sales-invoice?customer=${q(d.customer)}&status=Overdue"><i class="fas fa-file-invoice"></i> HĐ quá hạn</a>
        </div>
      </div>

      <div class="kt-card">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-file-invoice"></i> Hóa đơn còn nợ (${d.invoices.length})</div></div>
        <div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Số HĐ</th><th>Ngày</th><th>Hạn TT</th><th class="num">Tổng</th><th class="num">Còn nợ</th><th>Tuổi nợ</th><th></th></tr></thead>
            <tbody>
              ${d.invoices.map(
                (i) => html`<tr>
                  <td>${i.name}</td><td>${formatDate(i.posting_date)}</td><td>${formatDate(i.due_date)}</td>
                  <td class="num">${formatVND(i.grand_total)}</td><td class="num danger">${formatVND(i.outstanding_amount)}</td>
                  <td>${i.days_overdue > 0 ? html`<span class="kt-badge kt-badge--red">quá ${i.days_overdue}n</span>` : html`<span class="kt-badge kt-badge--green">trong hạn</span>`}</td>
                  <td class="num"><a class="kt-btn-icon" target="_blank" href="/app/sales-invoice/${q(i.name)}"><i class="fas fa-up-right-from-square"></i></a></td>
                </tr>`
              )}
            </tbody>
          </table></div>
          ${d.invoices.length === 0 ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không còn hóa đơn nợ</p></div>` : ""}
        </div>
      </div>
    `
  );
}
