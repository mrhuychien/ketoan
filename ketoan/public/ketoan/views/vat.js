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
    page: 1,
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
        ${ov.can_sync ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="vat-legacy"><i class="fas fa-right-left"></i> Chuyển số HĐ cũ</button>` : ""}
        ${ov.can_sync ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="vat-import"><i class="fas fa-file-import"></i> Nhập file MISA</button>` : ""}
        ${ov.can_sync ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="vat-sync"><i class="fas fa-rotate"></i> Đồng bộ MISA</button>` : ""}
        ${ov.can_sync && ov.missing_ref_id
          ? html`<button class="kt-btn kt-btn--danger kt-btn--sm" id="vat-refid"
                   title="Hóa đơn ghi sổ TRƯỚC khi cài app không đi qua hook cấp RefID, nên bị chặn ngay khi bấm xuất hóa đơn.">
              <i class="fas fa-key"></i> Cấp RefID cho ${ov.missing_ref_id} hóa đơn cũ
            </button>`
          : ""}
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
    state.page = 1;   // rổ khác, số trang cũ vô nghĩa
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
    state.page = 1;   // lọc lại thì phải về trang đầu, không thì rơi vào trang trống
    clearTimeout(timer);
    timer = setTimeout(() => loadTab(container, state), 350);
  });

  const imp = container.querySelector("#vat-import");
  if (imp) imp.addEventListener("click", () => pickFile(container, state));

  const leg = container.querySelector("#vat-legacy");
  if (leg) leg.addEventListener("click", () => openLegacyModal());

  const rid = container.querySelector("#vat-refid");
  if (rid) rid.addEventListener("click", async () => {
    if (!confirm(
        "Cấp RefID cho hóa đơn cũ (mỗi lượt tối đa 500)?\n\n" +
        "RefID chỉ là khóa nối để không bị chặn khi xuất hóa đơn. Việc này KHÔNG " +
        "phát hành lại hóa đơn nào: hóa đơn đã có số sẽ dừng ở 'Hóa đơn đã được " +
        "xuất trước đó'.")) return;
    rid.disabled = true;
    try {
      const r = await api.vatBackfillRefId(500);
      toast(`Đã cấp RefID cho ${r.updated} hóa đơn. Còn thiếu ${r.remaining}.`,
            "success");
      if (r.remaining) toast(`Còn ${r.remaining} hóa đơn — bấm lại để chạy tiếp.`, "error");
      location.reload();
    } catch (e) { toast(e.message, "error"); rid.disabled = false; }
  });

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
    res = await api.vatInvoices(state.tab, {
      from_date: state.from, to_date: state.to, search: state.search, page: state.page,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  // Xóa dữ liệu / đổi bộ lọc có thể làm trang đang xem rơi ra ngoài phạm vi.
  // Rơi vào trang trống mà báo "không có hóa đơn nào" là nói dối người dùng.
  if (!res.rows.length && (res.total || 0) > 0 && state.page > 1) {
    state.page = res.pages || 1;
    return loadTab(container, state);
  }
  if (!res.rows.length) {
    setHTML(body, html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có hóa đơn nào trong rổ này.</p></div>`);
    return;
  }
  setHTML(body, res.source === "erp" ? erpTable(state.tab, res.rows, res) : misaTable(state.tab, res.rows, res));
  if (res.source === "misa") bindMisaRows(container, state);
  bindPager(container, state);
}

// ── Chia trang ─────────────────────────────────────────────────────────────
// Tổng số ở đây là tổng THẬT của cả rổ (backend đếm riêng), không phải số dòng
// đang hiển thị — đọc nhầm hai con số này là đếm sót hóa đơn.
function pager(res, unit) {
  const total = res.total || 0;
  const pages = res.pages || 1;
  const page = res.page || 1;
  const from = (page - 1) * (res.page_size || 20) + 1;
  const to = from + (res.rows.length - 1);

  const btn = (p, label, disabled, active) => html`<button
    class="kt-btn kt-btn--sm ${active ? "" : "kt-btn--outline"}"
    data-page="${p}" ${disabled ? "disabled" : ""}>${label}</button>`;

  // Cửa sổ 5 trang quanh trang hiện tại — 63 trang mà in hết là vỡ hàng.
  let lo = Math.max(1, page - 2);
  const hi = Math.min(pages, lo + 4);
  lo = Math.max(1, hi - 4);
  const nums = [];
  for (let p = lo; p <= hi; p++) nums.push(p);

  return html`
    <div class="kt-pager" style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:10px">
      <span class="kt-sub">${from}–${to} / ${total} ${unit}</span>
      ${pages > 1 ? html`<span style="margin-left:auto;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
        ${btn(1, html`<i class="fas fa-angles-left"></i>`, page <= 1, false)}
        ${btn(page - 1, html`<i class="fas fa-angle-left"></i>`, page <= 1, false)}
        ${lo > 1 ? html`<span class="kt-sub">…</span>` : ""}
        ${nums.map((p) => btn(p, String(p), false, p === page))}
        ${hi < pages ? html`<span class="kt-sub">…</span>` : ""}
        ${btn(page + 1, html`<i class="fas fa-angle-right"></i>`, page >= pages, false)}
        ${btn(pages, html`<i class="fas fa-angles-right"></i>`, page >= pages, false)}
      </span>` : ""}
    </div>`;
}

function bindPager(container, state) {
  container.querySelectorAll(".kt-pager button[data-page]").forEach((b) => {
    b.addEventListener("click", () => {
      const p = parseInt(b.dataset.page, 10);
      if (!p || p === state.page) return;
      state.page = p;
      loadTab(container, state);
      const body = container.querySelector("#vat-body");
      if (body) body.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

// ── Bảng phía ERPNext ──────────────────────────────────────────────────────
function erpTable(tab, rows, res) {
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
            ${r.is_return ? html`<span class="kt-badge kt-badge--yellow">trả hàng</span>` : ""}</td>
          <td>${formatDate(r.posting_date)}</td>
          <td class="kt-cell-wrap">${r.customer_name || r.customer}</td>
          <td class="num">${formatVND(r.net_total)}</td>
          <td class="num">${formatVND(r.total_taxes_and_charges)}</td>
          <td class="num">${formatVND(r.grand_total)}</td>
          ${linked
            ? html`<td>${r.inv_series || "—"}</td>
                <td><b>${r.inv_no}</b>${relationBadge(r)}</td><td>${formatDate(r.inv_date)}</td>`
            : html`<td>${statusBadge(r.misa_status)}${relationBadge(r)}${r.note ? html`<div class="kt-sub">${r.note}</div>` : ""}</td>`}
          <td class="num" style="white-space:nowrap">
            ${r.link ? html`<a class="kt-btn-icon" target="_blank" href="${r.link}" title="Tra cứu trên MISA"><i class="fas fa-up-right-from-square"></i></a>` : ""}
          </td>
        </tr>`)}</tbody>
      </table></div>
      ${pager(res, "hóa đơn")}
    </div></div>`;
}

// ── Bảng phía MISA ─────────────────────────────────────────────────────────
function misaTable(tab, rows, res) {
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
            ${r.match_confidence === "Cần review" ? html`<span class="kt-badge kt-badge--yellow">cần review</span>` : ""}</td>
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
      ${pager(res, "hóa đơn trên MISA")}
    </div></div>`;
}

// Quan hệ thay thế/điều chỉnh là TRỤC RIÊNG, không phải một giá trị của trạng
// thái phát hành: một hóa đơn thay thế vẫn phải đi hết vòng cấp mã của nó.
// Bốn quan hệ, KHÔNG gộp. "Bị thay thế" là hết hiệu lực (đỏ), còn "Bị điều
// chỉnh" thì hóa đơn gốc VẪN còn hiệu lực, chỉ cộng thêm phần chênh (vàng) —
// tô hai cái này cùng màu là dẫn kế toán tới chỗ khai thiếu doanh thu.
const RELATION_BADGE = {
  "Hóa đơn thay thế": ["yellow", "fa-rotate-left", "bản thay thế", "Thay thế cho "],
  "Hóa đơn điều chỉnh": ["yellow", "fa-sliders", "bản điều chỉnh", "Điều chỉnh cho "],
  "Bị thay thế": ["red", "fa-ban", "bị thay thế", "Đã bị hóa đơn khác thay thế — hết hiệu lực. "],
  "Bị điều chỉnh": ["yellow", "fa-pen", "bị điều chỉnh", "Có hóa đơn điều chỉnh — bản này VẪN còn hiệu lực. "],
  "Chưa xác định": ["gray", "fa-question", "quan hệ ?", "MISA trả mã quan hệ chưa xác minh. "],
};

function relationBadge(r) {
  const b = RELATION_BADGE[r.relation];
  if (!b) return "";
  const [tone, icon, label, prefix] = b;
  return html` <span class="kt-badge kt-badge--${tone}" title="${prefix}${r.org_inv || ""}">
    <i class="fas ${icon}"></i> ${label}</span>`;
}

function statusBadge(s) {
  const map = {
    "Khớp": "green", "Đã phát hành": "green",
    "Lệch tiền": "red", "Phát hành lỗi": "red", "Chỉ có trên MISA": "red",
    "Đã hủy": "gray", "Đã thay thế": "red",
    "Chờ cấp mã": "yellow",
    "Đã đẩy (nháp)": "yellow", "Chưa đẩy": "yellow", "Chưa xác định": "gray",
  };
  if (!s) return html`<span class="kt-badge kt-badge--gray">—</span>`;
  return html`<span class="kt-badge kt-badge--${map[s] || "gray"}">${s}</span>`;
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
          <td>${r.inv_no ? html`<span class="kt-badge kt-badge--yellow">đã có số ${r.inv_no}</span>` : ""}</td>
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


// ── Chuyển số hóa đơn nhập tay sang nhóm field MISA ─────────────────────────
// Trước khi có tích hợp, kế toán gõ số vào `vn_einvoice_number`. Đối soát chỉ
// đọc `custom_misa_inv_no`, nên hóa đơn cũ trông như chưa có số. Màn hình này
// chép ngược — XEM TRƯỚC rồi mới ghi, vì ghi sai số hóa đơn là sai báo cáo thuế.
function openLegacyModal() {
  const modal = openModal({
    title: "Chuyển số hóa đơn nhập tay sang nhóm MISA",
    icon: "fa-right-left",
    maxWidth: 900,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  const st = { year: "", series: "" };
  loadLegacy(modal, st);
}

async function loadLegacy(modal, st) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let p;
  try {
    p = await api.vatLegacyPreview({ year: st.year || undefined, default_series: st.series || undefined });
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  if (!p.supported) {
    setHTML(modal.body, html`<div class="kt-empty"><p>${p.note}</p></div>`);
    return;
  }

  const years = p.years || [];
  const opts = p.default_series_options || [];

  setHTML(modal.body, html`
    <p class="kt-sub">
      Chép <b>vn_einvoice_number</b> → <b>Số hóa đơn MISA</b> cho hóa đơn cũ.
      Chỉ ghi khi ô số MISA đang trống — không đè số do đồng bộ tự động điền.
      Mã tra cứu cũ dạng uuid là rác của luồng cũ nên <b>không</b> được chép.
    </p>

    <div style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-bottom:12px">
      <div>
        <label class="kt-label">Năm</label>
        <select class="kt-input kt-input--sm" id="lg-year">
          <option value="">Tất cả</option>
          ${years.map((y) => html`<option value="${y.year}" ${String(st.year) === String(y.year) ? "selected" : ""}>
            ${y.year} (${y.total})</option>`)}
        </select>
      </div>
      <div>
        <label class="kt-label">Ký hiệu mặc định (dùng cho dòng chỉ có số)</label>
        ${opts.length
          ? html`<select class="kt-input kt-input--sm" id="lg-series">
              <option value="">— không đặt —</option>
              ${opts.map((s) => html`<option value="${s}" ${st.series === s ? "selected" : ""}>${s}</option>`)}
            </select>`
          : html`<input class="kt-input kt-input--sm" id="lg-series" placeholder="vd 1C25MHG" value="${st.series}">`}
      </div>
    </div>

    <div class="kt-stats kt-mb">
      <div class="kt-stat"><div class="kt-stat-label">Chép được</div>
        <div class="kt-stat-value">${p.ok}</div>
        <div class="kt-stat-sub">${p.on_misa} khớp sẵn bên MISA</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Bỏ qua</div>
        <div class="kt-stat-value ${p.skipped ? "warn" : ""}">${p.skipped}</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Không có ngày phát hành</div>
        <div class="kt-stat-value ${p.no_date ? "warn" : ""}">${p.no_date}</div>
        <div class="kt-stat-sub">để trống, không lấy ngày ghi sổ thay</div></div>
    </div>

    ${p.truncated
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">Danh sách bị cắt bớt</b>
          <div class="kt-sub">Còn hóa đơn chưa được đưa vào lượt này. Chạy từng năm một để chép hết.</div>
        </div></div>`
      : ""}

    ${years.length > 1 || (years.length === 1 && !st.year)
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <div class="kt-sub" style="margin-bottom:6px">Ký hiệu đọc được theo từng năm — chạy riêng từng năm nếu ký hiệu khác nhau</div>
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Năm</th><th class="num">Tổng</th><th class="num">Chép được</th><th class="num">Bỏ qua</th><th>Ký hiệu</th></tr></thead>
            <tbody>${years.map((y) => html`<tr>
              <td>${y.year || "—"}</td><td class="num">${y.total}</td>
              <td class="num">${y.ok}</td>
              <td class="num ${y.skipped ? "warn" : ""}">${y.skipped}</td>
              <td>${(y.series || []).map((s) => html`<span class="kt-badge kt-badge--gray">${s[0]} × ${s[1]}</span> `)}</td>
            </tr>`)}</tbody>
          </table></div></div></div>`
      : ""}

    ${(p.problem_counts || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          <b>${p.skipped} dòng KHÔNG được chép</b>
          <div class="kt-sub" style="margin:6px 0">Máy không đoán số hóa đơn. Những dòng này phải sửa tay trên Sales Invoice.</div>
          <div class="kt-table-wrap"><table class="kt-table">
            <tbody>${p.problem_counts.map((c) => html`<tr><td>${c.label}</td><td class="num">${c.count}</td></tr>`)}</tbody>
          </table></div>
          <details style="margin-top:8px"><summary class="kt-sub" style="cursor:pointer">Xem chi tiết ${Math.min(p.skipped, 100)} dòng đầu</summary>
            <div class="kt-table-wrap" style="max-height:240px;overflow:auto;margin-top:6px"><table class="kt-table">
              <thead><tr><th>Hóa đơn</th><th>Ngày</th><th>Giá trị đang có</th><th>Lý do</th></tr></thead>
              <tbody>${(p.problems || []).map((x) => html`<tr>
                <td><a target="_blank" href="/desk/sales-invoice/${q(x.name)}">${x.name}</a></td>
                <td>${formatDate(x.posting_date)}</td>
                <td><code>${x.legacy_no}</code></td>
                <td>${x.reason_label}${x.conflict_with ? html` — ${x.conflict_with}` : ""}</td>
              </tr>`)}</tbody>
            </table></div>
          </details>
        </div></div>`
      : ""}

    ${(p.sample || []).length
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <div class="kt-sub" style="margin-bottom:6px">${p.sample.length} dòng đầu sẽ được ghi — kiểm giúp ký hiệu và số</div>
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr><th>Hóa đơn</th><th>Ngày</th><th>Khách</th><th>Đang có</th><th>→ Ký hiệu</th><th>→ Số</th><th>Bên MISA</th></tr></thead>
            <tbody>${p.sample.map((x) => html`<tr>
              <td><a target="_blank" href="/desk/sales-invoice/${q(x.name)}">${x.name}</a></td>
              <td>${formatDate(x.posting_date)}</td>
              <td class="kt-cell-wrap">${x.customer_name || "—"}</td>
              <td><code>${x.legacy_no}</code></td>
              <td>${x.inv_series}</td><td><b>${x.inv_no}</b></td>
              <td>${x.on_misa
                ? html`<span class="kt-badge kt-badge--green">có</span>`
                : html`<span class="kt-sub">chưa thấy</span>`}</td>
            </tr>`)}</tbody>
          </table></div></div></div>`
      : ""}

    <div style="display:flex;gap:10px;justify-content:flex-end">
      <button class="kt-btn kt-btn--outline" id="lg-cancel">Đóng</button>
      <button class="kt-btn" id="lg-go" ${p.ok && p.can_run ? "" : "disabled"}>
        <i class="fas fa-right-left"></i> Chép ${p.ok} số hóa đơn
      </button>
    </div>
  `);

  const reload = () => {
    st.year = modal.body.querySelector("#lg-year").value;
    st.series = modal.body.querySelector("#lg-series").value.trim();
    loadLegacy(modal, st);
  };
  modal.body.querySelector("#lg-year").addEventListener("change", reload);
  modal.body.querySelector("#lg-series").addEventListener("change", reload);
  modal.body.querySelector("#lg-cancel").addEventListener("click", () => modal.close());

  const go = modal.body.querySelector("#lg-go");
  if (go) go.addEventListener("click", async () => {
    if (!confirm(`Ghi số hóa đơn cho ${p.ok} chứng từ đã ghi sổ. Xác nhận?`)) return;
    go.disabled = true;
    go.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang chép…';
    try {
      const r = await api.vatLegacyCommit({
        year: st.year || undefined,
        default_series: st.series || undefined,
        // Vân tay của đúng kế hoạch vừa hiện trên màn hình. Ai đó sửa số hóa
        // đơn trong lúc này thì backend dừng, không ghi gì.
        expected_hash: p.plan_hash,
      });
      toast(r.message + (r.rematch_queued ? " · đang đối soát lại ở nền" : ""), "success");
      modal.close();
      location.reload();
    } catch (e) {
      toast(e.message, "error");
      go.disabled = false;
      go.innerHTML = "Thử lại";
    }
  });
}
