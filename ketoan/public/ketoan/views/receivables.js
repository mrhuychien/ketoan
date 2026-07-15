// views/receivables.js — công nợ theo khách + tuổi nợ (tab Công nợ)
// và soát GIÁ BÁN vs Bảng giá bán hàng của kênh (tab Giá bán).
import { api } from "../lib/api.js";
import { html, setHTML, on } from "../lib/dom.js";
import { formatVND, formatVNDShort, formatDate } from "../lib/format.js";
import { navigate } from "../lib/router.js";
import { openModal } from "../components/modal.js";
import { toast } from "../components/toast.js";

const CHANNEL_LABEL = { npp: "kênh NPP", mt: "kênh MT", khac: "kênh Du lịch, Khác", "tat-ca": "toàn bộ" };
// Kênh → workspace có trang "Hướng dẫn & lối tắt" tương ứng.
const CHANNEL_HELP = { npp: "npp", mt: "mt", khac: "travel" };

export async function render({ container, params, query }) {
  const channel = (params && params.channel) || "tat-ca";
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let summary, aging;
  try {
    [summary, aging] = await Promise.all([api.arSummary(channel), api.aging(channel)]);
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  const rows = summary.rows;
  const state = { tab: query && query.tab === "gia" ? "gia" : "congno" };

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div>
          <div class="kt-view-title"><i class="fas fa-file-invoice-dollar"></i> Công nợ phải thu — ${CHANNEL_LABEL[channel] || channel}</div>
          <div class="kt-sub">${summary.count} khách · tổng ${formatVND(summary.total)}</div>
        </div>
        ${CHANNEL_HELP[channel]
          ? html`<a class="kt-btn kt-btn--outline kt-btn--sm" href="#/vt/${CHANNEL_HELP[channel]}"><i class="fas fa-book-open"></i> Hướng dẫn &amp; lối tắt</a>`
          : ""}
      </div>

      <div class="kt-segment kt-mb" id="ar-tabs">
        <button data-tab="congno" class="${state.tab === "congno" ? "is-active" : ""}">Công nợ</button>
        <button data-tab="gia" class="${state.tab === "gia" ? "is-active" : ""}">Giá bán vs bảng giá</button>
      </div>
      <div id="ar-tab-body"></div>
    `
  );

  const body = container.querySelector("#ar-tab-body");

  container.querySelector("#ar-tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-tab]");
    if (!b) return;
    state.tab = b.dataset.tab;
    container.querySelectorAll("#ar-tabs button").forEach((x) => x.classList.toggle("is-active", x === b));
    renderTab();
  });

  function renderTab() {
    if (state.tab === "gia") renderSellingPrices(body, channel, state);
    else renderCongNo(body, rows, aging);
  }

  // Click hàng → 360° (bỏ qua khi bấm nút Zalo/PDF trên dòng)
  on(container, "click", "[data-customer]", (e, el) => {
    if (e.target.closest("button,a")) return;
    navigate("/khach/" + encodeURIComponent(el.dataset.customer));
  });

  // Nhắc nợ Zalo / xuất biên bản đối chiếu ngay trên dòng.
  const findRow = (c) => rows.find((r) => r.customer === c);
  on(container, "click", ".ar-zalo", (e, el) => {
    e.stopPropagation();
    const r = findRow(el.dataset.c);
    if (r) openZaloReminder(r);
  });
  on(container, "click", ".ar-pdf", (e, el) => {
    e.stopPropagation();
    const r = findRow(el.dataset.c);
    if (r) openReconExport(r);
  });

  renderTab();
}

/* ---------- Tab 1: Công nợ (tuổi nợ + bảng kê) ---------- */
function renderCongNo(body, rows, aging) {
  const maxAging = Math.max(1, ...aging.buckets.map((b) => b.amount));
  setHTML(
    body,
    html`
      <div class="kt-card kt-mb">
        <div class="kt-card-head"><div class="kt-card-title"><i class="fas fa-layer-group"></i> Tuổi nợ</div></div>
        <div class="kt-card-body"><div class="kt-aging">
          ${aging.buckets.map(
            (b) => html`<div class="kt-aging-row"><span>${b.label}</span>
              <div class="kt-aging-track"><div class="kt-aging-fill" style="width:${Math.round((b.amount / maxAging) * 100)}%;background:${b.key === "over" ? "var(--kt-danger)" : b.key === "current" ? "var(--kt-success)" : "var(--kt-warning)"}"></div></div>
              <span class="kt-aging-amt">${formatVNDShort(b.amount)}</span></div>`
          )}
        </div></div>
      </div>

      <div class="kt-card">
        <div class="kt-card-head">
          <div class="kt-card-title"><i class="fas fa-users"></i> Bảng kê theo khách</div>
          <div class="kt-search"><i class="fas fa-search"></i><input class="kt-input" id="kt-ar-search" placeholder="Tìm khách..."></div>
        </div>
        <div class="kt-card-body">
          <div class="kt-table-wrap">
            <table class="kt-table">
              <thead><tr><th>Khách hàng</th><th>Nhóm</th><th class="num">Công nợ</th><th class="num">Quá hạn</th><th></th></tr></thead>
              <tbody id="kt-ar-body">
                ${rows.map((r) => rowHtml(r))}
              </tbody>
            </table>
          </div>
          ${rows.length === 0 ? html`<div class="kt-empty"><i class="fas fa-circle-check"></i><p>Không có công nợ</p></div>` : ""}
        </div>
      </div>
    `
  );

  // Tìm kiếm client-side
  const search = body.querySelector("#kt-ar-search");
  const tbody = body.querySelector("#kt-ar-body");
  search.addEventListener("input", () => {
    const q = search.value.toLowerCase().trim();
    const filtered = !q ? rows : rows.filter((r) => (r.customer_name || r.customer || "").toLowerCase().includes(q));
    setHTML(tbody, filtered.map((r) => rowHtml(r)).join(""));
  });
}

/* ---------- Tab 2: Soát giá bán vs Bảng giá (cảnh báo lệch không có Pricing Rule) ---------- */
const SP_DAYS = [30, 90, 180];

async function renderSellingPrices(body, channel, state) {
  if (state.spDays == null) state.spDays = 90;
  if (state.spTol == null) state.spTol = 1;
  if (state.spSearch == null) state.spSearch = "";
  setHTML(body, html`<div class="kt-boot"><div class="kt-spinner"></div><p>Đang quét hóa đơn bán…</p></div>`);
  let d;
  try { d = await api.sellingPriceWatch(channel, { days: state.spDays, tolerance: state.spTol }); }
  catch (e) { setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`); return; }

  const draw = () => {
    const qs = (state.spSearch || "").toLowerCase().trim();
    const items = !qs ? d.rows : d.rows.filter((r) =>
      (r.item_name || "").toLowerCase().includes(qs) || (r.item_code || "").toLowerCase().includes(qs));
    setHTML(
      body,
      html`
        <div class="kt-stats">
          <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-boxes-stacked"></i> Mặt hàng đã bán</div>
            <div class="kt-stat-value">${d.item_count}</div>
            <div class="kt-stat-sub">${d.days} ngày · quét Sales Invoice</div></div>
          <div class="kt-stat"><div class="kt-stat-label"><i class="fas fa-triangle-exclamation"></i> Mặt hàng có vi phạm</div>
            <div class="kt-stat-value ${d.alert_count ? "neg" : "pos"}">${d.alert_count}</div>
            <div class="kt-stat-sub">${d.viol_lines} dòng lệch bảng giá không có Pricing Rule / chưa có giá</div></div>
        </div>

        <div class="kt-card">
          <div class="kt-card-head">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
              <div class="kt-segment" id="sp-days">
                ${SP_DAYS.map((n) => html`<button data-d="${n}" class="${n === state.spDays ? "is-active" : ""}">${n} ngày</button>`)}
              </div>
              <label class="kt-sub" style="display:flex;align-items:center;gap:6px">Dung sai %
                <input type="number" id="sp-tol" class="kt-input" style="width:70px" min="0.1" step="0.5" value="${state.spTol}"></label>
            </div>
            <div class="kt-search"><i class="fas fa-search"></i><input class="kt-input" id="sp-search" placeholder="Tìm mặt hàng..." value="${state.spSearch}"></div>
          </div>
          <div class="kt-card-body">
            <div class="kt-table-wrap"><table class="kt-table">
              <thead><tr><th>Mặt hàng</th><th>Bảng giá</th><th class="num">Lần bán</th>
                <th class="num">Lệch không rule</th><th class="num">Chưa có giá</th>
                <th>Vi phạm gần nhất</th><th></th></tr></thead>
              <tbody>${items.map((r) => spRow(r))}</tbody>
            </table></div>
            ${items.length === 0 ? html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Không có mặt hàng nào trong kỳ</p></div>` : ""}
            ${d.truncated ? html`<p class="kt-sub" style="margin-top:8px">⚠ Kỳ này quá 20.000 dòng bán — thu hẹp số ngày để quét đủ.</p>` : ""}
            <p class="kt-sub" style="margin-top:8px">Vi phạm = giá bán lệch <b>price_list_rate</b> (giá Bảng giá trên chính dòng hóa đơn) quá dung sai mà <b>không có Pricing Rule</b> áp; hoặc bán khi bảng giá chưa có giá. Bấm dòng để xem từng hóa đơn.</p>
          </div>
        </div>
      `
    );

    body.querySelector("#sp-days").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-d]");
      if (!b) return;
      state.spDays = parseInt(b.dataset.d, 10);
      renderSellingPrices(body, channel, state);
    });
    body.querySelector("#sp-tol").addEventListener("change", (e) => {
      state.spTol = Math.max(0.1, parseFloat(e.target.value || "1"));
      renderSellingPrices(body, channel, state);
    });
    const search = body.querySelector("#sp-search");
    let timer = null;
    search.addEventListener("input", () => {
      state.spSearch = search.value;
      clearTimeout(timer);
      timer = setTimeout(draw, 200);
    });
    body.querySelectorAll("[data-sp-item]").forEach((tr) =>
      tr.addEventListener("click", (e) => {
        if (e.target.closest("a")) return;
        const r = d.rows.find((x) => x.item_code === tr.dataset.spItem);
        if (r) openSpViolations(r);
      })
    );
  };
  draw();
}

function spDiffBadge(v) {
  if (v.type === "no_price") return html`<span class="kt-badge kt-badge--yellow">chưa có giá</span>`;
  return v.diff_pct > 0
    ? html`<span class="kt-badge kt-badge--red">▲ +${v.diff_pct}%</span>`
    : html`<span class="kt-badge kt-badge--red">▼ ${v.diff_pct}%</span>`;
}

function spRow(r) {
  const v = r.last_viol;
  return html`<tr class="kt-row-link" data-sp-item="${r.item_code}" style="${r.alert ? "background:#fef2f2" : ""}">
    <td style="max-width:220px;white-space:normal">${r.alert ? html`<i class="fas fa-triangle-exclamation" style="color:var(--kt-danger)"></i> ` : ""}<b>${r.item_name}</b><br><span class="kt-sub">${r.item_code} · ${r.uom}</span></td>
    <td style="font-size:12px;max-width:150px;white-space:normal">${r.price_lists.length ? r.price_lists.join(", ") : "—"}</td>
    <td class="num">${r.sold}</td>
    <td class="num ${r.off_price_count ? "danger" : ""}">${r.off_price_count || "—"}</td>
    <td class="num ${r.no_price_count ? "danger" : ""}">${r.no_price_count || "—"}</td>
    <td style="font-size:12px;white-space:normal;max-width:260px">${v
      ? html`${formatDate(v.date)} · ${v.customer}<br>bán <b>${formatVND(v.rate)}</b> / bảng giá ${v.price_list_rate ? formatVND(v.price_list_rate) : "—"} ${spDiffBadge(v)}`
      : html`<span class="kt-badge kt-badge--green"><i class="fas fa-check"></i> Đúng bảng giá</span>`}</td>
    <td class="num"><span class="kt-btn-icon"><i class="fas fa-chevron-right"></i></span></td>
  </tr>`;
}

function openSpViolations(r) {
  const m = openModal({ title: "Vi phạm giá bán — " + r.item_name, icon: "fa-triangle-exclamation", maxWidth: 760,
    body: html`
      <p class="kt-sub kt-mb">${r.item_code} · ${r.viol_count} vi phạm trong kỳ (hiện tối đa 8 gần nhất)</p>
      <div class="kt-table-wrap"><table class="kt-table">
        <thead><tr><th>Ngày</th><th>Khách</th><th>Bảng giá</th><th class="num">Giá bảng giá</th><th class="num">Giá bán</th><th class="num">Lệch</th><th></th></tr></thead>
        <tbody>${(r.recent_viols || []).map((v) => html`<tr>
          <td>${formatDate(v.date)}</td>
          <td style="max-width:180px;white-space:normal;font-size:12px">${v.customer}</td>
          <td style="font-size:12px">${v.price_list || "—"}</td>
          <td class="num">${v.price_list_rate ? formatVND(v.price_list_rate) : "—"}</td>
          <td class="num"><b>${formatVND(v.rate)}</b></td>
          <td class="num">${spDiffBadge(v)}</td>
          <td class="num"><a class="kt-btn-icon" target="_blank" href="${v.route}" title="Mở hóa đơn"><i class="fas fa-up-right-from-square"></i></a></td>
        </tr>`)}</tbody>
      </table></div>
      <p class="kt-sub" style="margin-top:8px">Xử lý: hoặc tạo <b>Pricing Rule</b> cho chương trình giảm giá, hoặc cập nhật Bảng giá, hoặc sửa lại giá trên hóa đơn.</p>`,
  });
  return m;
}

function rowHtml(r) {
  const overdue = r.days_overdue > 0;
  return html`
    <tr class="kt-row-link" data-customer="${r.customer}">
      <td>${r.customer_name || r.customer}</td>
      <td>${r.customer_group ? html`<span class="kt-badge kt-badge--gray">${r.customer_group}</span>` : "—"}</td>
      <td class="num">${formatVND(r.outstanding)}</td>
      <td class="num ${overdue ? "danger" : "pos"}">${overdue ? "quá " + r.days_overdue + " ngày" : "trong hạn"}</td>
      <td class="num" style="white-space:nowrap">
        <button class="kt-btn-icon ar-zalo" data-c="${r.customer}" title="Nhắc nợ Zalo"><i class="fas fa-comment-dots"></i></button>
        <button class="kt-btn-icon ar-pdf" data-c="${r.customer}" title="Xuất biên bản đối chiếu (PDF)"><i class="fas fa-file-pdf"></i></button>
        <span class="kt-btn-icon"><i class="fas fa-chevron-right"></i></span>
      </td>
    </tr>`;
}

// ── Nhắc nợ Zalo cho 1 khách trong bảng kê ─────────────────────────────────
function openZaloReminder(r) {
  const overdue = r.days_overdue > 0;
  const msg = [
    `Kính gửi Quý khách ${r.customer_name || r.customer},`,
    ``,
    `Công ty Cổ phần Hoàng Giang xin thông báo công nợ hiện tại:`,
    `• Tổng công nợ: ${formatVND(r.outstanding)}`,
    overdue ? `• Trong đó có khoản đã quá hạn ${r.days_overdue} ngày.` : `• Các khoản đang trong hạn thanh toán.`,
    ``,
    `Kính mong Quý khách sắp xếp thanh toán đúng hạn. Trân trọng cảm ơn!`,
    `— Phòng Kế toán, Rồng Vàng Hoàng Gia`,
  ].join("\n");

  const m = openModal({
    title: "Tin nhắn nhắc nợ Zalo",
    icon: "fa-comment-dots",
    maxWidth: 480,
    body: html`
      <div class="kt-field"><label><i class="fas fa-user"></i> ${r.customer_name || r.customer}</label>
        <textarea class="kt-textarea" id="ar-zalo-msg" style="min-height:180px">${msg}</textarea></div>
      <div class="kt-modal-actions">
        <button class="kt-btn kt-btn--outline" id="ar-zalo-close">Đóng</button>
        <button class="kt-btn kt-btn--primary" id="ar-zalo-copy"><i class="fas fa-copy"></i> Sao chép</button>
      </div>`,
  });
  m.body.querySelector("#ar-zalo-close").addEventListener("click", m.close);
  m.body.querySelector("#ar-zalo-copy").addEventListener("click", async () => {
    const text = m.body.querySelector("#ar-zalo-msg").value;
    try { await navigator.clipboard.writeText(text); toast("Đã sao chép tin nhắn", "success"); }
    catch (_) { m.body.querySelector("#ar-zalo-msg").select(); document.execCommand("copy"); toast("Đã sao chép", "success"); }
  });
}

// ── Xuất biên bản đối chiếu (PDF) cho 1 khách trong bảng kê ────────────────
function openReconExport(r) {
  const todayStr = new Date().toISOString().slice(0, 10);
  const yearStart = todayStr.slice(0, 4) + "-01-01";
  const m = openModal({
    title: "Xuất biên bản đối chiếu công nợ",
    icon: "fa-file-pdf",
    maxWidth: 460,
    body: html`
      <p class="kt-sub kt-mb">Khách: <b>${r.customer_name || r.customer}</b></p>
      <div class="kt-row2">
        <div class="kt-field"><label><i class="fas fa-calendar"></i> Từ ngày</label>
          <input type="date" id="ar-rc-from" class="kt-input" value="${yearStart}"></div>
        <div class="kt-field"><label><i class="fas fa-calendar"></i> Đến ngày</label>
          <input type="date" id="ar-rc-to" class="kt-input" value="${todayStr}" max="${todayStr}"></div>
      </div>
      <div class="kt-modal-actions">
        <button class="kt-btn kt-btn--outline" id="ar-rc-cancel">Hủy</button>
        <button class="kt-btn kt-btn--primary" id="ar-rc-go"><i class="fas fa-download"></i> Tải PDF</button>
      </div>`,
  });
  m.body.querySelector("#ar-rc-cancel").addEventListener("click", m.close);
  const goBtn = m.body.querySelector("#ar-rc-go");
  goBtn.addEventListener("click", async () => {
    goBtn.disabled = true;
    goBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang tạo PDF…';
    try {
      await api.nppExportRecon(r.customer, m.body.querySelector("#ar-rc-from").value, m.body.querySelector("#ar-rc-to").value);
      m.close();
    } catch (e) {
      toast(e.message, "error");
      goBtn.disabled = false;
      goBtn.innerHTML = '<i class="fas fa-download"></i> Tải PDF';
    }
  });
}
