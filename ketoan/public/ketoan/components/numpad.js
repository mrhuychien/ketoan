// numpad.js — BÀN SỐ PHÍM TO cho màn kiểm hàng thu hồi. Port từ app sx
// (components/numpad.js + bàn số thùng/hộp `moSoHsd`, bỏ phần HSD).
//
// Vì sao tự dựng chứ không dùng bàn phím hệ thống: bàn phím ảo che nửa màn hình đúng
// lúc người kiểm cần nhìn tên mã đang nhập, và phím của nó nhỏ cho ngón tay đeo găng
// trong kho. Bàn số nằm trong một tấm trượt dưới đáy, phím 60px.
//
// Đếm theo NHIỀU ĐƠN VỊ: "2 thùng 3 hộp", không phải "51 hộp". Người kiểm đếm theo cách
// hàng xếp — thùng trước, lẻ ra bao nhiêu hộp thì đếm hộp. Bắt quy đổi trong đầu là chỗ
// sinh lỗi. Máy nhân hệ số; server tra lại hệ số trên Item, không tin số gửi lên.
import { escapeHtml } from "../lib/format.js";

/** Một lần bấm phím. Hàm THUẦN (kiểm được không cần trình duyệt).
 *  `chuaGo` = chưa gõ phím số nào kể từ lúc mở: phím số đầu GHI ĐÈ số điền sẵn, không
 *  nối đuôi — mở ra là để nhập số MỚI; gõ nối thì 120 gõ 50 thành 12050 mà không ai báo. */
export function bamPhim(value, k, chuaGo) {
  if (k === "⌫") return value.slice(0, -1);
  if (k === "C") return "";
  const goc = chuaGo ? "" : value;
  if (k === ",") return goc.includes(".") ? goc : `${goc || "0"}.`;
  return goc.replace(".", "").length < 9 ? goc + k : goc;
}

/** Tổng theo ĐVT kho → bậc lớn trước: 51 hộp (24/thùng) → 2 thùng 3 hộp.
 *  null khi không chia khớp tuyệt đối — thà không chia còn hơn ra một tổng khác. */
export function tachUom(tong, uoms) {
  const ds = (uoms || []).filter((u) => u && u.uom && Number(u.he_so) > 0);
  if (ds.length <= 1 || !(tong > 0)) return null;
  const bac = ds.slice().sort((a, b) => Number(b.he_so) - Number(a.he_so));
  const ra = [];
  let con = tong;
  bac.forEach((u, i) => {
    const h = Number(u.he_so);
    const sl = i === bac.length - 1 ? Math.round(con / h) : Math.floor(con / h + 1e-9);
    if (sl > 0) ra.push({ uom: u.uom, sl, he_so: h });
    con -= sl * h;
  });
  const lai = ra.reduce((a, c) => a + c.sl * c.he_so, 0);
  return Math.abs(lai - tong) < 1e-6 ? ra : null;
}

/** "2 Thùng + 3 Hộp" — rỗng khi chỉ một ĐVT (tổng đã nói đủ). */
export function moTaChiTiet(ct) {
  const ds = (ct || []).filter((c) => Number(c.sl) > 0);
  return ds.length > 1 ? ds.map((c) => `${fmt(c.sl)} ${c.uom}`).join(" + ") : "";
}

function fmt(n) {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 3 }).format(Number(n) || 0);
}

/** Tấm trượt đáy màn hình (giữa màn trên máy lớn). Trả {body, close, root}. */
export function openSheet({ kicker = "", title = "", onClose = null } = {}) {
  const root = document.createElement("div");
  root.className = "kt-th-sheet-overlay";
  root.innerHTML = `<div class="kt-th-sheet" role="dialog" aria-modal="true">
      <div class="kt-th-sheet-head">
        <div class="kt-th-sheet-titles">
          ${kicker ? `<div class="kt-th-sheet-kicker">${escapeHtml(kicker)}</div>` : ""}
          <div class="kt-th-sheet-title">${escapeHtml(title)}</div>
        </div>
        <button type="button" class="kt-th-sheet-close" aria-label="Đóng">&times;</button>
      </div>
      <div class="kt-th-sheet-body"></div>
    </div>`;
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    root.remove();
    document.removeEventListener("keydown", esc);
    if (onClose) onClose();
  };
  const esc = (e) => { if (e.key === "Escape") close(); };
  root.querySelector(".kt-th-sheet-close").addEventListener("click", close);
  root.addEventListener("click", (e) => { if (e.target === root) close(); });
  document.addEventListener("keydown", esc);
  document.body.appendChild(root);
  return { root, body: root.querySelector(".kt-th-sheet-body"), close };
}

/**
 * Bàn số có TAB ĐƠN VỊ. Gọi onOk(tong theo ĐVT kho, chiTiet | null).
 *   uoms      [{uom, he_so}] — mọi ĐVT đã khai quy đổi của mã (ĐVT kho he_so = 1)
 *   dvt       ĐVT kho (khi mã chỉ có một đơn vị)
 *   tong      tổng hiện có (sửa dòng) — điền sẵn, phím số đầu ghi đè
 *   chiTiet   chi tiết cũ [{uom, sl}] — mở lại đúng cách đã đếm
 *   tabDau    ĐVT mở sẵn (mã quét là mã THÙNG thì mở tab Thùng)
 *   phu       dòng phụ bên phải ô số (vd "siêu thị khai 48")
 *   okPhu     {label, onOk} — nút thứ hai cùng lưu số đang nhập (vd "+ QUÉT TIẾP")
 */
export function openSoLuong({ kicker = "", title = "", uoms = [], dvt = "", tong = 0, chiTiet = null,
  tabDau = null, phu = "", okLabel = "LƯU", okPhu = null, onOk }) {
  const ds = (uoms || []).filter((u) => u && u.uom && Number(u.he_so) > 0);
  const bac = ds.length ? ds.slice().sort((a, b) => Number(b.he_so) - Number(a.he_so)) : [{ uom: dvt || "ĐVT", he_so: 1 }];
  const heSo = (u) => Number(u.he_so) || 1;
  const goc = bac[bac.length - 1];
  const so = bac.map(() => 0);
  if (bac.length > 1 && chiTiet && chiTiet.length) {
    chiTiet.forEach((c) => { const i = bac.findIndex((u) => u.uom === c.uom); if (i >= 0) so[i] = Number(c.sl) || 0; });
  } else if (tong > 0) {
    const t = tachUom(tong, bac);
    if (t) t.forEach((c) => { so[bac.findIndex((u) => u.uom === c.uom)] = c.sl; });
    else so[bac.length - 1] = tong / heSo(goc);
  }
  let tab = tabDau ? Math.max(0, bac.findIndex((u) => u.uom === tabDau)) : so.findIndex((x) => x > 0);
  if (tab < 0) tab = 0;
  let value = so[tab] ? String(so[tab]) : "";
  let chuaGo = true;
  const tinh = () => bac.reduce((a, u, i) => a + so[i] * heSo(u), 0);

  const m = openSheet({ kicker, title });
  m.body.innerHTML = `
    ${bac.length > 1 ? '<div class="kt-th-np-tabs" role="tablist"></div>' : ""}
    <div class="kt-th-np-display"></div>
    <div class="kt-th-np-grid"></div>
    <div class="kt-th-np-loi" role="alert"></div>
    <div class="kt-th-np-hang"></div>`;
  const $ = (q) => m.body.querySelector(q);

  function ve() {
    const t = tinh();
    if (bac.length > 1) {
      $(".kt-th-np-tabs").innerHTML = bac.map((u, i) => `<button type="button" role="tab" aria-selected="${i === tab}"
        class="kt-th-np-tab${i === tab ? " is-on" : ""}" data-tab="${i}">${escapeHtml(u.uom)}${so[i] ? ` · ${fmt(so[i])}` : ""}${
        heSo(u) > 1 ? ` <i>(${fmt(heSo(u))} ${escapeHtml(goc.uom.toLowerCase())})</i>` : ""}</button>`).join("");
      $(".kt-th-np-tabs").querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
        tab = Number(b.dataset.tab);
        value = so[tab] ? String(so[tab]) : "";
        chuaGo = true;
        ve();
      }));
    }
    const nhan = [bac.length > 1 ? `Tổng ${fmt(t)} ${goc.uom.toLowerCase()}` : "", phu].filter(Boolean).join(" · ");
    $(".kt-th-np-display").innerHTML = `<div><div class="kt-th-np-unit">Số ${escapeHtml(bac[tab].uom.toLowerCase())}</div>
      <div class="kt-th-np-value">${escapeHtml(value || "0")}</div></div>
      ${nhan ? `<div class="kt-th-np-hint">${escapeHtml(nhan)}</div>` : ""}`;
    m.body.querySelectorAll("[data-ok]").forEach((b) => {
      b.textContent = (b.dataset.ok === "phu" ? okPhu.label : okLabel) + (t > 0 ? ` · ${fmt(t)} ${goc.uom.toUpperCase()}` : "");
    });
  }

  ["1", "2", "3", "4", "5", "6", "7", "8", "9", "C", "0", "⌫"].forEach((k) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "kt-th-np-key" + (k === "C" || k === "⌫" ? " is-phu" : "") + (k === "C" ? " is-xoa" : "");
    b.textContent = k;
    b.addEventListener("click", () => {
      value = bamPhim(value, k, chuaGo);
      chuaGo = false;
      so[tab] = Math.round(parseFloat(value || "0") || 0);
      ve();
    });
    $(".kt-th-np-grid").appendChild(b);
  });

  const xong = (fn) => {
    const t = tinh();
    if (!(t > 0)) {
      $(".kt-th-np-loi").textContent = `Chưa nhập số ${bac.map((u) => u.uom.toLowerCase()).join(" / ")}.`;
      return;
    }
    const ct = bac.length > 1 ? bac.map((u, i) => ({ uom: u.uom, sl: so[i], he_so: heSo(u) })).filter((c) => c.sl > 0) : null;
    m.close();
    fn(t, ct && ct.length ? ct : null);
  };
  const hang = $(".kt-th-np-hang");
  if (okPhu) {
    const b2 = document.createElement("button");
    b2.type = "button";
    b2.className = "kt-btn kt-btn--outline kt-th-np-ok";
    b2.dataset.ok = "phu";
    b2.addEventListener("click", () => xong(okPhu.onOk));
    hang.appendChild(b2);
  }
  const b1 = document.createElement("button");
  b1.type = "button";
  b1.className = "kt-btn kt-btn--primary kt-th-np-ok";
  b1.dataset.ok = "chinh";
  b1.addEventListener("click", () => xong(onOk));
  hang.appendChild(b1);
  ve();
  return m;
}
