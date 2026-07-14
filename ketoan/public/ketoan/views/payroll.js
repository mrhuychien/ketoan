// views/payroll.js — Tính lương tháng trong portal (SalaryDay + SalaryProduct).
// Port từ trang "Làm lương" chuẩn: quét & duyệt phiếu nháp, xuất 7 file Excel (ExcelJS),
// in PDF. Dùng frappe.client.get_list/get/submit qua api.call (tôn trọng quyền DocType).
// Gate: chỉ Kế toán trưởng (cap manager).
import { api } from "../lib/api.js";

const CSS = `
#lpay-app { --lp-bg:#f4f5f7; --lp-card:#fff; --lp-ink:#1f272e; --lp-sub:#6b7682;
  --lp-line:#e2e6ea; --lp-blue:#2490ef; --lp-blue-d:#1579d0; --lp-warn:#e8a33d;
  --lp-warn-d:#cf8a23; --lp-green:#28a745; --lp-red:#e24c4b; --lp-radius:8px;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif; color:var(--lp-ink); }
#lpay-app *, #lpay-app *::before, #lpay-app *::after { box-sizing:border-box; }
#lpay-app .lpay-wrap { max-width:860px; margin:0 auto; padding:4px 0 24px; }
#lpay-app .lpay-head { margin-bottom:18px; }
#lpay-app .lpay-title { font-size:22px; font-weight:700; margin:0; line-height:1.2; }
#lpay-app .lpay-sub { color:var(--lp-sub); margin:4px 0 0; font-size:14px; }
#lpay-app .lpay-panel { background:var(--lp-card); border:1px solid var(--lp-line); border-radius:var(--lp-radius); padding:18px; margin-bottom:16px; }
#lpay-app .lpay-period { display:flex; align-items:flex-end; gap:12px; flex-wrap:wrap; }
#lpay-app .lpay-label { display:block; font-size:13px; font-weight:600; color:var(--lp-sub); margin-bottom:6px; }
#lpay-app .lpay-month { height:38px; padding:0 12px; font-size:15px; border:1px solid var(--lp-line); border-radius:6px; background:#fff; color:var(--lp-ink); font-family:inherit; }
#lpay-app .lpay-month:focus { outline:none; border-color:var(--lp-blue); box-shadow:0 0 0 3px rgba(36,144,239,.15); }
#lpay-app select.lpay-month { min-width:180px; cursor:pointer; }
#lpay-app .lpay-period-field { display:flex; flex-direction:column; }
#lpay-app .lpay-period-field .lpay-link { font-weight:500; margin-left:6px; }
#lpay-app .lpay-h2 { font-size:16px; font-weight:700; margin:0 0 14px; display:flex; align-items:center; gap:9px; }
#lpay-app .lpay-h2-plain { margin:0; }
#lpay-app .lpay-step-no { display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; border-radius:50%; background:var(--lp-blue); color:#fff; font-size:13px; font-weight:700; flex:none; }
#lpay-app .lpay-note { font-size:13px; color:var(--lp-sub); margin:-4px 0 14px; }
#lpay-app .lpay-btn { height:38px; padding:0 16px; border:1px solid transparent; border-radius:6px; font-size:14px; font-weight:600; cursor:pointer; font-family:inherit; transition:background .12s,border-color .12s,opacity .12s; white-space:nowrap; }
#lpay-app .lpay-btn:disabled { opacity:.5; cursor:not-allowed; }
#lpay-app .lpay-btn-primary { background:var(--lp-blue); color:#fff; }
#lpay-app .lpay-btn-primary:not(:disabled):hover { background:var(--lp-blue-d); }
#lpay-app .lpay-btn-warn { background:var(--lp-warn); color:#fff; }
#lpay-app .lpay-btn-warn:not(:disabled):hover { background:var(--lp-warn-d); }
#lpay-app .lpay-btn-sm { height:32px; padding:0 12px; font-size:13px; }
#lpay-app .lpay-cards { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px; }
#lpay-app .lpay-c { border:1px solid var(--lp-line); border-radius:var(--lp-radius); padding:14px; }
#lpay-app .lpay-c-name { font-size:14px; font-weight:700; margin:0 0 2px; }
#lpay-app .lpay-c-dt { font-size:11px; color:var(--lp-sub); margin:0 0 12px; font-family:ui-monospace,Menlo,monospace; }
#lpay-app .lpay-c-row { display:flex; justify-content:space-between; align-items:baseline; padding:5px 0; font-size:13px; }
#lpay-app .lpay-c-row + .lpay-c-row { border-top:1px dashed var(--lp-line); }
#lpay-app .lpay-c-k { color:var(--lp-sub); }
#lpay-app .lpay-c-v { font-weight:700; font-size:18px; }
#lpay-app .lpay-c-v.lpay-zero { color:var(--lp-sub); font-weight:600; }
#lpay-app .lpay-c-v.lpay-has { color:var(--lp-warn-d); }
#lpay-app .lpay-c-btn { margin-top:12px; width:100%; }
#lpay-app .lpay-actions { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
#lpay-app .lpay-hint { font-size:12px; color:var(--lp-sub); }
#lpay-app .lpay-note b { color:var(--lp-ink); }
#lpay-app .lpay-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
#lpay-app .lpay-btn-export { background:#fff; border-color:var(--lp-line); color:var(--lp-ink); height:48px; justify-content:center; display:flex; align-items:center; }
#lpay-app .lpay-btn-export:not(:disabled):hover { border-color:var(--lp-blue); color:var(--lp-blue); background:#f6fafe; }
#lpay-app .lpay-btn-wide { grid-column:1 / -1; background:#f6fafe; border-color:var(--lp-blue); color:var(--lp-blue-d); }
#lpay-app .lpay-grid-2 { grid-template-columns:1fr 1fr; }
#lpay-app .lpay-btn-print { background:#fff; border-color:var(--lp-line); color:var(--lp-ink); height:48px; display:flex; align-items:center; justify-content:center; }
#lpay-app .lpay-btn-print:not(:disabled):hover { border-color:var(--lp-green); color:var(--lp-green); background:#f4fbf6; }
#lpay-app .lpay-note-sm { font-size:12px; margin:12px 0 0; }
#lpay-app .lpay-log-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
#lpay-app .lpay-link { background:none; border:none; color:var(--lp-blue); cursor:pointer; font-size:13px; font-family:inherit; padding:0; }
#lpay-app .lpay-link:hover { text-decoration:underline; }
#lpay-app .lpay-log { max-height:240px; overflow-y:auto; font-size:13px; line-height:1.5; font-family:ui-monospace,Menlo,Consolas,monospace; }
#lpay-app .lpay-log:empty::after { content:"Chưa có hoạt động."; color:var(--lp-sub); font-family:inherit; font-style:italic; }
#lpay-app .lpay-li { padding:5px 0; border-bottom:1px solid var(--lp-line); display:flex; gap:9px; }
#lpay-app .lpay-li:last-child { border-bottom:none; }
#lpay-app .lpay-t { color:var(--lp-sub); flex:none; }
#lpay-app .lpay-m-ok { color:var(--lp-green); }
#lpay-app .lpay-m-err { color:var(--lp-red); }
#lpay-app .lpay-m-info { color:var(--lp-ink); }
#lpay-app .lpay-spin { display:inline-block; width:13px; height:13px; border:2px solid rgba(255,255,255,.5); border-top-color:#fff; border-radius:50%; animation:lpay-rot .7s linear infinite; vertical-align:-2px; }
@keyframes lpay-rot { to { transform:rotate(360deg); } }
@media (max-width:640px) { #lpay-app .lpay-cards { grid-template-columns:1fr; } #lpay-app .lpay-grid { grid-template-columns:1fr 1fr; } #lpay-app .lpay-btn-export { height:44px; font-size:13px; padding:0 8px; } }
`;

const HTML = `
<div id="lpay-app"><div class="lpay-wrap">
  <header class="lpay-head">
    <h1 class="lpay-title">Tính lương tháng</h1>
    <p class="lpay-sub">Quét &amp; duyệt phiếu lương, xuất Excel &amp; in PDF theo kỳ · <a href="#/vt/payroll">Hướng dẫn &amp; lối tắt</a></p>
  </header>
  <section class="lpay-panel">
    <div class="lpay-period">
      <div class="lpay-period-field">
        <label class="lpay-label" for="lpay-period">Kỳ lương <span class="lpay-link" id="lpay-reload-period" role="button" tabindex="0">tải lại</span> · <span class="lpay-link" id="lpay-show-fields" role="button" tabindex="0">xem field</span></label>
        <select id="lpay-period" class="lpay-month"><option value="">Đang nạp kỳ…</option></select>
      </div>
      <button id="lpay-scan" class="lpay-btn lpay-btn-primary" type="button">Quét phiếu</button>
    </div>
  </section>
  <section class="lpay-panel" id="lpay-step1" hidden>
    <h2 class="lpay-h2"><span class="lpay-step-no">1</span> Quét &amp; duyệt phiếu nháp</h2>
    <div class="lpay-cards" id="lpay-cards"></div>
    <div class="lpay-actions">
      <button id="lpay-submit-all" class="lpay-btn lpay-btn-warn" type="button" disabled>Duyệt tất cả phiếu nháp</button>
      <span class="lpay-hint">Duyệt = submit phiếu trên ERPNext (không thể hoàn tác hàng loạt).</span>
    </div>
  </section>
  <section class="lpay-panel" id="lpay-step2" hidden>
    <h2 class="lpay-h2"><span class="lpay-step-no">2</span> Xuất file Excel</h2>
    <p class="lpay-note">Chỉ lấy dữ liệu đã <b>duyệt</b> (submitted) trong kỳ đã chọn.</p>
    <div class="lpay-grid">
      <button class="lpay-btn lpay-btn-export" data-loai="thnhat" type="button">Tổng hợp công nhật</button>
      <button class="lpay-btn lpay-btn-export" data-loai="thkhoan" type="button">Tổng hợp công khoán</button>
      <button class="lpay-btn lpay-btn-export" data-loai="nganhang" type="button">Chuyển khoản ngân hàng</button>
      <button class="lpay-btn lpay-btn-export" data-loai="tmnhat" type="button">Tiền mặt công nhật</button>
      <button class="lpay-btn lpay-btn-export" data-loai="tmkhoan" type="button">Tiền mặt công khoán</button>
      <button class="lpay-btn lpay-btn-export" data-loai="butru" type="button">Bù trừ chuyển khoản</button>
      <button class="lpay-btn lpay-btn-export lpay-btn-wide" data-loai="tonghop" type="button">Bảng tổng hợp lương</button>
    </div>
  </section>
  <section class="lpay-panel" id="lpay-step3" hidden>
    <h2 class="lpay-h2"><span class="lpay-step-no">3</span> In PDF</h2>
    <p class="lpay-note">Mở hộp thoại in — chọn “Đích/Máy in” là <b>Lưu thành PDF</b>.</p>
    <div class="lpay-grid lpay-grid-2">
      <button class="lpay-btn lpay-btn-print" data-group="bangluong" type="button">In bảng lương</button>
      <button class="lpay-btn lpay-btn-print" data-group="phatluong" type="button">In phát lương</button>
    </div>
    <p class="lpay-note lpay-note-sm">Bảng lương: công nhật + chuyển khoản. Phát lương: tiền mặt công nhật + công khoán + bù trừ (dòng cao để ký nhận).</p>
  </section>
  <section class="lpay-panel">
    <div class="lpay-log-head"><h2 class="lpay-h2 lpay-h2-plain">Nhật ký</h2><button id="lpay-clear-log" class="lpay-link" type="button">Xoá</button></div>
    <div id="lpay-log" class="lpay-log" aria-live="polite"></div>
  </section>
</div></div>
`;

const EXCELJS_SRC = "https://cdn.jsdelivr.net/npm/exceljs@4.4.0/dist/exceljs.min.js";
function loadExcelJS() {
  return new Promise((resolve, reject) => {
    if (window.ExcelJS) return resolve();
    let s = document.getElementById("lpay-exceljs");
    if (s) { s.addEventListener("load", () => resolve()); s.addEventListener("error", () => reject(new Error("Không tải được ExcelJS"))); return; }
    s = document.createElement("script");
    s.id = "lpay-exceljs"; s.src = EXCELJS_SRC;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Không tải được ExcelJS (kiểm tra mạng/CSP)"));
    document.head.appendChild(s);
  });
}

// ════════════════════ builders (window.PB tương đương) ════════════════════
const PB = (function () {
  "use strict";
  function XLSX_LIB() { var E = (typeof window !== "undefined" && window.ExcelJS); if (!E) throw new Error("Chưa tải được thư viện ExcelJS."); return E; }

  var DT_NHAT = "SalaryDay";
  var DT_KHOAN = "SalaryProduct";
  var FN = {
    employee_name: "employee_name", thang: "month", nam: "year", baohiem: "baohiem",
    luongthucnhan: "luongthucnhan", luongck: "luongck", chutaikhoan: "chutaikhoan",
    taikhoan: "taikhoan", nganhang: "nganhang", luongcoban: "luongcoban", congngay: "congngay",
    lamthem: "lamthem", luongngaycong: "luongngaycong", luonglamthem: "luonglamthem",
    anca: "anca", chuyencan: "chuyencan", hotrongaycong: "hotrongaycong", hotro: "hotro",
    luongsanpham: "luongsanpham",
  };
  var SIGN_DAY = 10;
  var BANLANHDAO_TONG = 166000000;
  var CK_NOIDUNG = "CK LUONG";
  var CK_ROUND = 1;
  var PERIOD = {
    nhat: { mode: "fields", monthField: "month", yearField: "year" },
    khoan: { mode: "date", dateField: "ngay" },
  };
  var BLD_NGANHANG = [
    { ten: "NGUYEN THI NGA", tk: "8848292453", tien: 15500000, cn: "NHTMCP DTPT VN-CN HAI DUONG - 31202005" },
    { ten: "NGUYEN THI TRANG NHUNG", tk: "8802759555", tien: 15500000, cn: "NHTMCP DTPT VN-CN THANH DONG-HAI DUONG - 31202004" },
    { ten: "KHUONG THI MINH LY", tk: "8824175155", tien: 21700000, cn: "NHTMCP DTPT VN-CN THANH DONG-HAI DUONG - 31202004" },
    { ten: "DAO VAN TIEN", tk: "4600018088", tien: 21700000, cn: "NHTMCP DTPT VN-CN HAI DUONG - 31202005" },
    { ten: "NGUYEN THI MIEN", tk: "4681729200", tien: 15500000, cn: "NHTMCP DTPT VN-CN THANH DONG-HAI DUONG - 31202004" },
    { ten: "DAO QUANG HON", tk: "8888292440", tien: 15500000, cn: "NHTMCP DTPT VN-CN HAI DUONG - 31202005" },
    { ten: "LE THI PHUONG", tk: "4681673079", tien: 13000000, cn: "NHTMCP DTPT VN-CN HAI DUONG - 31202005" },
    { ten: "DOAN THI HUONG", tk: "8828988889", tien: 15500000, cn: "NHTMCP DTPT VN-CN HAI DUONG - 31202005" },
  ];
  var BLD_BUTRU = [
    { ten: "Nguyễn Thị Nga", ltn: 42000000, lck: 31000000 },
    { ten: "Nguyễn Thị Miên", ltn: 47000000, lck: 37200000 },
    { ten: "Khương Thị Minh Lý", ltn: 64000000, lck: 37200000 },
    { ten: "Đoàn Thị Hương", ltn: 0, lck: 15500000 },
  ];
  var FIXED_NHAT = [];

  var COLSPEC_NHAT = [
    ["STT", null, "stt"], ["Họ tên", "employee_name", "txt"], ["Lương CB", "luongcoban", "money"],
    ["Công chính", "congngay", "qty"], ["Làm thêm", "lamthem", "qty"], ["Lương ngày công", "luongngaycong", "money"],
    ["Lương làm thêm", "luonglamthem", "money"], ["Ăn ca", "anca", "money"], ["Thưởng chuyên cần", "chuyencan", "money"],
    ["Hỗ trợ ngày công", "hotrongaycong", "money"], ["Trách nhiệm/Độc hại/Xăng xe", "hotro", "money"],
    ["Bảo hiểm", "baohiem", "money"], ["Tổng thu nhập", "luongthucnhan", "money"], ["Ký nhận", null, "sign"],
  ];
  var COLSPEC_KHOAN = [
    ["STT", null, "stt"], ["Họ tên", "employee_name", "txt"], ["Lương khoán sản phẩm", "luongsanpham", "money"],
    ["Tiền ăn ca", "anca", "money"], ["TN/Độc hại/Xăng xe", "hotro", "money"], ["Hỗ trợ ngày công", "hotrongaycong", "money"],
    ["Thưởng chuyên cần", "chuyencan", "money"], ["BHXH", "baohiem", "money"], ["Tổng thu nhập", "luongthucnhan", "money"], ["Ký nhận", null, "sign"],
  ];
  var NHAT_KEYS = ["employee_name", "luongcoban", "congngay", "lamthem", "luongngaycong", "luonglamthem", "anca", "chuyencan", "hotrongaycong", "hotro", "baohiem", "luongthucnhan", "luongck", "chutaikhoan", "taikhoan", "nganhang"];
  var KHOAN_KEYS = ["employee_name", "luongsanpham", "anca", "hotro", "hotrongaycong", "chuyencan", "baohiem", "luongthucnhan", "luongck", "chutaikhoan", "taikhoan", "nganhang"];

  var FONT = "Times New Roman";
  var FMT_VND = "#,##0;(#,##0)";
  var FMT_QTY = "#,##0.##";
  var BORDER = { top: { style: "thin" }, left: { style: "thin" }, bottom: { style: "thin" }, right: { style: "thin" } };

  function flt(v) { if (v === null || v === undefined || v === "") return 0; var n = Number(v); return isNaN(n) ? 0 : n; }
  function roundCK(n) { n = flt(n); return CK_ROUND > 0 ? Math.round(n / CK_ROUND) * CK_ROUND : n; }
  function cint(v) { var n = parseInt(Number(v), 10); return isNaN(n) ? 0 : n; }
  function pad2(n) { return String(n).padStart(2, "0"); }
  function sum(arr, key) { return arr.reduce(function (a, r) { return a + flt(r[key]); }, 0); }
  function colLetter(n) { var s = ""; while (n > 0) { var m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26); } return s; }

  function hdr(cell, val) { cell.value = val; cell.font = { name: FONT, bold: true, size: 11 }; cell.alignment = { horizontal: "center", vertical: "middle", wrapText: true }; cell.border = BORDER; cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFDDDDDD" } }; }
  function sty(c, o) { o = o || {}; c.font = { name: FONT, size: 11, bold: !!o.bold, italic: !!o.italic }; c.border = BORDER; if (o.num) { c.numFmt = o.qty ? FMT_QTY : FMT_VND; c.alignment = { horizontal: "right", vertical: "middle" }; } else { c.alignment = { horizontal: o.center ? "center" : "left", vertical: "middle" }; } }

  var COMPANY = "CÔNG TY CỔ PHẦN HOÀNG GIANG";
  function titleFor(loai, thang, nam) {
    var T = { thnhat: "BẢNG LƯƠNG CÔNG NHẬT", thkhoan: "BẢNG LƯƠNG CÔNG KHOÁN", tmnhat: "BẢNG THANH TOÁN TIỀN MẶT (CÔNG NHẬT)", tmkhoan: "BẢNG THANH TOÁN TIỀN MẶT (CÔNG KHOÁN)", butru: "BẢNG BÙ TRỪ LƯƠNG", nganhang: "DANH SÁCH CHUYỂN KHOẢN LƯƠNG" };
    return (T[loai] || "BẢNG LƯƠNG") + " THÁNG " + pad2(cint(thang)) + "/" + cint(nam);
  }
  function titleRows(ws, opts, nCol) {
    var line = 0;
    function mergeText(row, text, size) { ws.mergeCells(row, 1, row, nCol); var c = ws.getCell(row, 1); c.value = text; c.font = { name: FONT, bold: true, size: size }; c.alignment = { horizontal: "center", vertical: "middle" }; }
    if (opts.company) { line++; mergeText(line, opts.company, 12); }
    if (opts.title) { line++; mergeText(line, opts.title, 14); ws.getRow(line).height = 26; }
    return line > 0 ? line + 2 : 1;
  }
  function fmtVND(n) { n = Math.round(flt(n)); var neg = n < 0; n = Math.abs(n); var s = String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","); return neg ? "(" + s + ")" : s; }
  function fmtQty(n) { n = flt(n); return String(Math.round(n * 100) / 100); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>]/g, function (m) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[m]; }); }

  function buildSalary(recs, colspec, opts) {
    opts = opts || {}; var ExcelJS = XLSX_LIB(); var wb = new ExcelJS.Workbook(); var ws = wb.addWorksheet("Tong hop");
    var nCol = colspec.length; var hRow = titleRows(ws, opts, nCol);
    colspec.forEach(function (cs, j) { hdr(ws.getCell(hRow, j + 1), cs[0]); }); ws.getRow(hRow).height = 44;
    var first = hRow + 1, r = first;
    recs.forEach(function (rec, i) {
      colspec.forEach(function (cs, jj) { var key = cs[1], kind = cs[2], c = ws.getCell(r, jj + 1);
        if (kind === "stt") { c.value = i + 1; sty(c, { center: true }); }
        else if (kind === "sign") { sty(c); }
        else if (kind === "txt") { c.value = rec[key] || ""; sty(c); }
        else { c.value = flt(rec[key]); sty(c, { num: true, qty: kind === "qty" }); } });
      if (opts.tall) ws.getRow(r).height = 34; r++;
    });
    var last = r - 1;
    if (recs.length) {
      ws.mergeCells(r, 1, r, 2); var t = ws.getCell(r, 1); t.value = "Tổng"; t.font = { name: FONT, bold: true, size: 11 }; t.alignment = { horizontal: "center", vertical: "middle" };
      ws.getCell(r, 1).border = BORDER; ws.getCell(r, 2).border = BORDER;
      colspec.forEach(function (cs, jj) { var kind = cs[2], j = jj + 1; if (j <= 2) return; var c = ws.getCell(r, j);
        if (kind === "money" || kind === "qty") { var L = colLetter(j); c.value = { formula: "SUM(" + L + first + ":" + L + last + ")" }; sty(c, { num: true, bold: true, qty: kind === "qty" }); } else { sty(c, { bold: true }); } });
    }
    var w = { stt: 6, txt: 24, sign: 16, money: 13, qty: 9 };
    colspec.forEach(function (cs, jj) { ws.getColumn(jj + 1).width = w[cs[2]] || 13; });
    ws.views = [{ state: "frozen", ySplit: hRow }]; return wb;
  }

  function buildNganhang(data) {
    var ExcelJS = XLSX_LIB(); var wb = new ExcelJS.Workbook(); var ws = wb.addWorksheet("File luong mau");
    var H = ["STT\n(Bắt buộc, định dạng số, tối đa 4 ký tự)", "Tên người thụ hưởng \n(Bắt buộc, định dạng text, tối đa 70 ký tự)", "Tài khoản người thụ hưởng\n(Bắt buộc, định dạng text, tối đa 20 ký tự)", "Số tiền\n(Bắt buộc, định dạng số, mặc định là VND)", "Chi nhánh Ngân hàng hưởng\n(Định dạng Tên Chi nhánh ngân hàng_Mã 8 số) (bắt buộc)", "Nội dung\n(Bắt buộc, tối đa 150 ký tự)\n"];
    H.forEach(function (h, j) { hdr(ws.getCell(1, j + 1), h); }); ws.getRow(1).height = 58;
    ["(1)", "(2)", "(3)", "(4)", "(5)", "(6)"].forEach(function (t, j) { var c = ws.getCell(2, j + 1); c.value = t; sty(c, { center: true }); });
    var r = 3;
    data.forEach(function (row, i) { var ten = row[0], tk = row[1], tien = row[2], cn = row[3];
      var c1 = ws.getCell(r, 1); c1.value = i + 1; sty(c1, { center: true });
      var c2 = ws.getCell(r, 2); c2.value = ten || ""; sty(c2);
      var c3 = ws.getCell(r, 3); c3.value = String(tk || ""); sty(c3); c3.numFmt = "@";
      var c4 = ws.getCell(r, 4); c4.value = flt(tien); sty(c4, { num: true });
      var c5 = ws.getCell(r, 5); c5.value = cn || ""; sty(c5);
      var c6 = ws.getCell(r, 6); c6.value = CK_NOIDUNG; sty(c6); r++; });
    [8, 34, 24, 16, 48, 20].forEach(function (wd, j) { ws.getColumn(j + 1).width = wd; }); return wb;
  }

  function buildButru(empRows, opts) {
    opts = opts || {}; var ExcelJS = XLSX_LIB(); var wb = new ExcelJS.Workbook(); var ws = wb.addWorksheet("SalaryDay");
    var H = ["STT", "Họ và tên", "Lương thực nhận", "Lương chuyển khoản", "Bù trừ", "Ký nhận"];
    var hRow = titleRows(ws, opts, 6); H.forEach(function (h, j) { hdr(ws.getCell(hRow, j + 1), h); }); ws.getRow(hRow).height = 30;
    function row(r, idx, ten, ltn, lck) { var c;
      c = ws.getCell(r, 1); c.value = idx; sty(c, { center: true });
      c = ws.getCell(r, 2); c.value = ten || ""; sty(c);
      c = ws.getCell(r, 3); c.value = flt(ltn); sty(c, { num: true });
      c = ws.getCell(r, 4); c.value = flt(lck); sty(c, { num: true });
      c = ws.getCell(r, 5); c.value = { formula: "C" + r + "-D" + r }; sty(c, { num: true });
      c = ws.getCell(r, 6); sty(c); if (opts.tall) ws.getRow(r).height = 34; }
    var first = hRow + 1, r = first, idx = 1;
    empRows.forEach(function (rec) { row(r, idx, rec.employee_name, flt(rec.luongthucnhan), flt(rec.luongck)); r++; idx++; });
    BLD_BUTRU.forEach(function (b) { row(r, idx, b.ten, flt(b.ltn), flt(b.lck)); r++; idx++; });
    var last = r - 1;
    ws.mergeCells(r, 1, r, 2); var t = ws.getCell(r, 1); t.value = "Tổng"; t.font = { name: FONT, bold: true, size: 11 }; t.alignment = { horizontal: "center", vertical: "middle" };
    for (var col = 1; col <= 6; col++) ws.getCell(r, col).border = BORDER;
    var ce = ws.getCell(r, 5); ce.value = { formula: "SUM(E" + first + ":E" + last + ")" }; sty(ce, { num: true, bold: true });
    [6, 24, 16, 16, 15, 12].forEach(function (wd, j) { ws.getColumn(j + 1).width = wd; });
    ws.views = [{ state: "frozen", ySplit: hRow }]; return wb;
  }

  function buildTonghop(agg, thang, nam) {
    var ExcelJS = XLSX_LIB(); var wb = new ExcelJS.Workbook(); var ws = wb.addWorksheet("Tong hop");
    function money(c, v, o) { o = o || {}; c.value = v; c.font = { name: FONT, size: 11, bold: !!o.bold, italic: !!o.italic }; c.alignment = { horizontal: "right", vertical: "middle" }; c.numFmt = FMT_VND; c.border = BORDER; }
    function label(c, v, o) { o = o || {}; c.value = v; c.font = { name: FONT, size: 11, bold: !!o.bold, italic: !!o.italic }; c.alignment = { horizontal: o.center ? "center" : "left", vertical: "middle" }; c.border = BORDER; }
    ws.mergeCells("A1:C1"); var tt = ws.getCell(1, 1); tt.value = (COMPANY ? COMPANY + "\n" : "") + "TỔNG LƯƠNG THÁNG " + pad2(cint(thang)) + "/" + cint(nam); tt.font = { name: FONT, bold: true, size: 13 }; tt.alignment = { horizontal: "center", vertical: "middle", wrapText: true }; ws.getRow(1).height = COMPANY ? 44 : 28;
    ["STT", "Tên bộ phận", "Số tiền"].forEach(function (h, j) { hdr(ws.getCell(3, j + 1), h); });
    label(ws.getCell(4, 1), 1, { center: true }); label(ws.getCell(4, 2), "Bộ phận Công nhật"); money(ws.getCell(4, 3), agg.tong_nhat);
    label(ws.getCell(5, 1), 2, { center: true }); label(ws.getCell(5, 2), "Bộ phận Sản Xuất"); money(ws.getCell(5, 3), agg.tong_khoan);
    label(ws.getCell(6, 1), 3, { center: true }); label(ws.getCell(6, 2), "Lương Ban lãnh đạo"); money(ws.getCell(6, 3), agg.tong_bld);
    ws.mergeCells("A7:B7"); label(ws.getCell(7, 1), "Tổng", { bold: true, center: true }); ws.getCell(7, 2).border = BORDER; money(ws.getCell(7, 3), { formula: "SUM(C4:C6)" }, { bold: true });
    label(ws.getCell(9, 1), 1, { bold: true, center: true }); label(ws.getCell(9, 2), "Lương chuyển khoản", { bold: true }); money(ws.getCell(9, 3), agg.tong_ck, { bold: true });
    label(ws.getCell(10, 1), 2, { bold: true, center: true }); label(ws.getCell(10, 2), "Tiền mặt", { bold: true }); money(ws.getCell(10, 3), { formula: "C11+C12+C13" }, { bold: true });
    label(ws.getCell(11, 1), "2.1", { italic: true, center: true }); label(ws.getCell(11, 2), "Tiền mặt công nhật", { italic: true }); money(ws.getCell(11, 3), agg.tm_nhat, { italic: true });
    label(ws.getCell(12, 1), "2.2", { italic: true, center: true }); label(ws.getCell(12, 2), "Tiền mặt công khoán", { italic: true }); money(ws.getCell(12, 3), agg.tm_khoan, { italic: true });
    label(ws.getCell(13, 1), "2.3", { italic: true, center: true }); label(ws.getCell(13, 2), "Tiền mặt bù trừ", { italic: true }); money(ws.getCell(13, 3), agg.tm_butru, { italic: true });
    ws.mergeCells("A14:B14"); label(ws.getCell(14, 1), "Tổng", { bold: true, center: true }); ws.getCell(14, 2).border = BORDER; money(ws.getCell(14, 3), { formula: "C9+C10" }, { bold: true });
    ws.mergeCells("A16:C16"); var tm = cint(thang) + 1, ny = cint(nam); if (tm > 12) { tm = 1; ny++; }
    var f1 = ws.getCell(16, 1); f1.value = "Hải Dương, ngày " + pad2(SIGN_DAY) + " tháng " + pad2(tm) + " năm " + ny; f1.font = { name: FONT, size: 11, italic: true }; f1.alignment = { horizontal: "right" };
    ws.mergeCells("A17:C17"); var f2 = ws.getCell(17, 1); f2.value = "Giám đốc duyệt"; f2.font = { name: FONT, size: 11, bold: true }; f2.alignment = { horizontal: "right" };
    [8, 30, 20].forEach(function (wd, j) { ws.getColumn(j + 1).width = wd; }); return wb;
  }

  function computeAgg(nhat, khoan) {
    var bankEmp = 0;
    nhat.forEach(function (r) { if (flt(r.baohiem) > 0) { var lck = flt(r.luongck); bankEmp += lck > 0 ? lck : flt(r.luongthucnhan); } });
    khoan.forEach(function (r) { if (flt(r.baohiem) > 0) bankEmp += flt(r.luongthucnhan); });
    return {
      tong_nhat: sum(nhat, "luongthucnhan"), tong_khoan: sum(khoan, "luongthucnhan"), tong_bld: BANLANHDAO_TONG,
      tong_ck: bankEmp + BLD_NGANHANG.reduce(function (a, b) { return a + b.tien; }, 0),
      tm_nhat: nhat.filter(function (r) { return flt(r.baohiem) <= 0; }).reduce(function (a, r) { return a + flt(r.luongthucnhan); }, 0),
      tm_khoan: khoan.filter(function (r) { return flt(r.baohiem) <= 0; }).reduce(function (a, r) { return a + flt(r.luongthucnhan); }, 0),
      tm_butru: nhat.filter(function (r) { return flt(r.luongck) > 0; }).reduce(function (a, r) { return a + (flt(r.luongthucnhan) - flt(r.luongck)); }, 0) + BLD_BUTRU.reduce(function (a, b) { return a + (b.ltn - b.lck); }, 0),
    };
  }
  function bankRows(nhat, khoan) {
    var data = [];
    nhat.forEach(function (r) { if (flt(r.baohiem) > 0) { var lck = flt(r.luongck); data.push([r.chutaikhoan || r.employee_name || "", r.taikhoan, roundCK(lck > 0 ? lck : flt(r.luongthucnhan)), r.nganhang || ""]); } });
    khoan.forEach(function (r) { if (flt(r.baohiem) > 0) data.push([r.chutaikhoan || r.employee_name || "", r.taikhoan, roundCK(flt(r.luongthucnhan)), r.nganhang || ""]); });
    BLD_NGANHANG.forEach(function (b) { data.push([b.ten, b.tk, roundCK(b.tien), b.cn]); });
    return data;
  }
  function buildBank(nhat, khoan) { return buildNganhang(bankRows(nhat, khoan)); }

  function section(opts, inner) { var h = ""; if (opts.company) h += '<div class="co">' + esc(opts.company) + "</div>"; if (opts.title) h += '<div class="ti">' + esc(opts.title) + "</div>"; return "<section>" + h + "<table>" + inner + "</table></section>"; }
  var COLW = { stt: "3%", txt: "13%", qty: "4.5%", money: "7.5%", sign: "7%" };
  function colgroupFor(colspec) { return "<colgroup>" + colspec.map(function (cs) { return '<col style="width:' + (COLW[cs[2]] || "8%") + '">'; }).join("") + "</colgroup>"; }
  function htmlSalary(recs, colspec, opts) {
    opts = opts || {};
    var th = colspec.map(function (cs) { return "<th>" + esc(cs[0]) + "</th>"; }).join(""); var body = "";
    recs.forEach(function (rec, i) { var tds = colspec.map(function (cs) { var key = cs[1], kind = cs[2];
      if (kind === "stt") return '<td class="c">' + (i + 1) + "</td>"; if (kind === "sign") return "<td></td>"; if (kind === "txt") return "<td>" + esc(rec[key] || "") + "</td>";
      var v = flt(rec[key]); return '<td class="n">' + (kind === "qty" ? fmtQty(v) : fmtVND(v)) + "</td>"; }).join("");
      body += "<tr" + (opts.tall ? ' class="tall"' : "") + ">" + tds + "</tr>"; });
    var foot = "";
    if (recs.length) { var cells = colspec.map(function (cs, jj) { var kind = cs[2], j = jj + 1; if (j <= 2) return "";
      if (kind === "money" || kind === "qty") { var s = recs.reduce(function (a, r) { return a + flt(r[cs[1]]); }, 0); return '<td class="n b">' + (kind === "qty" ? fmtQty(s) : fmtVND(s)) + "</td>"; } return "<td></td>"; }).join("");
      foot = '<tr class="tot"><td class="c b" colspan="2">Tổng</td>' + cells + "</tr>"; }
    return section(opts, colgroupFor(colspec) + "<thead><tr>" + th + "</tr></thead><tbody>" + body + foot + "</tbody>");
  }
  function htmlNganhang(data, opts) {
    opts = opts || {}; var heads = ["STT", "Tên người thụ hưởng", "Tài khoản", "Số tiền", "Chi nhánh ngân hàng", "Nội dung"]; var th = heads.map(function (h) { return "<th>" + esc(h) + "</th>"; }).join("");
    var body = "", s = 0; data.forEach(function (row, i) { s += flt(row[2]); body += "<tr" + (opts.tall ? ' class="tall"' : "") + '><td class="c">' + (i + 1) + "</td><td>" + esc(row[0]) + "</td><td>" + esc(String(row[1] == null ? "" : row[1])) + '</td><td class="n">' + fmtVND(row[2]) + "</td><td>" + esc(row[3]) + "</td><td>" + esc(CK_NOIDUNG) + "</td></tr>"; });
    var foot = '<tr class="tot"><td class="c b" colspan="3">Tổng</td><td class="n b">' + fmtVND(s) + "</td><td></td><td></td></tr>";
    return section(opts, "<thead><tr>" + th + "</tr></thead><tbody>" + body + foot + "</tbody>");
  }
  function htmlButru(empRows, opts) {
    opts = opts || {}; var heads = ["STT", "Họ và tên", "Lương thực nhận", "Lương chuyển khoản", "Bù trừ", "Ký nhận"]; var th = heads.map(function (h) { return "<th>" + esc(h) + "</th>"; }).join("");
    var rows = []; empRows.forEach(function (r) { rows.push([r.employee_name, flt(r.luongthucnhan), flt(r.luongck)]); }); BLD_BUTRU.forEach(function (b) { rows.push([b.ten, flt(b.ltn), flt(b.lck)]); });
    var body = "", sBt = 0; rows.forEach(function (x, i) { var bt = x[1] - x[2]; sBt += bt; body += "<tr" + (opts.tall ? ' class="tall"' : "") + '><td class="c">' + (i + 1) + "</td><td>" + esc(x[0]) + '</td><td class="n">' + fmtVND(x[1]) + '</td><td class="n">' + fmtVND(x[2]) + '</td><td class="n">' + fmtVND(bt) + "</td><td></td></tr>"; });
    var foot = '<tr class="tot"><td class="c b" colspan="4">Tổng</td><td class="n b">' + fmtVND(sBt) + "</td><td></td></tr>";
    var cg = '<colgroup><col style="width:6%"><col style="width:30%"><col style="width:18%"><col style="width:18%"><col style="width:16%"><col style="width:12%"></colgroup>';
    return section(opts, cg + "<thead><tr>" + th + "</tr></thead><tbody>" + body + foot + "</tbody>");
  }
  function buildPrintHTML(group, nhat, khoan, thang, nam) {
    var nhatAll = (nhat || []).concat(FIXED_NHAT); khoan = khoan || []; var co = COMPANY; var secs = "";
    if (group === "bangluong") { secs += htmlSalary(nhatAll, COLSPEC_NHAT, { title: titleFor("thnhat", thang, nam), company: co }); secs += htmlSalary(khoan, COLSPEC_KHOAN, { title: titleFor("thkhoan", thang, nam), company: co }); }
    else { secs += htmlSalary(nhatAll.filter(function (r) { return flt(r.baohiem) <= 0; }), COLSPEC_NHAT, { title: titleFor("tmnhat", thang, nam), company: co, tall: true }); secs += htmlSalary(khoan.filter(function (r) { return flt(r.baohiem) <= 0; }), COLSPEC_KHOAN, { title: titleFor("tmkhoan", thang, nam), company: co, tall: true }); secs += htmlButru(nhatAll.filter(function (r) { return flt(r.luongck) > 0; }), { title: titleFor("butru", thang, nam), company: co, tall: true }); }
    return secs;
  }
  function buildFile(loai, nhat, khoan, thang, nam) {
    nhat = (nhat || []).concat(FIXED_NHAT); khoan = khoan || []; var co = COMPANY; function ti(l) { return titleFor(l, thang, nam); }
    switch (loai) {
      case "thnhat": return { wb: buildSalary(nhat, COLSPEC_NHAT, { title: ti("thnhat"), company: co }), rows: nhat.length };
      case "thkhoan": return { wb: buildSalary(khoan, COLSPEC_KHOAN, { title: ti("thkhoan"), company: co }), rows: khoan.length };
      case "tmnhat": { var f1 = nhat.filter(function (r) { return flt(r.baohiem) <= 0; }); return { wb: buildSalary(f1, COLSPEC_NHAT, { title: ti("tmnhat"), company: co, tall: true }), rows: f1.length }; }
      case "tmkhoan": { var f2 = khoan.filter(function (r) { return flt(r.baohiem) <= 0; }); return { wb: buildSalary(f2, COLSPEC_KHOAN, { title: ti("tmkhoan"), company: co, tall: true }), rows: f2.length }; }
      case "nganhang": { var n = nhat.filter(function (r) { return flt(r.baohiem) > 0; }).length + khoan.filter(function (r) { return flt(r.baohiem) > 0; }).length + BLD_NGANHANG.length; return { wb: buildBank(nhat, khoan), rows: n }; }
      case "butru": { var f3 = nhat.filter(function (r) { return flt(r.luongck) > 0; }); return { wb: buildButru(f3, { title: ti("butru"), company: co, tall: true }), rows: f3.length + BLD_BUTRU.length }; }
      case "tonghop": return { wb: buildTonghop(computeAgg(nhat, khoan), thang, nam), rows: nhat.length + khoan.length };
    }
    throw new Error("Loại file không hợp lệ: " + loai);
  }
  var NEED = { thnhat: "n", tmnhat: "n", butru: "n", thkhoan: "k", tmkhoan: "k", nganhang: "nk", tonghop: "nk" };

  return {
    buildFile: buildFile, computeAgg: computeAgg, buildPrintHTML: buildPrintHTML,
    COLSPEC_NHAT: COLSPEC_NHAT, COLSPEC_KHOAN: COLSPEC_KHOAN, NHAT_KEYS: NHAT_KEYS, KHOAN_KEYS: KHOAN_KEYS, NEED: NEED,
    FN: FN, DT_NHAT: DT_NHAT, DT_KHOAN: DT_KHOAN, PERIOD: PERIOD, flt: flt, cint: cint,
  };
})();

// ════════════════════════ controller ════════════════════════
var cint = PB.cint;
var LABEL = { thnhat: "Tổng hợp công nhật", thkhoan: "Tổng hợp công khoán", nganhang: "Chuyển khoản ngân hàng", tmnhat: "Tiền mặt công nhật", tmkhoan: "Tiền mặt công khoán", butru: "Bù trừ chuyển khoản", tonghop: "Bảng tổng hợp lương" };
var PREFIX_FILE = { thnhat: "TH_cong_nhat", thkhoan: "TH_cong_khoan", nganhang: "Chuyen_khoan_NH", tmnhat: "TM_cong_nhat", tmkhoan: "TM_cong_khoan", butru: "Bu_tru", tonghop: "Bang_tong_hop" };
var SUBMIT_ALL_LABEL = "Duyệt tất cả phiếu nháp";
var STD_FIELDS = { name: 1, owner: 1, creation: 1, modified: 1, modified_by: 1, docstatus: 1, idx: 1, parent: 1, parentfield: 1, parenttype: 1, doctype: 1 };

var $ = function (id) { return document.getElementById(id); };
var logBox, P = null, DATA = { nhat: [], khoan: [], loaded: false }, PF = { nhat: null, khoan: null };

function pad2(n) { return String(n).padStart(2, "0"); }
function nowt() { var d = new Date(); return pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":" + pad2(d.getSeconds()); }
function esc(s) { return String(s).replace(/[&<>]/g, function (m) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[m]; }); }
function log(msg, kind) { kind = kind || "info"; if (!logBox) return; var li = document.createElement("div"); li.className = "lpay-li"; li.innerHTML = '<span class="lpay-t">' + nowt() + "</span><span class=\"lpay-m-" + kind + '">' + esc(msg) + "</span>"; logBox.appendChild(li); logBox.scrollTop = logBox.scrollHeight; }
function shortErr(e) { var m = (e && e.message) ? e.message : String(e); return m.length > 200 ? m.slice(0, 200) + "…" : m; }
function call(method, args) { return api.call(method, args || {}); }

function readPeriod() { var sel = $("lpay-period"); var o = sel && sel.selectedOptions && sel.selectedOptions[0]; if (!o || !o.dataset || !o.dataset.year) return null; var thang = Number(o.dataset.month), nam = Number(o.dataset.year); if (!nam || !thang) return null; return { thang: thang, nam: nam }; }
function normalize(rows, keys) { return rows.map(function (r) { var o = {}; keys.forEach(function (k) { var fn = PB.FN[k]; o[k] = (fn in r) ? r[fn] : undefined; }); return o; }); }
function fetchAll(doctype) { var PAGE = 500, all = []; function more(start) { return call("frappe.client.get_list", { doctype: doctype, fields: ["*"], limit_start: start, limit_page_length: PAGE, order_by: "modified desc" }).then(function (rows) { rows = rows || []; all = all.concat(rows); if (rows.length === PAGE) return more(start + PAGE); return all; }); } return more(0); }
function keysOf(rows) { return rows.length ? Object.keys(rows[0]) : []; }
function parseYM(v) { if (v === null || v === undefined || v === "") return null; var m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})/); if (!m) return null; var yr = +m[1], mo = +m[2]; if (mo < 1 || mo > 12 || yr < 2000 || yr > 2100) return null; return { mo: mo, yr: yr }; }
function periodOf(r, pf) { if (!pf || !pf.ok) return null; if (pf.mode === "date") return parseYM(r[pf.dateField]); var mo = cint(r[pf.monthField]), yr = cint(r[pf.yearField]); if (mo >= 1 && mo <= 12 && yr >= 2000 && yr <= 2100) return { mo: mo, yr: yr }; return null; }
function resolvePeriod(cfg, rows) { var out = { mode: cfg.mode, monthField: cfg.monthField, yearField: cfg.yearField, dateField: cfg.dateField, ok: false }; if (!rows.length) { out.ok = true; return out; } var keys = keysOf(rows); if (cfg.mode === "date") out.ok = keys.indexOf(cfg.dateField) >= 0; else out.ok = keys.indexOf(cfg.monthField) >= 0 && keys.indexOf(cfg.yearField) >= 0; return out; }
function srcTxt(pf) { return pf.mode === "date" ? ("trường ngày ‘" + pf.dateField + "’") : ("field ‘" + pf.monthField + "’ & ‘" + pf.yearField + "’"); }

function buildPeriodOptions(keep) {
  var sel = $("lpay-period"); var prev = keep ? sel.value : null; var map = {};
  function addFrom(rows, pf) { rows.forEach(function (r) { var p = periodOf(r, pf); if (p) map[p.yr * 100 + p.mo] = { mo: p.mo, yr: p.yr }; }); }
  addFrom(DATA.nhat, PF.nhat); addFrom(DATA.khoan, PF.khoan);
  var periods = Object.keys(map).map(function (k) { return map[k]; }).sort(function (a, b) { return (b.yr * 100 + b.mo) - (a.yr * 100 + a.mo); });
  sel.innerHTML = ""; if (!periods.length) { sel.innerHTML = '<option value="">(không có kỳ)</option>'; return; }
  periods.forEach(function (p) { var o = document.createElement("option"); o.value = p.yr + "-" + pad2(p.mo); o.dataset.month = p.mo; o.dataset.year = p.yr; o.textContent = "Tháng " + pad2(p.mo) + "/" + p.yr; sel.appendChild(o); });
  sel.selectedIndex = 0; if (prev) { for (var i = 0; i < sel.options.length; i++) { if (sel.options[i].value === prev) { sel.selectedIndex = i; break; } } }
}
function loadData(keep) {
  var sel = $("lpay-period"); sel.innerHTML = '<option value="">Đang nạp dữ liệu…</option>';
  return Promise.all([fetchAll(PB.DT_NHAT), fetchAll(PB.DT_KHOAN)]).then(function (res) {
    DATA.nhat = res[0]; DATA.khoan = res[1]; DATA.loaded = true;
    if (!DATA.nhat.length && !DATA.khoan.length) { sel.innerHTML = '<option value="">(chưa có dữ liệu)</option>'; log("Hai DocType chưa có bản ghi nào.", "info"); return; }
    PF.nhat = resolvePeriod(PB.PERIOD.nhat, DATA.nhat); PF.khoan = resolvePeriod(PB.PERIOD.khoan, DATA.khoan);
    function lbl(dt, pf, arr) { if (!arr.length) return dt + ": 0 bản ghi"; if (!pf.ok) return dt + ": " + arr.length + " bản ghi, THIẾU trường kỳ (" + srcTxt(pf) + ") — bấm “xem field”"; return dt + ": " + arr.length + " bản ghi, kỳ theo " + srcTxt(pf); }
    var okN = !DATA.nhat.length || PF.nhat.ok, okK = !DATA.khoan.length || PF.khoan.ok;
    log(lbl(PB.DT_NHAT, PF.nhat, DATA.nhat) + " · " + lbl(PB.DT_KHOAN, PF.khoan, DATA.khoan), (okN && okK) ? "ok" : "err");
    if (!okN || !okK) log("DocType nào THIẾU trường kỳ sẽ hiện 0 phiếu — kiểm tên trường trong CONFIG (PERIOD).", "err");
    buildPeriodOptions(keep);
  }).catch(function (e) { sel.innerHTML = '<option value="">(lỗi nạp)</option>'; log("Không nạp được dữ liệu: " + shortErr(e), "err"); });
}
function showFields() {
  if (!DATA.loaded) { log("Chưa có dữ liệu — nạp xong mới xem được field.", "info"); return; }
  function dump(dt, rows) { if (!rows.length) { log(dt + ": chưa có bản ghi.", "info"); return; } log(dt + " field: " + Object.keys(rows[0]).filter(function (k) { return k.charAt(0) !== "_" && !STD_FIELDS[k]; }).join(", "), "info"); }
  dump(PB.DT_NHAT, DATA.nhat); dump(PB.DT_KHOAN, DATA.khoan);
}
function inPeriod(rows, pf, docstatus) { if (!pf || !pf.ok) return []; return rows.filter(function (r) { var p = periodOf(r, pf); return p && p.mo === P.thang && p.yr === P.nam && (docstatus === undefined || cint(r.docstatus) === docstatus); }); }

function setBusy(btn, busy, label) { if (!btn) return; if (busy) { if (btn.dataset.label === undefined) btn.dataset.label = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="lpay-spin"></span> ' + (label || "Đang xử lý…"); } else { btn.disabled = false; if (btn.dataset.label !== undefined) { btn.innerHTML = btn.dataset.label; delete btn.dataset.label; } } }
function setProg(btn, txt) { btn.disabled = true; btn.innerHTML = '<span class="lpay-spin"></span> ' + txt; }

function scan() {
  P = readPeriod(); if (!P) { log("Chưa chọn kỳ lương.", "err"); return Promise.resolve(); }
  if (!DATA.loaded) { log("Dữ liệu chưa nạp xong — đợi giây lát rồi thử lại.", "info"); return Promise.resolve(); }
  var s = { congnhat: { label: "Công nhật", doctype: PB.DT_NHAT, draft: inPeriod(DATA.nhat, PF.nhat, 0).length, submitted: inPeriod(DATA.nhat, PF.nhat, 1).length }, congkhoan: { label: "Công khoán", doctype: PB.DT_KHOAN, draft: inPeriod(DATA.khoan, PF.khoan, 0).length, submitted: inPeriod(DATA.khoan, PF.khoan, 1).length } };
  renderCards(s); $("lpay-step1").hidden = false; $("lpay-step2").hidden = false; $("lpay-step3").hidden = false;
  var td = s.congnhat.draft + s.congkhoan.draft;
  log("Kỳ tháng " + pad2(P.thang) + "/" + P.nam + ": " + td + " phiếu nháp (công nhật " + s.congnhat.draft + ", công khoán " + s.congkhoan.draft + "); đã duyệt " + (s.congnhat.submitted + s.congkhoan.submitted) + ".", td ? "info" : "ok");
  return Promise.resolve();
}
function refreshSubmitAll(anyDraft) { var sa = $("lpay-submit-all"); sa.innerHTML = SUBMIT_ALL_LABEL; delete sa.dataset.label; sa.disabled = !anyDraft; }
function renderCards(s) {
  var box = $("lpay-cards"); box.innerHTML = ""; var anyDraft = false;
  [["congnhat", s.congnhat], ["congkhoan", s.congkhoan]].forEach(function (pair) {
    var key = pair[0], c = pair[1]; var hasDraft = c.draft > 0; if (hasDraft) anyDraft = true;
    var card = document.createElement("div"); card.className = "lpay-c";
    card.innerHTML = '<p class="lpay-c-name">' + esc(c.label) + '</p><p class="lpay-c-dt">' + esc(c.doctype) + '</p><div class="lpay-c-row"><span class="lpay-c-k">Phiếu nháp</span><span class="lpay-c-v ' + (hasDraft ? "lpay-has" : "lpay-zero") + '">' + c.draft + '</span></div><div class="lpay-c-row"><span class="lpay-c-k">Đã duyệt</span><span class="lpay-c-v lpay-zero">' + c.submitted + "</span></div>";
    var b = document.createElement("button"); b.className = "lpay-btn lpay-btn-warn lpay-btn-sm lpay-c-btn"; b.type = "button"; b.textContent = "Duyệt " + c.label.toLowerCase(); b.disabled = !hasDraft; b.addEventListener("click", function () { submitDrafts(key, b); });
    card.appendChild(b); box.appendChild(card);
  });
  refreshSubmitAll(anyDraft);
}
function submitDrafts(loai, btn) {
  if (!P) { log("Chưa chọn kỳ lương.", "err"); return; } if (!DATA.loaded) { log("Dữ liệu chưa nạp xong.", "info"); return; }
  var tenLoai = loai === "all" ? "tất cả phiếu nháp" : (loai === "congnhat" ? "phiếu công nhật" : "phiếu công khoán");
  if (!window.confirm("Duyệt " + tenLoai + " của tháng " + pad2(P.thang) + "/" + P.nam + "?\n\nThao tác này submit phiếu trên ERPNext và KHÔNG thể hoàn tác hàng loạt.")) return;
  var queue = [];
  if (loai === "congnhat" || loai === "all") inPeriod(DATA.nhat, PF.nhat, 0).forEach(function (r) { queue.push({ dt: PB.DT_NHAT, name: r.name }); });
  if (loai === "congkhoan" || loai === "all") inPeriod(DATA.khoan, PF.khoan, 0).forEach(function (r) { queue.push({ dt: PB.DT_KHOAN, name: r.name }); });
  var total = queue.length; if (!total) { log("Không có phiếu nháp để duyệt.", "info"); return; }
  setProg(btn, "Đang duyệt 0/" + total + "…");
  var submitted = 0, failed = 0, errs = []; var seq = Promise.resolve();
  queue.forEach(function (item, i) { seq = seq.then(function () { setProg(btn, "Đang duyệt " + (i + 1) + "/" + total + "…"); return call("frappe.client.get", { doctype: item.dt, name: item.name }).then(function (doc) { return call("frappe.client.submit", { doc: JSON.stringify(doc) }); }).then(function () { submitted++; }).catch(function (e) { failed++; errs.push({ name: item.name, error: shortErr(e) }); }); }); });
  seq.then(function () { log("Đã duyệt " + submitted + " phiếu" + (failed ? (", lỗi " + failed + ".") : "."), failed ? "err" : "ok"); errs.slice(0, 10).forEach(function (e) { log("• " + e.name + ": " + e.error, "err"); }); }).catch(function (e) { log("Duyệt thất bại: " + shortErr(e), "err"); }).then(function () { return loadData(true); }).then(function () { return scan(); });
}
function downloadWb(wb, filename) { return wb.xlsx.writeBuffer().then(function (buf) { var blob = new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }); var url = URL.createObjectURL(blob); var a = document.createElement("a"); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); setTimeout(function () { URL.revokeObjectURL(url); }, 2000); }); }
function exportFile(loai, btn) {
  P = readPeriod(); if (!P) { log("Chưa chọn kỳ lương.", "err"); return; } if (!DATA.loaded) { log("Dữ liệu chưa nạp xong.", "info"); return; }
  if (!window.ExcelJS) { log("Chưa tải được thư viện ExcelJS — kiểm tra mạng hoặc CSP.", "err"); return; }
  setBusy(btn, true, "Đang tạo…");
  try {
    var need = PB.NEED[loai];
    var nhat = need.indexOf("n") >= 0 ? normalize(inPeriod(DATA.nhat, PF.nhat, 1), PB.NHAT_KEYS) : [];
    var khoan = need.indexOf("k") >= 0 ? normalize(inPeriod(DATA.khoan, PF.khoan, 1), PB.KHOAN_KEYS) : [];
    var out = PB.buildFile(loai, nhat, khoan, P.thang, P.nam);
    var fn = PREFIX_FILE[loai] + "_T" + pad2(P.thang) + "_" + P.nam + ".xlsx";
    downloadWb(out.wb, fn).then(function () { log(LABEL[loai] + ": " + out.rows + " dòng → đang tải file.", "ok"); }).catch(function (e) { log(LABEL[loai] + " lỗi: " + shortErr(e), "err"); }).then(function () { setBusy(btn, false); });
  } catch (e) { log(LABEL[loai] + " lỗi: " + shortErr(e), "err"); setBusy(btn, false); }
}
var PRINT_CSS = '*{box-sizing:border-box;}body{font-family:"Times New Roman",serif;color:#000;margin:0;}section{padding:0;}section + section{page-break-before:always;}.co{text-align:center;font-weight:bold;font-size:11pt;margin-bottom:1px;}.ti{text-align:center;font-weight:bold;font-size:13pt;margin:1px 0 6px;}table{width:100%;border-collapse:collapse;table-layout:fixed;}th,td{border:0.5pt solid #000;padding:1.5px 3px;font-size:8.5pt;line-height:1.1;vertical-align:middle;word-wrap:break-word;overflow-wrap:break-word;}th{text-align:center;font-weight:bold;background:#eee;font-size:8pt;}td.c{text-align:center;}td.n{text-align:right;}td.b,.b{font-weight:bold;}tr.tall td{height:42px;}thead{display:table-header-group;}tr{page-break-inside:avoid;}@page{size:A4 landscape;margin:8mm;}';
function printHTML(inner) {
  var old = $("lpay-print-frame"); if (old) old.parentNode.removeChild(old);
  var ifr = document.createElement("iframe"); ifr.id = "lpay-print-frame"; ifr.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden;"; document.body.appendChild(ifr);
  var d = ifr.contentWindow.document; d.open(); d.write('<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><title>In lương</title><style>' + PRINT_CSS + "</style></head><body>" + inner + "</body></html>"); d.close();
  var w = ifr.contentWindow; function cleanup() { setTimeout(function () { if (ifr && ifr.parentNode) ifr.parentNode.removeChild(ifr); }, 800); }
  setTimeout(function () { try { w.focus(); w.print(); if (w.matchMedia) { var mql = w.matchMedia("print"); mql.addListener(function (m) { if (!m.matches) cleanup(); }); } } catch (e) { log("Không mở được hộp thoại in: " + shortErr(e), "err"); } setTimeout(function () { if ($("lpay-print-frame")) cleanup(); }, 60000); }, 400);
}
function exportPDF(group, btn) {
  P = readPeriod(); if (!P) { log("Chưa chọn kỳ lương.", "err"); return; } if (!DATA.loaded) { log("Dữ liệu chưa nạp xong.", "info"); return; }
  setBusy(btn, true, "Đang tạo…");
  try { var nhat = normalize(inPeriod(DATA.nhat, PF.nhat, 1), PB.NHAT_KEYS); var khoan = normalize(inPeriod(DATA.khoan, PF.khoan, 1), PB.KHOAN_KEYS); var html = PB.buildPrintHTML(group, nhat, khoan, P.thang, P.nam); printHTML(html); log((group === "bangluong" ? "In bảng lương" : "In phát lương") + " (tháng " + pad2(P.thang) + "/" + P.nam + "): đã mở hộp thoại in.", "ok"); }
  catch (e) { log("In PDF lỗi: " + shortErr(e), "err"); } finally { setBusy(btn, false); }
}

function boot(container) {
  logBox = $("lpay-log");
  $("lpay-scan").addEventListener("click", function () { scan(); });
  $("lpay-submit-all").addEventListener("click", function () { submitDrafts("all", $("lpay-submit-all")); });
  Array.prototype.forEach.call(container.querySelectorAll(".lpay-btn-export"), function (b) { b.addEventListener("click", function () { exportFile(b.dataset.loai, b); }); });
  Array.prototype.forEach.call(container.querySelectorAll(".lpay-btn-print"), function (b) { b.addEventListener("click", function () { exportPDF(b.dataset.group, b); }); });
  $("lpay-clear-log").addEventListener("click", function () { logBox.innerHTML = ""; });
  var rl = $("lpay-reload-period"); rl.addEventListener("click", function () { loadData(true); }); rl.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); loadData(true); } });
  var sf = $("lpay-show-fields"); sf.addEventListener("click", function () { showFields(); }); sf.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); showFields(); } });
  loadExcelJS().catch(function () { log("Thư viện ExcelJS chưa tải — nút xuất Excel sẽ báo lỗi tới khi tải được.", "info"); });
  loadData(false);
}

export async function render({ container }) {
  if (!document.getElementById("lpay-style")) { var st = document.createElement("style"); st.id = "lpay-style"; st.textContent = CSS; document.head.appendChild(st); }
  container.innerHTML = HTML;
  boot(container);
}
