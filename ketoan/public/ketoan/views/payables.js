// views/payables.js — Công nợ phải trả: 3 tab (Công nợ NCC / Đến hạn / Kiểm soát).
import { api } from "../lib/api.js";
import { html, setHTML, on } from "../lib/dom.js";
import { formatVND, formatVNDShort, formatDate, escapeHtml } from "../lib/format.js";
import { navigate } from "../lib/router.js";

const q = encodeURIComponent;

export async function render({ container }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let summary, aging;
  try {
    [summary, aging] = await Promise.all([api.apSummary(), api.apAging()]);
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  const state = { tab: "ap", search: "" };
  const maxAging = Math.max(1, ...aging.buckets.map((b) => b.amount));

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div class="kt-view-title"><i class="fas fa-truck-field"></i> Công nợ phải trả</div>
        <div class="kt-sub">${summary.count} NCC · tổng ${formatVND(summary.total)}</div>
      </div>

      <div class="kt-card kt-mb">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-layer-group"></i> Tuổi nợ phải trả</div></div>
        <div class="kt-card-body"><div class="kt-aging">
          ${aging.buckets.map(
            (b) => html`<div class="kt-aging-row"><span>${b.label}</span>
              <div class="kt-aging-track"><div class="kt-aging-fill" style="width:${Math.round((b.amount / maxAging) * 100)}%;background:${b.key === "over" ? "var(--kt-danger)" : b.key === "current" ? "var(--kt-success)" : "var(--kt-warning)"}"></div></div>
              <span class="kt-aging-amt">${formatVNDShort(b.amount)}</span></div>`
          )}
        </div></div>
      </div>

      <div class="kt-segment kt-mb" id="ap-tabs">
        <button data-tab="ap" class="is-active">Công nợ NCC</button>
        <button data-tab="due">Đến hạn thanh toán</button>
        <button data-tab="control">Kiểm soát</button>
      </div>
      <div id="ap-tab-body"></div>
    `
  );

  const body = container.querySelector("#ap-tab-body");

  container.querySelector("#ap-tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-tab]");
    if (!b) return;
    state.tab = b.dataset.tab;
    container.querySelectorAll("#ap-tabs button").forEach((x) => x.classList.toggle("is-active", x === b));
    renderTab();
  });

  on(body, "click", "[data-supplier]", (e, el) => {
    if (e.target.closest("a,button,input")) return;
    navigate("/ncc/" + encodeURIComponent(el.dataset.supplier));
  });

  function renderTab() {
    if (state.tab === "ap") renderAP(body, summary, state);
    else if (state.tab === "due") renderDue(body);
    else renderControl(body);
  }
  renderTab();
}

/* ---------- Tab 1: bảng kê theo NCC ---------- */
function renderAP(body, summary, state) {
  const rows = filterRows(summary.rows, state.search);
  setHTML(
    body,
    html`
      <div class="kt-card">
        <div class="kt-card-head">
          <div class="kt-card-title"><i class="fas fa-industry"></i> Bảng kê theo NCC</div>
          <div class="kt-search"><i class="fas fa-search"></i><input class="kt-input" id="ap-search" placeholder="Tìm NCC..." value="${state.search}"></div>
        </div>
        <div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Nhà cung cấp</th><th>Nhóm</th><th class="num">Còn phải trả</th><th class="num">Quá hạn</th><th></th></tr></thead>
            <tbody>${rows.map(
              (r) => html`<tr class="kt-row-link" data-supplier="${r.supplier}">
                <td>${r.supplier_name || r.supplier}</td>
                <td>${r.supplier_group ? html`<span class="kt-badge kt-badge--gray">${r.supplier_group}</span>` : "—"}</td>
                <td class="num">${formatVND(r.outstanding)}</td>
                <td class="num ${r.days_overdue > 0 ? "danger" : "pos"}">${r.days_overdue > 0 ? "quá " + r.days_overdue + " ngày" : "trong hạn"}</td>
                <td class="num"><span class="kt-btn-icon"><i class="fas fa-chevron-right"></i></span></td>
              </tr>`
            )}</tbody>
          </table></div>
          ${rows.length === 0 ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có công nợ phải trả</p></div>` : ""}
        </div>
      </div>
    `
  );
  const search = body.querySelector("#ap-search");
  let timer = null;
  search.addEventListener("input", () => {
    state.search = search.value;
    clearTimeout(timer);
    timer = setTimeout(() => renderAP(body, summary, state), 200);
  });
}

function filterRows(rows, search) {
  const qs = (search || "").toLowerCase().trim();
  if (!qs) return rows;
  return rows.filter((r) => (r.supplier_name || r.supplier || "").toLowerCase().includes(qs));
}

/* ---------- Tab 2: lịch đến hạn ---------- */
async function renderDue(body) {
  setHTML(body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let d;
  try { d = await api.apDueSchedule({ days_ahead: 14 }); }
  catch (e) { setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`); return; }

  setHTML(
    body,
    html`
      <div class="kt-stats">
        <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-fire"></i> Đã quá hạn</div>
          <div class="kt-stat-value neg">${formatVND(d.overdue_total)}</div></div>
        <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-hourglass-half"></i> Đến hạn ${d.days_ahead} ngày tới</div>
          <div class="kt-stat-value warn">${formatVND(d.upcoming_total)}</div></div>
      </div>
      <div class="kt-card">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-calendar-days"></i> Hóa đơn cần thanh toán (${d.rows.length})</div></div>
        <div class="kt-card-body"><div class="kt-table-wrap"><table class="kt-table">
          <thead><tr><th>Hạn TT</th><th>NCC</th><th>Số HĐ NCC</th><th class="num">Còn phải trả</th><th>Trạng thái</th><th></th></tr></thead>
          <tbody>${d.rows.map(
            (r) => html`<tr class="kt-row-link" data-supplier="${r.supplier}">
              <td>${formatDate(r.due_date || r.posting_date)}</td>
              <td>${r.supplier_name || r.supplier}</td>
              <td>${r.bill_no || r.name}</td>
              <td class="num danger">${formatVND(r.outstanding_amount)}</td>
              <td>${r.days_to_due < 0 ? html`<span class="kt-badge kt-badge--red">quá ${-r.days_to_due}n</span>` : html`<span class="kt-badge kt-badge--yellow">còn ${r.days_to_due}n</span>`}</td>
              <td class="num" style="white-space:nowrap">
                <a class="kt-btn-icon" target="_blank" title="Mở hóa đơn" href="/app/purchase-invoice/${q(r.name)}"><i class="fas fa-up-right-from-square"></i></a>
                <a class="kt-btn-icon" target="_blank" title="Lập phiếu chi" href="/app/payment-entry/new?party_type=Supplier&party=${q(r.supplier)}"><i class="fas fa-money-bill-transfer"></i></a>
              </td>
            </tr>`
          )}</tbody>
        </table></div>
        ${d.rows.length === 0 ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có hóa đơn đến hạn</p></div>` : ""}
        </div>
      </div>
    `
  );
}

/* ---------- Tab 3: kiểm soát (trùng HĐ + khớp 3 chiều) ---------- */
async function renderControl(body) {
  setHTML(body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let d;
  try { d = await api.apControls(); }
  catch (e) { setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`); return; }

  setHTML(
    body,
    html`
      <div class="kt-card kt-mb">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-clone"></i> Trùng hóa đơn NCC (${d.duplicates.length})</div></div>
        <div class="kt-card-body">
          ${d.duplicates.length
            ? html`<div class="kt-table-wrap"><table class="kt-table">
                <thead><tr><th>NCC</th><th>Số HĐ NCC</th><th class="num">Số lần</th><th class="num">Tổng tiền</th><th>Các hóa đơn</th></tr></thead>
                <tbody>${d.duplicates.map(
                  (r) => html`<tr><td>${r.supplier_name || r.supplier}</td><td><span class="kt-badge kt-badge--red">${r.bill_no}</span></td>
                    <td class="num danger">${r.cnt}</td><td class="num">${formatVND(r.total)}</td>
                    <td style="white-space:normal;max-width:340px">${r.invoices}</td></tr>`
                )}</tbody>
              </table></div>
              <p class="kt-sub" style="margin-top:8px">Cùng NCC + cùng số hóa đơn xuất hiện nhiều lần — kiểm tra nhập trùng hoặc gian lận.</p>`
            : html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không phát hiện trùng hóa đơn</p></div>`}
        </div>
      </div>

      <div class="kt-card">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-link-slash"></i> Hóa đơn thiếu liên kết nhập kho (${d.missing_receipt.length})</div></div>
        <div class="kt-card-body">
          ${d.missing_receipt.length
            ? html`<div class="kt-table-wrap"><table class="kt-table">
                <thead><tr><th>Hóa đơn</th><th>NCC</th><th>Ngày</th><th class="num">Giá trị</th><th></th></tr></thead>
                <tbody>${d.missing_receipt.map(
                  (r) => html`<tr><td>${r.name}</td><td>${r.supplier_name}</td><td>${formatDate(r.posting_date)}</td>
                    <td class="num">${formatVND(r.grand_total)}</td>
                    <td class="num"><a class="kt-btn-icon" target="_blank" href="/app/purchase-invoice/${q(r.name)}"><i class="fas fa-up-right-from-square"></i></a></td></tr>`
                )}</tbody>
              </table></div>
              <p class="kt-sub" style="margin-top:8px">Khớp 3 chiều PO–nhập kho–hóa đơn: các hóa đơn này chưa gắn Purchase Receipt.</p>`
            : html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Mọi hóa đơn đều có liên kết nhập kho</p></div>`}
        </div>
      </div>
    `
  );
}
