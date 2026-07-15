// views/ledger.js — SỔ CÁI TỪNG TÀI KHOẢN ngay trên portal (kế toán hạch toán).
// Chọn TK bằng combobox (số TK + tên, hay dùng lên trước), chọn kỳ → bảng
// toàn bộ giao dịch với dư đầu / số dư lũy kế từng dòng / dư cuối.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, formatDate } from "../lib/format.js";
import { replaceQuery } from "../lib/router.js";
import { createCombobox, closeComboPanel } from "../components/combobox.js";

const CTX = window.KETOAN_CONTEXT || {};

const PERIODS = [
  { key: "thang", label: "Tháng này" },
  { key: "90d", label: "90 ngày" },
  { key: "ytd", label: "Năm nay" },
  { key: "all", label: "Tất cả" },
];

function periodFrom(key) {
  const t = new Date();
  const iso = (d) => d.toISOString().slice(0, 10);
  if (key === "thang") return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-01`;
  if (key === "90d") { const d = new Date(); d.setDate(d.getDate() - 90); return iso(d); }
  if (key === "ytd") return t.getFullYear() + "-01-01";
  return null; // all
}

// Link mở đúng báo cáo General Ledger trên Desk với TK + kỳ đang xem.
function deskGlUrl(account, from_date) {
  const iso = (d) => d.toISOString().slice(0, 10);
  const p = new URLSearchParams({
    company: CTX.company || "",
    from_date: from_date || new Date().getFullYear() + "-01-01",
    to_date: iso(new Date()),
    account: account || "",
    include_dimensions: "1",
    include_default_book_entries: "1",
  });
  return "/desk/query-report/General%20Ledger?" + p.toString();
}

export async function render({ container, query }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let accounts;
  try {
    accounts = await api.glAccounts();
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  const accOptions = accounts.map((a) => ({
    value: a.name,
    label: (a.account_number ? a.account_number + " — " : "") + (a.account_name || a.name),
    sub: a.name,
  }));
  const accLabel = {};
  accOptions.forEach((o) => { accLabel[o.value] = o.label; });

  const state = {
    account: (query && query.account) || "",
    period: (query && PERIODS.some((p) => p.key === query.period) && query.period) || "ytd",
  };

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div>
          <div class="kt-view-title"><i class="fas fa-book"></i> Sổ cái tài khoản</div>
          <div class="kt-sub">Chọn tài khoản để xem toàn bộ giao dịch ngay trên portal</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <a class="kt-btn kt-btn--outline kt-btn--sm" href="#/quy"><i class="fas fa-arrow-left"></i> Sổ quỹ</a>
          <a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" id="lg-desk" href="${deskGlUrl(state.account, periodFrom(state.period))}"><i class="fas fa-up-right-from-square"></i> Mở GL trên Desk</a>
        </div>
      </div>

      <div class="kt-card kt-mb">
        <div class="kt-card-body" style="display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap">
          <div class="kt-field" style="min-width:280px;flex:1;max-width:420px">
            <label><i class="fas fa-book"></i> Tài khoản</label>
            <div id="lg-acc"></div>
          </div>
          <div class="kt-field">
            <label><i class="fas fa-calendar"></i> Kỳ</label>
            <div class="kt-segment" id="lg-period">
              ${PERIODS.map((p) => html`<button data-p="${p.key}" class="${p.key === state.period ? "is-active" : ""}">${p.label}</button>`)}
            </div>
          </div>
        </div>
      </div>

      <div id="lg-body"></div>
    `
  );

  const body = container.querySelector("#lg-body");
  const deskBtn = container.querySelector("#lg-desk");

  createCombobox(container.querySelector("#lg-acc"), {
    options: accOptions,
    value: state.account || "",
    label: accLabel[state.account] || state.account || "",
    placeholder: "Gõ số/tên TK…",
    onPick: (it) => {
      if (!it) { state.account = ""; return; }
      state.account = it.value;
      sync();
      loadLedger();
    },
  });

  container.querySelector("#lg-period").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-p]");
    if (!b) return;
    state.period = b.dataset.p;
    container.querySelectorAll("#lg-period button").forEach((x) => x.classList.toggle("is-active", x === b));
    sync();
    loadLedger();
  });

  function sync() {
    const q2 = { period: state.period };
    if (state.account) q2.account = state.account;
    replaceQuery("/so-cai", q2);
    deskBtn.href = deskGlUrl(state.account, periodFrom(state.period));
  }

  async function loadLedger() {
    closeComboPanel();
    if (!state.account) {
      setHTML(body, html`<div class="kt-empty"><i class="fas fa-hand-pointer"></i><p>Chọn tài khoản ở trên để xem sổ cái.<br><span class="kt-sub">Tài khoản hay dùng hiện sẵn khi bấm vào ô — gõ số/tên (không cần dấu) để tìm.</span></p></div>`);
      return;
    }
    setHTML(body, html`<div class="kt-boot"><div class="kt-spinner"></div><p>Đang tải sổ cái…</p></div>`);
    let d;
    try {
      d = await api.glLedger(state.account, { from_date: periodFrom(state.period) });
    } catch (e) {
      setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
      return;
    }

    setHTML(
      body,
      html`
        <div class="kt-stats">
          <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-flag"></i> Dư đầu kỳ</div>
            <div class="kt-stat-value">${d.from_date ? formatVND(d.opening) : "—"}</div>
            <div class="kt-stat-sub">${d.account_label}</div></div>
          <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-arrow-down"></i> Phát sinh Nợ</div>
            <div class="kt-stat-value pos">${formatVND(d.total_debit)}</div></div>
          <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-arrow-up"></i> Phát sinh Có</div>
            <div class="kt-stat-value neg">${formatVND(d.total_credit)}</div></div>
          <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-scale-balanced"></i> Dư cuối kỳ</div>
            <div class="kt-stat-value ${d.closing < 0 ? "neg" : "is-grad"}">${formatVND(d.closing)}</div></div>
        </div>

        ${d.truncated ? html`<div class="kt-alert kt-alert--warning kt-mb">
          <div class="kt-alert-title"><i class="fas fa-triangle-exclamation"></i> Kỳ này quá 2.000 dòng — chỉ hiển thị 2.000 dòng đầu</div>
          <div class="kt-alert-hint">Thu hẹp kỳ (Tháng này / 90 ngày) hoặc mở GL trên Desk để xem đầy đủ.</div>
        </div>` : ""}

        <div class="kt-card">
          <div class="kt-card-head">
            <div class="kt-card-title"><i class="fas fa-list"></i> ${d.rows.length} giao dịch · ${d.account_label}</div>
          </div>
          <div class="kt-card-body">
            <div class="kt-table-wrap"><table class="kt-table">
              <thead><tr><th>Ngày</th><th>Chứng từ</th><th>Diễn giải / Đối ứng</th><th>Đối tượng</th>
                <th class="num">Nợ</th><th class="num">Có</th><th class="num">Số dư</th><th></th></tr></thead>
              <tbody>
                ${d.from_date ? html`<tr class="kt-lg-open"><td>${formatDate(d.from_date)}</td><td><b>Dư đầu kỳ</b></td><td></td><td></td><td class="num"></td><td class="num"></td><td class="num"><b>${formatVND(d.opening)}</b></td><td></td></tr>` : ""}
                ${d.rows.map((r) => html`<tr>
                  <td>${formatDate(r.posting_date)}</td>
                  <td>${r.voucher_no}<br><span class="kt-sub">${r.voucher_type}</span></td>
                  <td style="max-width:280px;white-space:normal;font-size:12px">${r.remarks || r.against || "—"}</td>
                  <td style="font-size:12px">${r.party || "—"}</td>
                  <td class="num">${r.debit ? formatVND(r.debit) : ""}</td>
                  <td class="num">${r.credit ? formatVND(r.credit) : ""}</td>
                  <td class="num ${r.balance < 0 ? "danger" : ""}">${formatVND(r.balance)}</td>
                  <td class="num"><a class="kt-btn-icon" target="_blank" href="${r.route}" title="Mở chứng từ trong Desk"><i class="fas fa-up-right-from-square"></i></a></td>
                </tr>`)}
                <tr class="kt-lg-total"><td></td><td><b>Cộng phát sinh</b></td><td></td><td></td>
                  <td class="num"><b>${formatVND(d.total_debit)}</b></td>
                  <td class="num"><b>${formatVND(d.total_credit)}</b></td>
                  <td class="num"><b>${formatVND(d.closing)}</b></td><td></td></tr>
              </tbody>
            </table></div>
            ${d.rows.length === 0 ? html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Không có giao dịch trong kỳ</p></div>` : ""}
          </div>
        </div>
      `
    );
  }

  sync();
  loadLedger();
}
