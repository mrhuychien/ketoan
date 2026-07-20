// views/customer.js — 360° công nợ 1 khách: hóa đơn outstanding + hạn mức + deep-link Desk.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, formatDate, escapeHtml } from "../lib/format.js";
import { openModal } from "../components/modal.js";
import { toast } from "../components/toast.js";

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
        <button class="kt-btn kt-btn--outline kt-btn--sm" id="kt-back"><i class="fas fa-arrow-left"></i> Quay lại</button>
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
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="/desk/customer/${q(d.customer)}"><i class="fas fa-up-right-from-square"></i> Mở khách</a>
        </div>
      </div>

      <div id="kt-ledger"></div>
    `
  );

  const exportBtn = container.querySelector("#kt-export-recon");
  if (exportBtn) exportBtn.addEventListener("click", () => openReconModal(d));

  // Quay lại trang trước (danh sách công nợ kênh / trang NPP...); không có lịch sử thì về trang chủ.
  container.querySelector("#kt-back").addEventListener("click", () => {
    if (history.length > 1) history.back();
    else location.hash = "#/";
  });

  // Việc cần xử lý: mở danh sách HĐ đến hạn / cuộn tới khối hồ sơ để tải lên.
  container.querySelectorAll("[data-task-action]").forEach((el) =>
    el.addEventListener("click", () => {
      if (el.dataset.taskAction === "overdue") openOverdueInvoices(d);
      else if (el.dataset.taskAction === "docs") openCustomerDocs(container);
    })
  );

  renderLedger(container.querySelector("#kt-ledger"), d.customer);
  renderCustomerFiles(container, d.customer);
}

// Danh sách hóa đơn CẦN THANH TOÁN của kỳ (đã đến hạn — HĐ đến hạn 30 ngày trở lên).
function openOverdueInvoices(d) {
  const rows = (d.invoices || []).filter((i) => i.days_overdue > 0)
    .slice().sort((a, b) => b.days_overdue - a.days_overdue);
  const total = rows.reduce((s, i) => s + i.outstanding_amount, 0);
  openModal({
    title: "Hóa đơn cần thanh toán kỳ này",
    icon: "fa-hand-holding-dollar",
    maxWidth: 720,
    body: html`
      <p class="kt-sub kt-mb">Khách: <b>${d.customer_name || d.customer}</b> · ${rows.length} hóa đơn đã đến hạn ·
        tổng còn phải thu <b style="color:var(--kt-danger)">${formatVND(total)}</b>.
        <br>Đơn đã đến hạn (chốt kỳ thu ngày 5, hóa đơn đến hạn 30 ngày trở lên).</p>
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr><th>Số HĐ</th><th>Ngày HĐ</th><th>Hạn TT</th><th class="num">Còn phải thu</th><th class="num">Quá hạn</th><th></th></tr></thead>
        <tbody>${rows.map((i) => html`<tr>
          <td>${i.name}</td>
          <td>${formatDate(i.posting_date)}</td>
          <td>${i.due_date ? formatDate(i.due_date) : "—"}</td>
          <td class="num danger">${formatVND(i.outstanding_amount)}</td>
          <td class="num danger">${i.days_overdue} ngày</td>
          <td class="num"><a class="kt-btn-icon" target="_blank" href="/desk/sales-invoice/${q(i.name)}" title="Mở hóa đơn"><i class="fas fa-up-right-from-square"></i></a></td>
        </tr>`)}</tbody>
      </table></div>
      ${rows.length === 0 ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có hóa đơn đến hạn</p></div>` : ""}`,
  });
}

// Cuộn tới khối "Hồ sơ khách hàng" và mở hộp thoại tải file (nếu đã tải xong).
function openCustomerDocs(container) {
  const card = container.querySelector("#kt-customer-files");
  if (!card) return;
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  const btn = card.querySelector("#cf-upload");
  if (btn) btn.click(); // trong ngữ cảnh user gesture → mở được hộp chọn file
}

/* ---- Sổ cái giao dịch + việc cần làm gắn từng chứng từ ---- */
const LEDGER_PERIODS = [
  { key: "90d", label: "90 ngày" },
  { key: "ytd", label: "Năm nay" },
  { key: "all", label: "Tất cả" },
];

function ledgerFrom(key) {
  const t = new Date();
  if (key === "90d") { const d = new Date(); d.setDate(d.getDate() - 90); return d.toISOString().slice(0, 10); }
  if (key === "ytd") return t.getFullYear() + "-01-01";
  return null;
}

async function renderLedger(host, customer, period = "ytd") {
  setHTML(host, html`<div class="kt-card"><div class="kt-card-body"><div class="kt-spinner" style="width:26px;height:26px"></div></div></div>`);
  let d;
  try {
    d = await api.customerLedger(customer, { from_date: ledgerFrom(period) });
  } catch (e) {
    setHTML(host, html`<div class="kt-card"><div class="kt-card-body kt-sub">${e.message}</div></div>`);
    return;
  }

  setHTML(
    host,
    html`
      <div class="kt-card">
        <div class="kt-card-head">
          <div class="kt-card-title"><i class="fas fa-book"></i> Giao dịch của khách (sổ cái)</div>
          <div class="kt-segment" id="lg-period">
            ${LEDGER_PERIODS.map((p) => html`<button data-p="${p.key}" class="${p.key === period ? "is-active" : ""}">${p.label}</button>`)}
          </div>
        </div>
        <div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Ngày</th><th>Chứng từ</th><th>TK đối ứng</th><th class="num">Nợ (bán)</th><th class="num">Có (thu/giảm)</th><th class="num">Số dư</th><th>Việc cần làm</th><th></th></tr></thead>
            <tbody>
              ${d.from_date ? html`<tr class="kt-lg-open"><td>${formatDate(d.from_date)}</td><td><b>Dư đầu kỳ</b></td><td></td><td class="num"></td><td class="num"></td><td class="num"><b>${formatVND(d.opening)}</b></td><td></td><td></td></tr>` : ""}
              ${d.rows.map((r) => ledgerRow(r))}
              <tr class="kt-lg-total"><td></td><td><b>Cộng phát sinh</b></td><td></td>
                <td class="num"><b>${formatVND(d.total_debit)}</b></td>
                <td class="num"><b>${formatVND(d.total_credit)}</b></td>
                <td class="num"><b>${formatVND(d.closing)}</b></td><td></td><td></td></tr>
              ${draftSection(d.drafts.filter((r) => r.kind === "return"), "Hàng trả lại chưa xử lý (nháp — chưa vào số dư)")}
              ${draftSection(d.drafts.filter((r) => r.kind !== "return"), "Bút toán JE đang treo (nháp — chưa vào số dư)")}
            </tbody>
          </table></div>
          ${d.rows.length === 0 && !d.drafts.length ? html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Không có giao dịch trong kỳ</p></div>` : ""}
        </div>
      </div>
    `
  );

  host.querySelector("#lg-period").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-p]");
    if (b) renderLedger(host, customer, b.dataset.p);
  });
}

// Nhóm chứng từ nháp trong sổ cái (Hàng trả lại / Bút toán JE) — có dòng tiêu đề riêng.
function draftSection(rows, title) {
  if (!rows.length) return "";
  return html`
    <tr><td colspan="8" style="background:var(--kt-bg-input);font-weight:700;font-size:11px;text-transform:uppercase;color:var(--kt-text-2)">${title} · ${rows.length}</td></tr>
    ${rows.map((r) => ledgerRow(r))}`;
}

function ledgerRow(r) {
  const draft = r.docstatus === 0;
  return html`<tr style="${draft ? "opacity:.85;background:#fffbeb" : ""}">
    <td>${formatDate(r.posting_date)}</td>
    <td>${r.voucher_no}<br><span class="kt-sub">${r.voucher_type}${draft ? html` <span class="kt-badge kt-badge--yellow">NHÁP</span>` : ""}</span></td>
    <td style="font-size:11px;color:var(--kt-text-2);max-width:180px">${r.against || "—"}</td>
    <td class="num">${r.debit ? formatVND(r.debit) : ""}</td>
    <td class="num">${r.credit ? formatVND(r.credit) : ""}</td>
    <td class="num">${r.balance == null ? "—" : formatVND(r.balance)}</td>
    <td>${(r.todos || []).length
      ? (r.todos || []).map((td) => html`<span class="kt-badge kt-badge--${td.sev === "red" ? "red" : "yellow"}" style="margin:1px 2px 1px 0"><i class="fas ${td.icon}"></i> ${td.label}</span>`)
      : html`<span class="kt-badge kt-badge--green"><i class="fas fa-check"></i> OK</span>`}</td>
    <td class="num"><a class="kt-btn-icon" target="_blank" href="${r.route}" title="Mở trong ERPNext"><i class="fas fa-up-right-from-square"></i></a></td>
  </tr>`;
}

// Khối "Việc cần xử lý với khách này" — nhóm theo nghiệp vụ.
function customerTasksBlock(d) {
  const t = d.tasks || {};
  const overdueInv = (d.invoices || []).filter((i) => i.days_overdue > 0);
  const overdueSum = overdueInv.reduce((s, i) => s + i.outstanding_amount, 0);

  const items = [];
  if (overdueInv.length)
    items.push({ icon: "fa-hand-holding-dollar", label: `Cần thu/đối chiếu: ${overdueInv.length} hóa đơn đến hạn (${formatVND(overdueSum)})`, sev: "red", action: "overdue" });
  if (t.missing_einvoice)
    items.push({ icon: "fa-file-circle-exclamation", label: `Cần xuất hóa đơn điện tử: ${t.missing_einvoice} hóa đơn`, sev: "red", href: "#/doi-chieu-npp?tab=einvoice" });
  if (t.pending_returns)
    items.push({ icon: "fa-rotate-left", label: `Hàng trả lại chưa xử lý: ${t.pending_returns} hồ sơ`, sev: "yellow", href: "#/doi-chieu-npp?tab=trahang" });
  if (t.pending_je)
    items.push({ icon: "fa-pen-to-square", label: `Bút toán JE đang treo (CK, thưởng, hỗ trợ...): ${t.pending_je}`, sev: "yellow", href: "#/doi-chieu-npp?tab=butoan" });
  if (d.unallocated_payment > 0)
    items.push({ icon: "fa-link-slash", label: `Khoản thu chưa khớp hóa đơn: ${formatVND(d.unallocated_payment)}`, sev: "yellow", href: `/desk/payment-entry?party=${q(d.customer)}&unallocated_amount=[">",0]` });
  if (d.over_limit)
    items.push({ icon: "fa-user-shield", label: "Vượt hạn mức tín dụng — cân nhắc khóa đơn/thu hồi", sev: "red", href: null });
  if (t.missing_docs)
    items.push({ icon: "fa-file-signature", label: "Bổ sung hợp đồng, pháp lý — chưa có hồ sơ đính kèm (bấm để tải lên)", sev: "yellow", action: "docs" });

  if (!items.length)
    return html`<div class="kt-alert kt-alert--info kt-mb"><div class="kt-alert-title"><i class="fas fa-circle-check" style="color:var(--kt-success)"></i> Không có việc tồn đọng với khách này</div></div>`;

  return html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
      <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-list-check"></i> Việc cần xử lý với khách này (${items.length})</div></div>
      <div class="kt-card-body"><div class="kt-ws-items">
        ${items.map((it) => {
          const ico = html`<span class="kt-ws-item-ico" style="${it.sev === "red" ? "background:#fee2e2;color:#b91c1c" : "background:#fef3c7;color:#b45309"}"><i class="fas ${it.icon}"></i></span>`;
          if (it.action)
            return html`<div class="kt-ws-item kt-row-link" data-task-action="${it.action}" style="cursor:pointer">
              ${ico}<span class="kt-ws-item-label">${it.label}</span>
              <span class="kt-ws-item-go"><i class="fas fa-chevron-right"></i></span>
            </div>`;
          if (!it.href)
            return html`<div class="kt-ws-item">${ico}<span class="kt-ws-item-label">${it.label}</span></div>`;
          return html`<a class="kt-ws-item" href="${it.href}" target="${it.href.startsWith("/desk") ? "_blank" : ""}">
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
  host.id = "kt-customer-files";
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
  const goBtn = m.body.querySelector("#kt-rc-go");
  goBtn.addEventListener("click", async () => {
    const f = m.body.querySelector("#kt-rc-from").value;
    const t = m.body.querySelector("#kt-rc-to").value;
    goBtn.disabled = true;
    goBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang tạo PDF…';
    try {
      await api.nppExportRecon(d.customer, f, t);
      m.close();
    } catch (e) {
      toast(e.message, "error");
      goBtn.disabled = false;
      goBtn.innerHTML = '<i class="fas fa-download"></i> Tải PDF';
    }
  });
}
