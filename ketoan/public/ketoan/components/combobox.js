// combobox.js — ô chọn CÓ TÌM KIẾM (vanilla, không thư viện).
// Nguồn dữ liệu: `options` tĩnh (lọc client — giữ nguyên thứ tự truyền vào,
// tức "hay dùng trước") hoặc `search(txt)` async (đối tượng KH/NCC).
// Chỉ hiện tối đa MAX_SHOW kết quả; gõ (không dấu cũng được) để thu hẹp.
// Panel dropdown là SINGLETON gắn vào <body> (position:fixed) để không bị
// .kt-table-wrap cuộn ngang cắt mất — giống awesomplete trong Desk grid.
import { escapeHtml } from "../lib/format.js";

const MAX_SHOW = 10;

// So khớp không phân biệt hoa thường + KHÔNG DẤU (gõ "phai thu" ra "Phải thu").
const strip = (s) =>
  (s == null ? "" : String(s)).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d");

// ── Panel dùng chung (chỉ 1 dropdown mở tại 1 thời điểm) ────────────────────
let panel = null;
let current = null; // instance đang mở

function ensurePanel() {
  if (panel) return panel;
  panel = document.createElement("div");
  panel.className = "kt-combo-panel";
  panel.style.display = "none";
  document.body.appendChild(panel);
  // preventDefault cho MỌI mousedown trên panel (kể cả scrollbar/viền): giữ focus
  // ở input để panel không bị blur-đóng giữa lúc cuộn; chọn item vẫn như cũ.
  panel.addEventListener("mousedown", (e) => {
    e.preventDefault();
    const el = e.target.closest(".kt-combo-item");
    if (el && current) current.pick(+el.dataset.i);
  });
  window.addEventListener("scroll", () => current && current.reposition(), true);
  window.addEventListener("resize", () => current && current.reposition());
  return panel;
}

// Đóng dropdown đang mở (bất kể của instance nào) — gọi TRƯỚC khi re-render DOM
// chứa combobox, tránh panel mồ côi (Safari/Firefox không phát blur khi detach).
export function closeComboPanel() {
  if (current) current.close();
}

// ── createCombobox(host, cfg) ───────────────────────────────────────────────
// cfg: { options?: [{value,label,sub?}], search?: async (txt)=>[{value,label,sub?}],
//        value?, label?, placeholder?, onPick?(item|null) }
// Trả { get value, set(item), input }.
export function createCombobox(host, cfg = {}) {
  ensurePanel();
  host.classList.add("kt-combo");
  host.innerHTML = "";
  const input = document.createElement("input");
  input.type = "text";
  input.className = "kt-input kt-combo-input";
  input.placeholder = cfg.placeholder || "Gõ để tìm…";
  input.autocomplete = "off";
  input.spellcheck = false;
  host.appendChild(input);

  let items = [];      // kết quả đang hiển thị trong panel
  let active = -1;     // chỉ số đang chọn bằng phím
  let picked = null;   // item đã chốt
  let timer = null;
  let blurTimer = null;
  let seq = 0;         // chống race của search async
  let pending = false; // search async đang bay

  function setPicked(item, fire = true) {
    picked = item || null;
    input.value = picked ? picked.label : "";
    input.title = picked ? (picked.sub || picked.label) : "";
    if (fire && cfg.onPick) cfg.onPick(picked);
  }
  if (cfg.value) setPicked({ value: cfg.value, label: cfg.label || cfg.value, sub: cfg.sub || "" }, false);

  const me = {
    reposition() {
      if (!input.isConnected) { me.close(); return; } // input đã bị re-render gỡ đi
      const r = input.getBoundingClientRect();
      panel.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 280)) + "px";
      panel.style.top = r.bottom + 4 + "px";
      panel.style.minWidth = Math.max(r.width, 260) + "px";
    },
    pick(i) {
      const it = items[i];
      if (it) setPicked(it);
      me.close();
    },
    close() {
      // Hủy cả search đang bay: nếu không, kết quả về muộn sẽ MỞ LẠI panel
      // (input vẫn giữ focus sau pick) và Enter kế tiếp chọn nhầm mục cũ.
      clearTimeout(timer);
      seq++;
      pending = false;
      if (current === me) {
        panel.style.display = "none";
        current = null;
      }
    },
  };

  function renderPanel(list, total, approx) {
    items = list;
    active = -1;
    // approx (search async): server chỉ trả tối đa 1 trang — số "còn lại" là ước lượng.
    const more = total > list.length
      ? `<div class="kt-combo-more">…còn ${total - list.length}${approx ? "+" : ""} kết quả — gõ thêm để thu hẹp</div>`
      : "";
    panel.innerHTML = list.length
      ? list.map((it, i) =>
          `<div class="kt-combo-item" data-i="${i}"><b>${escapeHtml(it.label)}</b>${it.sub && it.sub !== it.label ? `<span>${escapeHtml(it.sub)}</span>` : ""}</div>`
        ).join("") + more
      : '<div class="kt-combo-empty">Không thấy — thử từ khóa khác</div>';
    current = me;
    me.reposition();
    panel.style.display = "";
  }

  function open(txt) {
    if (cfg.search) {
      clearTimeout(timer);
      items = []; active = -1; // list cũ hết hiệu lực — Enter/click khi đang chờ không chọn nhầm
      if (current === me) panel.innerHTML = '<div class="kt-combo-empty">Đang tìm…</div>';
      pending = true;
      const mySeq = ++seq;
      timer = setTimeout(async () => {
        let rows = [];
        try { rows = (await cfg.search(txt || "")) || []; } catch (_) { rows = []; }
        if (mySeq !== seq) return;          // đã có lượt tìm mới / đã đóng
        pending = false;
        if (document.activeElement !== input) return; // đã blur trong lúc chờ
        renderPanel(rows.slice(0, MAX_SHOW), rows.length, true);
      }, txt ? 250 : 0);
    } else {
      const q = strip(txt);
      const all = cfg.options || [];
      const hit = !q ? all : all.filter((o) => strip(o.label + " " + (o.sub || "") + " " + o.value).includes(q));
      renderPanel(hit.slice(0, MAX_SHOW), hit.length, false);
    }
  }

  input.addEventListener("focus", () => {
    clearTimeout(blurTimer); // quay lại trong <120ms: hủy lệnh đóng của lần blur trước
    input.select();
    open("");
  });
  input.addEventListener("input", () => {
    if (picked) { picked = null; input.title = ""; if (cfg.onPick) cfg.onPick(null); } // gõ = bỏ lựa chọn cũ
    open(input.value.trim());
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { me.close(); input.value = picked ? picked.label : ""; return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (current !== me) {
        if (!pending) open(input.value.trim()); // đang chờ search: đừng reset debounce liên tục
        return;
      }
      if (!items.length) return;
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      panel.querySelectorAll(".kt-combo-item").forEach((el, i) => el.classList.toggle("is-active", i === active));
    } else if (e.key === "Enter") {
      e.preventDefault();
      // items=[] trong lúc search đang bay → Enter không chọn nhầm list cũ.
      if (current === me) me.pick(active >= 0 ? active : 0);
    }
  });
  input.addEventListener("blur", () => {
    // Đợi mousedown trên panel chạy trước (nếu có), rồi đóng + khôi phục nhãn.
    clearTimeout(blurTimer);
    blurTimer = setTimeout(() => {
      if (document.activeElement === input) return; // đã focus lại
      me.close();
      input.value = picked ? picked.label : "";
    }, 120);
  });

  return {
    get value() { return picked ? picked.value : ""; },
    set(item, fire = false) { setPicked(item, fire); },
    input,
  };
}
