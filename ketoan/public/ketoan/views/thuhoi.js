// views/thuhoi.js — THEO DÕI THU HỒI (#/thu-hoi) + một lô (#/thu-hoi/:id).
//
// Lô thu hồi được TẠO bên app vận chuyển (siêu thị gọi trả → xe lấy → nhận về kho).
// Kế toán tiếp nối từ "Đã nhận hàng": kiểm hàng (#/kiem-hang/:id, màn điện thoại) →
// chốt → lập hóa đơn trả về NHÁP từ hóa đơn gốc → ghi sổ trên Desk. Màn này KHÔNG
// sửa gì của bên vận chuyển; hồ sơ lô hiện ở đây là bản đọc sống.
import { api } from "../lib/api.js";
import { html, raw, setHTML } from "../lib/dom.js";
import { formatDate, formatNumber, formatVND } from "../lib/format.js";
import { replaceQuery } from "../lib/router.js";
import { toast } from "../components/toast.js";
import { openModal } from "../components/modal.js";

// Fallback khi backend cũ chưa trả `chang_list` — nguồn thật là thu_hoi.CHANG.
const CHANG_FB = ["Tạo yêu cầu", "Đã lấy hàng", "Đã nhận hàng", "Đang kiểm", "Đã kiểm hàng", "Đã nhập chứng từ", "Xong"];
const VC = 3; // ba chặng đầu thuộc bên vận chuyển

const fmtSl = (n) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 3 }).format(Number(n) || 0);

// Thẻ file: ảnh / PDF mở tab (proxy trả inline); Excel / Word / mail… proxy trả TẢI VỀ.
const XEM_TRONG_TAB = new Set(["jpg", "jpeg", "png", "webp", "gif", "pdf"]);
const ICON_FILE = {
  pdf: "fa-file-pdf", xls: "fa-file-excel", xlsx: "fa-file-excel", xlsm: "fa-file-excel", ods: "fa-file-excel",
  csv: "fa-file-csv", doc: "fa-file-word", docx: "fa-file-word", odt: "fa-file-word", rtf: "fa-file-word",
  txt: "fa-file-lines", eml: "fa-envelope", msg: "fa-envelope", zip: "fa-file-zipper", rar: "fa-file-zipper", "7z": "fa-file-zipper",
};

// "2026-10-17 09:12:33" → "17/10 09:12" (không qua new Date: Safari không đọc chuỗi có dấu cách).
function fmtLuc(s) {
  const m = String(s || "").match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  return m ? `${m[3]}/${m[2]} ${m[4]}:${m[5]}` : String(s || "");
}

export function changTone(chang, list = CHANG_FB) {
  const i = list.indexOf(chang);
  if (chang === "Xong") return "green";
  if (chang === "Đã nhận hàng" || chang === "Đã kiểm hàng") return "yellow"; // việc đang chờ KẾ TOÁN
  if (i >= 0 && i < VC) return "gray";
  return "gray";
}

function badge(chang, list) {
  return html`<span class="kt-badge kt-badge--${changTone(chang, list)}">${chang || ""}</span>`;
}

// Thanh 7 nấc — cùng hình với bên vận chuyển để hai bên nhìn một thứ.
function steps(chang, list = CHANG_FB) {
  const i = list.indexOf(chang);
  return html`<div class="kt-th-steps" title="${chang || ""}">${list.map((c, k) => raw(
    `<span class="kt-th-step ${k < VC ? "kt-th-step--vc" : "kt-th-step--kt"}${k <= i ? " is-on" : ""}${k === i ? " is-cur" : ""}"></span>`))}</div>`;
}

export async function render({ container, params, query }) {
  if (params && params.id) return renderLo(container, params.id);
  return renderList(container, query || {});
}

// ═══════════════════════════════════════════════════════════════════════════
// DANH SÁCH
// ═══════════════════════════════════════════════════════════════════════════
async function renderList(container, query) {
  const S = { chang: query.chang || "dang_mo", tim: query.tim || "", page: 1, data: null };
  setHTML(container, html`
    <div class="kt-view-head">
      <div class="kt-view-title"><i class="fas fa-rotate-left"></i> Theo dõi thu hồi</div>
      <div class="kt-sub">Mọi lô siêu thị xuất trả tạo bên vận chuyển. Kế toán tiếp nối khi hàng đã về kho: kiểm hàng → hóa đơn trả về.</div>
    </div>
    <div class="kt-th-toolbar">
      <div class="kt-search kt-th-search"><i class="fas fa-magnifying-glass"></i>
        <input class="kt-input" id="th-tim" type="search" autocomplete="off" placeholder="Tìm lô / khách / điểm / số phiếu / mã vận đơn" value="${S.tim}"></div>
    </div>
    <div class="kt-th-pills" id="th-pills"></div>
    <div id="th-body"><div class="kt-boot"><div class="kt-spinner"></div></div></div>`);

  let t = null;
  container.querySelector("#th-tim").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => { S.tim = e.target.value.trim(); S.page = 1; load(); }, 300);
  });

  async function load() {
    const body = container.querySelector("#th-body");
    try {
      const d = await api.thList({ chang: S.chang, tim: S.tim || undefined, page: S.page, page_size: 30 });
      if (S.page > 1 && S.data) d.rows = S.data.rows.concat(d.rows || []);
      S.data = d;
    } catch (e) {
      setHTML(body, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p></div>`);
      return;
    }
    replaceQuery("/thu-hoi", Object.fromEntries(Object.entries({ chang: S.chang !== "dang_mo" ? S.chang : "", tim: S.tim }).filter(([, v]) => v)));
    drawPills();
    drawRows();
  }

  function drawPills() {
    const c = S.data.counts || {};
    const ds = S.data.chang_list || CHANG_FB;
    const tong = ds.reduce((a, k) => a + (c[k] || 0), 0);
    const pill = (key, label, n, tone = "") => html`<button type="button" class="kt-th-pill${tone ? " kt-th-pill--" + tone : ""}${S.chang === key ? " is-on" : ""}" data-f="${key}">${label} <b>${n}</b></button>`;
    setHTML(container.querySelector("#th-pills"), html`
      ${pill("dang_mo", "Đang mở", tong - (c["Xong"] || 0))}
      ${ds.map((k, i) => pill(k, k, c[k] || 0, i < VC ? "vc" : (k === "Đã nhận hàng" || k === "Đã kiểm hàng") ? "viec" : ""))}
      ${pill("tat_ca", "Tất cả", tong)}`);
    container.querySelectorAll("#th-pills [data-f]").forEach((b) => b.addEventListener("click", () => {
      S.chang = b.dataset.f; S.page = 1; load();
    }));
  }

  function drawRows() {
    const body = container.querySelector("#th-body");
    const d = S.data;
    if (!d.vanchuyen) {
      setHTML(body, html`<div class="kt-alert kt-alert--info">${d.note || "Site chưa cài app vận chuyển."}</div>`);
      return;
    }
    const rows = d.rows || [];
    if (!rows.length) {
      setHTML(body, html`<div class="kt-empty"><i class="fas fa-inbox"></i><p>Không có lô nào${S.chang === "dang_mo" ? " đang mở" : ""}.</p></div>`);
      return;
    }
    const ds = d.chang_list || CHANG_FB;
    const hd = (r) => r.so_hd ? html`${r.so_hd_ghi_so}/${r.so_hd} ghi sổ<div class="kt-sub">${formatVND(r.tien_hd)}</div>` : html`<span class="kt-sub">—</span>`;
    const kiem = (r) => r.kiem_so_ma ? html`${fmtSl(r.kiem_sl)} <span class="kt-sub">/ ${r.kiem_so_ma} mã</span>` : html`<span class="kt-sub">${r.chang === "Đã nhận hàng" ? "chờ kiểm" : "—"}</span>`;
    setHTML(body, html`
      <div class="kt-table-wrap kt-th-desk"><table class="kt-table">
        <thead><tr><th>Lô</th><th>Yêu cầu</th><th>Khách · điểm</th><th>Vận chuyển</th><th class="num">Đã kiểm</th><th>HĐ trả về</th><th>Chặng</th></tr></thead>
        <tbody>${rows.map((r) => html`<tr class="kt-row-link" data-lo="${r.name}">
          <td><b>${r.name}</b>${r.so_phieu_sieu_thi ? html`<div class="kt-sub">phiếu ${r.so_phieu_sieu_thi}</div>` : ""}</td>
          <td>${formatDate(r.ngay_yeu_cau)}${r.tuoi > 0 ? html`<div class="kt-sub ${r.tuoi > 14 ? "kt-th-tre" : ""}">${r.tuoi} ngày</div>` : ""}</td>
          <td>${r.ten_diem || r.customer_name}<div class="kt-sub">${r.customer_name}${r.ma_diem ? " · " + r.ma_diem : ""}</div></td>
          <td>${r.don_vi_thu_hoi || html`<span class="kt-sub">chưa có đơn vị thu hồi</span>`}${r.ma_van_don ? html`<div class="kt-sub">VĐ ${r.ma_van_don}</div>` : ""}<div class="kt-sub">${r.nhan_luc ? "về kho " + fmtLuc(r.nhan_luc) : r.lay_luc ? "lấy " + fmtLuc(r.lay_luc) : r.ngay_hen_lay ? "thu " + formatDate(r.ngay_hen_lay) : ""}</div></td>
          <td class="num">${kiem(r)}</td>
          <td>${hd(r)}</td>
          <td>${badge(r.chang, ds)}${steps(r.chang, ds)}</td>
        </tr>`)}</tbody>
      </table></div>
      <div class="kt-th-cards kt-th-mob">${rows.map((r) => html`<a class="kt-th-card" href="#/thu-hoi/${encodeURIComponent(r.name)}">
        <div class="kt-th-card-head"><b>${r.ten_diem || r.customer_name}</b>${badge(r.chang, ds)}</div>
        <div class="kt-sub">${r.customer_name} · ${r.name}${r.so_phieu_sieu_thi ? " · phiếu " + r.so_phieu_sieu_thi : ""}</div>
        ${steps(r.chang, ds)}
        <div class="kt-th-card-meta">📅 ${formatDate(r.ngay_yeu_cau)}${r.tuoi > 0 ? ` · ${r.tuoi} ngày` : ""}${r.kiem_so_ma ? ` · đã kiểm ${fmtSl(r.kiem_sl)}` : ""}${r.so_hd ? ` · ${r.so_hd} HĐ trả về` : ""}</div>
        ${r.don_vi_thu_hoi || r.ma_van_don ? html`<div class="kt-th-card-meta">🚚 ${[r.don_vi_thu_hoi, r.ma_van_don ? "VĐ " + r.ma_van_don : ""].filter(Boolean).join(" · ")}</div>` : ""}
      </a>`)}</div>
      ${d.has_more ? html`<button type="button" class="kt-btn kt-btn--outline kt-th-more" id="th-more">Xem tiếp (đã hiện ${rows.length}/${d.total})</button>` : ""}`);
    body.querySelectorAll("tr[data-lo]").forEach((tr) => tr.addEventListener("click", () => {
      location.hash = "#/thu-hoi/" + encodeURIComponent(tr.dataset.lo);
    }));
    const more = body.querySelector("#th-more");
    if (more) more.addEventListener("click", () => { S.page += 1; load(); });
  }

  await load();
}

// ═══════════════════════════════════════════════════════════════════════════
// MỘT LÔ
// ═══════════════════════════════════════════════════════════════════════════
async function renderLo(container, name) {
  let D = null;

  async function reload(d) {
    if (d) D = d;
    else {
      try { D = await api.thGet(name); } catch (e) {
        setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i><p>${e.message}</p><p><a href="#/thu-hoi">← Theo dõi thu hồi</a></p></div>`);
        return;
      }
    }
    draw();
  }

  function draw() {
    const lo = D.lo;
    const ds = D.chang_list || CHANG_FB;
    const ph = D.phieu;
    const f = D.flags || {};
    const moc = (nhan, luc, ai) => luc ? html`<div><span class="kt-sub">${nhan}</span> ${fmtLuc(luc)}${ai ? " · " + ai : ""}</div>` : "";
    setHTML(container, html`
      <div class="kt-th-back"><a href="#/thu-hoi"><i class="fas fa-arrow-left"></i> Theo dõi thu hồi</a></div>
      <div class="kt-view-head">
        <div class="kt-view-title"><i class="fas fa-rotate-left"></i> ${lo.name} · ${lo.ten_diem || lo.customer_name} ${badge(D.chang, ds)}</div>
        <div class="kt-sub">${lo.customer_name}${lo.ma_diem ? " · " + lo.ma_diem : ""}${lo.so_phieu_sieu_thi ? " · phiếu xuất trả " + lo.so_phieu_sieu_thi : ""}</div>
        ${steps(D.chang, ds)}
      </div>

      <div class="kt-th-grid">
        <div class="kt-card">
          <div class="kt-card-head"><b><i class="fas fa-truck"></i> Hồ sơ lô (vận chuyển)</b><span class="kt-sub">bản đọc sống — sửa bên app vận chuyển</span></div>
          <div class="kt-th-pad">
            <div class="kt-th-kv">
              <div><span class="kt-sub">Điểm lấy hàng</span> ${lo.ten_diem}${lo.ma_diem ? " · " + lo.ma_diem : ""}</div>
              <div><span class="kt-sub">Địa chỉ</span> ${lo.dia_chi || "—"}${lo.sdt_diem ? " · ☎ " + lo.sdt_diem : ""}</div>
              <div><span class="kt-sub">Ngày yêu cầu</span> ${formatDate(lo.ngay_yeu_cau)}${lo.ly_do ? " · " + lo.ly_do : ""}</div>
              ${lo.nguoi_lien_he || lo.sdt_lien_he ? html`<div><span class="kt-sub">Liên hệ</span> ${lo.nguoi_lien_he || ""} ${lo.sdt_lien_he || ""}</div>` : ""}
              <div><span class="kt-sub">Thu hồi</span> ${lo.don_vi_thu_hoi || "chưa chọn đơn vị"}${lo.ma_van_don ? " · VĐ " + lo.ma_van_don : ""}${lo.ngay_hen_lay ? " · thu " + formatDate(lo.ngay_hen_lay) : ""}</div>
              ${moc("Lấy hàng", lo.lay_luc, lo.lay_boi)}
              ${moc("Nhận về kho", lo.nhan_luc, lo.nhan_boi)}
              ${lo.so_kien_du_kien || lo.so_kien_nhan ? html`<div><span class="kt-sub">Kiện</span> theo vận đơn ${lo.so_kien_du_kien ? fmtSl(lo.so_kien_du_kien) : "—"} · thực nhận ${lo.so_kien_nhan ? fmtSl(lo.so_kien_nhan) : "—"}</div>` : ""}
              ${lo.gia_tri_khai ? html`<div><span class="kt-sub">Giá trị theo phiếu siêu thị</span> ${formatVND(lo.gia_tri_khai)}</div>` : ""}
              ${lo.ghi_chu ? html`<div><span class="kt-sub">Ghi chú</span> ${lo.ghi_chu}</div>` : ""}
            </div>
            ${lo.chi_tiet_hang ? mailBlock(lo.chi_tiet_hang) : ""}
            <div class="kt-th-files">${(D.files || []).length ? D.files.map((x) => html`<a class="kt-th-file" href="${x.url}" ${
              XEM_TRONG_TAB.has(x.ext) ? html`target="_blank" rel="noopener"` : html`download="${x.file_name}"`}>
              ${x.is_image ? html`<img src="${x.url}" alt="" loading="lazy">` : html`<span class="kt-th-file-ico"><i class="fas ${ICON_FILE[x.ext] || "fa-file"}"></i></span>`}<span>${x.file_name}</span></a>`) : html`<div class="kt-sub">Chưa có chứng từ đính kèm.</div>`}</div>
          </div>
        </div>

        <div class="kt-card">
          <div class="kt-card-head"><b><i class="fas fa-barcode"></i> Kiểm hàng</b>${ph ? html`<span class="kt-sub">${ph.da_chot ? `đã chốt ${fmtLuc(ph.chot_luc)} · ${ph.chot_boi || ""}` : "đang kiểm"}</span>` : ""}</div>
          <div class="kt-th-pad">${kiemBlock(lo, ph, f)}</div>
        </div>
      </div>

      ${ph && ph.da_chot ? html`<div class="kt-card kt-th-mt">
        <div class="kt-card-head"><b><i class="fas fa-scale-balanced"></i> ${D.co_khai ? "Siêu thị khai · đã kiểm · đã lập hóa đơn" : "Đã kiểm · đã lập hóa đơn"}</b><span class="kt-sub">ĐVT kho</span></div>
        ${soSanh()}
      </div>` : ""}
      ${ph && !ph.da_chot && D.co_khai ? html`<div class="kt-sub kt-th-mt">Số siêu thị khai hiện SAU khi chốt phiếu: đếm mù rồi mới so — thấy số khai trước là dễ gõ lại số khai cho nhanh, và lệch thật không bao giờ lộ.</div>` : ""}

      ${ph && ph.da_chot ? html`<div class="kt-card kt-th-mt">
        <div class="kt-card-head"><b><i class="fas fa-file-invoice"></i> Hóa đơn trả về</b>
          <span>${f.cap_nhat ? html`<button type="button" class="kt-btn kt-btn--outline kt-btn--sm" id="th-capnhat"><i class="fas fa-rotate"></i> Cập nhật hóa đơn trả về theo số mới</button>` : ""}</span></div>
        <div class="kt-th-pad">${hoaDonBlock(ph, f)}</div>
      </div>` : ""}`);
    bind();
  }

  function kiemBlock(lo, ph, f) {
    if (!ph) {
      if (f.bat_dau) {
        return html`<p>Hàng đã về kho. Mở phiếu kiểm rồi đếm trên điện thoại: quét mã vạch hoặc tìm mã, nhập số thùng / hộp.</p>
          <button type="button" class="kt-btn kt-btn--primary kt-th-big" id="th-batdau"><i class="fas fa-barcode"></i> Bắt đầu kiểm hàng</button>`;
      }
      return html`<div class="kt-alert kt-alert--info">Lô đang ở <b>${lo.trang_thai}</b> bên vận chuyển. Kế toán tiếp nối khi hàng đã về kho — điều phối bấm "Đã nhận hàng" trên app vận chuyển.</div>`;
    }
    return html`
      <div class="kt-th-sum"><div><div class="kt-sub">Đã kiểm</div><div class="kt-th-sum-so">${fmtSl(ph.tong_sl)}</div><div class="kt-sub">${ph.so_ma || 0} mã · ĐVT kho</div></div>
        ${ph.da_chot && D.co_khai ? html`<div><div class="kt-sub">Siêu thị khai</div><div class="kt-th-sum-so kt-th-sum-so--nhat">${fmtSl(D.tong_khai)}</div></div>` : ""}</div>
      ${ph.khong_lap_hd ? html`<div class="kt-alert kt-alert--warning">KTT kết luận <b>không lập hóa đơn trả về</b>: ${ph.ly_do_khong_lap} — ${ph.ket_luan_boi || ""}</div>` : ""}
      <div class="kt-th-actions">
        <a class="kt-btn kt-btn--primary" href="#/kiem-hang/${encodeURIComponent(ph.name)}"><i class="fas fa-mobile-screen"></i> ${ph.da_chot ? "Xem phiếu kiểm" : "Mở màn kiểm hàng"}</a>
        ${f.chot ? html`<button type="button" class="kt-btn kt-btn--success" id="th-chot"><i class="fas fa-lock"></i> Chốt phiếu</button>` : ""}
        ${f.mo_lai ? html`<button type="button" class="kt-btn kt-btn--outline" id="th-molai"><i class="fas fa-lock-open"></i> Mở lại để sửa</button>` : ""}
        ${f.ket_luan ? html`<button type="button" class="kt-btn kt-btn--outline" id="th-ketluan"><i class="fas fa-user-tie"></i> Không lập hóa đơn trả về…</button>` : ""}
        ${f.xoa ? html`<button type="button" class="kt-btn kt-btn--outline" id="th-xoa"><i class="fas fa-trash"></i> Xóa phiếu kiểm</button>` : ""}
      </div>
      <div class="kt-field kt-th-mt"><label class="kt-label">Ghi chú kiểm hàng</label>
        <textarea class="kt-textarea" id="th-ghichu" rows="2" placeholder="Hàng móp, thiếu tem, lệch số kiện...">${ph.ghi_chu || ""}</textarea></div>`;
  }

  // Mail siêu thị dán nguyên văn bên vận chuyển: giữ tab / xuống dòng (<pre>); dài thì gọn lại.
  function mailBlock(text) {
    const dai = (text.match(/\n/g) || []).length > 10 || text.length > 900;
    return html`<div class="kt-th-mail"><div class="kt-sub">Chi tiết hàng siêu thị gửi (dán từ mail)</div>
      <pre class="kt-th-paste${dai ? " is-gon" : ""}" id="th-mail">${text}</pre>
      ${dai ? html`<button type="button" class="kt-btn kt-btn--outline kt-btn--sm" id="th-mail-mo">Xem hết</button>` : ""}</div>`;
  }

  function soSanh() {
    const rows = D.so_sanh || [];
    if (!rows.length) return html`<div class="kt-th-pad kt-sub">Chưa có mã nào — chưa kiểm dòng nào.</div>`;
    if (!D.co_khai) {
      // Lô mới: bên vận chuyển không gõ mã hàng (mail dán nguyên văn ở hồ sơ) — không có cột khai.
      return html`<div class="kt-table-wrap kt-th-flush"><table class="kt-table">
        <thead><tr><th>Mã hàng</th><th class="num">Đã kiểm</th><th class="num">Đã lập HĐ trả</th></tr></thead>
        <tbody>${rows.map((r) => html`<tr><td>${r.item_name}<div class="kt-sub">${r.item_code}${r.stock_uom ? " · " + r.stock_uom : ""}</div></td>
          <td class="num">${fmtSl(r.kiem)}</td><td class="num">${lapCell(r)}</td></tr>`)}</tbody>
      </table></div>`;
    }
    const lech = (r) => {
      const d = (Number(r.kiem) || 0) - (Number(r.khai) || 0);
      if (!r.khai || Math.abs(d) < 1e-6) return html`<span class="kt-sub">—</span>`;
      return html`<span class="${d < 0 ? "danger" : "pos"}">${d > 0 ? "+" : ""}${fmtSl(d)}</span>`;
    };
    return html`<div class="kt-table-wrap kt-th-flush"><table class="kt-table">
      <thead><tr><th>Mã hàng</th><th class="num">Siêu thị khai</th><th class="num">Đã kiểm</th><th class="num">Lệch kiểm − khai</th><th class="num">Đã lập HĐ trả</th></tr></thead>
      <tbody>${rows.map((r) => html`<tr><td>${r.item_name}<div class="kt-sub">${r.item_code}${r.stock_uom ? " · " + r.stock_uom : ""}</div></td>
        <td class="num">${r.khai ? fmtSl(r.khai) : "—"}</td><td class="num">${fmtSl(r.kiem)}</td><td class="num">${lech(r)}</td><td class="num">${lapCell(r)}</td></tr>`)}</tbody>
    </table></div>`;
  }

  // Đã lập lệch số đã kiểm thì tô đỏ — phiếu trả thừa / thiếu so với hàng thật về.
  function lapCell(r) {
    const d = (Number(r.da_lap) || 0) - (Number(r.kiem) || 0);
    return Math.abs(d) < 1e-6 ? fmtSl(r.da_lap) : html`<span class="danger">${fmtSl(r.da_lap)}</span>`;
  }

  function hoaDonBlock(ph, f) {
    const hd = D.hoa_don || [];
    const lech = D.lech || {};
    const thieuThua = Object.entries(lech);
    const con = Object.entries(D.con_can || {});
    return html`
      ${hd.length ? html`<div class="kt-th-hd-list">${hd.map((h) => html`<div class="kt-th-hd">
        <div class="kt-th-hd-head">
          <a href="${h.route}" target="_blank" rel="noopener"><b>${h.name}</b></a>
          <span class="kt-badge kt-badge--${h.docstatus === 1 ? "green" : "yellow"}">${h.docstatus === 1 ? "Đã ghi sổ" : "Nháp"}</span>
          <span class="kt-sub">trả cho ${h.return_against} · ${formatDate(h.posting_date)}</span>
          <b class="kt-th-hd-tien">${formatVND(h.tien)}</b>
        </div>
        <div class="kt-sub">${h.items.map((i) => `${i.item_name || i.item_code}: ${fmtSl(i.qty)} ${i.uom || ""}${i.noi ? "" : " (không nối dòng gốc)"}`).join(" · ")}</div>
        ${h.misa_no ? html`<div class="kt-sub">Số HĐĐT: ${h.misa_no}</div>` : ""}
        <div class="kt-th-actions">
          <a class="kt-btn kt-btn--outline kt-btn--sm" href="${h.route}" target="_blank" rel="noopener"><i class="fas fa-up-right-from-square"></i> ${h.docstatus === 1 ? "Mở trên Desk" : "Soát & ghi sổ trên Desk"}</a>
          ${h.docstatus === 0 ? html`<button type="button" class="kt-btn kt-btn--outline kt-btn--sm" data-xoahd="${h.name}"><i class="fas fa-trash"></i> Xóa bản nháp</button>` : ""}
        </div>
      </div>`)}</div>` : html`<div class="kt-sub">Chưa có hóa đơn trả về nào.</div>`}
      ${thieuThua.length && hd.length ? html`<div class="kt-alert kt-alert--warning kt-th-mt">Hóa đơn trả về chưa khớp số đã kiểm:
        ${thieuThua.map(([it, d]) => `${it} ${d > 0 ? "thừa" : "thiếu"} ${fmtSl(Math.abs(d))}`).join(" · ")}.
        ${f.cap_nhat ? "Bấm “Cập nhật hóa đơn trả về” để chia lại các bản nháp." : ""}</div>` : ""}
      ${hd.some((h) => h.items.some((i) => !i.noi)) ? html`<div class="kt-sub kt-th-mt">Dòng "không nối dòng gốc": phần lẻ hộp không biểu diễn đúng được theo ĐVT của dòng gốc (thùng). Trên Desk, ERPNext sẽ cảnh báo "Returned Item … does not exist" — đó là cảnh báo, không chặn; app đã tự giữ trần trả.</div>` : ""}
      ${f.lap_hd ? html`<div class="kt-th-can kt-th-mt">
        <div><b>Còn cần lập hóa đơn trả về:</b> ${con.map(([it, q]) => `${it}: ${fmtSl(q)}`).join(" · ")}</div>
        <button type="button" class="kt-btn kt-btn--primary" id="th-ungvien"><i class="fas fa-magnifying-glass"></i> Chọn hóa đơn gốc để lập hóa đơn trả về</button>
        <div id="th-uv"></div>
      </div>` : ""}
      ${!f.lap_hd && !thieuThua.length && hd.length ? html`<div class="kt-sub kt-th-mt">${hd.every((h) => h.docstatus === 1) ? "Đủ hóa đơn trả về, đã ghi sổ hết — lô xong." : "Đủ hóa đơn trả về. Mở từng bản nháp trên Desk để soát rồi ghi sổ."}</div>` : ""}`;
  }

  async function act(btn, fn, ok) {
    if (btn) btn.disabled = true;
    try {
      const r = await fn();
      if (ok) toast(ok, "success");
      await reload(r && r.lo ? r : (r && r.thu_hoi) || null);
    } catch (e) {
      if (btn) btn.disabled = false;
      toast(e.message, "error");
    }
  }

  function bind() {
    const $ = (id) => container.querySelector(id);
    if ($("#th-mail-mo")) $("#th-mail-mo").addEventListener("click", (e) => {
      const gon = $("#th-mail").classList.toggle("is-gon");
      e.currentTarget.textContent = gon ? "Xem hết" : "Thu gọn";
    });
    if ($("#th-batdau")) $("#th-batdau").addEventListener("click", async (e) => {
      e.currentTarget.disabled = true;
      try { await api.thBatDau(name); location.hash = "#/kiem-hang/" + encodeURIComponent(name); } catch (err) {
        e.currentTarget.disabled = false; toast(err.message, "error");
      }
    });
    if ($("#th-chot")) $("#th-chot").addEventListener("click", (e) => act(e.currentTarget, () => api.thChot(name), "Đã chốt phiếu kiểm"));
    if ($("#th-molai")) $("#th-molai").addEventListener("click", (e) => {
      if (!confirm("Mở lại phiếu đã chốt để sửa số? Hóa đơn trả về NHÁP (nếu có) sẽ phải cập nhật lại sau khi chốt lại.")) return;
      act(e.currentTarget, () => api.thMoLai(name), "Đã mở lại phiếu");
    });
    if ($("#th-xoa")) $("#th-xoa").addEventListener("click", (e) => {
      if (!confirm("Xóa phiếu kiểm này? Số đã đếm mất hẳn.")) return;
      act(e.currentTarget, async () => { await api.thXoaPhieu(name); return null; }, "Đã xóa phiếu kiểm");
    });
    if ($("#th-ketluan")) $("#th-ketluan").addEventListener("click", () => ketLuan());
    if ($("#th-capnhat")) $("#th-capnhat").addEventListener("click", (e) => act(e.currentTarget, () => api.thCapNhatHd(name), "Đã cập nhật hóa đơn trả về nháp"));
    if ($("#th-ungvien")) $("#th-ungvien").addEventListener("click", (e) => { UV.d = null; ungVien(e.currentTarget); });
    container.querySelectorAll("[data-xoahd]").forEach((b) => b.addEventListener("click", () => {
      if (!confirm(`Xóa hóa đơn trả về NHÁP ${b.dataset.xoahd}?`)) return;
      act(b, () => api.thXoaHd(name, b.dataset.xoahd), "Đã xóa bản nháp");
    }));
    const gc = $("#th-ghichu");
    if (gc) gc.addEventListener("change", async () => {
      try { await api.thGhiChu(name, gc.value); toast("Đã lưu ghi chú", "success"); } catch (e) { toast(e.message, "error"); }
    });
  }

  // Ứng viên hóa đơn gốc: MỌI hóa đơn đã ghi sổ của đúng khách + đúng điểm giao (50 tờ một
  // trang), mới nhất trước. Tờ không nhận được gì vẫn hiện — chỉ khóa nút lập, kèm lý do.
  const UV = { tim: "", moi_diem: false, page: 1, rows: [], d: null, luot: 0 };
  let uvGo = null;

  async function ungVien(btn, { tiep = false } = {}) {
    const box = container.querySelector("#th-uv");
    if (!box) return; // khung đã đóng (vừa lập xong hóa đơn) mà lượt tìm chờ gõ mới tới
    if (!tiep) { UV.page = 1; UV.rows = []; }
    const luot = ++UV.luot;
    if (btn) btn.disabled = true;
    if (!UV.d) setHTML(box, html`<div class="kt-boot"><div class="kt-spinner"></div></div>`);
    let d;
    try {
      d = await api.thUngVien(name, { tim: UV.tim || undefined, moi_diem: UV.moi_diem ? 1 : 0, page: UV.page });
    } catch (e) {
      if (btn) btn.disabled = false;
      if (luot === UV.luot) setHTML(box, html`<div class="kt-alert kt-alert--danger">${e.message}</div>`);
      return;
    }
    if (btn) btn.disabled = false;
    if (luot !== UV.luot || !box.isConnected) return; // gõ tìm nhanh: kết quả cũ về muộn không đè kết quả mới
    UV.d = d;
    UV.rows = UV.rows.concat(d.rows || []);
    veUngVien(box);
  }

  function veUngVien(box) {
    const d = UV.d;
    const rows = UV.rows;
    const khach = d.khach || {};
    const diem = d.diem || {};
    const dangGo = document.activeElement && document.activeElement.id === "uv-tim";
    // Cùng một dòng, hai cách đọc: bảng trên máy tính, thẻ trên điện thoại (như danh sách lô).
    const noiDiem = (r) => html`${r.ten_diem || r.address_title || r.shipping_address_name || "—"}${
      UV.moi_diem && r.cung_diem ? html` <span class="kt-badge kt-badge--green">điểm của lô</span>` : ""}`;
    const diaChi = (r) => [r.address_line1, r.city].filter(Boolean).join(", ");
    const nhan = (r) => r.lap_duoc ? html`${Object.entries(r.nhan).map(([it, q]) => `${it}: ${fmtSl(q)}`).join(" · ")}<div class="kt-sub">≈ ${formatVND(r.uoc_tien)}${
      r.dong_khong_noi ? ` · ${r.dong_khong_noi} dòng lẻ không nối dòng gốc` : ""}</div>` : html`<span class="kt-sub">${r.ly_do_khoa}</span>`;
    const nut = (r) => html`<button type="button" class="kt-btn kt-btn--success kt-btn--sm" data-tao="${r.name}" ${r.lap_duoc ? "" : "disabled"} title="${r.ly_do_khoa || ""}">Lập HĐ trả về</button>`;
    setHTML(box, html`<div class="kt-th-uv kt-th-mt">
      <div class="kt-th-uv-head">
        <div>Hóa đơn bán đã ghi sổ của <b>${khach.customer_name || khach.customer}</b> <span class="kt-sub">${khach.customer}</span>${
          UV.moi_diem ? html` — <b>mọi điểm giao</b>` : html` giao <b>${diem.ten || diem.name}</b> <span class="kt-sub">${diem.name}</span>`}
          · <b>${d.total}</b> hóa đơn</div>
        <div class="kt-th-uv-tools">
          <input class="kt-input" id="uv-tim" type="search" autocomplete="off" placeholder="Tìm số hóa đơn / PO / số HĐĐT" value="${UV.tim}">
          <button type="button" class="kt-btn kt-btn--outline kt-btn--sm" id="uv-diem">${UV.moi_diem ? "Chỉ điểm giao của lô" : "Xem mọi điểm của khách"}</button>
        </div>
      </div>
      ${rows.length ? html`<div class="kt-table-wrap kt-th-desk"><table class="kt-table">
        <thead><tr><th>Hóa đơn gốc</th><th>Ngày · PO</th><th>Khách · điểm giao</th><th class="num">Số tiền</th><th>Nhận được (ĐVT kho)</th><th></th></tr></thead>
        <tbody>${rows.map((r) => html`<tr class="${r.lap_duoc ? "" : "kt-th-uv-khoa"}">
          <td><b>${r.name}</b>${r.so_hddt ? html`<div class="kt-sub">HĐĐT ${r.so_hddt}</div>` : ""}</td>
          <td>${formatDate(r.posting_date)}${r.po ? html`<div class="kt-sub">PO ${r.po}</div>` : ""}</td>
          <td>${r.customer_name || r.customer}<div class="kt-sub">${noiDiem(r)}</div>${diaChi(r) ? html`<div class="kt-sub">${diaChi(r)}</div>` : ""}</td>
          <td class="num">${formatVND(r.grand_total)}<div class="kt-sub">còn nợ ${formatVND(r.outstanding_amount)}</div>${
            r.da_tra ? html`<div class="kt-sub">đã trả về ${formatVND(r.da_tra)}</div>` : ""}</td>
          <td>${nhan(r)}</td>
          <td class="kt-cell-act">${nut(r)}</td>
        </tr>`)}</tbody></table></div>
        <div class="kt-th-cards kt-th-mob">${rows.map((r) => html`<div class="kt-th-card kt-th-uv-card${r.lap_duoc ? "" : " kt-th-uv-khoa"}">
          <div class="kt-th-card-head"><span><b>${r.name}</b>${r.so_hddt ? html` <span class="kt-sub">HĐĐT ${r.so_hddt}</span>` : ""}</span><b class="kt-th-uv-tien">${formatVND(r.grand_total)}</b></div>
          <div class="kt-sub">${formatDate(r.posting_date)}${r.po ? ` · PO ${r.po}` : ""} · còn nợ ${formatVND(r.outstanding_amount)}${
            r.da_tra ? ` · đã trả về ${formatVND(r.da_tra)}` : ""}</div>
          <div class="kt-th-card-meta">${r.customer_name || r.customer} · ${noiDiem(r)}${diaChi(r) ? html`<div>${diaChi(r)}</div>` : ""}</div>
          <div class="kt-th-uv-nhan">${nhan(r)}</div>
          ${nut(r)}
        </div>`)}</div>
        ${d.has_more ? html`<button type="button" class="kt-btn kt-btn--outline kt-th-more" id="uv-tiep">Xem tiếp (đã hiện ${rows.length}/${d.total})</button>` : ""}
        <div class="kt-sub">"Nhận được" = phần tờ đó còn trả được trong số đang cần trả. Nút khóa là tờ đó không còn gì để trả.</div>`
      : html`<div class="kt-alert kt-alert--warning">${UV.tim ? `Không có hóa đơn nào khớp "${UV.tim}".` : UV.moi_diem
          ? "Khách này chưa có hóa đơn bán nào đã ghi sổ." : "Chưa có hóa đơn bán nào đã ghi sổ giao điểm này."}${
          UV.moi_diem ? "" : " Thử “Xem mọi điểm của khách”."} Hàng không thuộc hóa đơn nào thì nhờ KTT kết luận "không lập hóa đơn trả về".</div>`}
    </div>`);
    const tim = box.querySelector("#uv-tim");
    if (dangGo) { tim.focus(); tim.setSelectionRange(tim.value.length, tim.value.length); }
    tim.addEventListener("input", () => {
      clearTimeout(uvGo);
      uvGo = setTimeout(() => { UV.tim = tim.value.trim(); ungVien(null); }, 300);
    });
    box.querySelector("#uv-diem").addEventListener("click", () => { UV.moi_diem = !UV.moi_diem; ungVien(null); });
    const tiep = box.querySelector("#uv-tiep");
    if (tiep) tiep.addEventListener("click", () => { UV.page += 1; ungVien(tiep, { tiep: true }); });
    box.querySelectorAll("[data-tao]").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        const r = await api.thTaoHd(name, b.dataset.tao);
        toast(`Đã lập ${r.name} (nháp, ${r.so_dong} dòng)${r.tk_5213 ? "" : " — chưa thấy TK 5213, dòng giữ TK doanh thu gốc"}`, "success");
        UV.d = null;
        await reload(r.thu_hoi);
      } catch (e) {
        b.disabled = false; toast(e.message, "error");
      }
    }));
  }

  function ketLuan() {
    const m = openModal({ title: "Không lập hóa đơn trả về", icon: "fa-user-tie", body: html`
      <p>Chỉ dùng khi lô này thật sự không ghi giảm công nợ: đổi hàng ngang giá, hàng không thuộc hóa đơn nào, hàng không về... Lý do lưu lại kèm tên người kết luận.</p>
      <div class="kt-field"><label class="kt-label">Lý do *</label><textarea class="kt-textarea" id="kl-lydo" rows="3"></textarea></div>
      <button type="button" class="kt-btn kt-btn--primary" id="kl-ok">Kết luận</button>` });
    m.body.querySelector("#kl-ok").addEventListener("click", async (e) => {
      const ly = m.body.querySelector("#kl-lydo").value.trim();
      if (ly.length < 5) { toast("Ghi rõ lý do", "warning"); return; }
      e.currentTarget.disabled = true;
      try { const r = await api.thKetLuan(name, ly); m.close(); toast("Đã kết luận — lô xong", "success"); await reload(r); } catch (err) {
        e.currentTarget.disabled = false; toast(err.message, "error");
      }
    });
  }

  await reload();
}
