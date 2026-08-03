// views/supplier.js — 360° công nợ 1 NCC: hóa đơn còn phải trả + deep-link Desk.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, formatDate } from "../lib/format.js";
import { glUrl } from "../lib/workspaces.js";
import { toast } from "../components/toast.js";

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

      ${d.missing_docs
        ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
            <div class="kt-card-body"><div class="kt-ws-items">
              <div class="kt-ws-item kt-row-link" id="sup-need-docs" style="cursor:pointer">
                <span class="kt-ws-item-ico" style="background:#fef3c7;color:#b45309"><i class="fas fa-file-signature"></i></span>
                <span class="kt-ws-item-label">Bổ sung hợp đồng, pháp lý — chưa có hồ sơ đính kèm (bấm để tải lên)</span>
                <span class="kt-ws-item-go"><i class="fas fa-chevron-right"></i></span>
              </div>
            </div></div>
          </div>`
        : ""}

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

  renderSupplierFiles(container, d.supplier);

  // Cảnh báo thiếu hồ sơ → cuộn tới khối hồ sơ và mở hộp chọn file.
  const needDocs = container.querySelector("#sup-need-docs");
  if (needDocs) needDocs.addEventListener("click", () => {
    const card = container.querySelector("#kt-supplier-files");
    if (!card) return;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    const btn = card.querySelector("#sf-upload");
    if (btn) btn.click();
  });
}

// Khối "Hồ sơ nhà cung cấp" — file đính kèm trên Supplier (hợp đồng, pháp lý, ĐKKD...)
async function renderSupplierFiles(container, supplier) {
  const host = document.createElement("div");
  host.className = "kt-card";
  host.id = "kt-supplier-files";
  host.style.marginTop = "16px";
  container.appendChild(host);
  setHTML(host, html`<div class="kt-card-body"><div class="kt-spinner" style="width:24px;height:24px"></div></div>`);

  async function load() {
    let files;
    try { files = await api.supplierFiles(supplier); }
    catch (e) { setHTML(host, html`<div class="kt-card-body kt-sub">${e.message}</div>`); return; }
    setHTML(
      host,
      html`
        <div class="kt-card-head">
          <div class="kt-card-title"><i class="fas fa-folder-open"></i> Hồ sơ nhà cung cấp (${files.length})</div>
          <button class="kt-btn kt-btn--outline kt-btn--sm" id="sf-upload"><i class="fas fa-upload"></i> Tải hồ sơ lên</button>
        </div>
        <div class="kt-card-body">
          ${files.length
            ? html`<div class="kt-table-wrap"><table class="kt-table"><tbody>
                ${files.map(
                  (f) => html`<tr><td><i class="fas fa-file-lines" style="color:var(--kt-primary)"></i> ${f.file_name}</td>
                    <td>${(f.creation || "").slice(0, 10)}</td>
                    <td class="num"><a class="kt-btn-icon" target="_blank" href="${f.file_url}" title="Mở file"><i class="fas fa-download"></i></a></td></tr>`
                )}
              </tbody></table></div>`
            : html`<div class="kt-sub">Chưa có hồ sơ (hợp đồng, phụ lục, ĐKKD, hồ sơ pháp lý...). Bấm "Tải hồ sơ lên".</div>`}
        </div>
      `
    );
    host.querySelector("#sf-upload").addEventListener("click", () => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx";
      input.onchange = () => {
        const file = input.files && input.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async () => {
          try { await api.supplierFileUpload(supplier, file.name, reader.result); toast("Đã tải hồ sơ lên", "success"); load(); }
          catch (e) { toast(e.message, "error"); }
        };
        reader.readAsDataURL(file);
      };
      input.click();
    });
  }
  load();
}
