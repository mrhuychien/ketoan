// views/receivables.js — bảng kê công nợ theo khách + tuổi nợ, tìm kiếm, vào 360°.
import { api } from "../lib/api.js";
import { html, setHTML, on } from "../lib/dom.js";
import { formatVND, formatVNDShort, escapeHtml } from "../lib/format.js";
import { navigate } from "../lib/router.js";
import { openModal } from "../components/modal.js";
import { toast } from "../components/toast.js";

const CHANNEL_LABEL = { npp: "kênh NPP", mt: "kênh MT", khac: "kênh Du lịch, Khác", "tat-ca": "toàn bộ" };
// Kênh → workspace có trang "Hướng dẫn & lối tắt" tương ứng.
const CHANNEL_HELP = { npp: "npp", mt: "mt", khac: "travel" };

export async function render({ container, params }) {
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
  const maxAging = Math.max(1, ...aging.buckets.map((b) => b.amount));

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
  const search = container.querySelector("#kt-ar-search");
  const body = container.querySelector("#kt-ar-body");
  search.addEventListener("input", () => {
    const q = search.value.toLowerCase().trim();
    const filtered = !q ? rows : rows.filter((r) => (r.customer_name || r.customer || "").toLowerCase().includes(q));
    setHTML(body, filtered.map((r) => rowHtml(r)).join(""));
  });

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
