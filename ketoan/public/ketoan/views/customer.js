// views/customer.js — 360° công nợ 1 khách: hóa đơn outstanding + hạn mức + deep-link Desk.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, formatDate, escapeHtml } from "../lib/format.js";
import { openModal } from "../components/modal.js";

const CTX = window.KETOAN_CONTEXT || {};
const isManager = CTX.isManager;
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

      ${customerTasksBlock(d)}

      <div class="kt-card kt-mb">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-bolt"></i> Thao tác</div></div>
        <div class="kt-card-body" style="display:flex;gap:10px;flex-wrap:wrap">
          <button class="kt-btn kt-btn--primary kt-btn--sm" id="kt-export-recon"><i class="fas fa-file-pdf"></i> Xuất đối chiếu (PDF)</button>
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

  const exportBtn = container.querySelector("#kt-export-recon");
  if (exportBtn) exportBtn.addEventListener("click", () => openReconModal(d));

  renderCustomerFiles(container, d.customer);
}

// Khối "Việc cần xử lý với khách này" — nhóm theo nghiệp vụ.
function customerTasksBlock(d) {
  const t = d.tasks || {};
  const overdueInv = (d.invoices || []).filter((i) => i.days_overdue > 0);
  const overdueSum = overdueInv.reduce((s, i) => s + i.outstanding_amount, 0);

  const items = [];
  if (overdueInv.length)
    items.push({ icon: "fa-hand-holding-dollar", label: `Cần thu/đối chiếu: ${overdueInv.length} hóa đơn quá hạn (${formatVND(overdueSum)})`, sev: "red", href: null });
  if (t.missing_einvoice)
    items.push({ icon: "fa-file-circle-exclamation", label: `Cần xuất hóa đơn điện tử: ${t.missing_einvoice} hóa đơn`, sev: "red", href: "#/doi-chieu-npp?tab=einvoice" });
  if (t.pending_returns)
    items.push({ icon: "fa-rotate-left", label: `Hàng trả lại đang xử lý: ${t.pending_returns} hồ sơ`, sev: "yellow", href: "#/doi-chieu-npp?tab=doitru" });
  if (t.pending_discount)
    items.push({ icon: "fa-percent", label: `Chiết khấu/KM đang treo: ${t.pending_discount} bút toán`, sev: "yellow", href: "#/doi-chieu-npp?tab=doitru" });
  if (d.unallocated_payment > 0)
    items.push({ icon: "fa-link-slash", label: `Khoản thu chưa khớp hóa đơn: ${formatVND(d.unallocated_payment)}`, sev: "yellow", href: `/app/payment-entry?party=${q(d.customer)}&unallocated_amount=[">",0]` });
  if (d.over_limit)
    items.push({ icon: "fa-user-shield", label: "Vượt hạn mức tín dụng — cân nhắc khóa đơn/thu hồi", sev: "red", href: null });

  if (!items.length)
    return html`<div class="kt-alert kt-alert--info kt-mb"><div class="kt-alert-title"><i class="fas fa-circle-check" style="color:var(--kt-success)"></i> Không có việc tồn đọng với khách này</div></div>`;

  return html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
      <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-list-check"></i> Việc cần xử lý với khách này (${items.length})</div></div>
      <div class="kt-card-body"><div class="kt-ws-items">
        ${items.map((it) => {
          const ico = html`<span class="kt-ws-item-ico" style="${it.sev === "red" ? "background:#fee2e2;color:#b91c1c" : "background:#fef3c7;color:#b45309"}"><i class="fas ${it.icon}"></i></span>`;
          if (!it.href)
            return html`<div class="kt-ws-item">${ico}<span class="kt-ws-item-label">${it.label}</span></div>`;
          return html`<a class="kt-ws-item" href="${it.href}" target="${it.href.startsWith("/app") ? "_blank" : ""}">
            ${ico}<span class="kt-ws-item-label">${it.label}</span>
            <span class="kt-ws-item-go"><i class="fas fa-chevron-right"></i></span>
          </a>`;
        })}
      </div></div>
    </div>`;
}

// Khối "Hồ sơ khách hàng" — file đính kèm trên Customer (hợp đồng, phụ lục, ĐKKD...)
async function renderCustomerFiles(container, customer) {
  const host = document.createElement("div");
  host.className = "kt-card";
  host.style.marginTop = "16px";
  container.appendChild(host);
  setHTML(host, html`<div class="kt-card-body"><div class="kt-spinner" style="width:24px;height:24px"></div></div>`);

  async function load() {
    let files;
    try { files = await api.customerFiles(customer); }
    catch (e) { setHTML(host, html`<div class="kt-card-body kt-sub">${e.message}</div>`); return; }
    setHTML(
      host,
      html`
        <div class="kt-card-head">
          <div class="kt-card-title"><i class="fas fa-folder-open"></i> Hồ sơ khách hàng (${files.length})</div>
          <button class="kt-btn kt-btn--outline kt-btn--sm" id="cf-upload"><i class="fas fa-upload"></i> Tải hồ sơ lên</button>
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
            : html`<div class="kt-sub">Chưa có hồ sơ (hợp đồng, phụ lục thương mại, ĐKKD...). Bấm "Tải hồ sơ lên".</div>`}
        </div>
      `
    );
    host.querySelector("#cf-upload").addEventListener("click", () => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx";
      input.onchange = () => {
        const file = input.files && input.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async () => {
          try { await api.customerFileUpload(customer, file.name, reader.result); load(); }
          catch (e) { alert(e.message); }
        };
        reader.readAsDataURL(file);
      };
      input.click();
    });
  }
  load();
}

function openReconModal(d) {
  const todayStr = new Date().toISOString().slice(0, 10);
  const yearStart = todayStr.slice(0, 4) + "-01-01";
  const m = openModal({
    title: "Xuất biên bản đối chiếu công nợ",
    icon: "fa-file-pdf",
    maxWidth: 460,
    body: html`
      <p class="kt-sub kt-mb">Khách: <b>${d.customer_name || d.customer}</b></p>
      <div class="kt-row2">
        <div class="kt-field"><label><i class="fas fa-calendar"></i> Từ ngày</label>
          <input type="date" id="kt-rc-from" class="kt-input" value="${yearStart}"></div>
        <div class="kt-field"><label><i class="fas fa-calendar"></i> Đến ngày</label>
          <input type="date" id="kt-rc-to" class="kt-input" value="${todayStr}" max="${todayStr}"></div>
      </div>
      <div class="kt-modal-actions">
        <button class="kt-btn kt-btn--outline" id="kt-rc-cancel">Hủy</button>
        <button class="kt-btn kt-btn--primary" id="kt-rc-go"><i class="fas fa-download"></i> Tải PDF</button>
      </div>`,
  });
  m.body.querySelector("#kt-rc-cancel").addEventListener("click", m.close);
  m.body.querySelector("#kt-rc-go").addEventListener("click", () => {
    const f = m.body.querySelector("#kt-rc-from").value;
    const t = m.body.querySelector("#kt-rc-to").value;
    const url = "/api/method/ketoan.api.npp.export_reconciliation"
      + `?customer=${q(d.customer)}&from_date=${q(f)}&to_date=${q(t)}&company=${q(CTX.company || "")}`;
    window.open(url, "_blank");
    m.close();
  });
}
