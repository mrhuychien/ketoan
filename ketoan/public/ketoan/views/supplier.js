// views/supplier.js — 360° công nợ 1 NCC: hóa đơn còn phải trả + deep-link Desk.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, formatDate } from "../lib/format.js";
import { glUrl } from "../lib/workspaces.js";

const q = encodeURIComponent;

export async function render({ container, params }) {
  const supplier = params.id;
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let d;
  try {
    d = await api.supplierDetail(supplier);
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div class="kt-view-title"><i class="fas fa-industry"></i> ${d.supplier_name || d.supplier}</div>
        <a class="kt-btn kt-btn--outline kt-btn--sm" href="#/cong-no-ncc"><i class="fas fa-arrow-left"></i> Công nợ phải trả</a>
      </div>

      <div class="kt-stats">
        <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-file-invoice-dollar"></i> Còn phải trả</div>
          <div class="kt-stat-value is-grad">${formatVND(d.outstanding)}</div>
          ${d.supplier_group ? html`<div class="kt-stat-sub">${d.supplier_group}${d.tax_id ? " · MST " + d.tax_id : ""}</div>` : ""}
        </div>
        <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-link-slash"></i> Chi trả trước chưa khớp</div>
          <div class="kt-stat-value ${d.unallocated_payment > 0 ? "warn" : ""}">${formatVND(d.unallocated_payment)}</div>
        </div>
      </div>

      <div class="kt-card kt-mb">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-bolt"></i> Thao tác trong ERPNext</div></div>
        <div class="kt-card-body" style="display:flex;gap:10px;flex-wrap:wrap">
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/desk/supplier/${q(d.supplier)}"><i class="fas fa-up-right-from-square"></i> Mở NCC</a>
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/desk/payment-entry/new?party_type=Supplier&party=${q(d.supplier)}"><i class="fas fa-money-bill-transfer"></i> Lập phiếu chi</a>
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="${glUrl({ party_type: "Supplier", party: d.supplier })}"><i class="fas fa-book"></i> Sổ cái</a>
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/desk/purchase-invoice?supplier=${q(d.supplier)}"><i class="fas fa-file-invoice"></i> Hóa đơn mua</a>
        </div>
      </div>

      <div class="kt-card">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-file-invoice"></i> Hóa đơn còn phải trả (${d.invoices.length})</div></div>
        <div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Hóa đơn</th><th>Số HĐ NCC</th><th>Ngày</th><th>Hạn TT</th><th class="num">Tổng</th><th class="num">Còn phải trả</th><th>Tuổi nợ</th><th></th></tr></thead>
            <tbody>${d.invoices.map(
              (i) => html`<tr>
                <td>${i.name}</td><td>${i.bill_no || "—"}</td><td>${formatDate(i.posting_date)}</td><td>${formatDate(i.due_date)}</td>
                <td class="num">${formatVND(i.grand_total)}</td><td class="num danger">${formatVND(i.outstanding_amount)}</td>
                <td>${i.days_overdue > 0 ? html`<span class="kt-badge kt-badge--red">quá ${i.days_overdue}n</span>` : html`<span class="kt-badge kt-badge--green">trong hạn</span>`}</td>
                <td class="num"><a class="kt-btn-icon" target="_blank" href="/desk/purchase-invoice/${q(i.name)}"><i class="fas fa-up-right-from-square"></i></a></td>
              </tr>`
            )}</tbody>
          </table></div>
          ${d.invoices.length === 0 ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không còn hóa đơn phải trả</p></div>` : ""}
        </div>
      </div>
    `
  );
}
