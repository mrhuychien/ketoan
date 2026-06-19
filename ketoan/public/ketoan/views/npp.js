// views/npp.js — Đối chiếu công nợ kênh NPP: công nợ, đến hạn (+Zalo), chiết khấu.
import { api } from "../lib/api.js";
import { html, setHTML, on } from "../lib/dom.js";
import { formatVND, formatVNDShort, escapeHtml } from "../lib/format.js";
import { navigate } from "../lib/router.js";
import { openModal } from "../components/modal.js";
import { toast } from "../components/toast.js";

const STATUS = {
  due: { cls: "red", label: "Cần thu" },
  normal: { cls: "green", label: "Bình thường" },
  negative: { cls: "gray", label: "Số dư âm" },
};

export async function render({ container }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let data;
  try {
    data = await api.nppDebts();
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  const state = { tab: "debt", statusFilter: "all", search: "", selected: new Set() };

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div class="kt-view-title"><i class="fas fa-handshake"></i> Đối chiếu công nợ NPP</div>
        <div class="kt-sub">${data.rows.length} NPP · nhóm "${escapeHtml(data.config.group)}"</div>
      </div>

      <div class="kt-stats">
        <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-file-invoice-dollar"></i> Tổng công nợ NPP</div>
          <div class="kt-stat-value is-grad">${formatVND(data.total_debt)}</div></div>
        <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-hand-holding-dollar"></i> Cần thanh toán</div>
          <div class="kt-stat-value neg">${formatVND(data.total_required)}</div></div>
        <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-calendar-check"></i> Chính sách</div>
          <div class="kt-stat-value ${data.policy === "tet" ? "warn" : "pos"}" style="font-size:18px">
            ${data.policy === "tet" ? "Tết 🧧" : "Bình thường"}</div>
          <div class="kt-stat-sub">${policyDesc(data)}</div></div>
      </div>

      <div class="kt-segment kt-mb" id="npp-tabs">
        <button data-tab="debt" class="is-active">Công nợ NPP</button>
        <button data-tab="due">Đến hạn</button>
        <button data-tab="discount">Chiết khấu ${data.config.discount_pct}%</button>
      </div>

      <div id="npp-tab-body"></div>
    `
  );

  const body = container.querySelector("#npp-tab-body");

  function renderTab() {
    if (state.tab === "debt") renderDebt(body, data, state);
    else if (state.tab === "due") renderDue(body, data, state);
    else renderDiscount(body, data, state);
  }

  container.querySelector("#npp-tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-tab]");
    if (!b) return;
    state.tab = b.dataset.tab;
    container.querySelectorAll("#npp-tabs button").forEach((x) => x.classList.toggle("is-active", x === b));
    renderTab();
  });

  // Click hàng (mọi tab) → 360° khách
  on(body, "click", "[data-customer]", (e, el) => {
    if (e.target.closest("input,button,a")) return;
    navigate("/khach/" + encodeURIComponent(el.dataset.customer));
  });

  renderTab();
}

function policyDesc(d) {
  if (d.policy === "tet") return `Cho nợ ${d.config.tet_pct}% HĐ Tết (từ ${d.tet_start})`;
  return `HĐ quá ${d.config.due_days} ngày là đến hạn`;
}

/* ---------- Tab 1: Công nợ NPP ---------- */
function renderDebt(body, data, state) {
  const filtered = applyFilter(data.rows, state);
  setHTML(
    body,
    html`
      <div class="kt-card">
        <div class="kt-card-head">
          <div class="kt-segment" id="npp-status">
            <button data-f="all" class="${state.statusFilter === "all" ? "is-active" : ""}">Tất cả</button>
            <button data-f="due" class="${state.statusFilter === "due" ? "is-active" : ""}">Cần thu</button>
            <button data-f="normal" class="${state.statusFilter === "normal" ? "is-active" : ""}">Bình thường</button>
            <button data-f="negative" class="${state.statusFilter === "negative" ? "is-active" : ""}">Số dư âm</button>
          </div>
          <div class="kt-search"><i class="fas fa-search"></i><input class="kt-input" id="npp-search" placeholder="Tìm NPP..." value="${state.search}"></div>
        </div>
        <div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>NPP</th><th class="num">Công nợ</th><th class="num">DS bình quân/tháng</th><th class="num">Cần thanh toán</th><th>Trạng thái</th><th></th></tr></thead>
            <tbody>${filtered.map((r) => debtRow(r))}</tbody>
          </table></div>
          ${filtered.length === 0 ? html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Không có NPP phù hợp</p></div>` : ""}
        </div>
      </div>
    `
  );
  const st = body.querySelector("#npp-status");
  st.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-f]");
    if (!b) return;
    state.statusFilter = b.dataset.f;
    renderDebt(body, data, state);
  });
  const search = body.querySelector("#npp-search");
  search.addEventListener("input", () => { state.search = search.value; });
  let timer = null;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => renderDebt(body, data, state), 200);
  });
}

function debtRow(r) {
  const s = STATUS[r.status] || STATUS.normal;
  return html`<tr class="kt-row-link" data-customer="${r.customer}">
    <td>${r.customer_name}</td>
    <td class="num ${r.debt < 0 ? "danger" : ""}">${formatVND(r.debt)}</td>
    <td class="num">${formatVND(r.monthly_sales)}</td>
    <td class="num ${r.required_payment > 0 ? "danger" : "pos"}">${r.required_payment > 0 ? formatVND(r.required_payment) : "—"}</td>
    <td><span class="kt-badge kt-badge--${s.cls}">${s.label}</span></td>
    <td class="num"><span class="kt-btn-icon"><i class="fas fa-chevron-right"></i></span></td>
  </tr>`;
}

/* ---------- Tab 2: Đến hạn + nhắc nợ Zalo ---------- */
function renderDue(body, data, state) {
  const due = data.rows.filter((r) => r.required_payment > 0.5);
  setHTML(
    body,
    html`
      <div class="kt-alert kt-alert--${data.policy === "tet" ? "warning" : "info"}">
        <div class="kt-alert-title"><i class="fas fa-circle-info"></i> Chính sách ${data.policy === "tet" ? "Tết" : "bình thường"}</div>
        <div class="kt-alert-hint">${policyDesc(data)} · ${due.length} NPP cần thanh toán · tổng ${formatVND(data.total_required)}</div>
      </div>
      <div class="kt-card">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-clock"></i> NPP cần thanh toán</div></div>
        <div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>NPP</th><th class="num">Công nợ</th><th class="num">Cần thanh toán</th><th>SĐT</th><th></th></tr></thead>
            <tbody>${due.map((r) => html`<tr class="kt-row-link" data-customer="${r.customer}">
              <td>${r.customer_name}</td>
              <td class="num">${formatVND(r.debt)}</td>
              <td class="num danger">${formatVND(r.required_payment)}</td>
              <td>${r.mobile_no || "—"}</td>
              <td class="num"><button class="kt-btn kt-btn--outline kt-btn--sm" data-zalo="${r.customer}"><i class="fas fa-comment-dots"></i> Nhắc nợ</button></td>
            </tr>`)}</tbody>
          </table></div>
          ${due.length === 0 ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có NPP đến hạn</p></div>` : ""}
        </div>
      </div>
    `
  );
  on(body, "click", "[data-zalo]", (e, el) => {
    e.stopPropagation();
    const r = data.rows.find((x) => x.customer === el.dataset.zalo);
    if (r) openZalo(r, data);
  });
}

function openZalo(r, data) {
  const msg = zaloMessage(r, data);
  const m = openModal({
    title: "Tin nhắn nhắc nợ Zalo",
    icon: "fa-comment-dots",
    maxWidth: 480,
    body: html`
      <div class="kt-field"><label><i class="fas fa-user"></i> ${r.customer_name}${r.mobile_no ? " · " + r.mobile_no : ""}</label>
        <textarea class="kt-textarea" id="zalo-msg" style="min-height:180px">${msg}</textarea></div>
      <div class="kt-modal-actions">
        <button class="kt-btn kt-btn--outline" id="zalo-close">Đóng</button>
        <button class="kt-btn kt-btn--primary" id="zalo-copy"><i class="fas fa-copy"></i> Sao chép</button>
      </div>`,
  });
  m.body.querySelector("#zalo-close").addEventListener("click", m.close);
  m.body.querySelector("#zalo-copy").addEventListener("click", async () => {
    const text = m.body.querySelector("#zalo-msg").value;
    try { await navigator.clipboard.writeText(text); toast("Đã sao chép tin nhắn", "success"); }
    catch (_) { m.body.querySelector("#zalo-msg").select(); document.execCommand("copy"); toast("Đã sao chép", "success"); }
  });
}

function zaloMessage(r, data) {
  const lines = [
    `Kính gửi Quý đối tác ${r.customer_name},`,
    ``,
    `Công ty Cổ phần Hoàng Giang xin thông báo công nợ hiện tại:`,
    `• Tổng công nợ: ${formatVND(r.debt)}`,
    `• Số cần thanh toán${data.policy === "tet" ? " (chính sách Tết)" : ""}: ${formatVND(r.required_payment)}`,
    ``,
    `Kính mong Quý đối tác sắp xếp thanh toán đúng hạn. Trân trọng cảm ơn!`,
    `— Phòng Kế toán, Rồng Vàng Hoàng Gia`,
  ];
  return lines.join("\n");
}

/* ---------- Tab 3: Chiết khấu ---------- */
function renderDiscount(body, data, state) {
  const eligible = data.rows.filter((r) => r.discount_eligible);
  const totalSel = () => eligible.filter((r) => state.selected.has(r.customer)).reduce((s, r) => s + r.discount_amount, 0);

  setHTML(
    body,
    html`
      ${!data.config.discount_account_set
        ? html`<div class="kt-alert kt-alert--warning"><div class="kt-alert-title"><i class="fas fa-gear"></i> Chưa cấu hình tài khoản</div>
            <div class="kt-alert-hint">Vào <b>Ketoan Portal Settings</b> đặt <i>TK chi phí chiết khấu (6412)</i> và <i>TK phải thu (131)</i> để tạo bút toán.</div></div>`
        : ""}
      <div class="kt-card">
        <div class="kt-card-head">
          <div class="kt-card-title"><i class="fas fa-percent"></i> NPP đủ điều kiện chiết khấu ${data.config.discount_pct}% (nợ ≥ ${formatVNDShort(data.config.threshold)})</div>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="kt-sub">Tổng chiết khấu chọn: <b id="npp-disc-total" style="color:var(--kt-success)">${formatVND(0)}</b></span>
            <button class="kt-btn kt-btn--success kt-btn--sm" id="npp-disc-create" ${data.config.discount_account_set ? "" : "disabled"}><i class="fas fa-file-circle-plus"></i> Tạo bút toán</button>
          </div>
        </div>
        <div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th><input type="checkbox" id="npp-disc-all"></th><th>NPP</th><th class="num">Công nợ</th><th class="num">Chiết khấu ${data.config.discount_pct}%</th></tr></thead>
            <tbody>${eligible.map((r) => html`<tr data-customer="${r.customer}">
              <td><input type="checkbox" class="npp-disc-cb" value="${r.customer}" ${state.selected.has(r.customer) ? "checked" : ""}></td>
              <td>${r.customer_name}</td>
              <td class="num">${formatVND(r.debt)}</td>
              <td class="num pos">${formatVND(r.discount_amount)}</td>
            </tr>`)}</tbody>
          </table></div>
          ${eligible.length === 0 ? html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Không có NPP đủ điều kiện</p></div>` : ""}
        </div>
      </div>
    `
  );

  const totalEl = body.querySelector("#npp-disc-total");
  const refreshTotal = () => { totalEl.textContent = formatVND(totalSel()); };

  body.querySelectorAll(".npp-disc-cb").forEach((cb) =>
    cb.addEventListener("change", () => {
      if (cb.checked) state.selected.add(cb.value); else state.selected.delete(cb.value);
      refreshTotal();
    })
  );
  const all = body.querySelector("#npp-disc-all");
  if (all) all.addEventListener("change", () => {
    body.querySelectorAll(".npp-disc-cb").forEach((cb) => {
      cb.checked = all.checked;
      if (all.checked) state.selected.add(cb.value); else state.selected.delete(cb.value);
    });
    refreshTotal();
  });
  refreshTotal();

  const createBtn = body.querySelector("#npp-disc-create");
  if (createBtn) createBtn.addEventListener("click", async () => {
    const picks = eligible.filter((r) => state.selected.has(r.customer)).map((r) => r.customer);
    if (!picks.length) { toast("Chọn ít nhất 1 NPP", "warning"); return; }
    if (!confirm(`Tạo ${picks.length} bút toán chiết khấu (nháp)?`)) return;
    createBtn.disabled = true; createBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang tạo...';
    try {
      const res = await api.nppCreateDiscount(picks);
      toast(`Đã tạo ${res.count} bút toán nháp` + (res.skipped.length ? ` · bỏ qua ${res.skipped.length}` : ""), "success");
      state.selected.clear();
      renderDiscount(body, data, state);
    } catch (e) {
      toast(e.message, "error");
      createBtn.disabled = false; createBtn.innerHTML = '<i class="fas fa-file-circle-plus"></i> Tạo bút toán';
    }
  });
}

/* ---------- helpers ---------- */
function applyFilter(rows, state) {
  let r = rows;
  if (state.statusFilter !== "all") r = r.filter((x) => x.status === state.statusFilter);
  const q = (state.search || "").toLowerCase().trim();
  if (q) r = r.filter((x) => (x.customer_name || x.customer || "").toLowerCase().includes(q));
  return r;
}
