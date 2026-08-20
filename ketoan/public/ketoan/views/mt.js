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
  { key: "but-toan", label: "Bút toán", icon: "fa-file-invoice-dollar",
    hint: "Sinh bút toán NHÁP từ bảng kê. Hệ thống không bao giờ tự ghi sổ — người duyệt mới ghi. Tài khoản lấy từ cấu hình, không hardcode." },
];

// Rổ hóa đơn của tab 1 — đúng khóa mà backend nhận (mt.get_invoices).
const INV_BUCKETS = [
  { key: "chua_thanh_toan", label: "Chưa thu đủ" },
  { key: "da_thanh_toan", label: "Đã thu đủ" },
  { key: "tat_ca", label: "Tất cả" },
];

// Danh sách chuỗi siêu thị đến TỪ BACKEND (`get_overview.chain_options`), khai
// gốc ở ketoan/install.py: MT_CHAINS.
//
// VÌ SAO không khai lại ở đây: đã có ba nơi phải khớp nhau (install.py, mt.py,
// DocType JSON) và bản sao thứ tư trong JS là bản chắc chắn bị quên nhất — thêm
// AEON ở Python mà quên ở đây thì kế toán không chọn được chuỗi để nạp lại khi
// tự nhận diện trượt, và họ sẽ tưởng file hỏng.
//
// `state.chainOptions` được nạp trong render(); mảng dưới đây CHỈ là lưới an
// toàn cho trường hợp backend cũ chưa trả field này — không phải nguồn thật.
const CHAINS_FALLBACK = ["WinCommerce", "Central Retail", "LOTTE", "Emart", "Saigon Co.op"];

const chainsOf = (state) =>
  (state && state.chainOptions && state.chainOptions.length)
    ? state.chainOptions
    : CHAINS_FALLBACK;

// Chuỗi CÓ trong danh sách nhưng CHƯA có tầng đọc bảng kê (ví dụ Mega Market:
// gán khách được, nạp file thì chưa). Đánh dấu ngay trên ô chọn để kế toán
// không mất công thử rồi nhận lỗi.
const chainOptionHTML = (state, selected) =>
  chainsOf(state).map((c) => {
    const noParser = state && state.chainParsers && state.chainParsers.length
      && !state.chainParsers.includes(c);
    return html`<option value="${c}" ${selected === c ? "selected" : ""}>${c}${noParser ? " (chưa đọc được file)" : ""}</option>`;
  });

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
    // Tab 'Bút toán': lọc theo trạng thái bút toán của bảng kê.
    jeState: query?.je_state || "",
    // Tab 'Bút toán' có hai cách nhìn: theo BẢNG KÊ (sinh bút toán) và theo
    // BÚT TOÁN (duyệt). Tách ra vì hai việc khác nhau, hai quyền khác nhau.
    jeView: query?.je_view === "duyet" ? "duyet" : "bang-ke",
    // Bút toán đang tick để duyệt/xóa hàng loạt.
    jePicked: new Set(),
    jeKind: query?.je_kind || "",
    // '0' = nháp chờ duyệt (mặc định), '1' = đã ghi sổ.
    jeDocstatus: query?.je_docstatus === "1" ? "1" : "0",
  };

  let ov;
  try {
    ov = await api.mtOverview({ from_date: state.from, to_date: state.to });
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  state.canManage = !!ov.can_import;   // backend: is_chief()
  // Danh sách chuỗi lấy từ backend — xem chú thích ở CHAINS_FALLBACK.
  state.chainOptions = Array.isArray(ov.chain_options) ? ov.chain_options : [];
  state.chainParsers = Array.isArray(ov.chain_parsers) ? ov.chain_parsers : [];
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
  if (state.tab === "but-toan") {
    return state.jeView === "duyet"
      ? loadJeApproval(container, state)
      : loadJournals(container, state);
  }

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
        ${chainOptionHTML(state, state.chain)}
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
// LUÔN xem trước rồi mới nạp. Mỗi chuỗi một khuôn file khác nhau, ba quy ước dấu
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
            ${chainOptionHTML(state, chain)}
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
      <label class="kt-label">Khách hàng (áp cho MỌI kỳ trong file)</label>
      <select class="kt-input" id="ma-customer">
        <option value="">— dùng kết quả nhận diện ở trên —</option>
      </select>
      <div class="kt-sub" style="margin-top:6px">
        Chọn ở đây là <b>đè</b> kết quả tự nhận diện, áp cho <b>tất cả</b> các kỳ trong file.
        File nhiều kỳ thuộc nhiều pháp nhân (Co.op) thì <b>đừng</b> chọn: để máy nhận diện
        theo từng kỳ. Chọn xong thì <b>chuỗi của khách tự gán luôn</b> theo chuỗi của file —
        không phải vào đâu gán lại.
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
  fillCustomerSelect(modal, p);

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
            Mọi chuỗi dùng chung dải ký hiệu, nên đọc lệch một chữ số là tiền của chuỗi này
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
      <button class="kt-btn kt-btn--outline kt-btn--sm" id="mt-assign-chain">
        <i class="fas fa-diagram-project"></i> Sửa chuỗi của khách
      </button>
      <button class="kt-btn kt-btn--outline kt-btn--sm" id="mt-stores">
        <i class="fas fa-store"></i> Điểm siêu thị
      </button>
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
  const asg = container.querySelector("#mt-assign-chain");
  if (asg) asg.addEventListener("click", () => openChainAssign(container, state));
  const stores = container.querySelector("#mt-stores");
  if (stores) stores.addEventListener("click", () => openStores(container, state));

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


// ── Gán chuỗi cho khách hàng ───────────────────────────────────────────────
// Đây là chỗ gán CHÍNH THỨC. Trước đó chuỗi chỉ suy được từ bảng kê đã nạp —
// vòng luẩn quẩn: khách mới ký hợp đồng, chưa có đồng thanh toán nào, thì không
// gán được; mà không gán thì công nợ của họ rơi vào rổ "Chưa gán chuỗi".
async function openChainAssign(container, state) {
  const modal = openModal({
    title: "Gán chuỗi siêu thị cho khách hàng",
    icon: "fa-diagram-project",
    maxWidth: 860,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  await renderChainAssign(container, state, modal, 1);
}

async function renderChainAssign(container, state, modal, onlyUnassigned) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let res;
  try {
    res = await api.mtChainAssignment({ only_unassigned: onlyUnassigned ? 1 : 0 });
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];

  setHTML(modal.body, html`
    ${!res.has_field
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">Site chưa có field gán chuỗi.</b>
          <div class="kt-sub">Quản trị chạy <code>bench --site TÊN_SITE migrate</code> rồi mở lại.</div>
        </div></div>`
      : ""}

    <p class="kt-sub">
      <b>Bình thường không cần vào đây.</b> Nạp bảng kê và chọn khách là chuỗi tự gán theo
      chuỗi của file. Màn này chỉ để <b>sửa</b> khi gán sai, khi khách đổi chuỗi, hoặc khi
      muốn gán trước cho khách mới ký hợp đồng mà chưa có bảng kê nào.
    </p>

    <div style="display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
      <label style="display:flex;gap:6px;align-items:center;cursor:pointer">
        <input type="checkbox" id="ca-only" ${onlyUnassigned ? "checked" : ""}>
        <span class="kt-sub">Chỉ hiện khách chưa chốt</span>
      </label>
      <span class="kt-sub" style="margin-left:auto">${rows.length} khách</span>
    </div>

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i>
          <p>Mọi khách hàng kênh MT đều đã được gán chuỗi.</p></div>`
      : html`<div class="kt-table-wrap" style="max-height:420px;overflow:auto">
          <table class="kt-table">
            <thead><tr><th>Khách hàng</th><th>Nguồn</th><th>Chuỗi</th></tr></thead>
            <tbody>${rows.map((r) => html`<tr>
              <td><b>${r.customer_name || r.customer}</b>
                ${r.customer_name ? html`<div class="kt-sub">${r.customer}</div>` : ""}</td>
              <td>${r.source === "khai_bao"
                ? html`<span class="kt-badge kt-badge--green">đã chốt</span>`
                : r.source === "suy_tu_bang_ke"
                  ? html`<span class="kt-badge kt-badge--yellow">máy suy từ bảng kê</span>`
                  : html`<span class="kt-badge kt-badge--gray">chưa gán</span>`}</td>
              <td><select class="kt-input kt-input--sm" data-assign="${r.customer}"
                    ${res.can_assign && res.has_field ? "" : "disabled"}>
                <option value="">— chưa gán —</option>
                ${(res.chains || []).map((c) => html`<option value="${c}" ${r.chain === c ? "selected" : ""}>${c}</option>`)}
              </select></td>
            </tr>`)}</tbody>
          </table></div>`}

    <div class="kt-sub" style="margin-top:8px">${res.note || ""}</div>
    ${!res.can_assign
      ? html`<div class="kt-sub" style="margin-top:6px">Chỉ kế toán trưởng mới được gán.</div>`
      : ""}
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:12px">
      <button class="kt-btn kt-btn--outline" id="ca-close">Đóng</button>
    </div>
  `);

  modal.body.querySelector("#ca-close").addEventListener("click", () => {
    modal.close();
    loadTab(container, state);   // số liệu đổi theo chuỗi vừa gán
  });
  modal.body.querySelector("#ca-only").addEventListener("change", (e) =>
    renderChainAssign(container, state, modal, e.target.checked ? 1 : 0));

  modal.body.querySelectorAll("select[data-assign]").forEach((sel) => {
    sel.addEventListener("change", async () => {
      const prev = sel.dataset.prev || "";
      sel.disabled = true;
      try {
        const r = await api.mtSetCustomerChain(sel.dataset.assign, sel.value || undefined);
        toast(r.message, "success");
        sel.dataset.prev = sel.value;
        const cell = sel.closest("tr").querySelector("td:nth-child(2)");
        if (cell) setHTML(cell, sel.value
          ? html`<span class="kt-badge kt-badge--green">đã chốt</span>`
          : html`<span class="kt-badge kt-badge--gray">chưa gán</span>`);
      } catch (e) {
        toast(e.message, "error");
        sel.value = prev;   // trả về giá trị cũ, đừng để màn hình nói dối
      }
      sel.disabled = false;
    });
  });
}


// Đổ danh sách khách kênh MT vào ô chọn của màn nạp bảng kê.
//
// Trước đây chỗ này là ô gõ mã trần ("CUS-0001") — bắt kế toán thuộc lòng mã
// khách, mà không ai thuộc. Danh sách nạp sau khi khung đã hiện: chậm mạng thì
// cùng lắm ô chọn trống một nhịp, không chặn cả màn xem trước.
async function fillCustomerSelect(modal, p) {
  const sel = modal.body.querySelector("#ma-customer");
  if (!sel) return;
  let res;
  try {
    res = await api.mtCustomers({ chain: p.chain || undefined });
  } catch (_) {
    return;   // giữ nguyên "dùng kết quả nhận diện" — vẫn nạp được
  }
  const rows = res.rows || [];
  if (!rows.length) return;

  // Khách đã thuộc đúng chuỗi của file lên nhóm trên, còn lại nhóm dưới — chọn
  // nhầm sang khách của chuỗi khác là ghi tiền sai chỗ.
  const same = rows.filter((r) => r.same_chain);
  const other = rows.filter((r) => !r.same_chain);
  const opt = (r) => html`<option value="${r.customer}">${r.customer_name || r.customer}${
    r.chain ? ` · ${r.chain}` : " · chưa gán chuỗi"}</option>`;

  setHTML(sel, html`
    <option value="">— dùng kết quả nhận diện ở trên —</option>
    ${same.length ? html`<optgroup label="Thuộc chuỗi ${p.chain}">${same.map(opt)}</optgroup>` : ""}
    ${other.length ? html`<optgroup label="${same.length ? "Khách khác của kênh MT" : "Khách kênh MT"}">
      ${other.map(opt)}</optgroup>` : ""}
  `);
}


// ── Điểm siêu thị (master) ─────────────────────────────────────────────────
//
// VÌ SAO cần màn hình riêng: mã điểm trên bảng kê chỉ là một chuỗi ký tự, còn
// cái kế toán thật sự cần là "điểm này thuộc PHÁP NHÂN nào" (đi đòi nợ theo pháp
// nhân, không theo chuỗi — riêng Co.op có ~120 siêu thị thành viên) và "xuất hóa
// đơn cho điểm này thì lấy địa chỉ/MST ở đâu".
//
// Điểm được DỰNG TỪ CÁC BẢNG KÊ ĐÃ NẠP, không từ file mẫu: file mẫu là ảnh chụp
// một kỳ, còn site luôn mới hơn.

const STORE_STATUS_TONE = { moi: "green", da_co: "gray", lech: "yellow" };

async function openStores(container, state) {
  const modal = openModal({
    title: "Điểm siêu thị",
    icon: "fa-store",
    maxWidth: 1000,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  const st = { chain: state.chain || "", search: "", page: 1, active: "" };
  await renderStores(container, state, modal, st);
}

async function renderStores(container, state, modal, st) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let res;
  try {
    res = await api.mtStores({ chain: st.chain || undefined, search: st.search || undefined,
                               active: st.active === "" ? undefined : st.active,
                               page: st.page, page_size: 50 });
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <label class="kt-label" style="margin:0">Chuỗi</label>
      <select class="kt-input kt-input--sm" id="ms-chain">
        <option value="">Tất cả</option>
        ${(res.chains || []).map((c) => html`<option value="${c}" ${st.chain === c ? "selected" : ""}>${c}</option>`)}
      </select>
      <select class="kt-input kt-input--sm" id="ms-active">
        <option value="" ${st.active === "" ? "selected" : ""}>Mọi trạng thái</option>
        <option value="1" ${st.active === "1" ? "selected" : ""}>Đang hoạt động</option>
        <option value="0" ${st.active === "0" ? "selected" : ""}>Đã đóng</option>
      </select>
      <input class="kt-input kt-input--sm" id="ms-search" placeholder="Tìm mã / tên điểm / khách…"
             value="${st.search}" style="min-width:220px">
      ${state.canManage
        ? html`<button class="kt-btn kt-btn--outline kt-btn--sm" id="ms-seed" style="margin-left:auto">
            <i class="fas fa-wand-magic-sparkles"></i> Dựng từ bảng kê đã nạp
          </button>`
        : ""}
    </div></div>

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-store-slash"></i>
          <p>Chưa có điểm siêu thị nào${st.search || st.chain ? " khớp bộ lọc" : ""}.</p>
          ${state.canManage && !st.search && !st.chain
            ? html`<div class="kt-sub">Bấm <b>Dựng từ bảng kê đã nạp</b> để hệ thống lấy mã điểm
                từ các bảng kê đã có trên site. Chuỗi chưa nạp bảng kê nào thì chưa dựng được điểm nào.</div>`
            : ""}
        </div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Chuỗi</th><th>Mã điểm</th><th>Tên điểm</th><th>Khách hàng</th>
              <th>Địa chỉ xuất HĐ</th><th>Mã NCC</th><th></th>
            </tr></thead>
            <tbody>
              ${rows.map((r) => html`<tr>
                <td><span class="kt-badge kt-badge--gray">${r.chain}</span></td>
                <td><code>${r.store_code}</code></td>
                <td>${r.store_name}
                  ${!r.active ? html` <span class="kt-badge kt-badge--red">đã đóng</span>` : ""}</td>
                <td>${r.customer
                  ? html`${r.customer_name || r.customer}`
                  : html`<span class="kt-badge kt-badge--yellow">chưa gán pháp nhân</span>`}</td>
                <td class="kt-sub">${r.address || "—"}</td>
                <td class="kt-sub">${r.vendor_code || "—"}</td>
                <td>${state.canManage
                  ? html`<button class="kt-btn kt-btn--outline kt-btn--sm ms-edit" data-name="${r.name}">
                      <i class="fas fa-pen"></i></button>`
                  : ""}</td>
              </tr>`)}
            </tbody>
          </table></div>
          ${storePager(res)}
          <div class="kt-sub" style="margin-top:8px">
            Điểm <b>chưa gán pháp nhân</b> vẫn hiện công nợ theo chuỗi, nhưng không đi đòi nợ
            theo pháp nhân được và không xuất được bảng kê chiết khấu có MST người mua.
          </div>
        </div></div>`}
  `);

  const rerender = () => renderStores(container, state, modal, st);
  const ch = modal.body.querySelector("#ms-chain");
  if (ch) ch.addEventListener("change", (e) => { st.chain = e.target.value; st.page = 1; rerender(); });
  const ac = modal.body.querySelector("#ms-active");
  if (ac) ac.addEventListener("change", (e) => { st.active = e.target.value; st.page = 1; rerender(); });
  const sb = modal.body.querySelector("#ms-search");
  if (sb) {
    let timer = null;
    sb.addEventListener("input", (e) => {
      st.search = e.target.value.trim();
      st.page = 1;
      clearTimeout(timer);
      timer = setTimeout(rerender, 350);
    });
  }
  modal.body.querySelectorAll(".ms-page").forEach((b) => {
    b.addEventListener("click", () => { st.page = Number(b.dataset.page); rerender(); });
  });
  modal.body.querySelectorAll(".ms-edit").forEach((b) => {
    b.addEventListener("click", () => {
      const row = rows.find((r) => r.name === b.dataset.name);
      if (row) openStoreEdit(container, state, modal, st, row);
    });
  });
  const seed = modal.body.querySelector("#ms-seed");
  if (seed) seed.addEventListener("click", () => openStoreSeed(container, state, modal, st));
}

function storePager(res) {
  if (!res || (res.pages || 1) <= 1) return "";
  const p = res.page || 1;
  return html`
    <div style="display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-top:10px">
      <span class="kt-sub">${res.total} điểm · trang ${p}/${res.pages}</span>
      <button class="kt-btn kt-btn--outline kt-btn--sm ms-page" data-page="${p - 1}"
              ${p <= 1 ? "disabled" : ""}><i class="fas fa-chevron-left"></i></button>
      <button class="kt-btn kt-btn--outline kt-btn--sm ms-page" data-page="${p + 1}"
              ${p >= res.pages ? "disabled" : ""}><i class="fas fa-chevron-right"></i></button>
    </div>`;
}

// ── Sửa một điểm ───────────────────────────────────────────────────────────
async function openStoreEdit(container, state, parent, st, row) {
  const modal = openModal({
    title: `${row.chain} · ${row.store_code}`,
    icon: "fa-pen",
    maxWidth: 620,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });

  let customers = [];
  try {
    customers = (await api.mtCustomers({ chain: row.chain })).rows || [];
  } catch (_) { /* vẫn sửa được các field khác */ }

  setHTML(modal.body, html`
    <div style="display:grid;gap:12px">
      <div>
        <label class="kt-label">Tên điểm</label>
        <input class="kt-input" id="se-name" value="${row.store_name || ""}">
      </div>
      <div>
        <label class="kt-label">Khách hàng (pháp nhân xuất hóa đơn)</label>
        <select class="kt-input" id="se-customer">
          <option value="">— chưa gán —</option>
          ${customers.map((c) => html`<option value="${c.customer}" ${row.customer === c.customer ? "selected" : ""}>${
            c.customer_name || c.customer}${c.chain ? ` · ${c.chain}` : ""}</option>`)}
        </select>
        <div class="kt-sub" style="margin-top:4px">
          Gán sai pháp nhân là cả kỳ công nợ chạy sang khách khác — và không tổng nào phát hiện ra.
        </div>
      </div>
      <div>
        <label class="kt-label">Địa chỉ xuất hóa đơn</label>
        <select class="kt-input" id="se-address">
          <option value="">— chưa gán —</option>
          ${row.address ? html`<option value="${row.address}" selected>${row.address}</option>` : ""}
        </select>
        <div class="kt-sub" style="margin-top:4px">
          Chỉ liệt kê địa chỉ của đúng khách đã chọn. Dùng địa chỉ của pháp nhân khác là
          in hóa đơn sai MST người mua.
        </div>
      </div>
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <div style="flex:1;min-width:180px">
          <label class="kt-label">MST riêng của điểm</label>
          <input class="kt-input" id="se-tax" value="${row.tax_id || ""}"
                 placeholder="để trống nếu dùng MST của địa chỉ">
        </div>
        <div style="flex:1;min-width:180px">
          <label class="kt-label">Mã NCC của mình tại chuỗi</label>
          <input class="kt-input" id="se-vendor" value="${row.vendor_code || ""}">
        </div>
      </div>
      <label style="display:flex;gap:8px;align-items:center">
        <input type="checkbox" id="se-active" ${row.active ? "checked" : ""}>
        <span>Đang hoạt động</span>
      </label>
      <div>
        <label class="kt-label">Ghi chú</label>
        <textarea class="kt-input" id="se-note" rows="2">${row.note || ""}</textarea>
      </div>
      ${row.seeded_from ? html`<div class="kt-sub">Nguồn dựng: ${row.seeded_from}</div>` : ""}
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="kt-btn kt-btn--outline" id="se-cancel">Hủy</button>
        <button class="kt-btn kt-btn--primary" id="se-save"><i class="fas fa-check"></i> Lưu</button>
      </div>
      <div id="se-msg"></div>
    </div>`);

  const cusSel = modal.body.querySelector("#se-customer");
  const addrSel = modal.body.querySelector("#se-address");

  async function loadAddresses() {
    const cus = cusSel.value;
    if (!cus) {
      setHTML(addrSel, html`<option value="">— chọn khách hàng trước —</option>`);
      return;
    }
    let list = [];
    try { list = await api.mtStoreAddresses("", cus); } catch (_) { /* để trống */ }
    setHTML(addrSel, html`
      <option value="">— chưa gán —</option>
      ${list.map((a) => html`<option value="${a.name}" ${row.address === a.name ? "selected" : ""}>${
        a.address_title || a.name}${a.tax_id ? ` · MST ${a.tax_id}` : ""}</option>`)}`);
  }
  cusSel.addEventListener("change", loadAddresses);
  if (row.customer) await loadAddresses();

  modal.body.querySelector("#se-cancel").addEventListener("click", () => modal.close());
  modal.body.querySelector("#se-save").addEventListener("click", async () => {
    const btn = modal.body.querySelector("#se-save");
    btn.disabled = true;
    try {
      await api.mtStoreSave({
        name: row.name,
        store_name: modal.body.querySelector("#se-name").value.trim(),
        // Gửi CHUỖI RỖNG (không phải null) khi muốn gỡ: backend hiểu rỗng là
        // "cố ý xóa", còn thiếu field là "giữ nguyên".
        customer: cusSel.value,
        address: addrSel.value,
        tax_id: modal.body.querySelector("#se-tax").value.trim(),
        vendor_code: modal.body.querySelector("#se-vendor").value.trim(),
        active: modal.body.querySelector("#se-active").checked ? 1 : 0,
        note: modal.body.querySelector("#se-note").value,
      });
      toast("Đã lưu điểm " + row.store_code, "success");
      modal.close();
      await renderStores(container, state, parent, st);
    } catch (e) {
      btn.disabled = false;
      setHTML(modal.body.querySelector("#se-msg"), html`
        <div class="kt-card" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <div class="kt-sub" style="white-space:pre-wrap">${e.message}</div>
        </div></div>`);
    }
  });
}

// ── Dựng master từ bảng kê đã nạp ──────────────────────────────────────────
//
// XEM TRƯỚC LÀ BẮT BUỘC. Điểm dựng bằng suy luận (Central Retail không in mã nên
// mã do hệ thống sinh từ tên; địa chỉ dò theo cụm trong ngoặc cuối), nên người
// phải nhìn trước khi ghi master. Backend đòi vân tay của đúng bản vừa xem.
async function openStoreSeed(container, state, parent, st) {
  const modal = openModal({
    title: "Dựng điểm siêu thị từ bảng kê đã nạp",
    icon: "fa-wand-magic-sparkles",
    maxWidth: 1000,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });

  let res;
  try {
    res = await api.mtStoreSeedPreview({});
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const s = res.summary || {};
  const stores = res.stores || [];

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <span class="kt-badge kt-badge--green">${s.moi || 0} sẽ tạo mới</span>
        <span class="kt-badge kt-badge--gray">${s.da_co || 0} đã có — bỏ qua</span>
        ${s.lech ? html`<span class="kt-badge kt-badge--yellow">${s.lech} lệch — KHÔNG đè</span>` : ""}
        ${s.thieu_khach ? html`<span class="kt-badge kt-badge--yellow">${s.thieu_khach} chưa rõ pháp nhân</span>` : ""}
      </div>
      <div class="kt-sub" style="margin-top:8px">${res.note || ""}</div>
    </div></div>

    ${(res.warnings || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          ${res.warnings.map((w) => html`<div class="kt-sub">• ${w}</div>`)}
        </div></div>`
      : ""}

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div class="kt-table-wrap" style="max-height:380px;overflow:auto"><table class="kt-table">
        <thead><tr>
          <th>Chuỗi</th><th>Mã điểm</th><th>Tên điểm</th><th>Khách hàng</th>
          <th class="num">Dòng</th><th>Trạng thái</th>
        </tr></thead>
        <tbody>
          ${stores.map((p) => html`<tr>
            <td><span class="kt-badge kt-badge--gray">${p.chain}</span></td>
            <td><code>${p.store_code}</code>
              ${p.code_synthesized
                ? html` <span class="kt-badge kt-badge--yellow" title="Chuỗi không in mã điểm — mã này do hệ thống sinh từ tên">mã tự sinh</span>`
                : ""}</td>
            <td>${p.store_name}</td>
            <td>${p.customer || html`<span class="kt-sub">—</span>`}</td>
            <td class="num">${p.n_lines}</td>
            <td>
              <span class="kt-badge kt-badge--${STORE_STATUS_TONE[p.status] || "gray"}">${p.status_label}</span>
              ${(p.issues || []).map((i) => html`<div class="kt-sub">• ${i}</div>`)}
            </td>
          </tr>`)}
        </tbody>
      </table></div>
    </div></div>

    <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center">
      <button class="kt-btn kt-btn--outline" id="ss-cancel">Đóng</button>
      <button class="kt-btn kt-btn--primary" id="ss-commit" ${!s.moi ? "disabled" : ""}>
        <i class="fas fa-check"></i> Tạo ${s.moi || 0} điểm
      </button>
    </div>
    <div id="ss-msg"></div>`);

  modal.body.querySelector("#ss-cancel").addEventListener("click", () => modal.close());
  const btn = modal.body.querySelector("#ss-commit");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      // `expected_hash` là vân tay của ĐÚNG bản vừa xem — backend từ chối nếu
      // dữ liệu đã đổi (bảng kê mới nạp, điểm vừa tạo tay) giữa xem và tạo.
      const out = await api.mtStoreSeedCommit({ expected_hash: res.plan_hash });
      toast(out.message || `Đã tạo ${out.created} điểm`, "success");
      if ((out.failed || []).length) {
        setHTML(modal.body.querySelector("#ss-msg"), html`
          <div class="kt-card" style="border-left:4px solid var(--kt-warning);margin-top:10px">
            <div class="kt-card-body">
              <b>${out.failed.length} điểm KHÔNG tạo được</b>
              ${out.failed.map((f) => html`<div class="kt-sub">• ${f.chain} ${f.store_code}: ${f.error}</div>`)}
            </div></div>`);
      } else {
        modal.close();
      }
      await renderStores(container, state, parent, st);
    } catch (e) {
      btn.disabled = false;
      setHTML(modal.body.querySelector("#ss-msg"), html`
        <div class="kt-card" style="border-left:4px solid var(--kt-danger);margin-top:10px">
          <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e.message}</div></div>
        </div>`);
    }
  });
}


// ── Tab 4: Bút toán ────────────────────────────────────────────────────────
//
// RÀNG BUỘC P0 — "KHÔNG GHI SỔ": màn hình này chỉ sinh Journal Entry ở trạng
// thái NHÁP. Không có nút nào ghi sổ ở đây; duyệt là việc riêng, có guard riêng.
//
// Tài khoản hạch toán lấy từ cấu hình (MT Account Map), KHÔNG hardcode: số hiệu
// là 112/5211/6411 nhưng TÀI KHOẢN CON cụ thể khác nhau theo công ty.

const JE_STATE_TONE = {
  "Chưa sinh": "gray",
  "Đã sinh nháp": "yellow",
  "Đã duyệt một phần": "yellow",
  "Đã duyệt đủ": "green",
};

async function loadJournals(container, state) {
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtJeAdvices({
      from_date: state.from, to_date: state.to,
      chain: state.chain || undefined,
      je_state: state.jeState || undefined,
      search: state.search || undefined,
      page: state.page, page_size: 20,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];

  setHTML(body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      ${jeViewSwitch(state)}
      <label class="kt-label" style="margin:0 0 0 8px">Chuỗi</label>
      <select class="kt-input kt-input--sm" id="mt-chain">
        <option value="">Tất cả chuỗi</option>
        ${chainOptionHTML(state, state.chain)}
      </select>
      <label class="kt-label" style="margin:0 0 0 8px">Bút toán</label>
      <select class="kt-input kt-input--sm" id="je-state">
        <option value="">Mọi trạng thái</option>
        ${(res.je_states || []).map((s) => html`<option value="${s}" ${state.jeState === s ? "selected" : ""}>${s}</option>`)}
      </select>
      <button class="kt-btn kt-btn--outline kt-btn--sm" id="je-accmap" style="margin-left:auto">
        <i class="fas fa-sliders"></i> Cấu hình tài khoản
      </button>
    </div></div>

    ${!res.can_create
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          <b>Chưa cấu hình tài khoản hạch toán cho kênh MT.</b>
          <div class="kt-sub" style="margin-top:4px">
            Bấm <b>Cấu hình tài khoản</b> để xem và điền. Hệ thống <b>không</b> lấy tài khoản
            mặc định đoán — sinh bút toán vào sai tài khoản còn tệ hơn không sinh.
          </div>
        </div></div>`
      : ""}

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-file-invoice"></i>
          <p>Chưa có bảng kê nào trong khoảng ngày này.</p></div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              <th>Bảng kê</th><th>Chuỗi</th><th>Khách hàng</th><th>Ngày TT</th>
              <th class="num">Thanh toán</th><th class="num">Chiết khấu</th><th class="num">Phí</th>
              <th>Bút toán</th><th></th>
            </tr></thead>
            <tbody>
              ${rows.map((a) => html`<tr>
                <td><code>${a.name}</code>
                  ${a.advice_no ? html`<div class="kt-sub">${a.advice_no}</div>` : ""}</td>
                <td><span class="kt-badge kt-badge--gray">${a.chain || "—"}</span></td>
                <td>${a.customer_name || a.customer || html`<span class="kt-badge kt-badge--yellow">chưa gán khách</span>`}</td>
                <td>${a.payment_date ? formatDate(a.payment_date) : html`<span class="kt-badge kt-badge--red">thiếu ngày</span>`}</td>
                <td class="num">${formatVND(Math.abs(a.total_payment || 0))}</td>
                <td class="num">${formatVND(Math.abs(a.total_discount || 0))}</td>
                <td class="num">${formatVND(Math.abs(a.total_fee || 0))}</td>
                <td>
                  <span class="kt-badge kt-badge--${JE_STATE_TONE[a.je_state] || "gray"}">${a.je_state}</span>
                  ${a.je_draft ? html`<div class="kt-sub">${a.je_draft} nháp${a.je_submitted ? ` · ${a.je_submitted} đã duyệt` : ""}</div>`
                    : (a.je_submitted ? html`<div class="kt-sub">${a.je_submitted} đã duyệt</div>` : "")}
                </td>
                <td><button class="kt-btn kt-btn--outline kt-btn--sm je-open" data-advice="${a.name}">
                  <i class="fas fa-eye"></i> Xem bút toán</button></td>
              </tr>`)}
            </tbody>
          </table></div>
          ${pager(res, "bảng kê")}
          <div class="kt-sub" style="margin-top:8px">
            Bút toán sinh ra ở trạng thái <b>Nháp</b>. Hệ thống không bao giờ tự ghi sổ.
            Bảng kê <b>thiếu ngày thanh toán</b> (Fuji không in ngày trong file) phải điền ngày trước —
            bút toán không có ngày sẽ rơi vào sai kỳ kế toán.
          </div>
        </div></div>`}
  `);

  bindChainFilter(container, state);
  bindPager(container, state);
  const js = container.querySelector("#je-state");
  if (js) js.addEventListener("change", (e) => {
    state.jeState = e.target.value;
    state.page = 1;
    loadTab(container, state);
  });
  const am = container.querySelector("#je-accmap");
  if (am) am.addEventListener("click", () => openAccountMap());
  bindJeViewSwitch(container, state);
  container.querySelectorAll(".je-open").forEach((b) => {
    b.addEventListener("click", () => openJePreview(container, state, b.dataset.advice));
  });
}

// ── Cấu hình tài khoản (chỉ xem — sửa trên Desk) ───────────────────────────
async function openAccountMap() {
  const modal = openModal({
    title: "Tài khoản hạch toán kênh MT",
    icon: "fa-sliders",
    maxWidth: 900,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  let res;
  try {
    res = await api.mtJeAccountMap({});
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];
  const acc = (name, no, label) => name
    ? html`<div><code>${no || "?"}</code> ${label || name}</div>`
    : html`<span class="kt-badge kt-badge--red">chưa khai</span>`;

  setHTML(modal.body, html`
    ${(res.incomplete || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">${res.incomplete.length} dòng còn thiếu tài khoản.</b>
          <div class="kt-sub">Sinh bút toán sẽ DỪNG ở những sự kiện đó — hệ thống không lấy tài khoản đoán.</div>
        </div></div>`
      : ""}
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr><th>Sự kiện</th><th>Chuỗi</th><th>TK Nợ chính</th><th>TK Nợ thuế</th><th>TK Có</th><th></th></tr></thead>
        <tbody>
          ${rows.map((r) => html`<tr>
            <td>${r.event}${!r.active ? html` <span class="kt-badge kt-badge--gray">tắt</span>` : ""}</td>
            <td>${r.chain || html`<span class="kt-sub">mặc định (mọi chuỗi)</span>`}</td>
            <td>${acc(r.debit_account, r.debit_no, r.debit_name)}</td>
            <td>${r.tax_account
              ? acc(r.tax_account, r.tax_no, r.tax_name)
              : html`<span class="kt-sub">không tách thuế</span>`}</td>
            <td>${acc(r.credit_account, r.credit_no, r.credit_name)}</td>
            <td><a class="kt-btn kt-btn--outline kt-btn--sm" href="/app/mt-account-map/${r.name}" target="_blank">
              <i class="fas fa-pen"></i></a></td>
          </tr>`)}
        </tbody>
      </table></div>
      <div class="kt-sub" style="margin-top:8px">${res.note || ""}</div>
    </div></div>`);
}

// ── Xem trước bút toán của một bảng kê ─────────────────────────────────────
async function openJePreview(container, state, advice) {
  const modal = openModal({
    title: "Bút toán từ bảng kê " + advice,
    icon: "fa-file-invoice-dollar",
    maxWidth: 1000,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  await renderJePreview(container, state, modal, advice);
}

async function renderJePreview(container, state, modal, advice) {
  setHTML(modal.body, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let res;
  try {
    res = await api.mtJePreview(advice, {});
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-card" style="border-left:4px solid var(--kt-danger)">
      <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e.message}</div></div></div>`);
    return;
  }
  const entries = res.entries || [];

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <span class="kt-badge kt-badge--gray">${res.chain || "—"}</span>
        ${res.customer ? html`<span class="kt-sub">${res.customer}</span>` : ""}
        ${res.payment_date ? html`<span class="kt-sub">· ngày ${formatDate(res.payment_date)}</span>` : ""}
        <span class="kt-badge kt-badge--${JE_STATE_TONE[res.je_state] || "gray"}">${res.je_state}</span>
        ${!res.reconciled ? html`<span class="kt-badge kt-badge--yellow">chưa tick đối chiếu khớp</span>` : ""}
      </div>
      <div class="kt-sub" style="margin-top:8px">${res.note || ""}</div>
    </div></div>

    ${(res.warnings || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          ${res.warnings.map((w) => html`<div class="kt-sub">• ${w}</div>`)}
        </div></div>`
      : ""}

    ${(res.not_posted || []).length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
          <b>Khoản KHÔNG sinh bút toán</b>
          ${res.not_posted.map((n) => html`<div class="kt-sub" style="margin-top:6px">
            • <b>${n.row_kind}</b> — ${n.n_rows} dòng, ${formatVND(n.amount)}
            ${n.mixed_signs
              ? html`<br><b>Nhóm có cả khoản trừ lẫn khoản hoàn:</b> số trên là RÒNG;
                     cộng độ lớn từng dòng ra ${formatVND(n.amount_gross)}.`
              : ""}
            <br>${n.reason}</div>`)}
        </div></div>`
      : ""}

    ${!entries.length
      ? html`<div class="kt-empty"><i class="fas fa-ban"></i><p>Bảng kê này không sinh được bút toán nào.</p></div>`
      : entries.map((e) => jeCard(e))}

    <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center;margin-top:10px">
      <button class="kt-btn kt-btn--outline" id="jp-close">Đóng</button>
      ${state.canManage
        ? html`<button class="kt-btn kt-btn--primary" id="jp-create" ${!res.can_create ? "disabled" : ""}>
            <i class="fas fa-file-circle-plus"></i> Sinh ${entries.filter((e) => !e.duplicate).length} bút toán nháp
          </button>`
        : html`<span class="kt-sub">Chỉ Kế toán trưởng mới sinh được bút toán.</span>`}
    </div>
    <div id="jp-msg"></div>`);

  modal.body.querySelector("#jp-close").addEventListener("click", () => modal.close());
  const btn = modal.body.querySelector("#jp-create");
  if (btn) btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      // `expected_hash` là vân tay của ĐÚNG bản vừa xem — backend từ chối nếu
      // liên kết hóa đơn hoặc cấu hình tài khoản đã đổi giữa xem và sinh.
      const out = await api.mtJeCreate(advice, { expected_hash: res.plan_hash });
      toast(out.message || `Đã sinh ${(out.created || []).length} bút toán nháp`, "success");
      await renderJePreview(container, state, modal, advice);
      await loadTab(container, state);
    } catch (e) {
      btn.disabled = false;
      setHTML(modal.body.querySelector("#jp-msg"), html`
        <div class="kt-card" style="border-left:4px solid var(--kt-danger);margin-top:10px">
          <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e.message}</div></div>
        </div>`);
    }
  });
}

function jeCard(e) {
  const a = e.accounts || {};
  return html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-${e.duplicate ? "warning" : "primary"})">
      <div class="kt-card-body">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <b>${e.kind}</b>
          <span class="kt-badge kt-badge--gray">${e.event}</span>
          <span class="kt-sub">ngày ${formatDate(e.posting_date)}</span>
          <b style="margin-left:auto">${formatVND(e.total)}</b>
        </div>
        ${e.duplicate
          ? html`<div class="kt-sub" style="margin-top:6px">
              <span class="kt-badge kt-badge--yellow">đã sinh rồi</span>
              Bút toán <code>${e.duplicate}</code> mang cùng vân tay — sẽ <b>không</b> sinh lại.
              Sinh lại rồi duyệt cả hai là trừ công nợ khách gấp đôi.
            </div>`
          : ""}
        ${a.is_default_row
          ? html`<div class="kt-sub" style="margin-top:4px">Dùng dòng cấu hình <b>mặc định</b> (không có dòng riêng cho chuỗi ${a.chain || "này"}).</div>`
          : ""}
        ${e.note_no_reference
          ? html`<div class="kt-sub" style="margin-top:6px;color:var(--kt-warning)"><b>${e.note_no_reference}</b></div>`
          : ""}
        ${e.mixed_signs
          ? html`<div class="kt-sub" style="margin-top:4px">
              Nhóm này có cả dòng <b>trừ</b> lẫn dòng <b>hoàn lại</b>. Bút toán ghi số
              <b>ròng</b> ${formatVND(e.total)} — đúng bằng số chuỗi thật sự trừ. Cộng độ lớn
              từng dòng sẽ ra ${formatVND(e.amount_gross)}, tức ghi khống
              ${formatVND(e.amount_gross - e.total)}đ.
            </div>`
          : ""}

        <div class="kt-table-wrap" style="margin-top:10px;max-height:260px;overflow:auto">
          <table class="kt-table">
            <thead><tr><th>Tài khoản</th><th>Đối tượng</th><th>Hóa đơn</th><th class="num">Nợ</th><th class="num">Có</th></tr></thead>
            <tbody>
              ${(e.debit_lines || []).map((l) => html`<tr>
                <td><code>${l.account}</code></td>
                <td class="kt-sub">${l.label || ""}</td>
                <td></td>
                <td class="num">${formatVND(l.amount)}</td>
                <td></td>
              </tr>`)}
              ${(e.credit_lines || []).map((l) => html`<tr>
                <td><code>${l.account}</code></td>
                <td>${l.party_name || l.party || ""}</td>
                <td><span class="kt-sub">tổng ${l.n_rows} dòng bảng kê</span></td>
                <td></td>
                <td class="num">${formatVND(l.amount)}</td>
              </tr>`)}
            </tbody>
          </table>
        </div>

        ${e.n_invoices != null
          ? html`<div class="kt-sub" style="margin-top:8px">
              Kỳ này gạch được <b>${e.n_invoices}</b> hóa đơn${e.n_unmatched
                ? html`, còn <b style="color:var(--kt-warning)">${e.n_unmatched} dòng chưa gạch</b>
                       — tiền VẪN vào bút toán (ghi tổng), xử lý việc gạch ở tab
                       <b>Quản lý thanh toán</b>.`
                : "."}
            </div>`
          : ""}
        ${e.n_review
          ? html`<div class="kt-sub" style="margin-top:4px">
              ${e.n_review} dòng nối hóa đơn ở mức <b>Cần review</b> — không ảnh hưởng số tiền
              bút toán, nhưng phải soi tay ở màn gạch hóa đơn.
            </div>`
          : ""}
        <details style="margin-top:8px">
          <summary class="kt-sub" style="cursor:pointer">Diễn giải ghi vào bút toán</summary>
          <pre class="kt-sub" style="white-space:pre-wrap;margin:6px 0 0">${e.remark}</pre>
        </details>
      </div>
    </div>`;
}


// ── Tab 4b: Duyệt bút toán ─────────────────────────────────────────────────
//
// ĐÂY LÀ CHỖ DUY NHẤT trong toàn bộ kênh MT mà tiền thật sự vào sổ. Mọi thứ
// trước đó — nạp bảng kê, khớp hóa đơn, sinh bút toán — đều là NHÁP và xóa được.
//
// Nút duyệt CHỈ hiện với người thật sự duyệt được (kế toán trưởng). Hiện cho
// người khác chỉ tạo một cú bấm để nhận lỗi quyền.

function jeViewSwitch(state) {
  const b = (key, label, icon) => html`<button
    class="kt-btn kt-btn--sm ${state.jeView === key ? "" : "kt-btn--outline"}"
    data-jeview="${key}"><i class="fas ${icon}"></i> ${label}</button>`;
  return html`<span style="display:inline-flex;gap:6px">
    ${b("bang-ke", "Theo bảng kê", "fa-file-invoice")}
    ${b("duyet", "Chờ duyệt", "fa-stamp")}
  </span>`;
}

function bindJeViewSwitch(container, state) {
  container.querySelectorAll("[data-jeview]").forEach((b) => {
    b.addEventListener("click", () => {
      if (state.jeView === b.dataset.jeview) return;
      state.jeView = b.dataset.jeview;
      state.page = 1;
      state.jePicked = new Set();   // chọn của màn này không mang sang màn kia
      loadTab(container, state);
    });
  });
}

async function loadJeApproval(container, state) {
  const body = container.querySelector("#mt-body");
  let res;
  try {
    res = await api.mtJeDrafts({
      from_date: state.from, to_date: state.to,
      chain: state.chain || undefined,
      kind: state.jeKind || undefined,
      docstatus: state.jeDocstatus === "1" ? 1 : 0,
      search: state.search || undefined,
      page: state.page, page_size: 20,
    });
  } catch (e) {
    setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }
  const rows = res.rows || [];
  const posted = state.jeDocstatus === "1";
  // Chỉ giữ lại lựa chọn của những dòng còn trên trang — tránh duyệt nhầm một
  // bút toán đã trôi khỏi bộ lọc.
  const onPage = new Set(rows.map((r) => r.name));
  state.jePicked = new Set([...state.jePicked].filter((n) => onPage.has(n)));

  setHTML(body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body"
         style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      ${jeViewSwitch(state)}
      <label class="kt-label" style="margin:0 0 0 8px">Chuỗi</label>
      <select class="kt-input kt-input--sm" id="mt-chain">
        <option value="">Tất cả chuỗi</option>
        ${chainOptionHTML(state, state.chain)}
      </select>
      <select class="kt-input kt-input--sm" id="je-kind">
        <option value="">Mọi loại</option>
        ${(res.kinds || []).map((k) => html`<option value="${k}" ${state.jeKind === k ? "selected" : ""}>${k}</option>`)}
      </select>
      <select class="kt-input kt-input--sm" id="je-docstatus">
        <option value="0" ${!posted ? "selected" : ""}>Nháp — chờ duyệt</option>
        <option value="1" ${posted ? "selected" : ""}>Đã ghi sổ</option>
      </select>
      <span class="kt-sub" style="margin-left:auto">
        ${res.total} bút toán · ${formatVND(res.total_amount)}
      </span>
    </div></div>

    ${!posted
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body kt-sub">
          <b>Duyệt là GHI SỔ.</b> ${res.note || ""}
        </div></div>`
      : ""}

    ${!rows.length
      ? html`<div class="kt-empty"><i class="fas fa-stamp"></i>
          <p>${posted ? "Chưa có bút toán MT nào đã ghi sổ trong khoảng này."
                      : "Không còn bút toán nháp nào chờ duyệt."}</p>
          ${!posted ? html`<div class="kt-sub">Sinh bút toán ở màn <b>Theo bảng kê</b>.</div>` : ""}
        </div>`
      : html`<div class="kt-card"><div class="kt-card-body">
          ${!posted && res.can_submit
            ? html`<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
                <label style="display:flex;gap:6px;align-items:center">
                  <input type="checkbox" id="je-all"> <span class="kt-sub">Chọn cả trang</span>
                </label>
                <span class="kt-sub" id="je-count"></span>
                <button class="kt-btn kt-btn--outline kt-btn--sm" id="je-del" style="margin-left:auto" disabled>
                  <i class="fas fa-trash"></i> Xóa nháp
                </button>
                <button class="kt-btn kt-btn--primary kt-btn--sm" id="je-sub" disabled>
                  <i class="fas fa-stamp"></i> Duyệt (ghi sổ)
                </button>
              </div>`
            : ""}
          <div class="kt-table-wrap"><table class="kt-table">
            <thead><tr>
              ${!posted && res.can_submit ? html`<th style="width:32px"></th>` : ""}
              <th>Bút toán</th><th>Loại</th><th>Chuỗi</th><th>Khách hàng</th>
              <th>Ngày</th><th class="num">Số tiền</th><th>Bảng kê</th><th></th>
            </tr></thead>
            <tbody>
              ${rows.map((r) => html`<tr>
                ${!posted && res.can_submit
                  ? html`<td><input type="checkbox" class="je-pick" data-name="${r.name}"
                           ${state.jePicked.has(r.name) ? "checked" : ""}></td>`
                  : ""}
                <td><code>${r.name}</code></td>
                <td><span class="kt-badge kt-badge--${KIND_TONE[r.kind] || "gray"}">${r.kind || "—"}</span></td>
                <td><span class="kt-badge kt-badge--gray">${r.chain || "—"}</span></td>
                <td>${r.customer_name || r.customer || "—"}</td>
                <td>${formatDate(r.posting_date)}</td>
                <td class="num">${formatVND(r.amount)}</td>
                <td><code class="kt-sub">${r.advice || "—"}</code>
                  ${!r.reconciled
                    ? html`<div><span class="kt-badge kt-badge--yellow">chưa đối chiếu</span></div>`
                    : ""}</td>
                <td><button class="kt-btn kt-btn--outline kt-btn--sm je-detail" data-name="${r.name}">
                  <i class="fas fa-eye"></i></button></td>
              </tr>`)}
            </tbody>
          </table></div>
          ${pager(res, "bút toán")}
        </div></div>`}
  `);

  bindChainFilter(container, state);
  bindPager(container, state);
  bindJeViewSwitch(container, state);

  const kind = container.querySelector("#je-kind");
  if (kind) kind.addEventListener("change", (e) => {
    state.jeKind = e.target.value; state.page = 1; loadTab(container, state);
  });
  const ds = container.querySelector("#je-docstatus");
  if (ds) ds.addEventListener("change", (e) => {
    state.jeDocstatus = e.target.value;
    state.page = 1;
    state.jePicked = new Set();
    loadTab(container, state);
  });
  container.querySelectorAll(".je-detail").forEach((b) => {
    b.addEventListener("click", () => openJeDetail(container, state, b.dataset.name));
  });

  const refreshPicked = () => {
    const n = state.jePicked.size;
    const cnt = container.querySelector("#je-count");
    if (cnt) cnt.textContent = n ? `${n} bút toán đang chọn` : "";
    const sub = container.querySelector("#je-sub");
    const del = container.querySelector("#je-del");
    if (sub) sub.disabled = !n;
    if (del) del.disabled = !n;
  };
  container.querySelectorAll(".je-pick").forEach((cb) => {
    cb.addEventListener("change", () => {
      if (cb.checked) state.jePicked.add(cb.dataset.name);
      else state.jePicked.delete(cb.dataset.name);
      refreshPicked();
    });
  });
  const all = container.querySelector("#je-all");
  if (all) all.addEventListener("change", () => {
    container.querySelectorAll(".je-pick").forEach((cb) => {
      cb.checked = all.checked;
      if (all.checked) state.jePicked.add(cb.dataset.name);
      else state.jePicked.delete(cb.dataset.name);
    });
    refreshPicked();
  });
  refreshPicked();

  const sub = container.querySelector("#je-sub");
  if (sub) sub.addEventListener("click", () => doSubmitJes(container, state, rows));
  const del = container.querySelector("#je-del");
  if (del) del.addEventListener("click", () => doDeleteJes(container, state, rows));
}

// ── Duyệt hàng loạt ────────────────────────────────────────────────────────
async function doSubmitJes(container, state, rows, force) {
  const names = [...state.jePicked];
  if (!names.length) return;
  const picked = rows.filter((r) => state.jePicked.has(r.name));
  const total = picked.reduce((s, r) => s + (r.amount || 0), 0);

  const modal = openModal({
    title: "Duyệt bút toán — ghi sổ",
    icon: "fa-stamp",
    maxWidth: 720,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });

  let res;
  try {
    res = await api.mtJeSubmit(names, force ? { force_unreconciled: 1 } : {});
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-card" style="border-left:4px solid var(--kt-danger)">
      <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e.message}</div></div></div>`);
    return;
  }

  // Backend TỪ CHỐI ghi sổ khi bảng kê nguồn chưa tick đối chiếu — đây là lần
  // xác nhận có ý thức, không phải một hộp thoại cho có.
  if (res.needs_confirm) {
    setHTML(modal.body, html`
      <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-warning)"><div class="kt-card-body">
        <b>${res.message}</b>
        <div class="kt-sub" style="margin-top:8px">
          Duyệt là ghi sổ. Hủy một bút toán đã ghi để lại vết trong sổ cái mà kiểm toán sẽ hỏi —
          bút toán nháp thì xóa sạch được.
        </div>
      </div></div>
      <div class="kt-card kt-mb"><div class="kt-card-body">
        <div class="kt-table-wrap" style="max-height:280px;overflow:auto"><table class="kt-table">
          <thead><tr><th>Bút toán</th><th>Loại</th><th>Bảng kê</th><th class="num">Số tiền</th></tr></thead>
          <tbody>${(res.unreconciled || []).map((u) => html`<tr>
            <td><code>${u.name}</code></td><td>${u.kind}</td>
            <td><code class="kt-sub">${u.advice}</code></td>
            <td class="num">${formatVND(u.amount)}</td>
          </tr>`)}</tbody>
        </table></div>
      </div></div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="kt-btn kt-btn--outline" id="jc-cancel">Để tôi soi lại</button>
        <button class="kt-btn kt-btn--danger" id="jc-force">
          <i class="fas fa-stamp"></i> Vẫn duyệt ${names.length} bút toán (${formatVND(total)})
        </button>
      </div>`);
    modal.body.querySelector("#jc-cancel").addEventListener("click", () => modal.close());
    modal.body.querySelector("#jc-force").addEventListener("click", () => {
      modal.close();
      doSubmitJes(container, state, rows, true);
    });
    return;
  }

  setHTML(modal.body, jeBatchResult(res.message, res.submitted || [], res.failed || [], "đã ghi sổ"));
  modal.body.querySelector("#jr-close").addEventListener("click", () => modal.close());
  toast(res.message, (res.failed || []).length ? "error" : "success");
  state.jePicked = new Set();
  await loadTab(container, state);
}

async function doDeleteJes(container, state, rows) {
  const names = [...state.jePicked];
  if (!names.length) return;
  const modal = openModal({
    title: "Xóa bút toán nháp",
    icon: "fa-trash",
    maxWidth: 640,
    body: html`
      <div class="kt-card kt-mb"><div class="kt-card-body">
        Xóa <b>${names.length}</b> bút toán <b>nháp</b>. Chưa ghi sổ nên xóa sạch, không để lại vết.
        <div class="kt-sub" style="margin-top:6px">
          Sinh lại được ngay sau khi sửa bảng kê — vân tay chống trùng chỉ chặn khi bản nháp cũ còn đó.
        </div>
      </div></div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="kt-btn kt-btn--outline" id="jd-cancel">Hủy</button>
        <button class="kt-btn kt-btn--danger" id="jd-ok"><i class="fas fa-trash"></i> Xóa</button>
      </div>
      <div id="jd-msg"></div>`,
  });
  modal.body.querySelector("#jd-cancel").addEventListener("click", () => modal.close());
  modal.body.querySelector("#jd-ok").addEventListener("click", async () => {
    const btn = modal.body.querySelector("#jd-ok");
    btn.disabled = true;
    try {
      const res = await api.mtJeDeleteDrafts(names);
      setHTML(modal.body, jeBatchResult(res.message,
        (res.deleted || []).map((n) => ({ name: n })), res.failed || [], "đã xóa"));
      modal.body.querySelector("#jr-close").addEventListener("click", () => modal.close());
      toast(res.message, (res.failed || []).length ? "error" : "success");
      state.jePicked = new Set();
      await loadTab(container, state);
    } catch (e) {
      btn.disabled = false;
      setHTML(modal.body.querySelector("#jd-msg"), html`
        <div class="kt-card" style="border-left:4px solid var(--kt-danger);margin-top:10px">
          <div class="kt-card-body"><div class="kt-sub" style="white-space:pre-wrap">${e.message}</div></div>
        </div>`);
    }
  });
}

// Kết quả TỪNG BÚT TOÁN — không gộp thành một chữ "xong". Duyệt 20 cái mà 3 cái
// hỏng thì kế toán phải biết ĐÍCH DANH ba cái nào.
function jeBatchResult(message, done, failed, verb) {
  return html`
    <div class="kt-card kt-mb" style="border-left:4px solid var(--kt-${failed.length ? "warning" : "success"})">
      <div class="kt-card-body"><b>${message}</b></div>
    </div>
    ${done.length
      ? html`<div class="kt-card kt-mb"><div class="kt-card-body">
          <div class="kt-sub" style="margin-bottom:6px">${done.length} bút toán ${verb}</div>
          <div class="kt-table-wrap" style="max-height:220px;overflow:auto"><table class="kt-table">
            <tbody>${done.map((d) => html`<tr>
              <td><code>${d.name}</code></td>
              <td>${d.kind || ""}</td>
              <td class="num">${d.amount != null ? formatVND(d.amount) : ""}</td>
            </tr>`)}</tbody>
          </table></div>
        </div></div>`
      : ""}
    ${failed.length
      ? html`<div class="kt-card kt-mb" style="border-left:4px solid var(--kt-danger)"><div class="kt-card-body">
          <b style="color:var(--kt-danger)">${failed.length} bút toán KHÔNG xử lý được</b>
          ${failed.map((f) => html`<div class="kt-sub" style="margin-top:6px">
            • <code>${f.name}</code>: ${f.error}</div>`)}
        </div></div>`
      : ""}
    <div style="display:flex;justify-content:flex-end">
      <button class="kt-btn kt-btn--outline" id="jr-close">Đóng</button>
    </div>`;
}

// ── Soi một bút toán trước khi duyệt ───────────────────────────────────────
async function openJeDetail(container, state, name) {
  const modal = openModal({
    title: "Bút toán " + name,
    icon: "fa-file-invoice-dollar",
    maxWidth: 860,
    body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>`,
  });
  let res;
  try {
    res = await api.mtJeDetail(name);
  } catch (e) {
    setHTML(modal.body, html`<div class="kt-empty kt-empty--error"><p>${e.message}</p></div>`);
    return;
  }
  const d = res.doc || {};
  const draft = Number(d.docstatus) === 0;

  setHTML(modal.body, html`
    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <span class="kt-badge kt-badge--${KIND_TONE[d.kind] || "gray"}">${d.kind || "—"}</span>
        <span class="kt-badge kt-badge--gray">${d.chain || "—"}</span>
        <span class="kt-badge kt-badge--${draft ? "yellow" : "green"}">${draft ? "Nháp — chưa ghi sổ" : "Đã ghi sổ"}</span>
        ${!d.reconciled ? html`<span class="kt-badge kt-badge--yellow">bảng kê chưa tick đối chiếu</span>` : ""}
        <span class="kt-sub">ngày ${formatDate(d.posting_date)}</span>
        <b style="margin-left:auto">${formatVND(d.total_debit)}</b>
      </div>
      <div class="kt-sub" style="margin-top:6px">
        Bảng kê nguồn <code>${d.advice || "—"}</code>${d.advice_no ? ` · ${d.advice_no}` : ""}
        ${d.file_name ? ` · file ${d.file_name}` : ""}
      </div>
    </div></div>

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr><th>Tài khoản</th><th>Đối tượng</th><th class="num">Nợ</th><th class="num">Có</th></tr></thead>
        <tbody>
          ${(res.lines || []).map((l) => html`<tr>
            <td><code>${l.account_number || ""}</code> ${l.account_name || l.account}</td>
            <td>${l.party || ""}</td>
            <td class="num">${l.debit ? formatVND(l.debit) : ""}</td>
            <td class="num">${l.credit ? formatVND(l.credit) : ""}</td>
          </tr>`)}
        </tbody>
      </table></div>
    </div></div>

    <div class="kt-card kt-mb"><div class="kt-card-body">
      <div class="kt-sub" style="margin-bottom:6px">Diễn giải</div>
      <pre class="kt-sub" style="white-space:pre-wrap;margin:0">${res.remark || "(trống)"}</pre>
    </div></div>

    <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center">
      <a class="kt-btn kt-btn--outline kt-btn--sm" href="${res.desk_url}" target="_blank">
        <i class="fas fa-arrow-up-right-from-square"></i> Mở trên Desk</a>
      <button class="kt-btn kt-btn--outline" id="jd2-close">Đóng</button>
      ${draft && res.can_submit
        ? html`<button class="kt-btn kt-btn--primary" id="jd2-sub"><i class="fas fa-stamp"></i> Duyệt bút toán này</button>`
        : ""}
    </div>`);

  modal.body.querySelector("#jd2-close").addEventListener("click", () => modal.close());
  const sub = modal.body.querySelector("#jd2-sub");
  if (sub) sub.addEventListener("click", async () => {
    modal.close();
    state.jePicked = new Set([name]);
    await doSubmitJes(container, state, [{ name, amount: d.total_debit }]);
  });
}
