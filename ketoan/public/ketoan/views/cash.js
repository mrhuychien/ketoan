// views/cash.js — sổ quỹ & dòng tiền: số dư TK tiền, thu/chi theo ngày, giao dịch + nhập sổ quỹ.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, formatDate, escapeHtml } from "../lib/format.js";
import { navigate } from "../lib/router.js";
import { openCashbook } from "../components/cashbook.js";

const q = encodeURIComponent;

export async function render({ container }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);

  async function load() {
    let balances, flow, txns;
    try {
      [balances, flow, txns] = await Promise.all([api.balances(), api.cashflow(), api.transactions({ limit: 100 })]);
    } catch (e) {
      setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
      return;
    }

    setHTML(
      container,
      html`
        <div class="kt-view-head">
          <div class="kt-view-title"><i class="fas fa-wallet"></i> Sổ quỹ &amp; dòng tiền</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="kt-btn kt-btn--outline kt-btn--sm" id="kt-import-bank"><i class="fas fa-file-import"></i> Nhập từ file (sao kê)</button>
            <button class="kt-btn kt-btn--success kt-btn--sm" id="kt-new-cash"><i class="fas fa-plus"></i> Nhập sổ quỹ</button>
          </div>
        </div>

        <div class="kt-stats">
          <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-sack-dollar"></i> Tổng số dư quỹ</div>
            <div class="kt-stat-value ${balances.total < 0 ? "neg" : "is-grad"}">${formatVND(balances.total)}</div></div>
          <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-arrow-down"></i> Thu (30 ngày)</div>
            <div class="kt-stat-value pos">${formatVND(flow.total_inflow)}</div></div>
          <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-arrow-up"></i> Chi (30 ngày)</div>
            <div class="kt-stat-value neg">${formatVND(flow.total_outflow)}</div></div>
          <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-scale-balanced"></i> Ròng (30 ngày)</div>
            <div class="kt-stat-value ${flow.net < 0 ? "neg" : "pos"}">${formatVND(flow.net)}</div></div>
        </div>

        <div class="kt-grid-2 kt-mb">
          <div class="kt-card"><div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-building-columns"></i> Số dư từng tài khoản</div></div>
            <div class="kt-card-body"><div class="kt-table-wrap"><table class="kt-table">
              <thead><tr><th>Tài khoản</th><th>Loại</th><th class="num">Số dư</th><th></th></tr></thead>
              <tbody>${balances.rows.map(
                (a) => html`<tr><td>${a.account_name || a.account}</td><td><span class="kt-badge kt-badge--gray">${a.account_type}</span></td>
                  <td class="num ${a.balance < 0 ? "danger" : "pos"}">${formatVND(a.balance)}</td>
                  <td class="num"><a class="kt-btn-icon" target="_blank" href="/app/general-ledger?account=${q(a.account)}"><i class="fas fa-book"></i></a></td></tr>`
              )}</tbody>
            </table></div>
            ${balances.rows.length === 0 ? html`<div class="kt-empty"><i class="fas fa-wallet"></i><p>Chưa có TK tiền</p></div>` : ""}
            </div></div>

          <div class="kt-card"><div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-chart-column"></i> Dòng tiền theo ngày (30 ngày)</div></div>
            <div class="kt-card-body"><div class="kt-table-wrap"><table class="kt-table">
              <thead><tr><th>Ngày</th><th class="num">Thu</th><th class="num">Chi</th><th class="num">Ròng</th></tr></thead>
              <tbody>${flow.rows.slice().reverse().map(
                (r) => html`<tr><td>${formatDate(r.posting_date)}</td><td class="num pos">${r.inflow ? formatVND(r.inflow) : "—"}</td>
                  <td class="num danger">${r.outflow ? formatVND(r.outflow) : "—"}</td><td class="num ${r.net < 0 ? "danger" : "pos"}">${formatVND(r.net)}</td></tr>`
              )}</tbody>
            </table></div>
            ${flow.rows.length === 0 ? html`<div class="kt-empty"><i class="fas fa-chart-column"></i><p>Không có giao dịch</p></div>` : ""}
            </div></div>
        </div>

        <div class="kt-card"><div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-list"></i> Giao dịch gần đây</div></div>
          <div class="kt-card-body"><div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Ngày</th><th>Diễn giải</th><th>Chứng từ</th><th class="num">Thu</th><th class="num">Chi</th><th></th></tr></thead>
            <tbody>${txns.rows.map(
              (t) => html`<tr><td>${formatDate(t.posting_date)}</td><td>${t.remarks || t.against || "—"}</td>
                <td>${t.voucher_no || "—"}</td><td class="num pos">${t.debit ? formatVND(t.debit) : ""}</td><td class="num danger">${t.credit ? formatVND(t.credit) : ""}</td>
                <td class="num">${t.voucher_no ? html`<a class="kt-btn-icon" target="_blank" href="/app/${voucherRoute(t.voucher_type)}/${q(t.voucher_no)}"><i class="fas fa-up-right-from-square"></i></a>` : ""}</td></tr>`
            )}</tbody>
          </table></div>
          ${txns.rows.length === 0 ? html`<div class="kt-empty"><i class="fas fa-list"></i><p>Không có giao dịch</p></div>` : ""}
          </div></div>
      `
    );

    container.querySelector("#kt-new-cash").addEventListener("click", () => openCashbook({ onDone: load }));
    container.querySelector("#kt-import-bank").addEventListener("click", () => navigate("/nhap-sao-ke"));
  }

  await load();
}

function voucherRoute(vt) {
  return (vt || "Journal Entry").toLowerCase().replace(/ /g, "-");
}
