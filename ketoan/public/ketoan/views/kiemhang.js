// views/kiemhang.js — KIỂM HÀNG THU HỒI trên điện thoại (#/kiem-hang/:id).
//
// Dựng theo màn Ghi hộp của app sx (cards/vaohop.js): tìm / QUÉT mã → bàn số phím to
// (tab Thùng / Hộp) → LƯU NGAY từng lần, không có nút "lưu tất cả" để quên bấm.
//   · Quét lại mã đã có = CỘNG THÊM vào dòng đó (một mã một dòng) — người kiểm đếm
//     từng chồng, không phải cộng nhẩm cả lô rồi mới nhập.
//   · Chạm vào SỐ để sửa tổng, ✕ để xóa dòng.
//   · "+ QUÉT TIẾP" lưu rồi mở camera ngay: quét 40 thùng không phải bấm 80 lần.
//   · Tìm tay: chỉ trong Hàng truyền thống + Hàng Tết (server lọc); mã HAY TRẢ (siêu thị
//     khai + khách này mua gần đây) nổi lên ĐẦU kết quả. Ô tìm trống thì không hiện gì.
//   · Đếm MÙ: số siêu thị khai chỉ hiện SAU khi chốt (màn lô), không hiện ở đây —
//     hiện số khai trước là mời người kiểm gõ lại số khai cho nhanh.
//   · NGOẠI LỆ — lô HỦY TẠI CHỖ (phiếu `theo_phieu`): không có hàng để đếm, kế toán CHÉP mã
//     + số theo phiếu / biên bản hủy của siêu thị — nên màn này hiện mail dán + file đính kèm.
//   · Lô có PHIẾU TRẢ VỀ đi kèm hàng: ghi số đếm thẳng lên phiếu rồi CHỤP lại (📷) — khỏi nhập
//     trên điện thoại. Ngồi máy tính mở lại màn này: ảnh LỚN bên trái (xoay, phóng to), ô nhập
//     bên phải, gõ phím thật — Enter ở ô tìm chọn mã đầu, bàn số nhận số + Enter là LƯU.
// Chốt rồi thì chỉ xem; muốn sửa: "Mở lại" ở màn lô.
import { api } from "../lib/api.js";
import { html, setHTML } from "../lib/dom.js";
import { anhGui } from "../lib/anh.js";
import { toast } from "../components/toast.js";
import { openSoLuong } from "../components/numpad.js";
import { moQuet } from "../components/quet.js";

const fmtSl = (n) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 3 }).format(Number(n) || 0);

// Bỏ dấu + hạ chữ để tìm "banh dau xanh" ra "Bánh đậu xanh".
const khongDau = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "")
  .replace(/đ/g, "d").replace(/Đ/g, "d").toLowerCase();

export async function render({ container, params }) {
  const name = params.id;
  let B = null; // boot: lo, phieu, danh_muc, ma_quet, goi_y
  let tim = "";
  let busy = false;

  try {
    B = await api.thBoot(name);
  } catch (e) {
    setHTML(container, html`<div class="kt-empty kt-empty--error"><i class="fas fa-circle-exclamation"></i>
      <p>${e.message}</p><p><a href="#/thu-hoi/${encodeURIComponent(name)}">← Về lô ${name}</a></p></div>`);
    return;
  }
  const byItem = {};
  B.danh_muc.forEach((d) => { byItem[d.item] = d; d._k = khongDau(`${d.ten} ${d.item}`); });

  const daChot = () => !!(B.phieu && B.phieu.da_chot);
  const tp = !!(B.phieu && B.phieu.theo_phieu);
  const XEM_TRONG_TAB = new Set(["jpg", "jpeg", "png", "webp", "gif", "pdf"]);
  const anh = () => B.anh_phieu || [];
  // Máy có chuột (ngồi máy nhập theo ảnh): lưu xong trả con trỏ về ô tìm để gõ mã kế tiếp.
  // Điện thoại thì KHÔNG — tự focus là bật bàn phím ảo che nửa màn hình.
  const mayTinh = () => !!(window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches);

  // Phiếu của siêu thị để chép (chỉ lô hủy tại chỗ): mail dán nguyên văn + biên bản / phiếu đính kèm.
  function phieuSieuThi() {
    const lo = B.lo || {};
    const files = B.files || [];
    if (!lo.chi_tiet_hang && !files.length) {
      return html`<div class="kt-alert kt-alert--warning">Lô chưa có mail / biên bản hủy nào — nhờ điều phối đính kèm phiếu của siêu thị bên app vận chuyển.</div>`;
    }
    return html`<div class="kt-th-kh-phieu">
      <div class="kt-th-kh-label">Phiếu siêu thị (chép theo đây)</div>
      ${lo.chi_tiet_hang ? html`<pre class="kt-th-paste" id="kh-mail">${lo.chi_tiet_hang}</pre>` : ""}
      ${files.length ? html`<div class="kt-th-kh-files">${files.map((f) => html`<a class="kt-btn kt-btn--outline kt-btn--sm" href="${f.url}" ${
        XEM_TRONG_TAB.has(f.ext) ? html`target="_blank" rel="noopener"` : html`download="${f.file_name}"`}><i class="fas fa-paperclip"></i> ${f.file_name}</a>`)}</div>` : ""}
    </div>`;
  }
  const dongCua = (item) => (B.phieu.items || []).find((r) => r.item_code === item);

  // Ảnh phiếu trên máy tính: cột trái LỚN, vẽ riêng — lưu số không vẽ lại cột này, nên ảnh
  // đang xoay / phóng to / cuộn tới đâu vẫn giữ nguyên lúc gõ tiếp.
  function veAnh() {
    const ds = anh();
    container.querySelector("#kh-wrap").classList.toggle("has-anh", ds.length > 0);
    const box = container.querySelector("#kh-anh-xem");
    setHTML(box, ds.length ? html`${ds.map((f, i) => html`<figure class="kt-th-kh-anh-fig">
      <figcaption class="kt-th-kh-anh-cu"><span>Ảnh ${i + 1}/${ds.length}${f.boi ? " · " + f.boi : ""}</span>
        <button type="button" class="kt-btn kt-btn--outline kt-btn--sm" data-xoay="${i}" title="Xoay 90°"><i class="fas fa-rotate-right"></i> Xoay</button>
        <button type="button" class="kt-btn kt-btn--outline kt-btn--sm" data-phong="${i}" title="Phóng to / thu nhỏ"><i class="fas fa-magnifying-glass-plus"></i> Phóng</button>
        <a class="kt-btn kt-btn--outline kt-btn--sm" href="${f.url}" target="_blank" rel="noopener">Mở tab</a></figcaption>
      <div class="kt-th-kh-anh-khung"><img src="${f.url}" alt="Ảnh phiếu ${i + 1}" data-anh="${i}"></div>
    </figure>`)}` : "");
    box.querySelectorAll("[data-xoay]").forEach((b) => b.addEventListener("click", () => xoay(box.querySelector(`img[data-anh="${b.dataset.xoay}"]`))));
    box.querySelectorAll("[data-phong]").forEach((b) => b.addEventListener("click", () => b.closest("figure").classList.toggle("is-to")));
  }

  // Xoay 90° bằng canvas (ảnh cùng tên miền — proxy của app): khung ảnh co giãn đúng chiều mới,
  // không như transform CSS xoay hình mà để nguyên cái hộp.
  function xoay(img) {
    if (!img || !img.complete || !img.naturalWidth) return; // lượt xoay trước chưa nạp xong
    const c = document.createElement("canvas");
    c.width = img.naturalHeight;
    c.height = img.naturalWidth;
    const g = c.getContext("2d");
    g.translate(c.width / 2, c.height / 2);
    g.rotate(Math.PI / 2);
    g.drawImage(img, -img.naturalWidth / 2, -img.naturalHeight / 2);
    img.src = c.toDataURL("image/jpeg", 0.92);
  }

  // Thẻ ảnh phiếu trong cột nhập: nút chụp + ảnh nhỏ (máy tính có ảnh lớn bên trái thì ẩn ảnh nhỏ).
  function theAnh() {
    const ds = anh();
    if (daChot() && !ds.length) return "";
    return html`<div class="kt-th-kh-anhcard${ds.length ? " has-anh" : ""}">
      <div class="kt-th-kh-anhcard-head"><b><i class="fas fa-camera"></i> Ảnh phiếu trả về</b>${ds.length ? html`<span class="kt-th-kh-anh-so">${ds.length} ảnh</span>` : ""}</div>
      ${ds.length ? html`<div class="kt-th-kh-thumbs">${ds.map((f) => html`<div class="kt-th-kh-thumb">
        <a href="${f.url}" target="_blank" rel="noopener"><img src="${f.url}" alt="Ảnh phiếu" loading="lazy"></a>
        ${daChot() ? "" : html`<button type="button" class="kt-th-kh-thumb-xoa" data-xoaanh="${f.name}" aria-label="Xóa ảnh">✕</button>`}
      </div>`)}</div>` : ""}
      ${daChot() ? "" : html`<div class="kt-th-kh-anhcard-hang">
        <div class="kt-sub">${ds.length
          ? "Đã chụp phiếu — ngồi máy nhập số theo ảnh rồi chốt. Thiếu trang thì chụp thêm."
          : "Lô có phiếu trả về? Ghi số đếm thẳng lên phiếu rồi chụp lại — ngồi máy nhập sau."}</div>
        <label class="kt-btn kt-btn--outline kt-th-kh-chup" id="kh-chup"><i class="fas fa-camera"></i> ${ds.length ? "Chụp thêm" : "Chụp phiếu"}
          <input type="file" accept="image/*" capture="environment" multiple id="kh-anh-input" hidden></label>
        <span class="kt-th-kh-anh-tt" id="kh-anh-tt" role="status"></span>
      </div>`}
    </div>`;
  }

  function khung() {
    setHTML(container, html`<div class="kt-th-kh-wrap" id="kh-wrap">
      <aside class="kt-th-kh-anh" id="kh-anh-xem" aria-label="Ảnh phiếu trả về"></aside>
      <div class="kt-th-kh" id="kh-cot"></div>
    </div>`);
    veAnh();
    paint();
  }

  function paint() {
    const ph = B.phieu;
    const lo = B.lo;
    setHTML(container.querySelector("#kh-cot"), html`
        <div class="kt-th-kh-top">
          <div>
            <div class="kt-th-kh-kicker">${tp ? "Nhập theo phiếu hủy" : "Kiểm hàng"} · ${lo.name}</div>
            <div class="kt-th-kh-title">${lo.ten_diem || lo.customer_name}</div>
            <div class="kt-th-kh-sub">${lo.customer_name}${lo.so_phieu_sieu_thi ? " · phiếu " + lo.so_phieu_sieu_thi : ""}</div>
          </div>
          <div class="kt-th-kh-tong"><div class="kt-th-kh-so">${fmtSl(ph.tong_sl)}</div><div class="kt-th-kh-sub">${(ph.items || []).length} mã ${tp ? "theo phiếu" : "đã kiểm"}</div></div>
        </div>
        ${tp ? phieuSieuThi() : ""}
        ${theAnh()}
        ${daChot() ? html`<div class="kt-alert kt-alert--info">Phiếu đã chốt — chỉ xem. Muốn sửa: bấm <b>Mở lại để sửa</b> ở <a href="#/thu-hoi/${encodeURIComponent(name)}">màn lô</a>.</div>` : html`
          <div class="kt-th-kh-tim">
            <input class="kt-input" id="kh-tim" type="search" autocomplete="off" autocorrect="off" spellcheck="false"
              enterkeyhint="search" placeholder="Tìm trong ${B.danh_muc.length} mã hàng…" value="${tim}">
            <button type="button" class="kt-btn kt-btn--primary kt-th-kh-quet" id="kh-quet">⌗ QUÉT</button>
          </div>
          ${(B.thieu_nhom || []).length ? html`<div class="kt-alert kt-alert--warning">Chưa thấy nhóm hàng
            ${B.thieu_nhom.map((g) => `“${g}”`).join(", ")} trong Item Group — ${(B.nhom_kiem || []).length
              ? `danh sách tìm chỉ có ${B.nhom_kiem.join(", ")}.` : "đang tìm trong mọi mã hàng bán."} Báo quản trị đặt đúng tên nhóm.</div>` : ""}
          <div id="kh-chon"></div>`}
        <div class="kt-th-kh-label">${tp ? "Đã chép theo phiếu" : "Đã kiểm"}</div>
        <div class="kt-th-kh-list" id="kh-dong"></div>
        ${daChot() ? "" : html`<div class="kt-th-kh-foot">
          <a class="kt-btn kt-btn--outline" href="#/thu-hoi/${encodeURIComponent(name)}"><i class="fas fa-arrow-left"></i> Lô</a>
          <button type="button" class="kt-btn kt-btn--success" id="kh-chot" ${(ph.items || []).length ? "" : "disabled"}>
            <i class="fas fa-lock"></i> ${tp ? "Chốt theo phiếu" : "Chốt phiếu"} · ${(ph.items || []).length} mã</button>
        </div>`}`);
    veChon();
    veDong();
    bind();
  }

  // Lựa chọn mã: CHỈ khi gõ tìm (ô trống thì không hiện gì — đỡ một khối chiếm nửa màn).
  // Mã HAY TRẢ (mã siêu thị khai + mã khách này mua gần đây — phần lớn lô quanh quẩn vài
  // mã đó) nổi lên ĐẦU kết quả theo thứ tự gợi ý, rồi tới các mã khác theo tên.
  const hay = new Map((B.goi_y || []).map((c, i) => [c, i]));
  const hang = (d) => (hay.has(d.item) ? hay.get(d.item) : hay.size);

  let dau = null; // mã đứng đầu kết quả tìm — Enter ở ô tìm chọn mã này

  function veChon() {
    const box = container.querySelector("#kh-chon");
    dau = null;
    if (!box) return;
    const q = khongDau(tim.trim());
    if (!q) {
      setHTML(box, "");
      return;
    }
    // sort ổn định: cùng hạng (mã thường) thì giữ thứ tự tên của danh mục.
    const ds = B.danh_muc.filter((d) => d._k.includes(q)).sort((a, b) => hang(a) - hang(b)).slice(0, 30);
    dau = ds.length ? ds[0].item : null;
    if (!ds.length) {
      setHTML(box, html`<div class="kt-sub">Không thấy mã nào khớp "${tim}".</div>`);
      return;
    }
    setHTML(box, html`<div class="kt-th-kh-label">Kết quả</div>
      <div class="kt-th-kh-chips">${ds.map((d) => {
        const co = dongCua(d.item);
        return html`<button type="button" class="kt-th-kh-chip${co ? " is-co" : ""}" data-item="${d.item}">
          <span>${d.ten}${hay.has(d.item) ? html` <b class="kt-th-kh-hay">hay trả</b>` : ""}</span>
          <i>${co ? `đã ${fmtSl(co.qty)} · ` : ""}${d.item} · ${d.dvt}</i></button>`;
      })}</div>`);
    box.querySelectorAll("[data-item]").forEach((b) => b.addEventListener("click", () => chonMa(b.dataset.item)));
  }

  function veDong() {
    const box = container.querySelector("#kh-dong");
    const rows = (B.phieu.items || []).slice().reverse(); // mới nhất lên đầu — vừa quét là thấy ngay
    if (!rows.length) {
      setHTML(box, tp
        ? html`<div class="kt-sub kt-th-kh-trong">Chưa chép mã nào. Gõ tên / mã hàng theo phiếu hủy của siêu thị ở ô tìm, nhập số lượng ghi trên phiếu.</div>`
        : html`<div class="kt-sub kt-th-kh-trong">Chưa kiểm mã nào. Bấm <b>⌗ QUÉT</b> rồi đưa mã vạch trên thùng / hộp vào khung, hoặc gõ tên mã.</div>`);
      return;
    }
    setHTML(box, html`${rows.map((r) => html`<div class="kt-th-kh-row">
      <div class="kt-th-kh-who"><div class="kt-th-kh-name">${r.item_name || r.item_code}</div>
        <div class="kt-th-kh-meta">${[r.mo_ta_dvt, r.item_code, r.nguoi_ghi].filter(Boolean).join(" · ")}</div></div>
      <button type="button" class="kt-th-kh-sl" data-sua="${r.name}" ${daChot() ? "disabled" : ""}>${fmtSl(r.qty)}<i>${r.stock_uom || ""}</i></button>
      ${daChot() ? "" : html`<button type="button" class="kt-th-kh-xoa" data-xoa="${r.name}" aria-label="Xóa dòng ${r.item_name || r.item_code}">✕</button>`}
    </div>`)}`);
    box.querySelectorAll("[data-sua]").forEach((b) => b.addEventListener("click", () => suaDong(b.dataset.sua)));
    box.querySelectorAll("[data-xoa]").forEach((b) => b.addEventListener("click", () => xoaDong(b.dataset.xoa)));
  }

  function bind() {
    const o = container.querySelector("#kh-tim");
    if (o) o.addEventListener("input", (e) => { tim = e.target.value; veChon(); });
    if (o) o.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || !dau) return;
      // Chặn cả lan lên: bàn số vừa mở nghe phím ở document — Enter này mà tới đó là "LƯU" số 0.
      e.preventDefault();
      e.stopPropagation();
      chonMa(dau);
    });
    const inp = container.querySelector("#kh-anh-input");
    if (inp) inp.addEventListener("change", () => guiAnh(inp));
    container.querySelectorAll("#kh-cot [data-xoaanh]").forEach((b) => b.addEventListener("click", () => xoaAnh(b.dataset.xoaanh)));
    const q = container.querySelector("#kh-quet");
    if (q) q.addEventListener("click", () => quet());
    const c = container.querySelector("#kh-chot");
    if (c) c.addEventListener("click", () => chot(c));
  }

  function quet() {
    moQuet({
      bang: B.ma_quet, kicker: `Kiểm hàng · ${B.lo.name}`, title: "Quét mã vạch trên thùng / hộp",
      onTim: (gt, ma) => chonMa(gt.item, { uom: gt.uom, ma, tiep: true }),
    });
  }

  // Một lần đếm cho MỘT mã. Mã đã có dòng → nhập phần CỘNG THÊM (đúng cách đếm từng chồng).
  function chonMa(item, { uom = null, ma = null, tiep = false } = {}) {
    if (daChot()) return;
    const d = byItem[item];
    if (!d) {
      toast(`Mã ${ma || item} không nằm trong danh sách kiểm hàng (${(B.nhom_kiem || []).join(", ") || "hàng bán"}).`, "error");
      return;
    }
    const co = dongCua(item);
    openSoLuong({
      kicker: co ? `Cộng thêm · đã có ${fmtSl(co.qty)} ${d.dvt}` : "Nhập số đã đếm",
      title: d.ten,
      uoms: d.uoms, dvt: d.dvt, tabDau: uom,
      okLabel: "LƯU",
      okPhu: tiep ? { label: "+ QUÉT TIẾP", onOk: (t, ct) => them(item, t, ct, ma, true) } : null,
      onOk: (t, ct) => them(item, t, ct, ma, false),
    });
  }

  async function them(item, tong, ct, ma, quetTiep) {
    if (busy) return;
    busy = true;
    const d = byItem[item] || {};
    const cong = !!dongCua(item);
    // "+1 Thùng = 24 Hộp" — nói đúng cách vừa đếm, kèm ĐVT kho, để người kiểm soát lại bằng mắt.
    const cach = (ct || []).map((c) => `${fmtSl(c.sl)} ${c.uom}`).join(" + ");
    const so = `${fmtSl(tong)} ${d.dvt || ""}`.trim();
    try {
      B.phieu = await api.thThem({ name, item_code: item, qty: tong, chi_tiet: ct ? JSON.stringify(ct) : undefined, ma_quet: ma || undefined });
      tim = "";
      paint();
      toast(`Đã lưu ${cong ? "+" : ""}${cach && cach !== so ? `${cach} = ${so}` : so} · ${d.ten || item}`, "success");
      if (quetTiep) quet();
      else veTim();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }

  function suaDong(row) {
    const r = (B.phieu.items || []).find((x) => x.name === row);
    if (!r) return;
    const d = byItem[r.item_code] || { ten: r.item_name, uoms: [], dvt: r.stock_uom };
    openSoLuong({
      kicker: "Sửa tổng đã kiểm", title: d.ten || r.item_code,
      uoms: d.uoms, dvt: d.dvt, tong: r.qty, chiTiet: r.chi_tiet,
      onOk: async (t, ct) => {
        try {
          B.phieu = await api.thSua({ name, row, qty: t, chi_tiet: ct ? JSON.stringify(ct) : undefined });
          paint();
          toast("Đã sửa", "success");
          veTim();
        } catch (e) { toast(e.message, "error"); }
      },
    });
  }

  function veTim() {
    const o = container.querySelector("#kh-tim");
    if (o && mayTinh()) o.focus();
  }

  // Gửi từng ảnh một (nén trước): ảnh lỗi không kéo ảnh khác chết theo.
  async function guiAnh(inp) {
    const files = [...(inp.files || [])];
    inp.value = "";
    if (!files.length) return;
    if (busy) {
      toast("Đang lưu dở — chụp lại sau một giây", "warning");
      return;
    }
    busy = true;
    const tt = container.querySelector("#kh-anh-tt");
    let ok = 0;
    for (const [i, f] of files.entries()) {
      if (tt) tt.textContent = `Đang gửi ảnh ${i + 1}/${files.length}…`;
      try {
        const { content, ten } = await anhGui(f);
        const r = await api.thAnhThem({ name, content, filename: ten });
        B.anh_phieu = r.anh_phieu || [];
        ok += 1;
      } catch (e) {
        toast(e.message, "error");
      }
    }
    busy = false;
    veAnh();
    paint();
    if (ok) toast(`Đã lưu ${ok} ảnh phiếu — ngồi máy nhập số theo ảnh rồi chốt`, "success");
  }

  async function xoaAnh(file) {
    if (busy || !confirm("Xóa ảnh phiếu này?")) return;
    try {
      const r = await api.thAnhXoa(name, file);
      B.anh_phieu = r.anh_phieu || [];
      veAnh();
      paint();
    } catch (e) { toast(e.message, "error"); }
  }

  async function xoaDong(row) {
    const r = (B.phieu.items || []).find((x) => x.name === row);
    if (!r || !confirm(`Xóa dòng ${r.item_name || r.item_code} (${fmtSl(r.qty)})?`)) return;
    try {
      B.phieu = await api.thXoaDong(name, row);
      paint();
    } catch (e) { toast(e.message, "error"); }
  }

  async function chot(btn) {
    const n = (B.phieu.items || []).length;
    if (!confirm(`${tp ? "Chốt theo phiếu hủy" : "Chốt phiếu kiểm"} ${name} với ${n} mã · tổng ${fmtSl(B.phieu.tong_sl)}?\nChốt rồi mới lập hóa đơn trả về; muốn sửa phải Mở lại.`)) return;
    btn.disabled = true;
    try {
      await api.thChot(name);
      toast("Đã chốt phiếu kiểm", "success");
      location.hash = "#/thu-hoi/" + encodeURIComponent(name);
    } catch (e) {
      btn.disabled = false;
      toast(e.message, "error");
    }
  }

  khung();
}
