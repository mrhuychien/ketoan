// views/bankimport.js — Nhập sổ quỹ từ file sao kê ngân hàng (Excel).
import { api } from "../lib/api.js";
import { html, setHTML, raw } from "../lib/dom.js";
import { formatVND, escapeHtml } from "../lib/format.js";
import { toast } from "../components/toast.js";
import { openModal } from "../components/modal.js";

export async function render({ container }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let opts;
  try {
    opts = await api.bankImportOptions();
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  const state = { txns: [], options: opts };
  const counterOpts = '<option value=""></option>' +
    opts.counter_accounts.map((a) => `<option value="${escapeHtml(a.name)}">${escapeHtml(a.account_name || a.name)}</option>`).join("");

  setHTML(
    container,
    html`
      <div class="kt-view-head">
        <div class="kt-view-title"><i class="fas fa-file-import"></i> Nhập sổ quỹ từ sao kê ngân hàng</div>
        <a class="kt-btn kt-btn--outline kt-btn--sm" href="#/quy"><i class="fas fa-arrow-left"></i> Sổ quỹ</a>
      </div>

      <div class="kt-card kt-mb">
        <div class="kt-card-body">
          <div class="kt-row2">
            <div class="kt-field"><label><i class="fas fa-building-columns"></i> Tài khoản ngân hàng (112)</label>
              <select id="bi-bank" class="kt-select">
                ${opts.bank_accounts.map((a) => html`<option value="${a.name}" ${a.name === opts.suggested_bank ? "selected" : ""}>${a.account_name || a.name}</option>`)}
              </select></div>
            <div class="kt-field"><label><i class="fas fa-file-excel"></i> File sao kê (.xlsx)</label>
              <input type="file" id="bi-file" class="kt-input" accept=".xlsx"></div>
          </div>
          <p class="kt-sub">Cột: Số tham chiếu · Ngày · Ghi nợ (tiền ra) · Ghi có (tiền vào) · Số dư · Nội dung. Giao dịch đã nhập trước sẽ tự lọc trùng.</p>
        </div>
      </div>

      <div id="bi-result"></div>
    `
  );

  const fileInput = container.querySelector("#bi-file");
  const result = container.querySelector("#bi-result");

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    setHTML(result, html`<div class="kt-boot"><div class="kt-spinner"></div><p>Đang đọc file…</p></div>`);
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const res = await api.bankParse(reader.result);
        state.txns = res.transactions || [];
        renderTable();
      } catch (e) {
        setHTML(result, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
      }
    };
    reader.onerror = () => toast("Không đọc được file", "error");
    reader.readAsDataURL(file);
  });

  function renderTable() {
    const txns = state.txns;
    const dups = txns.filter((t) => t.duplicate).length;
    const fresh = txns.filter((t) => !t.duplicate && !t.created).length;

    if (!txns.length) {
      setHTML(result, html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Không có giao dịch trong file</p></div>`);
      return;
    }

    setHTML(
      result,
      html`
        <div class="kt-card">
          <div class="kt-card-head">
            <div class="kt-card-title"><i class="fas fa-list"></i> ${txns.length} giao dịch · ${fresh} mới · ${dups} trùng · 💡 ${state.txns.filter((t) => t.suggested_counter && !t.duplicate).length} gợi ý</div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
              <button class="kt-btn kt-btn--outline kt-btn--sm" id="bi-rules"><i class="fas fa-sliders"></i> Quy tắc map</button>
              <select id="bi-default" class="kt-select" style="width:auto">${raw(counterOpts)}</select>
              <button class="kt-btn kt-btn--outline kt-btn--sm" id="bi-apply">Áp dụng TK cho dòng chọn</button>
              <button class="kt-btn kt-btn--success kt-btn--sm" id="bi-create"><i class="fas fa-file-circle-plus"></i> Tạo bút toán (<span id="bi-count">0</span>)</button>
            </div>
          </div>
          <div class="kt-card-body">
            <div class="kt-table-wrap"><table class="kt-table">
              <thead><tr>
                <th><input type="checkbox" id="bi-all"></th>
                <th>Ngày</th><th>Nội dung</th><th class="num">Tiền ra</th><th class="num">Tiền vào</th>
                <th>TK đối ứng</th><th>Đối tượng</th><th>Trạng thái</th><th></th>
              </tr></thead>
              <tbody>${txns.map((t) => txnRow(t))}</tbody>
            </table></div>
          </div>
        </div>
      `
    );

    // Prefill TK đối ứng theo gợi ý quy tắc.
    txns.forEach((t) => {
      if (t.suggested_counter && !t.duplicate && !t.created) {
        const sel = result.querySelector(`.bi-counter[data-key="${t.key}"]`);
        if (sel) sel.value = t.suggested_counter;
      }
    });

    result.querySelector("#bi-rules").addEventListener("click", openRulesManager);
    result.querySelectorAll(".bi-saverule").forEach((b) =>
      b.addEventListener("click", () => {
        const key = b.dataset.key;
        const t = state.txns.find((x) => x.key === key);
        const counter = result.querySelector(`.bi-counter[data-key="${key}"]`).value;
        const party = result.querySelector(`.bi-party[data-key="${key}"]`).value.trim();
        openSaveRule(t, counter, party);
      })
    );

    const countEl = result.querySelector("#bi-count");
    const refreshCount = () => {
      const n = result.querySelectorAll(".bi-cb:checked").length;
      countEl.textContent = n;
    };
    result.querySelectorAll(".bi-cb").forEach((cb) => cb.addEventListener("change", refreshCount));
    const all = result.querySelector("#bi-all");
    all.addEventListener("change", () => {
      result.querySelectorAll(".bi-cb:not(:disabled)").forEach((cb) => { cb.checked = all.checked; });
      refreshCount();
    });

    result.querySelector("#bi-apply").addEventListener("click", () => {
      const val = result.querySelector("#bi-default").value;
      result.querySelectorAll(".bi-cb:checked").forEach((cb) => {
        const sel = result.querySelector(`.bi-counter[data-key="${cb.value}"]`);
        if (sel) sel.value = val;
      });
      toast("Đã áp dụng TK đối ứng", "success");
    });

    result.querySelector("#bi-create").addEventListener("click", doCreate);
    refreshCount();
  }

  async function doCreate() {
    const bankAccount = container.querySelector("#bi-bank").value;
    const picks = [];
    result.querySelectorAll(".bi-cb:checked").forEach((cb) => {
      const key = cb.value;
      const t = state.txns.find((x) => x.key === key);
      if (!t) return;
      const counter = result.querySelector(`.bi-counter[data-key="${key}"]`).value;
      const party = result.querySelector(`.bi-party[data-key="${key}"]`).value.trim();
      picks.push({ ...t, counter_account: counter, party });
    });
    if (!picks.length) { toast("Chọn ít nhất 1 giao dịch", "warning"); return; }
    if (picks.some((p) => !p.counter_account)) { toast("Có dòng chưa chọn TK đối ứng", "warning"); return; }

    const btn = result.querySelector("#bi-create");
    btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang tạo...';
    try {
      const res = await api.bankImport(picks, bankAccount);
      const createdKeys = new Set(res.created.map((c) => c.key));
      state.txns.forEach((t) => { if (createdKeys.has(t.key)) t.created = true; });
      toast(`Đã tạo ${res.count} bút toán` + (res.skipped.length ? ` · bỏ qua ${res.skipped.length}` : ""), "success");
      if (res.skipped.length) console.warn("Bỏ qua:", res.skipped);
      renderTable();
    } catch (e) {
      toast(e.message, "error");
      btn.disabled = false; btn.innerHTML = '<i class="fas fa-file-circle-plus"></i> Tạo bút toán';
    }
  }

  const accType = {};
  opts.counter_accounts.forEach((a) => { accType[a.name] = a.account_type; });

  function applyRuleLocally(keyword, counter, directionLabel, party) {
    const low = (keyword || "").toLowerCase();
    state.txns.forEach((t) => {
      if (t.duplicate || t.created) return;
      if (directionLabel === "Tiền vào" && t.direction !== "in") return;
      if (directionLabel === "Tiền ra" && t.direction !== "out") return;
      if (!(t.content || "").toLowerCase().includes(low)) return;
      t.suggested_counter = counter;
      t.suggested_rule = keyword;
      if (party) t.suggested_party = party;
    });
    renderTable();
  }

  function openSaveRule(t, counter, party) {
    const dirDefault = t && t.direction === "in" ? "Tiền vào" : t && t.direction === "out" ? "Tiền ra" : "Bất kỳ";
    const m = openModal({
      title: "Lưu quy tắc map",
      icon: "fa-floppy-disk",
      maxWidth: 520,
      body: html`
        ${t ? html`<p class="kt-sub kt-mb" style="white-space:normal">Nội dung: ${(t.content || "").slice(0, 140)}</p>` : ""}
        <div class="kt-field"><label><i class="fas fa-key"></i> Từ khóa (xuất hiện trong nội dung) *</label>
          <input id="sr-keyword" class="kt-input" placeholder="VD: ATVN, tien hang, Dai Viet..."></div>
        <div class="kt-row2">
          <div class="kt-field"><label><i class="fas fa-right-left"></i> TK đối ứng *</label>
            <select id="sr-counter" class="kt-select">${raw(counterOpts)}</select></div>
          <div class="kt-field"><label><i class="fas fa-arrows-up-down"></i> Chiều tiền</label>
            <select id="sr-direction" class="kt-select">
              <option ${dirDefault === "Bất kỳ" ? "selected" : ""}>Bất kỳ</option>
              <option ${dirDefault === "Tiền vào" ? "selected" : ""}>Tiền vào</option>
              <option ${dirDefault === "Tiền ra" ? "selected" : ""}>Tiền ra</option>
            </select></div>
        </div>
        <div class="kt-field"><label><i class="fas fa-user"></i> Đối tượng cố định (tùy chọn — KH/NCC)</label>
          <input id="sr-party" class="kt-input" value="${party || ""}" placeholder="Để trống nếu đối tượng thay đổi"></div>
        <div class="kt-modal-actions">
          <button class="kt-btn kt-btn--outline" id="sr-cancel">Hủy</button>
          <button class="kt-btn kt-btn--primary" id="sr-save"><i class="fas fa-check"></i> Lưu quy tắc</button>
        </div>`,
    });
    if (counter) m.body.querySelector("#sr-counter").value = counter;
    m.body.querySelector("#sr-cancel").addEventListener("click", m.close);
    m.body.querySelector("#sr-save").addEventListener("click", async () => {
      const keyword = m.body.querySelector("#sr-keyword").value.trim();
      const counterAcc = m.body.querySelector("#sr-counter").value;
      const direction = m.body.querySelector("#sr-direction").value;
      const partyVal = m.body.querySelector("#sr-party").value.trim();
      if (!keyword) { toast("Nhập từ khóa", "warning"); return; }
      if (!counterAcc) { toast("Chọn TK đối ứng", "warning"); return; }
      const pType = partyVal ? (accType[counterAcc] === "Payable" ? "Supplier" : "Customer") : null;
      try {
        await api.bankSaveRule({ keyword, counter_account: counterAcc, direction, party_type: pType, party: partyVal || null });
        toast("Đã lưu quy tắc", "success");
        m.close();
        applyRuleLocally(keyword, counterAcc, direction, partyVal);
      } catch (e) { toast(e.message, "error"); }
    });
  }

  async function openRulesManager() {
    const m = openModal({ title: "Quy tắc map", icon: "fa-sliders", maxWidth: 640,
      body: html`<div class="kt-boot"><div class="kt-spinner"></div></div>` });
    async function reload() {
      let rules;
      try { rules = await api.bankGetRules(); } catch (e) { setHTML(m.body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`); return; }
      setHTML(m.body, html`
        ${rules.length ? html`<div class="kt-table-wrap"><table class="kt-table">
          <thead><tr><th>Từ khóa</th><th>TK đối ứng</th><th>Chiều</th><th>Đối tượng</th><th></th></tr></thead>
          <tbody>${rules.map((r) => html`<tr>
            <td>${r.keyword}</td><td>${r.counter_account}</td><td>${r.direction || "Bất kỳ"}</td>
            <td>${r.party || "—"}</td>
            <td class="num"><button class="kt-btn-icon sr-del" data-name="${r.name}" title="Xóa"><i class="fas fa-trash"></i></button></td>
          </tr>`)}</tbody></table></div>`
          : html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Chưa có quy tắc. Bấm 💾 ở từng dòng để lưu.</p></div>`}
        <p class="kt-sub" style="margin-top:10px">Có thể thêm/sửa chi tiết trong Desk: <b>Ketoan Bank Map Rule</b>.</p>`);
      m.body.querySelectorAll(".sr-del").forEach((b) =>
        b.addEventListener("click", async () => {
          if (!confirm("Xóa quy tắc này?")) return;
          try { await api.bankDeleteRule(b.dataset.name); toast("Đã xóa", "success"); reload(); }
          catch (e) { toast(e.message, "error"); }
        })
      );
    }
    reload();
  }

  function txnRow(t) {
    const done = t.created;
    const dup = t.duplicate;
    const disabled = done || dup;
    const status = done
      ? html`<span class="kt-badge kt-badge--green">Đã tạo</span>`
      : dup
        ? html`<span class="kt-badge kt-badge--gray">Trùng</span>`
        : html`<span class="kt-badge kt-badge--${t.direction === "in" ? "green" : "red"}">${t.direction === "in" ? "Tiền vào" : "Tiền ra"}</span>`;
    return html`<tr>
      <td><input type="checkbox" class="bi-cb" value="${t.key}" ${disabled ? "disabled" : ""}></td>
      <td>${t.date}</td>
      <td title="${t.content}" style="max-width:320px;white-space:normal">${(t.content || "").slice(0, 90)}${t.content && t.content.length > 90 ? "…" : ""}</td>
      <td class="num ${t.debit ? "danger" : ""}">${t.debit ? formatVND(t.debit) : ""}</td>
      <td class="num ${t.credit ? "pos" : ""}">${t.credit ? formatVND(t.credit) : ""}</td>
      <td>${disabled ? "—" : raw(`<select class="kt-select bi-counter" data-key="${escapeHtml(t.key)}">${counterOpts}</select>`)}</td>
      <td>${disabled ? "—" : html`<input class="kt-input bi-party" data-key="${t.key}" value="${t.suggested_party || ""}" placeholder="KH/NCC (nếu 131/331)" style="min-width:140px">`}</td>
      <td>${status}${t.suggested_rule && !disabled ? html` <span class="kt-badge kt-badge--green" title="Gợi ý từ quy tắc: ${t.suggested_rule}">💡</span>` : ""}</td>
      <td>${disabled ? "" : html`<button class="kt-btn-icon bi-saverule" data-key="${t.key}" title="Lưu quy tắc từ dòng này"><i class="fas fa-floppy-disk"></i></button>`}</td>
    </tr>`;
  }
}
