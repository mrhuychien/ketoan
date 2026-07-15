// views/bankimport.js — Nhập sổ quỹ từ file sao kê ngân hàng (Excel).
// TK đối ứng & Đối tượng chọn bằng COMBOBOX: hiện ~10 TK hay dùng trước, gõ để
// tìm (có số TK, không cần gõ dấu). TK phải thu/phải trả bắt buộc chọn đối tượng
// (Customer/Supplier load từ server, hay dùng lên trước) — giống bút toán Desk.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { formatVND } from "../lib/format.js";
import { toast } from "../components/toast.js";
import { openModal } from "../components/modal.js";
import { createCombobox, closeComboPanel } from "../components/combobox.js";

export async function render({ container }) {
  setHTML(container, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
  let opts;
  try {
    opts = await api.bankImportOptions();
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
    return;
  }

  const state = { txns: [], defaultCounter: "" };

  // Danh sách TK đối ứng cho combobox — server đã xếp TK HAY DÙNG lên trước.
  const accOptions = opts.counter_accounts.map((a) => ({
    value: a.name,
    label: (a.account_number ? a.account_number + " — " : "") + (a.account_name || a.name),
    sub: a.name,
  }));
  const accType = {};
  const accLabel = {};
  opts.counter_accounts.forEach((a) => { accType[a.name] = a.account_type; });
  accOptions.forEach((o) => { accLabel[o.value] = o.label; });

  // TK có đối tượng: Receivable → Customer, Payable → Supplier (như Desk).
  const partyTypeOf = (acc) =>
    accType[acc] === "Receivable" ? "Customer" : accType[acc] === "Payable" ? "Supplier" : null;
  const partySearch = (pt) => (txt) =>
    api.bankSearchParty(pt, txt).then((rows) =>
      (rows || []).map((r) => ({ value: r.name, label: r.label || r.name, sub: r.name }))
    );

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
                ${opts.bank_accounts.map((a) => html`<option value="${a.name}" ${a.name === opts.suggested_bank ? "selected" : ""}>${(a.account_number ? a.account_number + " — " : "") + (a.account_name || a.name)}</option>`)}
              </select></div>
            <div class="kt-field"><label><i class="fas fa-file-excel"></i> File sao kê (.xlsx)</label>
              <input type="file" id="bi-file" class="kt-input" accept=".xlsx"></div>
          </div>
          <p class="kt-sub">Cột: Số tham chiếu · Ngày · Ghi nợ (tiền ra) · Ghi có (tiền vào) · Số dư · Nội dung. Giao dịch đã nhập trước sẽ tự lọc trùng. TK đối ứng: gõ số TK hoặc tên (không cần dấu) để tìm.</p>
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
        // 2 dòng giống hệt nhau trong file → trùng key: đánh dấu dòng sau là trùng
        // (backend cũng chỉ tạo 1 JE/key), tránh combobox/checkbox điều khiển nhầm dòng đầu.
        const seenKeys = new Set();
        state.txns.forEach((t) => {
          if (seenKeys.has(t.key)) t.duplicate = true;
          seenKeys.add(t.key);
        });
        // Nhận gợi ý từ quy tắc map làm lựa chọn ban đầu — CHỈ khi TK còn dùng được
        // với company này (rule cũ có thể trỏ TK đã disable / company khác).
        state.txns.forEach((t) => {
          if (t.suggested_counter && !(t.suggested_counter in accType)) {
            t.suggested_counter = null;
            t.suggested_party = null;
            t.suggested_rule = null;
          }
          t.counter_account = t.suggested_counter || "";
          t.last_counter = t.counter_account; // TK đã CHỐT gần nhất (giữ party khi gõ tìm lại)
          t.party = t.suggested_party || "";
          t.checked = false;
        });
        renderTable();
      } catch (e) {
        setHTML(result, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
      }
    };
    reader.onerror = () => toast("Không đọc được file", "error");
    reader.readAsDataURL(file);
  });

  function renderTable() {
    closeComboPanel(); // panel đang mở thuộc DOM sắp bị thay — đóng trước
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
            <div class="kt-card-title"><i class="fas fa-list"></i> ${txns.length} giao dịch · ${fresh} mới · ${dups} trùng · 💡 ${txns.filter((t) => t.suggested_counter && !t.duplicate).length} gợi ý</div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
              <button class="kt-btn kt-btn--outline kt-btn--sm" id="bi-rules"><i class="fas fa-sliders"></i> Quy tắc map</button>
              <div id="bi-default-host" style="min-width:230px"></div>
              <button class="kt-btn kt-btn--outline kt-btn--sm" id="bi-apply">Áp dụng TK cho dòng chọn</button>
              <button class="kt-btn kt-btn--success kt-btn--sm" id="bi-create"><i class="fas fa-file-circle-plus"></i> Tạo bút toán (<span id="bi-count">0</span>)</button>
            </div>
          </div>
          <div class="kt-card-body">
            <div class="kt-table-wrap"><table class="kt-table">
              <thead><tr>
                <th><input type="checkbox" id="bi-all"></th>
                <th>Ngày</th><th>Nội dung</th><th class="num">Tiền ra</th><th class="num">Tiền vào</th>
                <th style="min-width:210px">TK đối ứng</th><th style="min-width:190px">Đối tượng</th><th>Trạng thái</th><th></th>
              </tr></thead>
              <tbody>${txns.map((t) => txnRow(t))}</tbody>
            </table></div>
          </div>
        </div>
      `
    );

    // Combobox TK đối ứng + Đối tượng cho từng dòng còn nhập được.
    txns.forEach((t) => {
      if (t.duplicate || t.created) return;
      const cHost = result.querySelector(`.bi-counter-host[data-key="${t.key}"]`);
      if (cHost)
        createCombobox(cHost, {
          options: accOptions,
          value: t.counter_account || "",
          label: accLabel[t.counter_account] || t.counter_account || "",
          placeholder: "Gõ số/tên TK…",
          onPick: (it) => {
            // Đang gõ để tìm lại (it=null): chỉ tạm bỏ TK, GIỮ đối tượng.
            // So loại đối tượng với TK đã CHỐT gần nhất (last_counter) — chốt lại
            // đúng TK cũ hoặc TK cùng loại thì không mất đối tượng đã chọn.
            if (!it) { t.counter_account = ""; return; }
            const oldPt = partyTypeOf(t.last_counter);
            t.counter_account = t.last_counter = it.value;
            if (oldPt !== partyTypeOf(it.value)) t.party = "";
            renderPartyCell(t);
          },
        });
      renderPartyCell(t);
    });

    // Combobox "TK mặc định" áp dụng hàng loạt.
    const defCombo = createCombobox(result.querySelector("#bi-default-host"), {
      options: accOptions,
      value: state.defaultCounter || "",
      label: accLabel[state.defaultCounter] || state.defaultCounter || "",
      placeholder: "TK áp dụng hàng loạt…",
      onPick: (it) => { state.defaultCounter = it ? it.value : ""; },
    });

    result.querySelector("#bi-rules").addEventListener("click", openRulesManager);
    result.querySelectorAll(".bi-saverule").forEach((b) =>
      b.addEventListener("click", () => {
        const t = state.txns.find((x) => x.key === b.dataset.key);
        if (t) openSaveRule(t, t.counter_account, t.party);
      })
    );

    const countEl = result.querySelector("#bi-count");
    const refreshCount = () => {
      countEl.textContent = state.txns.filter((t) => t.checked && !t.duplicate && !t.created).length;
    };
    result.querySelectorAll(".bi-cb").forEach((cb) =>
      cb.addEventListener("change", () => {
        const t = state.txns.find((x) => x.key === cb.value);
        if (t) t.checked = cb.checked;
        refreshCount();
      })
    );
    const all = result.querySelector("#bi-all");
    // Khôi phục trạng thái "chọn tất cả" sau re-render.
    all.checked = fresh > 0 && txns.every((t) => t.duplicate || t.created || t.checked);
    all.addEventListener("change", () => {
      result.querySelectorAll(".bi-cb:not(:disabled)").forEach((cb) => {
        cb.checked = all.checked;
        const t = state.txns.find((x) => x.key === cb.value);
        if (t) t.checked = all.checked;
      });
      refreshCount();
    });

    result.querySelector("#bi-apply").addEventListener("click", () => {
      const val = defCombo.value || state.defaultCounter;
      if (!val) { toast("Chọn TK đối ứng để áp dụng", "warning"); return; }
      let n = 0;
      state.txns.forEach((t) => {
        if (!t.checked || t.duplicate || t.created) return;
        const oldPt = partyTypeOf(t.last_counter);
        t.counter_account = t.last_counter = val;
        if (oldPt !== partyTypeOf(val)) t.party = "";
        n++;
      });
      if (!n) { toast("Tick chọn ít nhất 1 dòng trước", "warning"); return; }
      renderTable();
      toast(`Đã áp dụng TK đối ứng cho ${n} dòng`, "success");
    });

    result.querySelector("#bi-create").addEventListener("click", doCreate);
    refreshCount();
  }

  // Ô Đối tượng của 1 dòng: chỉ hiện khi TK đối ứng là phải thu/phải trả.
  function renderPartyCell(t) {
    const host = result.querySelector(`.bi-party-host[data-key="${t.key}"]`);
    if (!host) return;
    closeComboPanel(); // host sắp bị thay nội dung — đóng panel nếu đang mở
    const pt = partyTypeOf(t.counter_account);
    if (!pt) {
      t.party = "";
      host.classList.remove("kt-combo");
      host.innerHTML = '<span class="kt-sub">—</span>';
      return;
    }
    createCombobox(host, {
      search: partySearch(pt),
      value: t.party || "",
      label: t.party || "",
      placeholder: pt === "Customer" ? "Chọn khách hàng…" : "Chọn nhà cung cấp…",
      onPick: (it) => { t.party = it ? it.value : ""; },
    });
  }

  async function doCreate() {
    const bankAccount = container.querySelector("#bi-bank").value;
    const picks = state.txns.filter((t) => t.checked && !t.duplicate && !t.created);
    if (!picks.length) { toast("Chọn ít nhất 1 giao dịch", "warning"); return; }
    if (picks.some((p) => !p.counter_account)) { toast("Có dòng chưa chọn TK đối ứng", "warning"); return; }
    const needParty = picks.filter((p) => partyTypeOf(p.counter_account) && !p.party);
    if (needParty.length) {
      toast(`${needParty.length} dòng dùng TK phải thu/phải trả nhưng chưa chọn đối tượng (KH/NCC)`, "warning");
      return;
    }

    const btn = result.querySelector("#bi-create");
    btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang tạo...';
    try {
      const rows = picks.map((t) => ({ ...t, party: t.party || "" }));
      const res = await api.bankImport(rows, bankAccount);
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

  function applyRuleLocally(keyword, counter, directionLabel, party) {
    const low = (keyword || "").toLowerCase();
    state.txns.forEach((t) => {
      if (t.duplicate || t.created) return;
      if (directionLabel === "Tiền vào" && t.direction !== "in") return;
      if (directionLabel === "Tiền ra" && t.direction !== "out") return;
      if (!(t.content || "").toLowerCase().includes(low)) return;
      t.suggested_counter = counter;
      t.suggested_rule = keyword;
      const oldPt = partyTypeOf(t.last_counter);
      t.counter_account = t.last_counter = counter;
      const pt = partyTypeOf(counter);
      if (!pt || pt !== oldPt) t.party = ""; // đổi loại đối tượng → xóa party cũ sai loại
      if (pt && party) t.party = party;
    });
    renderTable();
  }

  function openSaveRule(t, counter, party) {
    const dirDefault = t && t.direction === "in" ? "Tiền vào" : t && t.direction === "out" ? "Tiền ra" : "Bất kỳ";
    let srCounter = counter || "";
    let srLast = srCounter; // TK đã chốt gần nhất (srCounter bị xóa tạm khi gõ tìm)
    let srParty = party || "";
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
            <div id="sr-counter-host"></div></div>
          <div class="kt-field"><label><i class="fas fa-arrows-up-down"></i> Chiều tiền</label>
            <select id="sr-direction" class="kt-select">
              <option ${dirDefault === "Bất kỳ" ? "selected" : ""}>Bất kỳ</option>
              <option ${dirDefault === "Tiền vào" ? "selected" : ""}>Tiền vào</option>
              <option ${dirDefault === "Tiền ra" ? "selected" : ""}>Tiền ra</option>
            </select></div>
        </div>
        <div class="kt-field"><label><i class="fas fa-user"></i> Đối tượng cố định (tùy chọn — KH/NCC)</label>
          <div id="sr-party-host"></div></div>
        <div class="kt-modal-actions">
          <button class="kt-btn kt-btn--outline" id="sr-cancel">Hủy</button>
          <button class="kt-btn kt-btn--primary" id="sr-save"><i class="fas fa-check"></i> Lưu quy tắc</button>
        </div>`,
    });

    function renderSrParty() {
      const host = m.body.querySelector("#sr-party-host");
      closeComboPanel();
      const pt = partyTypeOf(srCounter);
      if (!pt) {
        srParty = "";
        host.classList.remove("kt-combo");
        host.innerHTML = '<span class="kt-sub">— TK này không cần đối tượng</span>';
        return;
      }
      createCombobox(host, {
        search: partySearch(pt),
        value: srParty || "",
        label: srParty || "",
        placeholder: "Để trống nếu đối tượng thay đổi",
        onPick: (it) => { srParty = it ? it.value : ""; },
      });
    }
    createCombobox(m.body.querySelector("#sr-counter-host"), {
      options: accOptions,
      value: srCounter || "",
      label: accLabel[srCounter] || srCounter || "",
      placeholder: "Gõ số/tên TK…",
      onPick: (it) => {
        if (!it) { srCounter = ""; return; } // đang gõ tìm lại — giữ ô đối tượng
        const oldPt = partyTypeOf(srLast);
        srCounter = srLast = it.value;
        if (oldPt !== partyTypeOf(srCounter)) srParty = ""; // đổi loại → bỏ đối tượng sai loại
        renderSrParty();
      },
    });
    renderSrParty();

    m.body.querySelector("#sr-cancel").addEventListener("click", () => { closeComboPanel(); m.close(); });
    m.body.querySelector("#sr-save").addEventListener("click", async () => {
      const keyword = m.body.querySelector("#sr-keyword").value.trim();
      const direction = m.body.querySelector("#sr-direction").value;
      if (!keyword) { toast("Nhập từ khóa", "warning"); return; }
      if (!srCounter) { toast("Chọn TK đối ứng", "warning"); return; }
      const pType = srParty ? (accType[srCounter] === "Payable" ? "Supplier" : "Customer") : null;
      try {
        await api.bankSaveRule({ keyword, counter_account: srCounter, direction, party_type: pType, party: srParty || null });
        toast("Đã lưu quy tắc", "success");
        closeComboPanel();
        m.close();
        applyRuleLocally(keyword, srCounter, direction, srParty);
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
      <td><input type="checkbox" class="bi-cb" value="${t.key}" ${disabled ? "disabled" : ""} ${!disabled && t.checked ? "checked" : ""}></td>
      <td>${t.date}</td>
      <td title="${t.content}" style="max-width:320px;white-space:normal">${(t.content || "").slice(0, 90)}${t.content && t.content.length > 90 ? "…" : ""}</td>
      <td class="num ${t.debit ? "danger" : ""}">${t.debit ? formatVND(t.debit) : ""}</td>
      <td class="num ${t.credit ? "pos" : ""}">${t.credit ? formatVND(t.credit) : ""}</td>
      <td>${disabled ? "—" : html`<div class="bi-counter-host" data-key="${t.key}"></div>`}</td>
      <td>${disabled ? "—" : html`<div class="bi-party-host" data-key="${t.key}"></div>`}</td>
      <td>${status}${t.suggested_rule && !disabled ? html` <span class="kt-badge kt-badge--green" title="Gợi ý từ quy tắc: ${t.suggested_rule}">💡</span>` : ""}</td>
      <td>${disabled ? "" : html`<button class="kt-btn-icon bi-saverule" data-key="${t.key}" title="Lưu quy tắc từ dòng này"><i class="fas fa-floppy-disk"></i></button>`}</td>
    </tr>`;
  }
}
