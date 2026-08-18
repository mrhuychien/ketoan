// views/vat.js — Hóa đơn VAT: đối soát ERPNext ↔ MISA.
// 4 rổ: Đã liên kết / Chỉ có trên phần mềm / Chỉ có trên MISA / Lệch tiền.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, formatVNDShort, formatDate, escapeHtml } from "../lib/format.js";
import { openModal } from "../components/modal.js";
import { toast } from "../components/toast.js";

const q = encodeURIComponent;

const BUCKETS = [
  { key: "erp_only", label: "Chỉ có trên phần mềm", icon: "fa-file-circle-question", tone: "warn",
    hint: "Đã ghi sổ trên ERPNext nhưng CHƯA có số hóa đơn MISA — nguy cơ bán mà chưa xuất hóa đơn." },
  { key: "misa_only", label: "Chỉ có trên MISA", icon: "fa-file-circle-exclamation", tone: "danger",
    hint: "Có trên MISA nhưng không nối được về ERPNext — nguy cơ xuất hóa đơn ngoài sổ." },
  { key: "mismatch", label: "Lệch tiền", icon: "fa-scale-unbalanced", tone: "danger",
    hint: "Nối được nhưng số tiền hai bên không khớp." },
  { key: "linked", label: "Đã liên kết", icon: "fa-link", tone: "ok",
    hint: "Hóa đơn ERPNext đã có số hóa đơn MISA." },
];

const todayISO = () => new Date().toISOString().slice(0, 10);
const monthsAgo = (n) => { const d = new Date(); d.setMonth(d.getMonth() - n); return d.toISOString().slice(0, 10); };

export async function render({ container, query }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);

  const state = {
    tab: BUCKETS.some((b) => b.key === query?.tab) ? query.tab : "erp_only",
    from: query?.from || monthsAgo(1),
    to: query?.to || todayISO(),
    search: "",
  };

  let ov;
  try {
    ov = await api.vatOverview({ from_date: state.from, to_date: state.to });
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  setHTML(container, shell(state, ov));
  bind(container, state, ov);
  await loadTab(container, state);
}

function shell(state, ov) {
  const b = ov.buckets;
  return html`
    <div class="kt-view-head">
      <div>
        <div class="kt-view-title"><i class="fas fa-receipt"></i> Hóa đơn VAT</div>
        <div class="kt-sub">Đối soát hóa đơn ERPNext với MISA meInvoice${
          ov.last_sync ? ` · đồng bộ gần nhất ${formatDate((ov.last_sync.finished_at || "").slice(0, 10))} (${ov.last_sync.status})` : ""
        }</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input type="date" class="kt-input kt-input--sm" id="vat-from" value="${state.from}">
        <span class="kt-sub">→</span>
        <input type="date" class="kt-input kt-input--sm" id="vat-to" value="${state.to}">
        ${ov.can_sync ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="vat-import"><i class="fas fa-file-import"></i> Nhập file MISA</button>` : ""}
        ${ov.can_sync ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="vat-sync"><i class="fas fa-rotate"></i> Đồng bộ MISA</button>` : ""}
      </div>
    </div>

    ${ov.last_sync && ov.last_sync.status !== "Thành công" && ov.last_sync.error_log
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)">
          <div class="kt-card-body">
            <div style="font-weight:600;color:var(--kt-danger)">
              <i class="fas fa-triangle-exclamation"></i> Lần đồng bộ gần nhất chưa sạch — số liệu bên dưới CHƯA đủ tin cậy
            </div>
            <div class="kt-sub" style="margin-top:6px;white-space:pre-wrap">${ov.last_sync.error_log}</div>
          </div></div>`
      : ""}

    ${!ov.has_snapshot
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body kt-sub">
            <b>Chưa có dữ liệu MISA.</b> Hai rổ "Chỉ có trên MISA" và "Lệch tiền" sẽ trống cho tới khi nạp lần đầu.
            ${ov.can_sync
              ? "Bấm <b>Nhập file MISA</b> — xuất Excel danh sách hóa đơn từ MISA rồi tải lên. Cách này không phụ thuộc API."
              : "Nhờ kế toán trưởng nạp dữ liệu."}
          </div></div>`
      : ""}

    <div class="kt-stats kt-mb">
      ${BUCKETS.map((x) => html`
        <div class="kt-stat kt-row-link" data-goto="${x.key}" style="cursor:pointer">
          <div class="kt-stat-label"><i class="fas ${x.icon}"></i> ${x.label}</div>
          <div class="kt-stat-value ${x.tone === "danger" ? "danger" : x.tone === "warn" ? "warn" : ""}">${b[x.key].count}</div>
          <div class="kt-stat-sub">${formatVNDShort(b[x.key].amount)}</div>
        </div>`)}
    </div>

    <div class="kt-segment kt-mb" id="vat-tabs">
      ${BUCKETS.map((x) => html`<button data-tab="${x.key}" class="${state.tab === x.key ? "is-active" : ""}">${x.label} (${b[x.key].count})</button>`)}
    </div>

    <div class="kt-card kt-mb"><div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <i class="fas fa-circle-info kt-sub"></i>
      <span class="kt-sub" id="vat-hint">${BUCKETS.find((x) => x.key === state.tab).hint}</span>
      <input class="kt-input kt-input--sm" id="vat-search" placeholder="Tìm số hóa đơn / khách…" style="margin-left:auto;min-width:220px">
    </div></div>

    <div id="vat-body"></div>
  `;
}

function bind(container, state, ov) {
  const reload = () => {
    const url = `#/hoa-don-vat?tab=${state.tab}&from=${state.from}&to=${state.to}`;
    history.replaceState(null, "", url);
    loadTab(container, state);
  };

  container.querySelector("#vat-tabs").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-tab]");
    if (!btn) return;
    state.tab = btn.dataset.tab;
    container.querySelectorAll("#vat-tabs button").forEach((x) => x.classList.toggle("is-active", x === btn));
    container.querySelector("#vat-hint").textContent = BUCKETS.find((x) => x.key === state.tab).hint;
    reload();
  });

  container.querySelectorAll("[data-goto]").forEach((el) => {
    el.addEventListener("click", () => {
      const btn = container.querySelector(`#vat-tabs button[data-tab="${el.dataset.goto}"]`);
      if (btn) btn.click();
    });
  });

  const from = container.querySelector("#vat-from");
  const to = container.querySelector("#vat-to");
  const onDate = () => { state.from = from.value; state.to = to.value; location.hash = `/hoa-don-vat?tab=${state.tab}&from=${state.from}&to=${state.to}`; };
  from.addEventListener("change", onDate);
  to.addEventListener("change", onDate);

  let timer = null;
  container.querySelector("#vat-search").addEventListener("input", (e) => {
    state.search = e.target.value.trim();
    clearTimeout(timer);
    timer = setTimeout(() => loadTab(container, state), 350);
  });

  const imp = container.querySelector("#vat-import");
  if (imp) imp.addEventListener("click", () => pickFile(container, state));

  const sync = container.querySelector("#vat-sync");
  if (sync) sync.addEventListener("click", async () => {
    sync.disabled = true;
    const old = sync.innerHTML;
    sync.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang đồng bộ…';
    try {
      // Đồng bộ chạy NỀN: một tháng có tới hơn nghìn hóa đơn, chạy trong request
      // là chắc chắn timeout gateway và để lại dữ liệu nạp dở.
      const r = await api.vatSync({ from_date: state.from, to_date: state.to });
      toast(r.message || "Đã xếp lịch đồng bộ, đang chạy nền", "success");
      sync.innerHTML = '<i class="fas fa-hourglass-half"></i> Đang chạy nền…';
      frappe_hint(container);
    } catch (e) {
      toast(e.message, "error");
      sync.disabled = false;
      sync.innerHTML = old;
    }
  });
}

// Đồng bộ chạy nền nên trang không tự có dữ liệu mới — nói rõ chứ đừng để
// người dùng ngồi chờ một cái sẽ không tự đến.
function frappe_hint(container) {
  const head = container.querySelector(".kt-view-head");
  if (!head || container.querySelector("#vat-bg-note")) return;
  const note = document.createElement("div");
  note.id = "vat-bg-note";
  note.className = "kt-card kt-mb";
  note.style.borderLeft = "4px solid var(--kt-primary)";
  setHTML(note, html`<div class="kt-card-body kt-sub">
    Đồng bộ đang chạy nền. Vài phút nữa <b>tải lại trang</b> để xem kết quả —
    tiến độ chi tiết xem ở <a target="_blank" href="/desk/misa-sync-run">MISA Sync Run</a>.
  </div>`);
  head.insertAdjacentElement("afterend", note);
}

async function loadTab(container, state) {
  const body = container.querySelector("#vat-body");
  if (!body) return;
  setHTML(body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let res;
  try {
    res = await api.vatInvoices(state.tab, { from_date: state.from, to_date: state.to, search: state.search });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  if (!res.rows.length) {
    setHTML(body, html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có hóa đơn nào trong rổ này.</p></div>`);
    return;
  }
  setHTML(body, res.source === "erp" ? erpTable(state.tab, res.rows) : misaTable(state.tab, res.rows));
  if (res.source === "misa") bindMisaRows(container, state);
}

// ── Bảng phía ERPNext ──────────────────────────────────────────────────────
function erpTable(tab, rows) {
  const linked = tab === "linked";
  return html`
    <div class="kt-card"><div class="kt-card-body">
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr>
          <th>Hóa đơn ERPNext</th><th>Ngày</th><th>Khách</th>
          <th class="num">Trước thuế</th><th class="num">Thuế</th><th class="num">Tổng</th>
          ${linked ? html`<th>Ký hiệu</th><th>Số HĐ</th><th>Ngày HĐ</th>` : html`<th>Trạng thái MISA</th>`}
          <th></th>
        </tr></thead>
        <tbody>${rows.map((r) => html`<tr>
          <td><a target="_blank" href="/desk/sales-invoice/${q(r.name)}">${r.name}</a>
            ${r.is_return ? html`<span class="kt-badge kt-badge--amber">trả hàng</span>` : ""}</td>
          <td>${formatDate(r.posting_date)}</td>
          <td class="kt-cell-wrap">${r.customer_name || r.customer}</td>
          <td class="num">${formatVND(r.net_total)}</td>
          <td class="num">${formatVND(r.total_taxes_and_charges)}</td>
          <td class="num">${formatVND(r.grand_total)}</td>
          ${linked
            ? html`<td>${r.inv_series || "—"}</td><td><b>${r.inv_no}</b></td><td>${formatDate(r.inv_date)}</td>`
            : html`<td>${statusBadge(r.misa_status)}${r.note ? html`<div class="kt-sub">${r.note}</div>` : ""}</td>`}
          <td class="num" style="white-space:nowrap">
            ${r.link ? html`<a class="kt-btn-icon" target="_blank" href="${r.link}" title="Tra cứu trên MISA"><i class="fas fa-up-right-from-square"></i></a>` : ""}
          </td>
        </tr>`)}</tbody>
      </table></div>
      <div class="kt-sub" style="margin-top:8px">${rows.length} hóa đơn</div>
    </div></div>`;
}

// ── Bảng phía MISA ─────────────────────────────────────────────────────────
function misaTable(tab, rows) {
  return html`
    <div class="kt-card"><div class="kt-card-body">
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr>
          <th>Ký hiệu</th><th>Số HĐ</th><th>Ngày</th><th>Người mua</th><th>MST</th>
          <th class="num">Trước thuế</th><th class="num">Thuế</th><th class="num">Tổng</th>
          <th>Đối soát</th><th>Hóa đơn ERPNext</th><th></th>
        </tr></thead>
        <tbody>${rows.map((r) => html`<tr data-snap="${r.name}">
          <td>${r.inv_series}</td><td><b>${r.inv_no}</b></td><td>${formatDate(r.inv_date)}</td>
          <td class="kt-cell-wrap">${r.buyer_name || "—"}</td><td>${r.buyer_tax_code || "—"}</td>
          <td class="num">${formatVND(r.amount_before_vat)}</td>
          <td class="num">${formatVND(r.vat_amount)}</td>
          <td class="num">${formatVND(r.total_amount)}</td>
          <td>${statusBadge(r.match_status)}
            ${r.match_confidence === "Cần review" ? html`<span class="kt-badge kt-badge--amber">cần review</span>` : ""}</td>
          <td>${r.sales_invoice
            ? html`<a target="_blank" href="/desk/sales-invoice/${q(r.sales_invoice)}">${r.sales_invoice}</a>`
            : html`<span class="kt-sub">chưa nối</span>`}</td>
          <td class="num" style="white-space:nowrap">
            ${r.transaction_id ? html`<a class="kt-btn-icon" target="_blank" title="Tra cứu trên MISA"
              href="https://www.meinvoice.vn/tra-cuu/?sc=${q(r.transaction_id)}"><i class="fas fa-up-right-from-square"></i></a>` : ""}
            <button class="kt-btn-icon" data-link="${r.name}" title="Chốt liên kết tay"><i class="fas fa-link"></i></button>
          </td>
        </tr>`)}</tbody>
      </table></div>
      <div class="kt-sub" style="margin-top:8px">${rows.length} hóa đơn trên MISA</div>
    </div></div>`;
}

function statusBadge(s) {
  const map = {
    "Khớp": "green", "Đã phát hành": "green",
    "Lệch tiền": "red", "Phát hành lỗi": "red", "Chỉ có trên MISA": "red",
    "Đã hủy": "grey", "Đã thay thế": "amber",
    "Đã đẩy (nháp)": "amber", "Chưa đẩy": "amber", "Chưa xác định": "grey",
  };
  if (!s) return html`<span class="kt-badge kt-badge--grey">—</span>`;
  return html`<span class="kt-badge kt-badge--${map[s] || "grey"}">${s}</span>`;
}

// ── Chốt liên kết tay ──────────────────────────────────────────────────────
function bindMisaRows(container, state) {
  container.querySelectorAll("button[data-link]").forEach((btn) => {
    btn.addEventListener("click", () => openLinkModal(container, state, btn.dataset.link));
  });
}

function openLinkModal(container, state, snapshot) {
  const modal = openModal({
    title: "Chốt liên kết hóa đơn MISA",
    body: html`
      <p class="kt-sub">Chỉ dùng khi máy không tự khớp được. Liên kết chốt tay sẽ KHÔNG bị job đồng bộ ghi đè.</p>
      <label class="kt-label">Tìm hóa đơn ERPNext</label>
      <input class="kt-input" id="vl-search" placeholder="Số hóa đơn hoặc tên khách…" autocomplete="off">
      <div id="vl-results" style="max-height:260px;overflow:auto;margin-top:8px"></div>
      <label class="kt-label" style="margin-top:12px">Ghi chú (lý do chốt tay)</label>
      <input class="kt-input" id="vl-note" placeholder="vd: khớp theo biên bản đối chiếu ngày…">
    `,
    icon: "fa-link",
    maxWidth: 720,
  });

  const box = modal.body.querySelector("#vl-results");
  let timer = null;
  modal.body.querySelector("#vl-search").addEventListener("input", (e) => {
    const txt = e.target.value.trim();
    clearTimeout(timer);
    if (txt.length < 2) { setHTML(box, ""); return; }
    timer = setTimeout(async () => {
      setHTML(box, html`<div class="kt-sub">Đang tìm…</div>`);
      try {
        const rows = await api.vatSearchInvoices(txt);
        if (!rows.length) { setHTML(box, html`<div class="kt-sub">Không tìm thấy.</div>`); return; }
        setHTML(box, html`<table class="kt-table"><tbody>${rows.map((r) => html`<tr>
          <td>${r.name}</td><td>${formatDate(r.posting_date)}</td>
          <td class="kt-cell-wrap">${r.customer_name}</td>
          <td class="num">${formatVND(r.grand_total)}</td>
          <td>${r.inv_no ? html`<span class="kt-badge kt-badge--amber">đã có số ${r.inv_no}</span>` : ""}</td>
          <td class="num"><button class="kt-btn kt-btn--sm" data-pick="${escapeHtml(r.name)}">Chọn</button></td>
        </tr>`)}</tbody></table>`);
        box.querySelectorAll("button[data-pick]").forEach((b) => {
          b.addEventListener("click", async () => {
            b.disabled = true;
            try {
              await api.vatRelink(snapshot, b.dataset.pick, modal.body.querySelector("#vl-note").value.trim());
              toast("Đã chốt liên kết", "success");
              modal.close();
              loadTab(container, state);
            } catch (err) { toast(err.message, "error"); b.disabled = false; }
          });
        });
      } catch (err) { setHTML(box, html`<div class="kt-sub">${err.message}</div>`); }
    }, 350);
  });
}


// ── Nhập file Excel/CSV xuất từ MISA ───────────────────────────────────────
// Luôn XEM TRƯỚC bản đồ cột rồi mới ghi: tên cột file MISA chưa được xác minh,
// nạp nhầm cột là hỏng toàn bộ đối soát mà không ai biết.
function pickFile(container, state) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".xlsx,.xls,.csv";
  input.onchange = () => {
    const file = input.files && input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => showPreview(container, state, reader.result, file.name);
    reader.readAsDataURL(file);
  };
  input.click();
}

const FIELD_LABEL = {
  inv_series: "Ký hiệu", inv_no: "Số hóa đơn", inv_date: "Ngày hóa đơn",
  buyer_tax_code: "MST người mua", buyer_name: "Tên người mua",
  amount_before_vat: "Tiền trước thuế", vat_amount: "Tiền thuế",
  total_amount: "Tổng tiền", transaction_id: "Mã tra cứu",
  invoice_code: "Mã CQT", einvoice_status: "Trạng thái",
};

async function showPreview(container, state, content, filename) {
  const modal = openModal({
    title: "Nhập hóa đơn MISA — " + filename,
    icon: "fa-file-import",
    maxWidth: 900,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });

  let p;
  try {
    p = await api.vatImportPreview(content);
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }

  const missing = p.missing || [];
  setHTML(modal.body, html`
    ${missing.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">Thiếu cột bắt buộc: ${missing.map((m) => FIELD_LABEL[m] || m).join(", ")}</b>
          <div class="kt-sub">Không nạp được. Kiểm tra lại file xuất từ MISA có đủ cột ký hiệu và số hóa đơn chưa.</div>
        </div></div>`
      : ""}

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="font-weight:600;margin-bottom:6px">Hệ thống hiểu file như sau — kiểm giúp trước khi nạp</div>
      <div class="kt-table-wrap"><table class="kt-table"><tbody>
        ${Object.keys(FIELD_LABEL).map((f) => html`<tr>
          <td style="width:180px">${FIELD_LABEL[f]}</td>
          <td>${p.mapping[f]
            ? html`<span class="kt-badge kt-badge--green">${p.mapping[f]}</span>`
            : html`<span class="kt-sub">không tìm thấy cột</span>`}</td>
        </tr>`)}
      </tbody></table></div>
    </div></div>

    <div class="kt-stats kt-mb">
      <div class="kt-stat"><div class="kt-stat-label">Dòng đọc được</div><div class="kt-stat-value">${p.total_rows}</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Trùng trong file</div>
        <div class="kt-stat-value ${p.duplicates ? "warn" : ""}">${p.duplicates}</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Thiếu ngày</div>
        <div class="kt-stat-value ${p.no_date ? "warn" : ""}">${p.no_date}</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Thiếu tiền</div>
        <div class="kt-stat-value ${p.no_amount ? "warn" : ""}">${p.no_amount}</div></div>
    </div>

    ${p.sample && p.sample.length
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <div class="kt-sub" style="margin-bottom:6px">${p.sample.length} dòng đầu</div>
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Ký hiệu</th><th>Số HĐ</th><th>Ngày</th><th>Người mua</th>
              <th class="num">Trước thuế</th><th class="num">Thuế</th><th class="num">Tổng</th></tr></thead>
            <tbody>${p.sample.map((r) => html`<tr>
              <td>${r.inv_series}</td><td>${r.inv_no}</td><td>${formatDate(r.inv_date)}</td>
              <td class="kt-cell-wrap">${r.buyer_name || "—"}</td>
              <td class="num">${formatVND(r.amount_before_vat)}</td>
              <td class="num">${formatVND(r.vat_amount)}</td>
              <td class="num">${formatVND(r.total_amount)}</td>
            </tr>`)}</tbody>
          </table></div>
        </div></div>`
      : ""}

    <div style="display:flex;gap:10px;justify-content:flex-end">
      <button class="kt-btn kt-btn--outline" id="vi-cancel">Hủy</button>
      <button class="kt-btn" id="vi-go" ${missing.length || !p.total_rows ? "disabled" : ""}>
        <i class="fas fa-download"></i> Nạp ${p.total_rows} hóa đơn
      </button>
    </div>
  `);

  modal.body.querySelector("#vi-cancel").addEventListener("click", () => modal.close());
  const go = modal.body.querySelector("#vi-go");
  if (go) go.addEventListener("click", async () => {
    go.disabled = true;
    go.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang nạp…';
    try {
      const r = await api.vatImportCommit(content);
      const im = r.imported || {};
      const mt = r.matched || {};
      toast(`Nạp xong: ${im.created || 0} mới · ${im.updated || 0} cập nhật · khớp ${mt.matched || 0} · lệch ${mt.mismatched || 0}`, "success");
      modal.close();
      location.reload();
    } catch (e) {
      toast(e.message, "error");
      go.disabled = false;
      go.innerHTML = "Thử lại";
    }
  });
}
