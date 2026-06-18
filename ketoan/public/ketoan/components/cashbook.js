// components/cashbook.js — modal "Nhập sổ quỹ": tạo Journal Entry (Thu/Chi) + QR VietQR.
// Shared module → PHẢI có trong import map của www page.
import { openModal } from "./modal.js";
import { toast } from "./toast.js";
import { api } from "../lib/api.js";
import { html } from "../lib/dom.js";
import { formatVND } from "../lib/format.js";

// BIN VietQR các ngân hàng phổ biến.
const BANKS = [
  ["970436", "Vietcombank"], ["970422", "MB Bank"], ["970415", "VietinBank"],
  ["970418", "BIDV"], ["970405", "Agribank"], ["970407", "Techcombank"],
  ["970416", "ACB"], ["970423", "TPBank"], ["970432", "VPBank"],
  ["970403", "Sacombank"], ["970437", "HDBank"], ["970448", "OCB"],
];
const QUICK = [100000, 200000, 500000, 1000000, 2000000, 5000000];

export async function openCashbook({ onDone } = {}) {
  let opts = { cash_accounts: [], counter_accounts: [] };
  try {
    opts = await api.cashbookOptions();
  } catch (e) {
    toast("Không tải được tùy chọn: " + e.message, "error");
    return;
  }
  const today = new Date().toISOString().slice(0, 10);

  const m = openModal({
    title: "Nhập sổ quỹ",
    icon: "fa-money-bill-wave",
    maxWidth: 540,
    body: html`
      <div class="kt-field">
        <label><i class="fas fa-right-left"></i> Loại phiếu</label>
        <div class="kt-segment" id="cb-type">
          <button type="button" data-type="Chi" class="is-active">Chi tiền</button>
          <button type="button" data-type="Thu">Thu tiền</button>
        </div>
      </div>
      <div class="kt-row2">
        <div class="kt-field"><label><i class="fas fa-calendar"></i> Ngày *</label>
          <input type="date" id="cb-date" class="kt-input" value="${today}" max="${today}"></div>
        <div class="kt-field"><label><i class="fas fa-coins"></i> Số tiền (₫) *</label>
          <input type="number" id="cb-amount" class="kt-input" placeholder="0" min="0"></div>
      </div>
      <div class="kt-chips" id="cb-chips">
        ${QUICK.map((a) => html`<button type="button" class="kt-chip" data-amt="${a}">+${a / 1000 >= 1000 ? a / 1e6 + "tr" : a / 1000 + "k"}</button>`)}
        <button type="button" class="kt-chip" data-amt="0">Xóa</button>
      </div>
      <div class="kt-field" style="margin-top:12px"><label><i class="fas fa-align-left"></i> Nội dung *</label>
        <textarea id="cb-content" class="kt-textarea" placeholder="VD: Chi đổ dầu xe 29C-12345..."></textarea></div>
      <div class="kt-row2">
        <div class="kt-field"><label><i class="fas fa-wallet"></i> TK quỹ (tiền) *</label>
          <select id="cb-cash" class="kt-select">${opts.cash_accounts.map((a) => html`<option value="${a.name}">${a.account_name || a.name}</option>`)}</select></div>
        <div class="kt-field"><label><i class="fas fa-right-left"></i> TK đối ứng *</label>
          <select id="cb-counter" class="kt-select">${opts.counter_accounts.map((a) => html`<option value="${a.name}">${a.account_name || a.name}</option>`)}</select></div>
      </div>
      <div class="kt-field"><label><i class="fas fa-user"></i> Khách hàng (tùy chọn — để đối trừ công nợ)</label>
        <input id="cb-customer" class="kt-input" placeholder="Mã khách hàng (bỏ trống nếu không gắn)"></div>

      <div class="kt-divider"><i class="fas fa-qrcode"></i> QR chuyển khoản (tùy chọn)</div>
      <div class="kt-row2">
        <div class="kt-field"><label><i class="fas fa-university"></i> Ngân hàng</label>
          <select id="cb-bank" class="kt-select"><option value="">— Chọn NH —</option>${BANKS.map((b) => html`<option value="${b[0]}">${b[1]}</option>`)}</select></div>
        <div class="kt-field"><label><i class="fas fa-hashtag"></i> Số TK</label>
          <input id="cb-accno" class="kt-input" placeholder="Số tài khoản"></div>
      </div>
      <div class="kt-field"><label><i class="fas fa-id-card"></i> Tên chủ TK</label>
        <input id="cb-accname" class="kt-input" placeholder="NGUYEN VAN A" style="text-transform:uppercase"></div>
      <div class="kt-qr" id="cb-qr"><img id="cb-qr-img" alt="QR"><div style="font-size:12px;color:var(--kt-text-2);margin-top:8px">Quét để chuyển khoản</div></div>

      <div class="kt-modal-actions">
        <button class="kt-btn kt-btn--outline" id="cb-cancel">Hủy</button>
        <button class="kt-btn kt-btn--success" id="cb-save"><i class="fas fa-check"></i> Tạo phiếu (nháp)</button>
      </div>
    `,
  });

  const $ = (id) => m.body.querySelector(id);
  let entryType = "Chi";

  $("#cb-type").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-type]");
    if (!b) return;
    entryType = b.dataset.type;
    m.body.querySelectorAll("#cb-type button").forEach((x) => x.classList.toggle("is-active", x === b));
  });

  $("#cb-chips").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-amt]");
    if (!b) return;
    const amt = Number(b.dataset.amt);
    const inp = $("#cb-amount");
    inp.value = amt === 0 ? "" : String((Number(inp.value) || 0) + amt);
    updateQR();
  });

  ["#cb-amount", "#cb-bank", "#cb-accno", "#cb-accname", "#cb-content"].forEach((id) =>
    $(id).addEventListener("input", updateQR)
  );

  function updateQR() {
    const bank = $("#cb-bank").value, accno = $("#cb-accno").value.trim();
    const amount = Number($("#cb-amount").value) || 0;
    const qr = $("#cb-qr");
    if (!bank || !accno || amount <= 0) { qr.classList.remove("is-show"); return; }
    const url = `https://img.vietqr.io/image/${bank}-${accno}-compact2.png?amount=${amount}`
      + `&addInfo=${encodeURIComponent($("#cb-content").value || "Thanh toan")}`
      + `&accountName=${encodeURIComponent($("#cb-accname").value || "")}`;
    $("#cb-qr-img").src = url;
    qr.classList.add("is-show");
  }

  $("#cb-cancel").addEventListener("click", m.close);
  $("#cb-save").addEventListener("click", async () => {
    const payload = {
      entry_type: entryType,
      posting_date: $("#cb-date").value,
      amount: Number($("#cb-amount").value) || 0,
      content: $("#cb-content").value.trim(),
      cash_account: $("#cb-cash").value,
      counter_account: $("#cb-counter").value,
      customer: $("#cb-customer").value.trim() || null,
    };
    if (payload.amount <= 0) { toast("Nhập số tiền > 0", "warning"); return; }
    if (!payload.content) { toast("Nhập nội dung", "warning"); return; }

    const btn = $("#cb-save");
    btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang tạo...';
    try {
      const res = await api.cashbookCreate(payload);
      toast(`Đã tạo ${res.name} (${res.docstatus === 1 ? "đã ghi sổ" : "nháp"})`, "success");
      m.close();
      if (typeof onDone === "function") onDone(res);
      if (res.route) window.open(res.route, "_blank");
    } catch (e) {
      toast(e.message, "error");
      btn.disabled = false; btn.innerHTML = '<i class="fas fa-check"></i> Tạo phiếu (nháp)';
    }
  });
}
