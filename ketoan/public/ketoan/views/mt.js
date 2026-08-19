// views/mt.js — Công nợ MT (kênh siêu thị hiện đại).
//
// Ba tab: Quản lý thanh toán · Quản lý chiết khấu · Công nợ chung của chuỗi.
//
// ĐIỀU PHẢI NÓI RÕ TRÊN MÀN HÌNH, KHÔNG ĐƯỢC GIẤU:
// Mọi con số "đã thu / còn lại" ở đây tính từ BẢNG KÊ THANH TOÁN của chuỗi, KHÔNG
// phải outstanding_amount của ERPNext. Hệ thống cố ý KHÔNG tự tạo Payment Entry /
// Journal Entry từ file nhập — con người đọc bảng kê rồi mới quyết định hạch toán.
// Nếu kế toán tưởng đây là số dư sổ cái thì sẽ đối chiếu nhầm với sổ cái và kết
// luận sai. Vì vậy câu cảnh báo đó nằm ngay dưới tiêu đề, không nằm trong tooltip.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND, formatVNDShort, formatDate } from "../lib/format.js";
import { openModal } from "../components/modal.js";
import { toast } from "../components/toast.js";

const q = encodeURIComponent;

const TABS = [
  { key: "thanh-toan", label: "Quản lý thanh toán", icon: "fa-money-check-dollar",
    hint: "Hóa đơn bán cho chuỗi và tiền chuỗi đã trả theo BẢNG KÊ. Một hóa đơn có thể được trả làm nhiều kỳ — cột 'đã nhận' là tổng cộng dồn của mọi bảng kê." },
  { key: "chiet-khau", label: "Quản lý chiết khấu", icon: "fa-percent",
    hint: "Các khoản chuỗi TRỪ LẠI: chiết khấu, phí dịch vụ, hàng trả lại, khoản khác. Phần lớn không gắn với hóa đơn nào nên đây là danh sách DÒNG bảng kê, không phải danh sách hóa đơn." },
  { key: "chuoi", label: "Công nợ chung của chuỗi", icon: "fa-store",
    hint: "Gộp theo chuỗi siêu thị. Ánh xạ khách hàng → chuỗi lấy từ bảng kê kế toán đã chốt; hệ thống KHÔNG tự đoán từ tên khách." },
];

// Rổ hóa đơn của tab 1 — đúng khóa mà backend nhận (mt.get_invoices).
const INV_BUCKETS = [
  { key: "chua_thanh_toan", label: "Chưa thu đủ" },
  { key: "da_thanh_toan", label: "Đã thu đủ" },
  { key: "tat_ca", label: "Tất cả" },
];

// Đúng options của field `chain` trên DocType MT Payment Advice. Không tự thêm
// chuỗi mới ở đây: chuỗi nào chưa có parser đã xác minh thì chưa được nạp file.
const CHAINS = ["WinCommerce", "Central Retail", "LOTTE", "Emart", "Saigon Co.op"];

// Nhãn row_kind (tiếng Việt, đúng options DocType) → màu badge.
// 'Ghi giảm' tô đỏ vì nó làm GIẢM tiền về; 'Khác' tô xám vì máy KHÔNG hiểu loại
// dòng đó — xám là lời mời người xem phân loại tay, không phải "bình thường".
const KIND_TONE = {
  "Thanh toán": "green",
  "Chiết khấu": "yellow",
  "Phí": "yellow",
  "Ghi giảm": "red",
  "Khác": "gray",
};

const STATUS_TONE = { "Nháp": "gray", "Đã đối chiếu": "yellow", "Đã ghi nhận": "green" };

const CONF_TONE = { "Chắc chắn": "green", "Cần review": "yellow", "Không khớp": "red" };

const todayISO = () => new Date().toISOString().slice(0, 10);
const monthsAgo = (n) => { const d = new Date(); d.setMonth(d.getMonth() - n); return d.toISOString().slice(0, 10); };

export async function render({ container, query }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);

  const state = {
    tab: TABS.some((t) => t.key === query?.tab) ? query.tab : "thanh-toan",
    bucket: INV_BUCKETS.some((b) => b.key === query?.bucket) ? query.bucket : "chua_thanh_toan",
    from: query?.from || monthsAgo(3),
    to: query?.to || todayISO(),
    chain: query?.chain || "",
    // Lọc theo KHÁCH, dùng chung cho cả ba tab: kế toán MT đối chiếu trên đầu
    // từng pháp nhân chứ không phải trên cả kênh.
    customer: query?.customer || "",
    // Tab 3 xem theo "khach" (chi tiết từng khách) hay "chuoi" (nhìn tổng).
    // Mặc định theo khách vì đó mới là cái đi đòi nợ được.
    chainView: query?.view === "chuoi" ? "chuoi" : "khach",
    search: "",
    page: 1,
    // Chốt tay liên kết đi qua guard_manager ở backend. Hiện nút cho người không
    // có quyền chỉ tạo ra một cú bấm để nhận lỗi — nên ẩn hẳn.
    canManage: false,
  };

  let ov;
  try {
    ov = await api.mtOverview({ from_date: state.from, to_date: state.to });
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  state.canManage = !!ov.can_import;   // backend: is_chief()
  setHTML(container, shell(state, ov));
  bind(container, state, ov);
  await loadTab(container, state);
}

// ── Khung màn hình ─────────────────────────────────────────────────────────
function shell(state, ov) {
  const b = ov.buckets || {};
  const chua = b.chua_thanh_toan || {};
  const da = b.da_thanh_toan || {};
  const ck = b.chiet_khau || {};
  const debt = ov.debt || {};
  const att = ov.attention || {};
  const unmatched = att.unmatched_payment_lines || {};

  return html`
    <div class="kt-view-head">
      <div>
        <div class="kt-view-title"><i class="fas fa-store"></i> Công nợ MT</div>
        <div class="kt-sub">
          Kênh siêu thị hiện đại — đối chiếu hóa đơn bán ra với bảng kê thanh toán của chuỗi.
        </div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input type="date" class="kt-input kt-input--sm" id="mt-from" value="${state.from}">
        <span class="kt-sub">→</span>
        <input type="date" class="kt-input kt-input--sm" id="mt-to" value="${state.to}">
        ${ov.can_import
          ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="mt-import"><i class="fas fa-file-import"></i> Nạp bảng kê</button>`
          : ""}
      </div>
    </div>

    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
      <div class="kt-card-body kt-sub">
        <b>Số ở màn hình này tính từ BẢNG KÊ CỦA CHUỖI, không phải số dư sổ cái.</b>
        Hệ thống cố ý <b>không</b> tự tạo Payment Entry / Journal Entry từ file nhập —
        nó chỉ ghi nhận và đánh dấu. Sau khi soi xong, kế toán tự lập chứng từ hạch toán.
        Vì vậy <code>outstanding_amount</code> của ERPNext vẫn chưa trừ tiền chuỗi đã trả.
      </div>
    </div>

    ${unmatched.count
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)">
          <div class="kt-card-body">
            <div style="font-weight:600;color:var(--kt-danger)">
              <i class="fas fa-triangle-exclamation"></i>
              ${unmatched.count} dòng thanh toán chưa nối được hóa đơn — ${formatVND(unmatched.amount)}
            </div>
            <div class="kt-sub" style="margin-top:6px">
              Tiền đã về theo bảng kê nhưng máy không biết của hóa đơn nào. Mở bảng kê trên Desk
              (<a target="_blank" href="/desk/mt-payment-advice">MT Payment Advice</a>) để xem, hoặc chốt tay
              liên kết ngay trên dòng thanh toán ở tab "Quản lý thanh toán".
            </div>
          </div></div>`
      : ""}

    ${att.need_review_lines
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)">
          <div class="kt-card-body kt-sub">
            <b>${att.need_review_lines} dòng đang ở mức "Cần review".</b>
            Máy khớp được nhưng không chắc — thường là Emart (chuỗi không cấp ký hiệu hóa đơn,
            chỉ khớp được bằng số + ngày + tiền) hoặc dòng có nhiều hóa đơn ứng viên.
            Người phải xác nhận, đừng coi là đã khớp.
          </div></div>`
      : ""}

    <div class="kt-stats kt-mb">
      <div class="kt-stat kt-row-link" data-goto="chua_thanh_toan" style="cursor:pointer">
        <div class="kt-stat-label"><i class="fas fa-hourglass-half"></i> Hóa đơn chưa thu đủ</div>
        <div class="kt-stat-value warn">${chua.count || 0}</div>
        <div class="kt-stat-sub">còn thiếu ${formatVNDShort(chua.remaining)}</div>
      </div>
      <div class="kt-stat kt-row-link" data-goto="da_thanh_toan" style="cursor:pointer">
        <div class="kt-stat-label"><i class="fas fa-circle-check"></i> Hóa đơn đã thu đủ</div>
        <div class="kt-stat-value">${da.count || 0}</div>
        <div class="kt-stat-sub">${formatVNDShort(da.collected)}</div>
      </div>
      <div class="kt-stat kt-row-link" data-goto="chiet_khau" style="cursor:pointer">
        <div class="kt-stat-label"><i class="fas fa-percent"></i> Chuỗi trừ lại</div>
        <div class="kt-stat-value danger">${ck.count || 0}</div>
        <div class="kt-stat-sub">${formatVNDShort(ck.amount)} — chiết khấu · phí · ghi giảm</div>
      </div>
      <div class="kt-stat">
        <div class="kt-stat-label"><i class="fas fa-file-invoice-dollar"></i> Công nợ chuỗi (đến ${formatDate(debt.as_of)})</div>
        <div class="kt-stat-value ${(debt.estimate || 0) > 0 ? "warn" : ""}">${formatVNDShort(debt.estimate)}</div>
        <div class="kt-stat-sub">${debt.unpaid_count || 0} hóa đơn chưa thu đủ · đã trừ ${formatVNDShort(debt.credit_notes)} trả hàng</div>
      </div>
    </div>

    <div class="kt-segment kt-mb" id="mt-tabs">
      ${TABS.map((t) => html`<button data-tab="${t.key}" class="${state.tab === t.key ? "is-active" : ""}">${t.label}</button>`)}
    </div>

    <div class="kt-card kt-mb"><div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <i class="fas fa-circle-info kt-sub"></i>
      <span class="kt-sub" id="mt-hint">${TABS.find((t) => t.key === state.tab).hint}</span>
      <input class="kt-input kt-input--sm" id="mt-search" placeholder="Tìm số hóa đơn / khách / siêu thị…"
        style="margin-left:auto;min-width:240px${state.tab === "chuoi" ? ";display:none" : ""}">
    </div></div>

    <div id="mt-body"></div>
  `;
}

function bind(container, state) {
  const syncHash = () => {
    const url = `#/cong-no-mt?tab=${state.tab}&bucket=${state.bucket}&from=${state.from}&to=${state.to}`
      + (state.chain ? `&chain=${q(state.chain)}` : "");
    history.replaceState(null, "", url);
  };

  container.querySelector("#mt-tabs").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-tab]");
    if (!btn) return;
    state.tab = btn.dataset.tab;
    state.page = 1;   // tab khác, số trang cũ vô nghĩa
    container.querySelectorAll("#mt-tabs button").forEach((x) => x.classList.toggle("is-active", x === btn));
    container.querySelector("#mt-hint").textContent = TABS.find((t) => t.key === state.tab).hint;
    // Tab "công nợ chuỗi" là bảng tổng hợp, không có ô tìm kiếm nào áp dụng được.
    const s = container.querySelector("#mt-search");
    if (s) s.style.display = state.tab === "chuoi" ? "none" : "";
    syncHash();
    loadTab(container, state);
  });

  container.querySelectorAll("[data-goto]").forEach((el) => {
    el.addEventListener("click", () => {
      const goto = el.dataset.goto;
      state.page = 1;
      if (goto === "chiet_khau") {
        state.tab = "chiet-khau";
      } else {
        state.tab = "thanh-toan";
        state.bucket = goto;
      }
      const btn = container.querySelector(`#mt-tabs button[data-tab="${state.tab}"]`);
      container.querySelectorAll("#mt-tabs button").forEach((x) => x.classList.toggle("is-active", x === btn));
      container.querySelector("#mt-hint").textContent = TABS.find((t) => t.key === state.tab).hint;
      syncHash();
      loadTab(container, state);
    });
  });

  const from = container.querySelector("#mt-from");
  const to = container.querySelector("#mt-to");
  // Đổi khoảng ngày thì mọi thẻ tổng ở đầu màn hình cũng phải tính lại → nạp lại
  // cả view qua hash, đừng chỉ nạp lại bảng bên dưới (số đầu trang sẽ nói dối).
  const onDate = () => {
    state.from = from.value;
    state.to = to.value;
    location.hash = `/cong-no-mt?tab=${state.tab}&bucket=${state.bucket}&from=${state.from}&to=${state.to}`;
  };
  from.addEventListener("change", onDate);
  to.addEventListener("change", onDate);

  let timer = null;
  container.querySelector("#mt-search").addEventListener("input", (e) => {
    state.search = e.target.value.trim();
    state.page = 1;   // lọc lại phải về trang đầu, không thì rơi vào trang trống
    clearTimeout(timer);
    timer = setTimeout(() => loadTab(container, state), 350);
  });

  const imp = container.querySelector("#mt-import");
  if (imp) imp.addEventListener("click", () => pickFile(container, state));
}

// ── Nạp nội dung theo tab ──────────────────────────────────────────────────
async function loadTab(container, state) {
  const body = container.querySelector("#mt-body");
  if (!body) return;
  setHTML(body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);

  if (state.tab === "chuoi") return loadChains(container, state);

  const bucket = state.tab === "chiet-khau" ? "chiet_khau" : state.bucket;
  let res;
  try {
    res = await api.mtInvoices(bucket, {
      from_date: state.from, to_date: state.to, search: state.search,
      page: state.page, chain: state.tab === "chiet-khau" ? (state.chain || undefined) : undefined,
      customer: state.customer || undefined,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  // Đổi bộ lọc có thể làm trang đang xem rơi ra ngoài phạm vi. Hiện trang trống
  // rồi báo "không có dòng nào" là nói dối người dùng.
  if (!res.rows.length && (res.total || 0) > 0 && state.page > 1) {
    state.page = res.pages || 1;
    return loadTab(container, state);
  }

  if (state.tab === "chiet-khau") {
    setHTML(body, html`${customerFilterBar(state)}${deductionTable(state, res)}`);
    bindChainFilter(container, state);
  } else {
    setHTML(body, html`${customerFilterBar(state)}${invoiceTable(state, res)}`);
    bindBuckets(container, state);
    bindRelink(container, state);
  }
  bindCustomerFilter(container, state);
  bindPager(container, state);
}

// ── Chia trang ─────────────────────────────────────────────────────────────
// Tổng ở đây là tổng THẬT của cả rổ (backend đếm riêng bằng COUNT), không phải
// số dòng đang hiển thị — đọc nhầm hai con số này là đếm sót.
function pager(res, unit) {
  const total = res.total || 0;
  const pages = res.pages || 1;
  const page = res.page || 1;
  const from = (page - 1) * (res.page_size || 20) + 1;
  const to = from + (res.rows.length - 1);

  const btn = (p, label, disabled, active) => html`<button
    class="kt-btn kt-btn--sm ${active ? "" : "kt-btn--outline"}"
    data-page="${p}" ${disabled ? "disabled" : ""}>${label}</button>`;

  // Cửa sổ 5 trang quanh trang hiện tại — kênh MT có hàng nghìn hóa đơn/tháng,
  // in hết số trang là vỡ hàng.
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
      const body = container.querySelector("#mt-body");
      if (body) body.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

// ── Tab 1: Quản lý thanh toán ──────────────────────────────────────────────
function invoiceTable(state, res) {
  const tol = res.tolerance || 0;
  return html`
    <div class="kt-segment kt-mb" id="mt-buckets">
      ${INV_BUCKETS.map((x) => html`<button data-bucket="${x.key}"
        class="${state.bucket === x.key ? "is-active" : ""}">${x.label}</button>`)}
    </div>

    <div class="kt-card"><div class="kt-card-body">
      ${!res.rows.length
        ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có hóa đơn nào trong rổ này.</p></div>`
        : html`<div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Hóa đơn</th><th>Ngày</th><th>Khách</th><th>Ký hiệu · Số HĐ</th>
              <th class="num">Tổng tiền</th><th class="num">Đã nhận</th><th class="num">Còn lại</th>
              <th>Bảng kê đã trả</th>
            </tr></thead>
            <tbody>${res.rows.map((r) => invoiceRow(r, tol, state.canManage))}</tbody>
          </table></div>
          ${pager(res, "hóa đơn")}`}
    </div></div>`;
}

function invoiceRow(r, tol, canManage) {
  const total = Math.abs(r.grand_total || 0);
  const paid = r.paid || 0;
  const remaining = r.remaining || 0;
  // "Đã trả đủ" chỉ khi phần còn thiếu nằm trong sai số 1 đồng do backend công bố.
  // Nới rộng sai số ở giao diện là tự tay dán nhãn "đủ" cho hóa đơn còn thiếu tiền.
  const done = paid > 0 && remaining <= tol;
  const over = paid - total > tol;

  return html`<tr>
    <td><a target="_blank" href="/desk/sales-invoice/${q(r.name)}">${r.name}</a>
      ${r.is_return ? html` <span class="kt-badge kt-badge--yellow">trả hàng</span>` : ""}</td>
    <td>${formatDate(r.posting_date)}</td>
    <td class="kt-cell-wrap">${r.customer_name || r.customer}</td>
    <td>${r.inv_series || "—"}${r.inv_no ? html` · <b>${r.inv_no}</b>` : ""}</td>
    <td class="num">${formatVND(total)}</td>
    <td class="num">${paid ? formatVND(paid) : html`<span class="kt-sub">—</span>`}
      ${over ? html`<div><span class="kt-badge kt-badge--red">trả vượt</span></div>` : ""}</td>
    <td class="num">${done
      ? html`<span class="kt-badge kt-badge--green">đủ</span>`
      : html`<b>${formatVND(remaining)}</b>`}</td>
    <td>${paymentCell(r, canManage)}</td>
  </tr>`;
}

// Một hóa đơn có thể được chuỗi trả LÀM NHIỀU LẦN (Co.op tách 8 kỳ trong một file,
// LOTTE 2 ngày thanh toán). Liệt kê từng lần chứ không gộp — gộp là mất dấu vết
// và kế toán không biết tiền về từ bảng kê nào.
function paymentCell(r, canManage) {
  const lines = r.payments || [];
  if (!lines.length) return html`<span class="kt-sub">chưa có bảng kê nào</span>`;
  return html`<div style="display:flex;flex-direction:column;gap:4px">
    ${lines.map((ln) => html`<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
      <span class="kt-badge kt-badge--${STATUS_TONE[ln.status] || "gray"}">${ln.chain || "—"}</span>
      <span class="kt-sub">${formatDate(ln.payment_date)}${ln.advice_no ? " · " + ln.advice_no : ""}</span>
      <b>${formatVND(Math.abs(ln.total_amount || 0))}</b>
      ${ln.match_confidence && ln.match_confidence !== "Chắc chắn"
        ? html`<span class="kt-badge kt-badge--${CONF_TONE[ln.match_confidence] || "gray"}">${ln.match_confidence}</span>`
        : ""}
      <a class="kt-btn-icon" target="_blank" title="Mở bảng kê"
        href="/desk/mt-payment-advice/${q(ln.advice)}"><i class="fas fa-up-right-from-square"></i></a>
      ${canManage
        ? html`<button class="kt-btn-icon" data-relink="${ln.line}" data-si="${r.name}"
            title="Chốt tay / gỡ liên kết dòng này"><i class="fas fa-link"></i></button>`
        : ""}
    </div>`)}
  </div>`;
}

function bindBuckets(container, state) {
  container.querySelectorAll("#mt-buckets button[data-bucket]").forEach((b) => {
    b.addEventListener("click", () => {
      if (state.bucket === b.dataset.bucket) return;
      state.bucket = b.dataset.bucket;
      state.page = 1;
      loadTab(container, state);
    });
  });
}

// ── Tab 2: Quản lý chiết khấu (dòng khấu trừ, KHÔNG phải hóa đơn) ───────────
function deductionTable(state, res) {
  return html`
    <div class="kt-card kt-mb"><div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <label class="kt-label" style="margin:0">Chuỗi</label>
      <select class="kt-input kt-input--sm" id="mt-chain">
        <option value="">Tất cả chuỗi</option>
        ${CHAINS.map((c) => html`<option value="${c}" ${state.chain === c ? "selected" : ""}>${c}</option>`)}
      </select>
      <span class="kt-sub">
        Đây là các khoản chuỗi <b>trừ lại</b> khi thanh toán. Chúng KHÔNG được nối vào hóa đơn bán ra —
        dòng chiết khấu của Central Retail có mang ký hiệu hóa đơn của chính mình nhưng không phải
        thanh toán cho hóa đơn đó.
      </span>
    </div></div>

    <div class="kt-card"><div class="kt-card-body">
      ${!res.rows.length
        ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có khoản khấu trừ nào trong khoảng này.</p></div>`
        : html`<div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Ngày TT</th><th>Chuỗi</th><th>Loại</th><th>Siêu thị</th>
              <th>Số chứng từ</th><th>Diễn giải</th>
              <th class="num">Trước thuế</th><th class="num">Thuế</th><th class="num">Số tiền</th>
              <th>Bảng kê</th>
            </tr></thead>
            <tbody>${res.rows.map((r) => html`<tr>
              <td>${formatDate(r.payment_date)}</td>
              <td>${r.chain || "—"}</td>
              <td><span class="kt-badge kt-badge--${KIND_TONE[r.row_kind] || "gray"}">${r.row_kind || "—"}</span></td>
              <td class="kt-cell-wrap">${r.store_name || r.store_code || "—"}</td>
              <td>${r.doc_no || "—"}</td>
              <td class="kt-cell-wrap">${r.description || "—"}</td>
              <td class="num">${r.amount_before_vat == null ? html`<span class="kt-sub">—</span>` : formatVND(r.amount_before_vat)}</td>
              <td class="num">${r.vat_amount == null ? html`<span class="kt-sub">—</span>` : formatVND(r.vat_amount)}</td>
              <td class="num"><b>${formatVND(r.total_amount)}</b></td>
              <td><a target="_blank" href="/desk/mt-payment-advice/${q(r.advice)}">${r.advice_no || r.advice}</a>
                ${r.status ? html` <span class="kt-badge kt-badge--${STATUS_TONE[r.status] || "gray"}">${r.status}</span>` : ""}</td>
            </tr>`)}</tbody>
          </table></div>
          <div class="kt-sub" style="margin-top:8px">
            Cột "Trước thuế" và "Thuế" để trống khi file của chuỗi chỉ có MỘT cột tiền —
            hệ thống không chia 1,1 hay 1,08 để suy ra, vì đó là bịa số.
          </div>
          ${pager(res, "dòng khấu trừ")}`}
    </div></div>`;
}

function bindChainFilter(container, state) {
  const sel = container.querySelector("#mt-chain");
  if (!sel) return;
  sel.addEventListener("change", () => {
    state.chain = sel.value;
    state.page = 1;
    loadTab(container, state);
  });
}

// ── Tab 3: Công nợ chung của chuỗi ─────────────────────────────────────────
async function loadChains(container, state) {
  if (state.chainView === "khach") return loadCustomers(container, state);
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtChainSummary({ from_date: state.from, to_date: state.to });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const chains = res.chains || [];
  const t = res.totals || {};

  setHTML(body, html`
    ${(res.ambiguous_customers || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">
            <i class="fas fa-triangle-exclamation"></i>
            ${res.ambiguous_customers.length} khách hàng đang bị gán cho NHIỀU chuỗi
          </b>
          <div class="kt-sub" style="margin-top:6px">
            Hệ thống không tự chọn giùm — công nợ của những khách này rơi vào nhóm "Chưa gán chuỗi".
            Sửa trường Khách hàng trên các bảng kê tương ứng cho thống nhất.
          </div>
          <div class="kt-table-wrap" style="margin-top:8px"><table class="kt-table">
            <tbody>${res.ambiguous_customers.map((x) => html`<tr>
              <td><a target="_blank" href="/desk/customer/${q(x.customer)}">${x.customer}</a></td>
              <td>${(x.chains || []).map((c) => html`<span class="kt-badge kt-badge--yellow">${c}</span> `)}</td>
            </tr>`)}</tbody>
          </table></div>
        </div></div>`
      : ""}

    <div class="kt-card"><div class="kt-card-body">
      ${!chains.length
        ? html`<div class="kt-empty"><i class="fas fa-store-slash"></i><p>Chưa có phát sinh nào của kênh MT trong khoảng này.</p></div>`
        : html`<div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Chuỗi</th><th class="num">Hóa đơn</th>
              <th class="num">Đã xuất</th><th class="num">Trả hàng</th>
              <th class="num">Đã thu</th><th class="num">Còn lại</th>
              <th class="num">Tiền hàng trong kỳ</th><th class="num">Chiết khấu</th>
              <th class="num">Phí</th><th class="num">Khác</th>
              <th class="num">Thực nhận</th><th class="num">Dòng bảng kê</th>
            </tr></thead>
            <tbody>
              ${chains.map((c) => html`<tr>
                <td><b>${c.chain}</b>
                  ${(c.customers || []).length
                    ? html`<div class="kt-sub">${c.customers.length} khách hàng</div>`
                    : ""}</td>
                <td class="num">${c.invoice_count}${c.unpaid_count
                  ? html` <span class="kt-badge kt-badge--yellow">${c.unpaid_count} chưa đủ</span>`
                  : ""}</td>
                <td class="num">${formatVND(c.invoiced)}</td>
                <td class="num">${c.returns ? formatVND(c.returns) : html`<span class="kt-sub">—</span>`}</td>
                <td class="num">${formatVND(c.collected)}</td>
                <td class="num"><b>${formatVND(c.outstanding)}</b></td>
                <td class="num">${formatVND(c.received_in_period)}</td>
                <td class="num">${formatVND(c.discount)}</td>
                <td class="num">${formatVND(c.fee)}</td>
                <td class="num">${formatVND(c.other)}</td>
                <td class="num"><b>${formatVND(c.net_received_est)}</b></td>
                <td class="num">${c.advice_lines}</td>
              </tr>`)}
              <tr>
                <td><b>TỔNG</b></td>
                <td class="num"><b>${t.invoice_count || 0}</b></td>
                <td class="num"><b>${formatVND(t.invoiced)}</b></td>
                <td class="num"><b>${formatVND(t.returns)}</b></td>
                <td class="num"><b>${formatVND(t.collected)}</b></td>
                <td class="num"><b>${formatVND(t.outstanding)}</b></td>
                <td class="num"><b>${formatVND(t.received_in_period)}</b></td>
                <td class="num"><b>${formatVND(t.discount)}</b></td>
                <td class="num"><b>${formatVND(t.fee)}</b></td>
                <td class="num"><b>${formatVND(t.other)}</b></td>
                <td class="num"><b>${formatVND(t.net_received_est)}</b></td>
                <td class="num"><b>${t.advice_lines || 0}</b></td>
              </tr>
            </tbody>
          </table></div>
          <div class="kt-sub" style="margin-top:8px">
            <b>Hai trục thời gian khác nhau, cố ý không gộp:</b>
            "Đã xuất / Đã thu / Còn lại" tính theo hóa đơn <b>ghi sổ trong kỳ</b> (tiền của chúng thu lúc nào cũng tính) —
            đó là công nợ. Bốn cột sau tính theo <b>ngày thanh toán của bảng kê</b> — đó là dòng tiền.
            Cộng hai nhóm vào nhau sẽ ra con số không có nghĩa kế toán nào.
            <br><b>"Tiền hàng trong kỳ" là tổng GỘP các dòng hóa đơn, chưa trừ gì.</b>
            Cột <b>"Thực nhận"</b> mới là số xấp xỉ khớp được với sao kê ngân hàng:
            tiền hàng trừ chiết khấu, phí và các khoản ghi giảm. Đọc nhầm hai cột này là
            lệch đúng bằng phần chuỗi đã trừ lại (với Co.op tháng mẫu là hơn 2,2 tỉ đồng).
          </div>`}
    </div></div>`);
}

// ── Chốt tay liên kết dòng bảng kê ↔ hóa đơn ───────────────────────────────
function bindRelink(container, state) {
  container.querySelectorAll("button[data-relink]").forEach((btn) => {
    btn.addEventListener("click", () => openRelinkModal(container, state, btn.dataset.relink, btn.dataset.si));
  });
}

function openRelinkModal(container, state, line, currentSI) {
  const modal = openModal({
    title: "Chốt tay liên kết dòng bảng kê",
    icon: "fa-link",
    maxWidth: 760,
    body: html`
      <p class="kt-sub">
        Dòng này đang nối với <b>${currentSI || "(chưa nối)"}</b>.
        Chỉ dòng loại <b>Thanh toán</b> mới được nối hóa đơn — dòng chiết khấu / phí bị backend chặn.
        Việc chốt tay chỉ đổi liên kết, <b>không</b> sinh chứng từ kế toán nào.
      </p>
      <label class="kt-label">Tìm hóa đơn ERPNext</label>
      <input class="kt-input" id="mr-search" placeholder="Số hóa đơn hoặc tên khách…" autocomplete="off">
      <div id="mr-results" style="max-height:260px;overflow:auto;margin-top:8px"></div>
      <label class="kt-label" style="margin-top:12px">Ghi chú (lý do chốt tay)</label>
      <input class="kt-input" id="mr-note" placeholder="vd: khớp theo bảng đối chiếu chuỗi ngày…">
      <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:12px">
        <button class="kt-btn kt-btn--outline" id="mr-unlink"><i class="fas fa-link-slash"></i> Gỡ liên kết</button>
      </div>
    `,
  });

  const note = () => modal.body.querySelector("#mr-note").value.trim();

  const apply = async (si, btn) => {
    if (btn) btn.disabled = true;
    try {
      await api.mtRelinkLine(line, si || null, note());
      toast(si ? "Đã chốt liên kết" : "Đã gỡ liên kết", "success");
      modal.close();
      loadTab(container, state);
    } catch (e) {
      toast(e.message, "error");
      if (btn) btn.disabled = false;
    }
  };

  modal.body.querySelector("#mr-unlink").addEventListener("click", (e) => apply(null, e.currentTarget));

  const box = modal.body.querySelector("#mr-results");
  let timer = null;
  modal.body.querySelector("#mr-search").addEventListener("input", (e) => {
    const txt = e.target.value.trim();
    clearTimeout(timer);
    if (txt.length < 2) { setHTML(box, ""); return; }
    timer = setTimeout(async () => {
      setHTML(box, html`<div class="kt-sub">Đang tìm…</div>`);
      try {
        // Dùng chung API tìm hóa đơn của luồng MISA: cùng một tập Sales Invoice đã
        // ghi sổ, và kế toán MT có quyền gọi (guard_sales_any).
        const rows = await api.vatSearchInvoices(txt);
        if (!rows.length) { setHTML(box, html`<div class="kt-sub">Không tìm thấy.</div>`); return; }
        setHTML(box, html`<table class="kt-table"><tbody>${rows.map((r) => html`<tr>
          <td>${r.name}</td>
          <td>${formatDate(r.posting_date)}</td>
          <td class="kt-cell-wrap">${r.customer_name}</td>
          <td class="num">${formatVND(r.grand_total)}</td>
          <td>${r.inv_no ? html`<span class="kt-badge kt-badge--gray">HĐ ${r.inv_no}</span>` : ""}</td>
          <td class="num"><button class="kt-btn kt-btn--sm" data-pick="${r.name}">Chọn</button></td>
        </tr>`)}</tbody></table>`);
        box.querySelectorAll("button[data-pick]").forEach((b) => {
          b.addEventListener("click", () => apply(b.dataset.pick, b));
        });
      } catch (err) { setHTML(box, html`<div class="kt-sub">${err.message}</div>`); }
    }, 350);
  });
}

// ── Nạp bảng kê thanh toán của chuỗi ───────────────────────────────────────
// LUÔN xem trước rồi mới nạp. Năm chuỗi năm khuôn file khác nhau, ba quy ước dấu
// khác nhau; nạp mù là ghi nhận sai loại dòng hoặc nhân đôi tiền mà không ai thấy.
function pickFile(container, state) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".xlsx,.xls";
  input.onchange = () => {
    const file = input.files && input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => openAdviceModal(container, state, reader.result, file.name);
    reader.readAsDataURL(file);
  };
  input.click();
}

function openAdviceModal(container, state, content, filename) {
  const modal = openModal({
    title: "Nạp bảng kê thanh toán — " + filename,
    icon: "fa-file-import",
    maxWidth: 1000,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  // chain rỗng = để hệ thống tự nhận. Không nhận ra thì backend THROW chứ không
  // đoán bừa — chọn nhầm parser là đọc sai cột tiền mà kết quả vẫn trông hợp lý.
  showAdvicePreview(container, state, modal, content, filename, "");
}

async function showAdvicePreview(container, state, modal, content, filename, chain) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);

  let p;
  try {
    p = await api.mtAdvicePreview({ content, filename, chain: chain || undefined });
  } catch (e) {
    // Thường gặp nhất: không nhận ra chuỗi. Cho chọn tay rồi thử lại, KHÔNG tự đoán.
    setHTML(modal.body, html`
      <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
        <b style="color:var(--kt-danger)">Không đọc được file</b>
        <div class="kt-sub" style="margin-top:6px;white-space:pre-wrap">${e.message}</div>
      </div></div>
      <div style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
        <div>
          <label class="kt-label">Chọn chuỗi rồi thử lại</label>
          <select class="kt-input kt-input--sm" id="ma-chain">
            <option value="">— tự nhận —</option>
            ${CHAINS.map((c) => html`<option value="${c}" ${chain === c ? "selected" : ""}>${c}</option>`)}
          </select>
        </div>
        <button class="kt-btn kt-btn--outline" id="ma-retry"><i class="fas fa-rotate"></i> Đọc lại</button>
      </div>`);
    modal.body.querySelector("#ma-retry").addEventListener("click", () => {
      showAdvicePreview(container, state, modal, content, filename,
        modal.body.querySelector("#ma-chain").value);
    });
    return;
  }

  const advices = p.advices || [];
  const g = p.grand_totals || {};
  const dup = p.duplicates || [];
  const problems = advices.flatMap((a) => (a.problems || []).map((x) => ({ ...x, _adv: a })));
  const badDeclared = advices.filter((a) => a.declared_diff != null && Math.abs(a.declared_diff) > 3);
  const totalLines = advices.reduce((s, a) => s + (a.line_count || 0), 0);
  const totalMatched = advices.reduce((s, a) => s + (a.matched || 0), 0);
  const totalPayLines = advices.reduce((s, a) => s + (a.payment_lines || 0), 0);
  const totalReview = advices.reduce((s, a) => s + (a.need_review || 0), 0);
  const totalUnknown = advices.reduce((s, a) => s + (a.unknown_kind || 0), 0);

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <span>Chuỗi nhận ra: <b>${p.chain}</b></span>
      <span class="kt-badge kt-badge--gray">${p.advice_count} kỳ thanh toán trong file</span>
      ${p.skipped_rows ? html`<span class="kt-badge kt-badge--gray">${p.skipped_rows} dòng rác đã loại</span>` : ""}
      <span class="kt-sub" style="margin-left:auto">
        Một file có thể chứa NHIỀU kỳ (Co.op 8 kỳ, LOTTE 2 ngày) → mỗi kỳ thành một bản ghi riêng.
      </span>
    </div></div>

    ${dup.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)"><i class="fas fa-copy"></i> Bảng kê này đã được nạp rồi</b>
          <div class="kt-sub" style="margin-top:6px">
            ${dup.join(", ")} — nạp lại là <b>cộng đôi</b> tiền đã thu và mọi hóa đơn của kỳ đó
            lập tức trông như đã trả gấp đôi. Muốn nạp lại thì xóa bản cũ trước.
          </div>
        </div></div>`
      : ""}

    ${badDeclared.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)"><i class="fas fa-scale-unbalanced"></i>
            ${badDeclared.length} kỳ lệch số kiểm tra của chính file</b>
          <div class="kt-sub" style="margin-top:6px">
            Số kiểm tra do chuỗi in trong file là chân lý. Lệch ±1..3đ là do chuỗi làm tròn ở cấp
            dòng và cấp nhóm độc lập nhau (đã đo trên file Co.op thật) — chấp nhận được.
            Lệch lớn hơn nghĩa là đọc sót hoặc đọc thừa dòng tiền: <b>đừng nạp</b> cho tới khi làm rõ.
          </div>
        </div></div>`
      : ""}

    ${(p.warnings || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          <b>Cảnh báo từ tầng đọc file</b>
          <ul class="kt-sub" style="margin:6px 0 0 18px">
            ${p.warnings.map((w) => html`<li>${w}</li>`)}
          </ul>
        </div></div>`
      : ""}

    ${riskBlocks(advices)}

    <div class="kt-stats kt-mb">
      <div class="kt-stat"><div class="kt-stat-label">Dòng đọc được</div>
        <div class="kt-stat-value">${totalLines}</div>
        <div class="kt-stat-sub">${totalPayLines} dòng thanh toán</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Khớp được hóa đơn</div>
        <div class="kt-stat-value ${totalMatched < totalPayLines ? "warn" : ""}">${totalMatched}/${totalPayLines}</div>
        <div class="kt-stat-sub">${totalReview} dòng cần review</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Tổng thanh toán</div>
        <div class="kt-stat-value">${formatVNDShort(g.total_payment)}</div>
        <div class="kt-stat-sub">${formatVND(g.total_payment)}</div></div>
      <div class="kt-stat"><div class="kt-stat-label">Chuỗi trừ lại</div>
        <div class="kt-stat-value">${formatVNDShort((g.total_discount || 0) + (g.total_fee || 0) + (g.total_other || 0))}</div>
        <div class="kt-stat-sub">CK ${formatVNDShort(g.total_discount)} · phí ${formatVNDShort(g.total_fee)} · khác ${formatVNDShort(g.total_other)}</div></div>
    </div>

    ${totalUnknown
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body kt-sub">
          <b>${totalUnknown} dòng máy không hiểu loại</b> — chúng được xếp vào "Khác" chứ không bị bỏ im lặng
          (bỏ im lặng là mất tiền khỏi tổng mà không ai thấy). Sau khi nạp phải phân loại tay.
        </div></div>`
      : ""}

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="font-weight:600;margin-bottom:6px">Từng kỳ thanh toán trong file — kiểm giúp trước khi nạp</div>
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr>
          <th>Ngày TT</th><th>Số chứng từ</th><th>Nguồn</th>
          <th class="num">Dòng</th><th class="num">Khớp</th><th class="num">Chưa khớp</th><th class="num">Cần review</th>
          <th class="num">Thanh toán</th><th class="num">Số kiểm tra</th><th class="num">Lệch</th><th>Trạng thái</th>
        </tr></thead>
        <tbody>${advices.map((a) => html`<tr>
          <td>${formatDate(a.payment_date)}</td>
          <td>${a.advice_no || "—"}</td>
          <td class="kt-sub">${a.source_sheet || "—"}</td>
          <td class="num">${a.line_count}</td>
          <td class="num">${a.matched}</td>
          <td class="num ${a.unmatched ? "warn" : ""}">${a.unmatched}</td>
          <td class="num ${a.need_review ? "warn" : ""}">${a.need_review}</td>
          <td class="num">${formatVND(a.totals ? a.totals.total_payment : 0)}</td>
          <td class="num">${a.declared_total_payment == null
            ? html`<span class="kt-sub">file không có</span>`
            : formatVND(a.declared_total_payment)}</td>
          <td class="num">${a.declared_diff == null
            ? html`<span class="kt-sub">—</span>`
            : (Math.abs(a.declared_diff) <= 3
                ? html`<span class="kt-badge kt-badge--green">${formatVND(a.declared_diff)}</span>`
                : html`<span class="kt-badge kt-badge--red">${formatVND(a.declared_diff)}</span>`)}</td>
          <td>${a.existing
            ? html`<span class="kt-badge kt-badge--red">đã nạp: ${a.existing}</span>`
            : html`<span class="kt-badge kt-badge--green">mới</span>`}
            ${(a.repeated_invoices || []).length
              ? html` <span class="kt-badge kt-badge--yellow">${a.repeated_invoices.length} HĐ bị nối nhiều dòng</span>`
              : ""}</td>
        </tr>`)}</tbody>
      </table></div>
    </div></div>

    ${problems.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          <b>${problems.length} dòng thanh toán chưa nối được hóa đơn</b>
          <div class="kt-sub" style="margin:6px 0">
            Vẫn nạp được — tiền được ghi nhận, chỉ là chưa biết của hóa đơn nào. Sau khi nạp thì
            chốt tay ở tab "Quản lý thanh toán". Máy KHÔNG nối bừa: nối nhầm là đánh dấu đã trả
            cho hóa đơn của khách khác.
          </div>
          <details><summary class="kt-sub" style="cursor:pointer">Xem ${Math.min(problems.length, 50)} dòng đầu</summary>
            <div class="kt-table-wrap" style="max-height:260px;overflow:auto;margin-top:6px"><table class="kt-table">
              <thead><tr><th>Dòng</th><th>Ký hiệu</th><th>Số HĐ</th><th>Ngày HĐ</th>
                <th>Siêu thị</th><th class="num">Số tiền</th><th>Lý do</th></tr></thead>
              <tbody>${problems.slice(0, 50).map((x) => html`<tr>
                <td class="kt-sub">${x.source_row || "—"}</td>
                <td>${x.inv_series || "—"}</td>
                <td>${x.inv_no || "—"}</td>
                <td>${formatDate(x.inv_date)}</td>
                <td class="kt-cell-wrap">${x.store_name || x.store_code || "—"}</td>
                <td class="num">${formatVND(x.total_amount)}</td>
                <td><code>${x.match_method || "—"}</code></td>
              </tr>`)}</tbody>
            </table></div>
          </details>
        </div></div>`
      : ""}

    ${customerBlock(advices)}

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <label class="kt-label">Ghi đè khách hàng cho MỌI kỳ (để trống = dùng kết quả nhận diện ở trên)</label>
      <input class="kt-input" id="ma-customer" placeholder="Mã Customer trong ERPNext, vd CUS-0001">
      <div class="kt-sub" style="margin-top:6px">
        Chỉ điền khi muốn <b>đè</b> kết quả tự nhận diện — giá trị này áp cho <b>tất cả</b> các kỳ
        trong file. File nhiều kỳ thuộc nhiều pháp nhân (Co.op) thì <b>đừng</b> điền: để máy nhận
        diện theo từng kỳ, kỳ nào máy không chắc thì sửa sau trên Desk.
      </div>
      <label class="kt-label" style="margin-top:12px">Ghi chú</label>
      <input class="kt-input" id="ma-note" placeholder="vd: bảng kê chuỗi gửi qua email ngày…">
    </div></div>

    <div style="display:flex;gap:10px;justify-content:flex-end;align-items:center;flex-wrap:wrap">
      ${!p.can_commit
        ? html`<span class="kt-sub">Chỉ kế toán trưởng mới được nạp.</span>`
        : ""}
      <button class="kt-btn kt-btn--outline" id="ma-cancel">Hủy</button>
      <button class="kt-btn" id="ma-go" ${(!p.can_commit || dup.length || !p.advice_count) ? "disabled" : ""}>
        <i class="fas fa-download"></i> Ghi nhận ${p.advice_count} bảng kê
      </button>
    </div>

    <div class="kt-sub" style="margin-top:8px;text-align:right">
      Ghi nhận = lưu bảng kê + đánh dấu. <b>Không</b> tạo Payment Entry / Journal Entry nào.
    </div>
  `);

  modal.body.querySelector("#ma-cancel").addEventListener("click", () => modal.close());

  const go = modal.body.querySelector("#ma-go");
  if (go) go.addEventListener("click", async () => {
    if (!confirm(`Ghi nhận ${p.advice_count} bảng kê của chuỗi ${p.chain}? Hệ thống sẽ KHÔNG tự hạch toán.`)) return;
    go.disabled = true;
    go.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang ghi nhận…';
    try {
      const r = await api.mtAdviceCommit({
        content,
        filename,
        chain: p.chain,
        // Vân tay của ĐÚNG kế hoạch vừa hiện trên màn hình. Giữa lúc xem trước và
        // lúc bấm nạp, một hóa đơn mới ghi sổ có thể làm kết quả khớp đổi — backend
        // so vân tay, lệch một dòng cũng dừng và không ghi gì.
        expected_hash: p.plan_hash,
        customer: modal.body.querySelector("#ma-customer").value.trim() || undefined,
        note: modal.body.querySelector("#ma-note").value.trim() || undefined,
      });
      // Cảnh báo SAU KHI GHI là kênh duy nhất báo cho người nạp biết tiền vừa
      // được ghi vào hóa đơn của khách khác, hoặc chỉ mục hóa đơn bị cắt cụt.
      // Trước đây chúng bị vứt ngay: `toast(r.message)` rồi `location.reload()`
      // xóa sạch màn hình — kế toán chỉ thấy một dòng xanh "đã ghi nhận".
      const post = [...(r.warnings || []),
        ...(r.lines_on_other_customer || []).map(
          (x) => `Dòng ${x.source_row || "?"} · HĐ ${x.inv_series || ""} ${x.inv_no || ""} `
               + `đã nối vào ${x.sales_invoice || "?"} của khách ${x.si_customer_name || x.si_customer || "?"}`)];
      if (!post.length) {
        toast(r.message || `Đã ghi nhận ${r.advice_count} bảng kê`, "success");
        modal.close();
        location.reload();
        return;
      }
      // Có cảnh báo thì KHÔNG tự đóng và KHÔNG reload — bắt người đọc rồi tự đóng.
      setHTML(modal.body, html`
        <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-success)"><div class="kt-card-body">
          <b><i class="fas fa-circle-check"></i> ${r.message || `Đã ghi nhận ${r.advice_count} bảng kê`}</b>
        </div></div>
        <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">Đã ghi nhận NHƯNG có ${post.length} điểm cần kiểm ngay</b>
          <div class="kt-sub" style="margin:6px 0">
            Dữ liệu đã được ghi. Những dòng dưới đây có thể đã gán tiền sang hóa đơn của khách
            khác — mở bảng kê trên Desk để sửa liên kết nếu sai.
          </div>
          <ul class="kt-sub" style="margin:6px 0 0 18px">${post.map((w) => html`<li>${w}</li>`)}</ul>
        </div></div>
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <a class="kt-btn kt-btn--outline" target="_blank" href="/desk/mt-payment-advice">Mở trên Desk</a>
          <button class="kt-btn" id="ma-done">Tôi đã đọc</button>
        </div>`);
      modal.body.querySelector("#ma-done").addEventListener("click", () => {
        modal.close();
        location.reload();
      });
    } catch (e) {
      toast(e.message, "error");
      go.disabled = false;
      go.innerHTML = "Thử lại";
    }
  });
}


// ── Ba lưới an toàn của màn xem trước ───────────────────────────────────────
// Backend dựng sẵn amount_mismatches / overpaid_invoices / cross_chain nhưng
// trước đây màn xem trước KHÔNG đọc tới, nên cảnh báo sinh ra rồi vứt ngay
// trong cùng một tick — kế toán chỉ thấy một dòng "khớp N/N" màu xanh.
//
// Đây đúng là ba chiều nối nhầm hóa đơn nguy hiểm nhất, và cả ba đều KHÔNG làm
// số kiểm tra của file lệch một đồng nào, nên không có lưới nào khác bắt được.
function riskRows(list, cols) {
  return html`<div class="kt-table-wrap" style="max-height:240px;overflow:auto;margin-top:6px">
    <table class="kt-table"><thead><tr>
      <th>Dòng</th><th>Hóa đơn trên bảng kê</th><th>Nối vào</th><th>Khách</th>
      ${cols.map((c) => html`<th class="num">${c.label}</th>`)}
    </tr></thead><tbody>
      ${list.map((x) => html`<tr>
        <td>${x.source_row || "—"}</td>
        <td>${x.inv_series || ""} <b>${x.inv_no || "—"}</b></td>
        <td>${x.sales_invoice
          ? html`<a target="_blank" href="/desk/sales-invoice/${encodeURIComponent(x.sales_invoice)}">${x.sales_invoice}</a>`
          : html`<span class="kt-sub">chưa nối</span>`}</td>
        <td class="kt-cell-wrap">${x.si_customer_name || x.si_customer || "—"}</td>
        ${cols.map((c) => html`<td class="num">${c.get(x)}</td>`)}
      </tr>`)}
    </tbody></table></div>`;
}

function riskBlocks(advices) {
  const gather = (k) => (advices || []).flatMap((a) => a[k] || []);
  const mism = gather("amount_mismatches");
  const over = gather("overpaid_invoices");
  const cross = gather("cross_chain");
  const trunc = (advices || []).some((a) => a.index_truncated);

  return html`
    ${trunc
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)"><i class="fas fa-scissors"></i> Chỉ mục hóa đơn bị cắt cụt</b>
          <div class="kt-sub" style="margin-top:6px">
            Số hóa đơn trong khoảng vượt trần tra cứu, nên một số dòng có thể KHÔNG khớp được
            dù hóa đơn có thật. Thu hẹp khoảng ngày rồi nạp lại — đừng kết luận "chưa xuất hóa đơn".
          </div>
        </div></div>`
      : ""}

    ${cross.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)"><i class="fas fa-shuffle"></i>
            ${cross.length} dòng nối vào hóa đơn của CHUỖI KHÁC hoặc hóa đơn đã hủy/đã thay thế</b>
          <div class="kt-sub" style="margin:6px 0">
            Cả 5 chuỗi dùng chung dải ký hiệu, nên đọc lệch một chữ số là tiền của chuỗi này
            được ghi vào hóa đơn của chuỗi kia — hai bên lệch công nợ ngược chiều nhau.
            Những dòng này đã bị hạ xuống <b>Cần review</b>, kiểm trước khi nạp.
          </div>
          ${riskRows(cross, [{ label: "Tiền", get: (x) => formatVND(x.total_amount) }])}
        </div></div>`
      : ""}

    ${over.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)"><i class="fas fa-arrow-up-right-dots"></i>
            ${over.length} hóa đơn bị trả VƯỢT giá trị</b>
          <div class="kt-sub" style="margin:6px 0">
            Tổng tiền phân bổ vào hóa đơn đã vượt giá trị của nó. Thường là nối nhầm, hoặc kỳ
            này đã được nạp ở một bản ghi khác rồi.
          </div>
          ${riskRows(over, [
            { label: "Đã trả trước", get: (x) => formatVND(x.paid_before) },
            { label: "Vượt", get: (x) => formatVND(x.over) }])}
        </div></div>`
      : ""}

    ${mism.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          <b><i class="fas fa-scale-unbalanced"></i> ${mism.length} dòng khớp được nhưng LỆCH tiền</b>
          <div class="kt-sub" style="margin:6px 0">
            Không chặn nạp — chuỗi có quyền trả từng phần, nhiều kỳ mới đủ. Nhưng lệch cũng là
            dấu hiệu nối nhầm hóa đơn, nên phải nhìn thấy.
          </div>
          ${riskRows(mism, [
            { label: "Bảng kê", get: (x) => formatVND(x.total_amount) },
            { label: "Hóa đơn", get: (x) => formatVND(x.si_grand_total) },
            { label: "Lệch", get: (x) => formatVND(x.diff) }])}
        </div></div>`
      : ""}
  `;
}


// ── Nhận diện khách hàng theo TỪNG KỲ ──────────────────────────────────────
// Không đọc mã trong file: cái bảng kê in ra là định danh của CHÍNH TA
// (LOTTE Vendor CD 007466, Emart VENDOR CODE 100968, Co.op Mã cung cấp 012556
// đều là Hoàng Giang). Máy suy từ SỔ CỦA MÌNH — hóa đơn nào khớp được thì
// Sales Invoice.customer chính là người đã mua.
const DET_TONE = {
  "Chắc chắn": "green",
  "Cần xác nhận": "yellow",
  "Nhiều khách": "red",
  "Không xác định": "gray",
};

const DET_WHY = {
  hoa_don_da_khop: "mọi hóa đơn khớp được đều của khách này",
  hoa_don_da_khop_ap_dao: "khách này chiếm phần lớn tiền của kỳ",
  nhieu_khach_trong_mot_ky: "kỳ này trả cho NHIỀU khách — máy không chọn hộ",
  lich_su_bang_ke_cua_chuoi: "suy từ các bảng kê trước của chuỗi, chưa có hóa đơn nào khớp",
  lich_su_chuoi_co_nhieu_khach: "chuỗi này trước giờ gán cho nhiều khách khác nhau",
  khong_co_can_cu: "không khớp được hóa đơn nào và chuỗi chưa có lịch sử",
};

function customerBlock(advices) {
  const list = advices || [];
  if (!list.length) return "";
  const sure = list.filter((a) => a.detected_confidence === "Chắc chắn").length;
  const bad = list.filter((a) => a.detected_confidence === "Nhiều khách"
                              || a.detected_confidence === "Không xác định");

  return html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-${bad.length ? "warning" : "success"})">
      <div class="kt-card-body">
        <b><i class="fas fa-user-check"></i> Nhận diện khách hàng — ${sure}/${list.length} kỳ chắc chắn</b>
        <div class="kt-sub" style="margin:6px 0">
          Máy suy từ <b>hóa đơn đã khớp trong sổ của mình</b>, không đọc mã trong file:
          mã "nhà cung cấp" mà bảng kê in ra là mã của <b>chính công ty ta</b> bên hệ thống chuỗi,
          không phải mã khách. Chỉ kỳ nào <b>Chắc chắn</b> mới được điền tự động.
        </div>
        <div class="kt-table-wrap"><table class="kt-table">
          <thead><tr><th>Kỳ thanh toán</th><th>Khách hàng</th><th>Mức tin</th><th>Căn cứ</th></tr></thead>
          <tbody>${list.map((a) => html`<tr>
            <td>${formatDate(a.payment_date) || html`<span class="kt-sub">chưa rõ ngày</span>`}
              ${a.advice_no ? html`<div class="kt-sub">${a.advice_no}</div>` : ""}</td>
            <td>${a.detected_customer
              ? html`<b>${a.detected_customer}</b>${(a.customer_candidates || [])[0]
                  && (a.customer_candidates[0].customer_name)
                  ? html`<div class="kt-sub">${a.customer_candidates[0].customer_name}</div>` : ""}`
              : html`<span class="kt-sub">— sẽ để trống, sửa sau trên Desk —</span>`}</td>
            <td><span class="kt-badge kt-badge--${DET_TONE[a.detected_confidence] || "gray"}">
              ${a.detected_confidence || "?"}</span></td>
            <td class="kt-sub">${DET_WHY[a.detected_evidence] || a.detected_evidence || ""}
              ${(a.customer_candidates || []).length > 1
                ? html`<div>${a.customer_candidates.slice(0, 4).map((c) => html`
                    <span class="kt-badge kt-badge--gray">${c.customer} ${Math.round((c.share || 0) * 100)}%</span> `)}</div>`
                : ""}</td>
          </tr>`)}</tbody>
        </table></div>
        ${bad.length
          ? html`<div class="kt-sub" style="margin-top:8px">
              <b>${bad.length} kỳ máy không kết luận được.</b> Những kỳ đó sẽ được ghi nhận với
              khách hàng <b>để trống</b> — công nợ rơi vào nhóm "Chưa gán chuỗi" cho tới khi kế toán
              mở bảng kê trên Desk và điền. Máy cố ý không chọn đại: một kỳ trả cho nhiều pháp nhân
              (Co.op có 120 siêu thị thành viên) mà gán một khách là dồn công nợ sai chỗ.
            </div>`
          : ""}
      </div></div>`;
}


// ── Tab 3 (chế độ mặc định): công nợ chi tiết TRÊN ĐẦU TỪNG KHÁCH ──────────
// Cấp chuỗi chỉ để nhìn tổng. Đi đòi nợ thì phải theo pháp nhân — riêng Co.op
// có tới 120 siêu thị thành viên, con số cấp chuỗi không dùng được vào việc gì.
function viewSwitch(state) {
  const btn = (v, label, icon) => html`<button
    class="kt-btn kt-btn--sm ${state.chainView === v ? "" : "kt-btn--outline"}"
    data-view="${v}"><i class="fas ${icon}"></i> ${label}</button>`;
  return html`<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
    ${btn("khach", "Theo khách hàng", "fa-user")}
    ${btn("chuoi", "Theo chuỗi", "fa-store")}
  </div>`;
}

async function loadCustomers(container, state) {
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtCustomerSummary({
      from_date: state.from, to_date: state.to,
      chain: state.chain || undefined, search: state.search || undefined,
      page: state.page,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];
  const t = res.totals || {};

  setHTML(body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      ${viewSwitch(state)}
      <label class="kt-label" style="margin:0 0 0 8px">Chuỗi</label>
      <select class="kt-input kt-input--sm" id="mt-chain">
        <option value="">Tất cả chuỗi</option>
        ${(res.chains || []).map((c) => html`<option value="${c}" ${state.chain === c ? "selected" : ""}>${c}</option>`)}
      </select>
      <input class="kt-input kt-input--sm" id="mt-cus-search" placeholder="Tìm khách hàng…"
             value="${state.search}" style="margin-left:auto;min-width:220px">
    </div></div>

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-store-slash"></i><p>Chưa có phát sinh nào của kênh MT trong khoảng này.</p></div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Khách hàng</th><th>Chuỗi</th><th class="num">Hóa đơn</th>
              <th class="num">Đã xuất</th><th class="num">Trả hàng</th>
              <th class="num">Đã thu</th><th class="num">Còn lại</th>
              <th class="num">Tiền hàng trong kỳ</th><th class="num">Chiết khấu</th>
              <th class="num">Phí</th><th class="num">Khác</th>
              <th class="num">Thực nhận</th><th></th>
            </tr></thead>
            <tbody>
              ${rows.map((r) => html`<tr>
                <td><b>${r.customer_name || r.customer}</b>
                  ${r.customer_name ? html`<div class="kt-sub">${r.customer}</div>` : ""}</td>
                <td>${r.chain === "Chưa gán chuỗi"
                  ? html`<span class="kt-badge kt-badge--yellow">${r.chain}</span>`
                  : html`<span class="kt-sub">${r.chain}</span>`}</td>
                <td class="num">${r.invoice_count}${r.unpaid_count
                  ? html` <span class="kt-badge kt-badge--yellow">${r.unpaid_count} chưa đủ</span>`
                  : ""}</td>
                <td class="num">${formatVND(r.invoiced)}</td>
                <td class="num">${r.returns ? formatVND(r.returns) : html`<span class="kt-sub">—</span>`}</td>
                <td class="num">${formatVND(r.collected)}</td>
                <td class="num"><b>${formatVND(r.outstanding)}</b></td>
                <td class="num">${formatVND(r.received_in_period)}</td>
                <td class="num">${formatVND(r.discount)}</td>
                <td class="num">${formatVND(r.fee)}</td>
                <td class="num">${formatVND(r.other)}</td>
                <td class="num"><b>${formatVND(r.net_received_est)}</b></td>
                <td class="num" style="white-space:nowrap">
                  ${r.customer && r.customer !== "Chưa gán khách"
                    ? html`<button class="kt-btn-icon" data-drill-inv="${r.customer}" title="Xem hóa đơn của khách này"><i class="fas fa-file-invoice"></i></button>
                           <button class="kt-btn-icon" data-drill-ded="${r.customer}" title="Xem khoản khấu trừ của khách này"><i class="fas fa-percent"></i></button>`
                    : ""}
                </td>
              </tr>`)}
              <tr>
                <td><b>TỔNG</b></td><td></td>
                <td class="num"><b>${t.invoice_count || 0}</b></td>
                <td class="num"><b>${formatVND(t.invoiced)}</b></td>
                <td class="num"><b>${formatVND(t.returns)}</b></td>
                <td class="num"><b>${formatVND(t.collected)}</b></td>
                <td class="num"><b>${formatVND(t.outstanding)}</b></td>
                <td class="num"><b>${formatVND(t.received_in_period)}</b></td>
                <td class="num"><b>${formatVND(t.discount)}</b></td>
                <td class="num"><b>${formatVND(t.fee)}</b></td>
                <td class="num"><b>${formatVND(t.other)}</b></td>
                <td class="num"><b>${formatVND(t.net_received_est)}</b></td>
                <td></td>
              </tr>
            </tbody>
          </table></div>
          ${pager(res, "khách hàng")}
          <div class="kt-sub" style="margin-top:8px">${res.note || ""}</div>
        </div></div>`}
  `);

  bindChainFilter(container, state);
  bindPager(container, state);
  bindViewSwitch(container, state);
  bindDrill(container, state);

  const box = container.querySelector("#mt-cus-search");
  if (box) {
    let timer = null;
    box.addEventListener("input", (e) => {
      state.search = e.target.value.trim();
      state.page = 1;
      clearTimeout(timer);
      timer = setTimeout(() => loadTab(container, state), 350);
    });
  }
}

function bindViewSwitch(container, state) {
  container.querySelectorAll("button[data-view]").forEach((b) => {
    b.addEventListener("click", () => {
      if (state.chainView === b.dataset.view) return;
      state.chainView = b.dataset.view;
      state.page = 1;
      loadTab(container, state);
    });
  });
}

// Bấm từ dòng khách sang đúng danh sách của khách đó — đây là thao tác chính
// khi đối chiếu: nhìn số tổng thấy lệch thì mở ngay chi tiết của khách đó.
function bindDrill(container, state) {
  const go = (tab, customer, bucket) => {
    state.customer = customer;
    state.tab = tab;
    if (bucket) state.bucket = bucket;
    state.page = 1;
    state.search = "";
    const btn = container.querySelector(`#mt-tabs button[data-tab="${tab}"]`);
    if (btn) container.querySelectorAll("#mt-tabs button").forEach((x) => x.classList.toggle("is-active", x === btn));
    loadTab(container, state);
  };
  container.querySelectorAll("button[data-drill-inv]").forEach((b) =>
    b.addEventListener("click", () => go("thanh-toan", b.dataset.drillInv, "tat_ca")));
  container.querySelectorAll("button[data-drill-ded]").forEach((b) =>
    b.addEventListener("click", () => go("chiet-khau", b.dataset.drillDed)));
}


// Thanh báo "đang xem của riêng khách X". Lọc mà không hiện là nguy hiểm: kế
// toán nhìn một danh sách đã bị lọc rồi tưởng đó là toàn bộ kênh MT.
function customerFilterBar(state) {
  if (!state.customer) return "";
  return html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-primary)">
      <div class="kt-card-body" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <i class="fas fa-filter"></i>
        <span>Đang lọc theo khách hàng <b>${state.customer}</b> — danh sách dưới đây
          <b>không phải</b> toàn bộ kênh MT.</span>
        <button class="kt-btn kt-btn--outline kt-btn--sm" id="mt-clear-cus" style="margin-left:auto">
          <i class="fas fa-xmark"></i> Bỏ lọc
        </button>
      </div></div>`;
}

function bindCustomerFilter(container, state) {
  const btn = container.querySelector("#mt-clear-cus");
  if (!btn) return;
  btn.addEventListener("click", () => {
    state.customer = "";
    state.page = 1;
    loadTab(container, state);
  });
}
