// views/payables.js — Công nợ phải trả: 4 tab (Công nợ NCC / Đến hạn / Kiểm soát / Giá nhập NL).
import { api } from "../lib/api.js";
import { html, setHTML, on } from "../lib/dom.js";
import { formatVND, formatVNDShort, formatDate, escapeHtml } from "../lib/format.js";
import { navigate } from "../lib/router.js";
import { openModal } from "../components/modal.js";

const q = encodeURIComponent;

const AP_TABS = ["ap", "due", "control", "gia"];

export async function render({ container, query }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let summary, aging;
  try {
    [summary, aging] = await Promise.all([api.apSummary(), api.apAging()]);
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  const state = { tab: query && AP_TABS.includes(query.tab) ? query.tab : "ap", search: "" };
  const maxAging = Math.max(1, ...aging.buckets.map((b) => b.amount));

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div>
          <div class="kt-view-title"><i class="fas fa-truck-field"></i> Công nợ phải trả</div>
          <div class="kt-sub">${summary.count} NCC · tổng ${formatVND(summary.total)}</div>
        </div>
        <a class="kt-btn kt-btn--outline kt-btn--sm" href="#/vt/purchase"><i class="fas fa-book-open"></i> Hướng dẫn &amp; lối tắt</a>
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
        <button data-tab="ap" class="${state.tab === "ap" ? "is-active" : ""}">Công nợ NCC</button>
        <button data-tab="due" class="${state.tab === "due" ? "is-active" : ""}">Đến hạn thanh toán</button>
        <button data-tab="control" class="${state.tab === "control" ? "is-active" : ""}">Kiểm soát</button>
        <button data-tab="gia" class="${state.tab === "gia" ? "is-active" : ""}">Giá nhập NL</button>
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
    else if (state.tab === "control") renderControl(body);
    else renderPrices(body, state);
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
                <a class="kt-btn-icon" target="_blank" title="Mở hóa đơn" href="/desk/purchase-invoice/${q(r.name)}"><i class="fas fa-up-right-from-square"></i></a>
                <a class="kt-btn-icon" target="_blank" title="Lập phiếu chi" href="/desk/payment-entry/new?party_type=Supplier&party=${q(r.supplier)}"><i class="fas fa-money-bill-transfer"></i></a>
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
                    <td class="num"><a class="kt-btn-icon" target="_blank" href="/desk/purchase-invoice/${q(r.name)}"><i class="fas fa-up-right-from-square"></i></a></td></tr>`
                )}</tbody>
              </table></div>
              <p class="kt-sub" style="margin-top:8px">Khớp 3 chiều PO–nhập kho–hóa đơn: các hóa đơn này chưa gắn Purchase Receipt.</p>`
            : html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Mọi hóa đơn đều có liên kết nhập kho</p></div>`}
        </div>
      </div>
    `
  );
}

/* ---------- Tab 4: theo dõi GIÁ NHẬP nguyên liệu (quét Purchase Invoice) ---------- */
const PW_DAYS = [90, 180, 365];

async function renderPrices(body, state) {
  if (state.pwDays == null) state.pwDays = 180;
  if (state.pwTh == null) state.pwTh = 10;
  if (state.pwSearch == null) state.pwSearch = "";
  setHTML(body, html`<div class="kt-boot"><div class="kt-spinner"></div><p>Đang quét hóa đơn mua…</p></div>`);
  let d;
  try { d = await api.apPriceWatch({ days: state.pwDays, threshold: state.pwTh }); }
  catch (e) { setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`); return; }

  const draw = () => {
    const qs = (state.pwSearch || "").toLowerCase().trim();
    const rows = !qs ? d.rows : d.rows.filter((r) =>
      (r.item_name || "").toLowerCase().includes(qs) || (r.item_code || "").toLowerCase().includes(qs));
    setHTML(
      body,
      html`
        <div class="kt-stats">
          <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-boxes-stacked"></i> Nguyên liệu theo dõi</div>
            <div class="kt-stat-value">${d.item_count}</div>
            <div class="kt-stat-sub">${d.days} ngày · quét Purchase Invoice</div></div>
          <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-triangle-exclamation"></i> Biến động ≥ ${d.threshold}%</div>
            <div class="kt-stat-value ${d.alert_count ? "neg" : "pos"}">${d.alert_count}</div></div>
        </div>

        <div class="kt-card">
          <div class="kt-card-head">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
              <div class="kt-segment" id="pw-days">
                ${PW_DAYS.map((n) => html`<button data-d="${n}" class="${n === state.pwDays ? "is-active" : ""}">${n} ngày</button>`)}
              </div>
              <label class="kt-sub" style="display:flex;align-items:center;gap:6px">Ngưỡng %
                <input type="number" id="pw-th" class="kt-input" style="width:70px" min="1" max="100" value="${state.pwTh}"></label>
            </div>
            <div class="kt-search"><i class="fas fa-search"></i><input class="kt-input" id="pw-search" placeholder="Tìm nguyên liệu..." value="${state.pwSearch}"></div>
          </div>
          <div class="kt-card-body">
            <div class="kt-table-wrap"><table class="kt-table">
              <thead><tr><th>Nguyên liệu</th><th>NCC</th><th class="num">Giá gần nhất</th>
                <th class="num">So lần trước</th><th class="num">TB kỳ</th><th class="num">So TB</th>
                <th class="num">Min–Max</th><th class="num">Lần mua</th><th></th></tr></thead>
              <tbody>${rows.map((r) => pwRow(r))}</tbody>
            </table></div>
            ${rows.length === 0 ? html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Không có nguyên liệu nào trong kỳ</p></div>` : ""}
            ${d.truncated ? html`<p class="kt-sub" style="margin-top:8px">⚠ Kỳ này quá 20.000 dòng mua — thu hẹp số ngày để quét đủ.</p>` : ""}
          </div>
        </div>
      `
    );

    body.querySelector("#pw-days").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-d]");
      if (!b) return;
      state.pwDays = parseInt(b.dataset.d, 10);
      renderPrices(body, state);
    });
    body.querySelector("#pw-th").addEventListener("change", (e) => {
      state.pwTh = Math.max(1, parseFloat(e.target.value || "10"));
      renderPrices(body, state);
    });
    const search = body.querySelector("#pw-search");
    let timer = null;
    search.addEventListener("input", () => {
      state.pwSearch = search.value;
      clearTimeout(timer);
      timer = setTimeout(draw, 200);
    });
    body.querySelectorAll("[data-pw-item]").forEach((tr) =>
      tr.addEventListener("click", (e) => {
        if (e.target.closest("a")) return;
        openPriceHistory(tr.dataset.pwItem);
      })
    );
  };
  draw();
}

function pctBadge(pct) {
  if (pct == null) return html`<span class="kt-sub">—</span>`;
  if (Math.abs(pct) < 0.05) return html`<span class="kt-badge kt-badge--gray">0%</span>`;
  // Giá NHẬP tăng = xấu (đỏ), giảm = tốt (xanh).
  return pct > 0
    ? html`<span class="kt-badge kt-badge--red">▲ +${pct}%</span>`
    : html`<span class="kt-badge kt-badge--green">▼ ${pct}%</span>`;
}

function pwRow(r) {
  const sup = r.suppliers.join(", ") + (r.supplier_count > 3 ? ` +${r.supplier_count - 3}` : "");
  return html`<tr class="kt-row-link" data-pw-item="${r.item_code}" style="${r.alert ? "background:#fef2f2" : ""}">
    <td style="max-width:220px;white-space:normal">${r.alert ? html`<i class="fas fa-triangle-exclamation" style="color:var(--kt-danger)"></i> ` : ""}<b>${r.item_name}</b><br><span class="kt-sub">${r.item_code} · ${r.uom}</span></td>
    <td style="max-width:180px;white-space:normal;font-size:12px" title="${sup}">${r.last_supplier}${r.supplier_count > 1 ? html`<br><span class="kt-sub">${r.supplier_count} NCC</span>` : ""}</td>
    <td class="num"><b>${formatVND(r.last_price)}</b><br><span class="kt-sub">${formatDate(r.last_date)}</span></td>
    <td class="num">${pctBadge(r.chg_last_pct)}</td>
    <td class="num">${formatVND(r.avg_price)}</td>
    <td class="num">${pctBadge(r.chg_avg_pct)}</td>
    <td class="num" style="font-size:12px">${formatVNDShort(r.min_price)}–${formatVNDShort(r.max_price)}</td>
    <td class="num">${r.buys}</td>
    <td class="num"><span class="kt-btn-icon"><i class="fas fa-chevron-right"></i></span></td>
  </tr>`;
}

async function openPriceHistory(itemCode) {
  const m = openModal({ title: "Lịch sử giá nhập", icon: "fa-chart-line", maxWidth: 720,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>` });
  let d;
  try { d = await api.apPriceHistory(itemCode, { days: 365 }); }
  catch (e) { setHTML(m.body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`); return; }
  setHTML(m.body, html`
    <p class="kt-sub kt-mb"><b>${d.item_name}</b> (${d.item_code}) · ${d.rows.length} lần mua trong ${d.days} ngày</p>
    <div class="kt-table-wrap"><table class="kt-table">
      <thead><tr><th>Ngày</th><th>NCC</th><th class="num">SL</th><th class="num">Đơn giá</th><th class="num">So lần trước</th><th></th></tr></thead>
      <tbody>${d.rows.map((r) => html`<tr>
        <td>${formatDate(r.date)}</td>
        <td style="max-width:200px;white-space:normal;font-size:12px">${r.supplier_name}</td>
        <td class="num">${r.qty} ${r.uom}</td>
        <td class="num"><b>${formatVND(r.price)}</b></td>
        <td class="num">${pctBadge(r.chg_pct)}</td>
        <td class="num"><a class="kt-btn-icon" target="_blank" href="${r.route}" title="Mở hóa đơn"><i class="fas fa-up-right-from-square"></i></a></td>
      </tr>`)}</tbody>
    </table></div>`);
}
