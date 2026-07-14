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

const NPP_TABS = ["debt", "due", "discount", "trahang", "butoan", "einvoice"];
const LEGACY_TABS = { doitru: "trahang" };

export async function render({ container, query }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let data;
  try {
    data = await api.nppDebts();
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  const qtab = query && (LEGACY_TABS[query.tab] || query.tab);
  const initTab = qtab && NPP_TABS.includes(qtab) ? qtab : "debt";
  const state = { tab: initTab, statusFilter: "all", search: "", debtSelected: new Set(), discountMonth: currentMonth(), discSelected: new Set(), discData: null };

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div>
          <div class="kt-view-title"><i class="fas fa-handshake"></i> Đối chiếu công nợ NPP</div>
          <div class="kt-sub">${data.rows.length} NPP · nhóm "${escapeHtml(data.config.group)}"</div>
        </div>
        <a class="kt-btn kt-btn--outline kt-btn--sm" href="#/vt/npp"><i class="fas fa-book-open"></i> Hướng dẫn &amp; lối tắt</a>
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
        <button data-tab="debt" class="${state.tab === "debt" ? "is-active" : ""}">Công nợ &amp; chính sách</button>
        <button data-tab="due" class="${state.tab === "due" ? "is-active" : ""}">Đến hạn</button>
        <button data-tab="discount" class="${state.tab === "discount" ? "is-active" : ""}">Chiết khấu</button>
        <button data-tab="trahang" class="${state.tab === "trahang" ? "is-active" : ""}">Trả hàng</button>
        <button data-tab="butoan" class="${state.tab === "butoan" ? "is-active" : ""}">Bút toán JE</button>
        <button data-tab="einvoice" class="${state.tab === "einvoice" ? "is-active" : ""}">Chưa xuất HĐĐT</button>
      </div>

      <div id="npp-tab-body"></div>
    `
  );

  const body = container.querySelector("#npp-tab-body");

  function renderTab() {
    if (state.tab === "debt") renderDebt(body, data, state);
    else if (state.tab === "due") renderDue(body, data, state);
    else if (state.tab === "discount") renderDiscount(body, data, state);
    else if (state.tab === "trahang") renderReturns(body, data, state);
    else if (state.tab === "butoan") renderJEs(body, data, state);
    else renderEinvoice(body);
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
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <button class="kt-btn kt-btn--primary kt-btn--sm" id="npp-bulk-export"><i class="fas fa-file-pdf"></i> Xuất đối chiếu (<span id="npp-sel-count">0</span>)</button>
            <div class="kt-search"><i class="fas fa-search"></i><input class="kt-input" id="npp-search" placeholder="Tìm NPP..." value="${state.search}"></div>
          </div>
        </div>
        <div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th><input type="checkbox" id="npp-debt-all"></th><th>NPP</th><th class="num">Công nợ</th><th class="num">DS bình quân/tháng</th><th class="num">Cần thanh toán</th><th>Trạng thái</th><th></th></tr></thead>
            <tbody>${filtered.map((r) => debtRow(r, state))}</tbody>
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
  let timer = null;
  search.addEventListener("input", () => {
    state.search = search.value;
    clearTimeout(timer);
    timer = setTimeout(() => renderDebt(body, data, state), 200);
  });

  // Chọn để xuất hàng loạt
  const countEl = body.querySelector("#npp-sel-count");
  const refreshCount = () => { countEl.textContent = state.debtSelected.size; };
  body.querySelectorAll(".npp-debt-cb").forEach((cb) =>
    cb.addEventListener("change", () => {
      if (cb.checked) state.debtSelected.add(cb.value); else state.debtSelected.delete(cb.value);
      refreshCount();
    })
  );
  const all = body.querySelector("#npp-debt-all");
  if (all) all.addEventListener("change", () => {
    body.querySelectorAll(".npp-debt-cb").forEach((cb) => {
      cb.checked = all.checked;
      if (all.checked) state.debtSelected.add(cb.value); else state.debtSelected.delete(cb.value);
    });
    refreshCount();
  });
  refreshCount();

  body.querySelector("#npp-bulk-export").addEventListener("click", () => {
    if (!state.debtSelected.size) { toast("Chọn ít nhất 1 NPP để xuất", "warning"); return; }
    openBulkExport([...state.debtSelected]);
  });
}

function debtRow(r, state) {
  const s = STATUS[r.status] || STATUS.normal;
  const checked = state.debtSelected.has(r.customer) ? "checked" : "";
  return html`<tr class="kt-row-link" data-customer="${r.customer}">
    <td><input type="checkbox" class="npp-debt-cb" value="${r.customer}" ${checked}></td>
    <td>${r.customer_name}</td>
    <td class="num ${r.debt < 0 ? "danger" : ""}">${formatVND(r.debt)}</td>
    <td class="num">${formatVND(r.monthly_sales)}</td>
    <td class="num ${r.required_payment > 0 ? "danger" : "pos"}">${r.required_payment > 0 ? formatVND(r.required_payment) : "—"}</td>
    <td><span class="kt-badge kt-badge--${s.cls}">${s.label}</span></td>
    <td class="num"><span class="kt-btn-icon"><i class="fas fa-chevron-right"></i></span></td>
  </tr>`;
}

function openBulkExport(picks) {
  const todayStr = new Date().toISOString().slice(0, 10);
  const yearStart = todayStr.slice(0, 4) + "-01-01";
  const m = openModal({
    title: `Xuất đối chiếu ${picks.length} NPP`,
    icon: "fa-file-pdf",
    maxWidth: 460,
    body: html`
      <p class="kt-sub kt-mb">Gộp ${picks.length} biên bản vào 1 file PDF (mỗi NPP một trang).</p>
      <div class="kt-row2">
        <div class="kt-field"><label><i class="fas fa-calendar"></i> Từ ngày</label>
          <input type="date" id="npp-bx-from" class="kt-input" value="${yearStart}"></div>
        <div class="kt-field"><label><i class="fas fa-calendar"></i> Đến ngày</label>
          <input type="date" id="npp-bx-to" class="kt-input" value="${todayStr}" max="${todayStr}"></div>
      </div>
      <div class="kt-modal-actions">
        <button class="kt-btn kt-btn--outline" id="npp-bx-cancel">Hủy</button>
        <button class="kt-btn kt-btn--primary" id="npp-bx-go"><i class="fas fa-download"></i> Tải PDF</button>
      </div>`,
  });
  m.body.querySelector("#npp-bx-cancel").addEventListener("click", m.close);
  m.body.querySelector("#npp-bx-go").addEventListener("click", async () => {
    const f = m.body.querySelector("#npp-bx-from").value;
    const t = m.body.querySelector("#npp-bx-to").value;
    const btn = m.body.querySelector("#npp-bx-go");
    btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang tạo...';
    try {
      await api.nppExportBulk(picks, f, t);
      toast("Đã xuất PDF", "success");
      m.close();
    } catch (e) {
      toast(e.message, "error");
      btn.disabled = false; btn.innerHTML = '<i class="fas fa-download"></i> Tải PDF';
    }
  });
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

/* ---------- Tab 3: Chiết khấu (theo doanh số THÁNG) ---------- */
async function renderDiscount(body, data, state) {
  const months = monthOptions();
  const shell = (inner, dd) => html`
    <div class="kt-card">
      <div class="kt-card-head">
        <div>
          <div class="kt-card-title"><i class="fas fa-percent"></i> Chương trình chiết khấu</div>
          <div class="kt-sub">Doanh số tháng ≥ ngưỡng → thưởng % doanh số. Server tự tính &amp; chống tạo trùng.</div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <select class="kt-select" id="npp-disc-month" style="width:auto">
            ${months.map((m) => html`<option value="${m.value}" ${m.value === state.discountMonth ? "selected" : ""}>${m.label}</option>`)}
          </select>
          <button class="kt-btn kt-btn--primary kt-btn--sm" id="npp-disc-check"><i class="fas fa-magnifying-glass"></i> Kiểm tra</button>
        </div>
      </div>
      <div class="kt-card-body">${inner}</div>
    </div>`;

  setHTML(body, shell(html`<div class="kt-boot"><div class="kt-spinner"></div></div>`));
  bindMonth(body, data, state);

  let dd;
  try {
    dd = await api.nppDiscountEligible(state.discountMonth);
  } catch (e) {
    setHTML(body.querySelector(".kt-card-body"), html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  state.discData = dd;
  state.discSelected = new Set();

  const pending = dd.rows.filter((r) => r.status !== "created");
  const totalSel = () => dd.rows.filter((r) => state.discSelected.has(r.customer)).reduce((s, r) => s + r.discount_amount, 0);

  const inner = html`
    ${!dd.config.discount_account_set
      ? html`<div class="kt-alert kt-alert--warning"><div class="kt-alert-title"><i class="fas fa-gear"></i> Chưa cấu hình tài khoản</div>
          <div class="kt-alert-hint">Vào <b>Ketoan Portal Settings</b> đặt <i>TK chi phí chiết khấu (6412)</i> và <i>TK phải thu (131)</i> để tạo bút toán.</div></div>`
      : ""}
    <div class="kt-mb" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
      <span class="kt-sub">Ngưỡng ${formatVNDShort(dd.config.threshold)} · ${dd.config.discount_pct}% doanh số · ${dd.rows.length} NPP đủ điều kiện tháng ${dd.month}</span>
      <span class="kt-sub">Tổng chiết khấu chọn: <b id="npp-disc-total" style="color:var(--kt-success)">${formatVND(0)}</b>
        <button class="kt-btn kt-btn--success kt-btn--sm" id="npp-disc-create" style="margin-left:8px" ${dd.config.discount_account_set ? "" : "disabled"}><i class="fas fa-file-circle-plus"></i> Tạo bút toán</button></span>
    </div>
    <div class="kt-table-wrap"><table class="kt-table">
      <thead><tr><th><input type="checkbox" id="npp-disc-all" ${pending.length ? "" : "disabled"}></th><th>Khách hàng</th><th class="num">Doanh số tháng</th><th class="num">Chiết khấu ${dd.config.discount_pct}%</th><th>Trạng thái</th><th>Thao tác</th></tr></thead>
      <tbody>${dd.rows.map((r) => discRow(r))}</tbody>
    </table></div>
    ${dd.rows.length === 0 ? html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Không có NPP đủ điều kiện trong tháng ${dd.month}</p></div>` : ""}
  `;
  setHTML(body.querySelector(".kt-card-body"), inner);

  const totalEl = body.querySelector("#npp-disc-total");
  const refreshTotal = () => { totalEl.textContent = formatVND(totalSel()); };

  body.querySelectorAll(".npp-disc-cb").forEach((cb) =>
    cb.addEventListener("change", () => {
      if (cb.checked) state.discSelected.add(cb.value); else state.discSelected.delete(cb.value);
      refreshTotal();
    })
  );
  const all = body.querySelector("#npp-disc-all");
  if (all) all.addEventListener("change", () => {
    body.querySelectorAll(".npp-disc-cb:not(:disabled)").forEach((cb) => {
      cb.checked = all.checked;
      if (all.checked) state.discSelected.add(cb.value); else state.discSelected.delete(cb.value);
    });
    refreshTotal();
  });
  refreshTotal();

  const createBtn = body.querySelector("#npp-disc-create");
  if (createBtn) createBtn.addEventListener("click", async () => {
    const picks = [...state.discSelected];
    if (!picks.length) { toast("Chọn ít nhất 1 NPP", "warning"); return; }
    if (!confirm(`Tạo ${picks.length} bút toán chiết khấu tháng ${dd.month} (nháp)?`)) return;
    createBtn.disabled = true; createBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang tạo...';
    try {
      const res = await api.nppCreateDiscount(picks, state.discountMonth);
      toast(`Đã tạo ${res.count} bút toán nháp` + (res.skipped.length ? ` · bỏ qua ${res.skipped.length}` : ""), "success");
      renderDiscount(body, data, state);
    } catch (e) {
      toast(e.message, "error");
      createBtn.disabled = false; createBtn.innerHTML = '<i class="fas fa-file-circle-plus"></i> Tạo bút toán';
    }
  });
}

function discRow(r) {
  const created = r.status === "created";
  return html`<tr>
    <td><input type="checkbox" class="npp-disc-cb" value="${r.customer}" ${created ? "disabled" : ""}></td>
    <td>${r.customer_name}</td>
    <td class="num">${formatVND(r.monthly_sales)}</td>
    <td class="num pos">${formatVND(r.discount_amount)}</td>
    <td>${created ? html`<span class="kt-badge kt-badge--green">Đã tạo JE</span>` : html`<span class="kt-badge kt-badge--gray">Chờ tạo</span>`}</td>
    <td>${r.route ? html`<a class="kt-btn kt-btn--outline kt-btn--sm" target="_blank" href="${r.route}">Xem JE</a>` : "—"}</td>
  </tr>`;
}

function bindMonth(body, data, state) {
  const sel = body.querySelector("#npp-disc-month");
  const btn = body.querySelector("#npp-disc-check");
  const go = () => { state.discountMonth = sel.value; renderDiscount(body, data, state); };
  if (sel) sel.addEventListener("change", go);
  if (btn) btn.addEventListener("click", go);
}

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function monthOptions() {
  const out = [];
  const d = new Date();
  for (let i = 0; i < 12; i++) {
    const y = d.getFullYear(), m = d.getMonth() + 1;
    out.push({ value: `${y}-${String(m).padStart(2, "0")}`, label: `Tháng ${m}/${y}` });
    d.setMonth(d.getMonth() - 1);
  }
  return out;
}

/* ---------- Tab 4a/4b: Trả hàng & Bút toán JE (đối trừ công nợ) ---------- */
const DT_STATUS = {
  cho_hoadon: { label: "Chờ hóa đơn NPP", cls: "yellow" },
  cho_duyet: { label: "Chờ KTT duyệt", cls: "red" },
  done: { label: "Đã trừ công nợ", cls: "green" },
};

function dtBadges(c) {
  const st = DT_STATUS[c.status] || DT_STATUS.cho_hoadon;
  return {
    att: c.attachments
      ? html`<span class="kt-badge kt-badge--green"><i class="fas fa-paperclip"></i> ${c.attachments}</span>`
      : html`<span class="kt-badge kt-badge--yellow">chưa có</span>`,
    status: html`<span class="kt-badge kt-badge--${st.cls}">${st.label}</span>`,
  };
}

function dtActions(c, canApprove) {
  const draft = c.status !== "done";
  return html`
    ${draft ? html`<button class="kt-btn-icon dt-upload" title="Đính kèm hóa đơn NPP" data-dt="${c.doctype}" data-name="${c.name}"><i class="fas fa-paperclip"></i></button>` : ""}
    ${draft && canApprove && c.status === "cho_duyet" ? html`<button class="kt-btn kt-btn--success kt-btn--sm dt-approve" data-dt="${c.doctype}" data-name="${c.name}">Duyệt</button>` : ""}
    <a class="kt-btn-icon" target="_blank" href="${c.route}" title="Mở trong ERPNext"><i class="fas fa-up-right-from-square"></i></a>`;
}

// Gắn handler upload + duyệt cho các nút trong body; reload() gọi lại render tab.
function bindDtActions(body, reload) {
  body.querySelectorAll(".dt-upload").forEach((btn) =>
    btn.addEventListener("click", () => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".pdf,.jpg,.jpeg,.png,.xml";
      input.onchange = () => {
        const file = input.files && input.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async () => {
          btn.disabled = true;
          try {
            await api.doitruUpload(btn.dataset.dt, btn.dataset.name, file.name, reader.result);
            toast("Đã đính kèm hóa đơn NPP", "success");
            reload();
          } catch (e) { toast(e.message, "error"); btn.disabled = false; }
        };
        reader.readAsDataURL(file);
      };
      input.click();
    })
  );
  body.querySelectorAll(".dt-approve").forEach((btn) =>
    btn.addEventListener("click", async () => {
      if (!confirm(`Duyệt & ghi sổ ${btn.dataset.name}? Thao tác này trừ công nợ NPP.`)) return;
      btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
      try {
        await api.doitruApprove(btn.dataset.dt, btn.dataset.name);
        toast("Đã duyệt — công nợ được trừ", "success");
        reload();
      } catch (e) { toast(e.message, "error"); btn.disabled = false; btn.innerHTML = "Duyệt"; }
    })
  );
}

function dtCountBadges(c) {
  return html`
    <span class="kt-badge kt-badge--yellow">${c.cho_hoadon} chờ HĐ</span>
    <span class="kt-badge kt-badge--red">${c.cho_duyet} chờ duyệt</span>
    <span class="kt-badge kt-badge--green">${c.done} xong</span>`;
}

/* --- Tab: TRẢ HÀNG --- */
async function renderReturns(body, data, state) {
  setHTML(body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let d;
  try { d = await api.doitruCases(); }
  catch (e) { setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`); return; }

  setHTML(
    body,
    html`
      <div class="kt-alert kt-alert--info">
        <div class="kt-alert-title"><i class="fas fa-circle-info"></i> Quy trình trả hàng</div>
        <div class="kt-alert-hint">Tạo SI trả về NHÁP → chờ NPP xuất hóa đơn → <b>đính kèm</b> vào chứng từ → <b>KTT duyệt</b> (submit) → trừ công nợ.</div>
      </div>
      <div class="kt-card">
        <div class="kt-card-head">
          <div class="kt-card-title"><i class="fas fa-rotate-left"></i> Hàng trả lại · ${dtCountBadges(d.returns_counts)}</div>
          <button class="kt-btn kt-btn--primary kt-btn--sm" id="dt-new-return"><i class="fas fa-plus"></i> Trả hàng</button>
        </div>
        <div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Chứng từ</th><th>NPP</th><th>Ngày</th><th class="num">Giá trị</th><th>HĐ NPP</th><th>Trạng thái</th><th></th></tr></thead>
            <tbody>${d.returns.map((c) => {
              const b = dtBadges(c);
              return html`<tr>
                <td>${c.name}${c.against ? html`<br><span class="kt-sub">gốc: ${c.against}</span>` : ""}</td>
                <td>${c.label}</td><td>${c.date || "—"}</td>
                <td class="num">${formatVND(c.amount)}</td>
                <td>${b.att}</td><td>${b.status}</td>
                <td class="num" style="white-space:nowrap">${dtActions(c, d.can_approve)}</td>
              </tr>`;
            })}</tbody>
          </table></div>
          ${d.returns.length === 0 ? html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Chưa có hồ sơ trả hàng</p></div>` : ""}
        </div>
      </div>
    `
  );

  body.querySelector("#dt-new-return").addEventListener("click", () => openNewReturn(body, data, state));
  bindDtActions(body, () => renderReturns(body, data, state));
}

/* --- Tab: BÚT TOÁN JE (chiết khấu, thưởng, hỗ trợ...) --- */
async function renderJEs(body, data, state) {
  setHTML(body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let d;
  try { d = await api.doitruCases(); }
  catch (e) { setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`); return; }

  setHTML(
    body,
    html`
      <div class="kt-alert kt-alert--info">
        <div class="kt-alert-title"><i class="fas fa-circle-info"></i> Bút toán JE gắn khách NPP</div>
        <div class="kt-alert-hint">Gồm chiết khấu, thưởng, hỗ trợ, điều chỉnh... JE NHÁP → chờ NPP xuất hóa đơn → <b>đính kèm</b> → <b>KTT duyệt</b> → trừ công nợ. (Chiết khấu tạo từ tab "Chiết khấu"; JE khác tạo trong Desk.)</div>
      </div>
      <div class="kt-card">
        <div class="kt-card-head">
          <div class="kt-card-title"><i class="fas fa-pen-to-square"></i> Bút toán JE · ${dtCountBadges(d.je_counts)}</div>
          <a class="kt-btn kt-btn--primary kt-btn--sm" target="_blank" href="/app/journal-entry/new"><i class="fas fa-plus"></i> Bút toán JE (Desk)</a>
        </div>
        <div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Chứng từ</th><th>NPP</th><th>Loại</th><th>Ngày</th><th class="num">Giá trị</th><th>HĐ NPP</th><th>Trạng thái</th><th></th></tr></thead>
            <tbody>${d.jes.map((c) => {
              const b = dtBadges(c);
              return html`<tr>
                <td title="${c.remark || ""}">${c.name}</td>
                <td>${c.label}</td>
                <td><span class="kt-badge kt-badge--gray">${c.purpose}</span></td>
                <td>${c.date || "—"}</td>
                <td class="num">${formatVND(c.amount)}</td>
                <td>${b.att}</td><td>${b.status}</td>
                <td class="num" style="white-space:nowrap">${dtActions(c, d.can_approve)}</td>
              </tr>`;
            })}</tbody>
          </table></div>
          ${d.jes.length === 0 ? html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Không có bút toán JE gắn khách NPP</p></div>` : ""}
        </div>
      </div>
    `
  );

  bindDtActions(body, () => renderJEs(body, data, state));
}

function openNewReturn(body, data, state) {
  const npps = data.rows;
  const m = openModal({
    title: "Tạo hồ sơ trả hàng",
    icon: "fa-rotate-left",
    maxWidth: 520,
    body: html`
      <div class="kt-field"><label><i class="fas fa-user"></i> NPP *</label>
        <select id="nr-customer" class="kt-select"><option value="">— Chọn NPP —</option>
          ${npps.map((r) => html`<option value="${r.customer}">${r.customer_name}</option>`)}</select></div>
      <div class="kt-field"><label><i class="fas fa-file-invoice"></i> Hóa đơn gốc *</label>
        <select id="nr-invoice" class="kt-select" disabled><option value="">— Chọn NPP trước —</option></select></div>
      <p class="kt-sub">Tạo Sales Invoice trả về NHÁP từ hóa đơn gốc (chỉnh số lượng/tiền trong Desk nếu trả một phần).</p>
      <div class="kt-modal-actions">
        <button class="kt-btn kt-btn--outline" id="nr-cancel">Hủy</button>
        <button class="kt-btn kt-btn--primary" id="nr-go" disabled><i class="fas fa-plus"></i> Tạo nháp</button>
      </div>`,
  });
  const $sel = (id) => m.body.querySelector(id);
  $sel("#nr-cancel").addEventListener("click", m.close);

  $sel("#nr-customer").addEventListener("change", async () => {
    const cust = $sel("#nr-customer").value;
    const inv = $sel("#nr-invoice");
    inv.disabled = true; inv.innerHTML = '<option value="">Đang tải…</option>';
    if (!cust) return;
    try {
      const rows = await api.doitruReturnSources(cust);
      inv.innerHTML = '<option value="">— Chọn hóa đơn —</option>' +
        rows.map((r) => `<option value="${r.name}">${r.name} · ${r.posting_date} · ${formatVND(r.grand_total)}</option>`).join("");
      inv.disabled = false;
    } catch (e) { toast(e.message, "error"); }
  });
  $sel("#nr-invoice").addEventListener("change", () => { $sel("#nr-go").disabled = !$sel("#nr-invoice").value; });

  $sel("#nr-go").addEventListener("click", async () => {
    const invoice = $sel("#nr-invoice").value;
    const btn = $sel("#nr-go");
    btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang tạo…';
    try {
      const res = await api.doitruCreateReturn(invoice);
      toast(`Đã tạo ${res.name} (nháp)`, "success");
      m.close();
      window.open(res.route, "_blank");
      renderReturns(body, data, state);
    } catch (e) { toast(e.message, "error"); btn.disabled = false; btn.innerHTML = '<i class="fas fa-plus"></i> Tạo nháp'; }
  });
}

/* ---------- Tab 5: Hàng đi chưa xuất HĐĐT ---------- */
async function renderEinvoice(body) {
  setHTML(body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let d;
  try { d = await api.doitruMissingEinvoice(); }
  catch (e) { setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`); return; }

  if (!d.supported) {
    setHTML(body, html`<div class="kt-empty"><i class="fas fa-plug-circle-xmark"></i><p>${d.note || "Site chưa có field vn_einvoice_number"}</p></div>`);
    return;
  }
  setHTML(
    body,
    html`
      <div class="kt-card">
        <div class="kt-card-head">
          <div class="kt-card-title"><i class="fas fa-file-circle-exclamation"></i> Hóa đơn bán chưa xuất HĐĐT (${d.rows.length})</div>
          <span class="kt-sub">Quy ước: chưa điền số HĐĐT (vn_einvoice_number) = chưa xuất · tổng ${formatVND(d.total)}</span>
        </div>
        <div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Hóa đơn</th><th>NPP</th><th>Ngày</th><th class="num">Giá trị</th><th></th></tr></thead>
            <tbody>${d.rows.map(
              (r) => html`<tr><td>${r.name}</td><td>${r.customer_name}</td><td>${r.posting_date}</td>
                <td class="num">${formatVND(r.grand_total)}</td>
                <td class="num"><a class="kt-btn-icon" target="_blank" href="/app/sales-invoice/${r.name}"><i class="fas fa-up-right-from-square"></i></a></td></tr>`
            )}</tbody>
          </table></div>
          ${d.rows.length === 0 ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Tất cả hàng đi đã xuất HĐĐT 👍</p></div>` : ""}
        </div>
      </div>
    `
  );
}

/* ---------- helpers ---------- */
function applyFilter(rows, state) {
  let r = rows;
  if (state.statusFilter !== "all") r = r.filter((x) => x.status === state.statusFilter);
  const q = (state.search || "").toLowerCase().trim();
  if (q) r = r.filter((x) => (x.customer_name || x.customer || "").toLowerCase().includes(q));
  return r;
}
