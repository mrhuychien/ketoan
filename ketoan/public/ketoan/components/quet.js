// quet.js — QUÉT MÃ VẠCH bằng camera, bấm là mở camera ngay. Port từ app sx
// (components/quet.js, D63/D77/D78) — đọc docstring bên đó cho đủ lý do; tóm tắt:
//
//   · XIN LẤY NÉT liên tục + 1920×1080: mặc định trình duyệt hay 640×480 nét cố định,
//     vạch hẹp của EAN/ITF chỉ dày một hai điểm ảnh — mã vạch đọc mãi không ra.
//   · Ô ngắm RỘNG cho mã vạch (ô vuông dạy người ta lùi xa, lùi xa thì vạch càng nhỏ),
//     bấm vào khung để lấy nét lại, nút đèn khi kho tối.
//   · HAI BỘ GIẢI MÃ: BarcodeDetector (Chrome/Android) và zxing1d đóng gói trong repo
//     (Safari/iPhone không có BarcodeDetector). Nạp trễ để Android khỏi tải 184KB.
//   · MÁY QUÉT CẦM TAY (keyboard wedge) nghe phím ở cấp document — không focus ô nào,
//     focus ô nhập trên điện thoại là bật bàn phím ảo che camera.
//   · TRA Ở MÁY: bảng tra có sẵn từ boot — quét phải phản hồi tức thì.
import { escapeHtml } from "../lib/format.js";
import { openSheet } from "./numpad.js";

const CAM = {
  video: {
    facingMode: { ideal: "environment" },
    width: { ideal: 1920 },
    height: { ideal: 1080 },
    advanced: [{ focusMode: "continuous" }],
  },
};

export function coCamera() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

/** Tra mã trong bảng, nới ĐÚNG MỘT chữ số 0 đầu cho EAN-13 ↔ UPC-A.
 *  EAN-13 bắt đầu bằng 0 CHÍNH LÀ UPC-A: bộ đọc trả 12 số, ERPNext hay lưu 13 số. */
export function traBang(bang, key) {
  if (!bang || !key) return undefined;
  if (bang[key] !== undefined) return bang[key];
  if (/^\d{12}$/.test(key) && bang[`0${key}`] !== undefined) return bang[`0${key}`];
  if (/^0\d{12}$/.test(key) && bang[key.slice(1)] !== undefined) return bang[key.slice(1)];
  return undefined;
}

/** Vùng khung hình ứng với ô ngắm (video object-fit: cover cắt bớt một chiều). */
export function vungNgam(W, H, rC, rO) {
  const ca = { sx: 0, sy: 0, sw: W, sh: H };
  if (!W || !H || !rC || !rO || !rC.width || !rC.height) return ca;
  const ti = Math.max(rC.width / W, rC.height / H);
  const leX = (W * ti - rC.width) / 2;
  const leY = (H * ti - rC.height) / 2;
  const sx = Math.max(0, (rO.left - rC.left + leX) / ti);
  const sy = Math.max(0, (rO.top - rC.top + leY) / ti);
  const sw = Math.min(W - sx, rO.width / ti);
  const sh = Math.min(H - sy, rO.height / ti);
  return sw < 8 || sh < 8 ? ca : { sx, sy, sw, sh };
}

/**
 * Mở cửa sổ quét. `bang` = {mã: giá trị}; `onTim(giaTri, maGoc)`.
 * Mã lạ thì NÓI RÕ và để quét tiếp — im lặng là người ta quét mãi một tem hỏng.
 */
export function moQuet({ bang, title = "Quét mã vạch", kicker = "", onTim }) {
  let dungLai = () => {};
  const m = openSheet({ title, kicker, onClose: () => dungLai() });
  m.body.innerHTML = `
    <div class="kt-th-quet-khung"><div class="kt-th-quet-tt">Đang mở camera…</div></div>
    <div class="kt-th-quet-hang"></div>
    <div class="kt-th-quet-tt kt-th-quet-bao">Đưa mã vào giữa khung.</div>
    <button type="button" class="kt-btn kt-btn--outline kt-th-quet-tay">⌨ Gõ mã bằng tay</button>`;
  const khung = m.body.querySelector(".kt-th-quet-khung");
  const bao = m.body.querySelector(".kt-th-quet-bao");
  const hang = m.body.querySelector(".kt-th-quet-hang");

  let xong = false;
  function nhan(ma) {
    const key = String(ma || "").trim();
    if (!key || xong) return false;
    const gt = traBang(bang, key);
    if (!gt) {
      bao.textContent = `Không nhận ra mã "${key}". Mã chưa khai trên Item, hoặc tem sai — tìm theo tên bên ngoài.`;
      bao.className = "kt-th-quet-tt kt-th-quet-bao kt-th-quet-loi";
      return false;
    }
    xong = true;
    try { if (navigator.vibrate) navigator.vibrate(60); } catch (e) { /* máy không rung */ }
    dungLai();
    m.close();
    if (onTim) onTim(gt, key);
    return true;
  }

  let dem = "";
  let lucCuoi = 0;
  const nghePhim = (e) => {
    const gio = Date.now();
    if (gio - lucCuoi > 120) dem = ""; // người gõ tay chậm hơn máy quét nhiều
    lucCuoi = gio;
    if (e.key === "Enter") {
      if (dem.length >= 3) { e.preventDefault(); nhan(dem); }
      dem = "";
      return;
    }
    if (e.key.length === 1) dem += e.key;
  };
  document.addEventListener("keydown", nghePhim);

  m.body.querySelector(".kt-th-quet-tay").addEventListener("click", (e) => {
    e.currentTarget.remove();
    const o = document.createElement("input");
    o.className = "kt-input kt-th-quet-input";
    o.setAttribute("autocomplete", "off");
    o.setAttribute("inputmode", "numeric");
    o.placeholder = "Gõ mã rồi Enter";
    o.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); ev.stopPropagation(); nhan(o.value); }
    });
    m.body.insertBefore(o, bao);
    o.focus();
  });

  batCamera({ khung, hang, bao, nhan })
    .then((stop) => { dungLai = () => { stop(); document.removeEventListener("keydown", nghePhim); }; })
    .catch(() => { dungLai = () => document.removeEventListener("keydown", nghePhim); });
  return m;
}

function khaNang(track) {
  try { return (track && track.getCapabilities && track.getCapabilities()) || {}; } catch (e) { return {}; }
}
const coNet = (kn, cd) => !!(kn.focusMode && kn.focusMode.indexOf(cd) >= 0);
async function apDung(track, nc) {
  try { await track.applyConstraints({ advanced: nc }); return true; } catch (e) { return false; }
}

async function batCamera({ khung, hang, bao, nhan }) {
  if (!coCamera()) {
    khung.innerHTML = '<div class="kt-th-quet-tt kt-th-quet-loi">Máy này không mở được camera. Dùng máy quét cầm tay, hoặc "Gõ mã bằng tay".</div>';
    return () => {};
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia(CAM);
  } catch (e) {
    // Từ chối quyền và không chạy HTTPS là hai lỗi khác nhau, cách sửa cũng khác.
    const lyDo = e && e.name === "NotAllowedError"
      ? "Bạn đã từ chối quyền camera. Vào cài đặt trình duyệt bật lại cho trang này."
      : !window.isSecureContext ? "Trang không chạy HTTPS nên trình duyệt chặn camera."
        : "Không mở được camera (máy đang bận, hoặc không có camera sau).";
    khung.innerHTML = `<div class="kt-th-quet-tt kt-th-quet-loi">${escapeHtml(lyDo)}<br>Dùng máy quét cầm tay, hoặc "Gõ mã bằng tay".</div>`;
    throw e;
  }
  const video = document.createElement("video");
  video.className = "kt-th-quet-video";
  video.setAttribute("playsinline", "");
  video.setAttribute("muted", "");
  video.muted = true;
  video.srcObject = stream;
  khung.innerHTML = "";
  khung.appendChild(video);
  const oNgam = document.createElement("div");
  oNgam.className = "kt-th-quet-o-ngam";
  khung.appendChild(oNgam);
  await video.play().catch(() => {});

  let chay = true;
  const track = stream.getVideoTracks()[0];
  const kn = khaNang(track);
  if (coNet(kn, "continuous")) await apDung(track, [{ focusMode: "continuous" }]);
  const netDuoc = coNet(kn, "continuous") || coNet(kn, "single-shot") || !!kn.pointsOfInterest;
  if (netDuoc) {
    khung.addEventListener("click", async (e) => {
      const o = khung.getBoundingClientRect();
      if (!o.width || !o.height) return;
      const x = Math.min(1, Math.max(0, (e.clientX - o.left) / o.width));
      const y = Math.min(1, Math.max(0, (e.clientY - o.top) / o.height));
      const nc = [];
      if (kn.pointsOfInterest) nc.push({ pointsOfInterest: [{ x, y }] });
      if (coNet(kn, "single-shot")) nc.push({ focusMode: "single-shot" });
      else if (coNet(kn, "continuous")) nc.push({ focusMode: "continuous" });
      if (nc.length && (await apDung(track, nc)) && coNet(kn, "single-shot") && coNet(kn, "continuous")) {
        setTimeout(() => apDung(track, [{ focusMode: "continuous" }]), 1200);
      }
    });
  }
  if (kn.torch) {
    const den = document.createElement("button");
    den.type = "button";
    den.className = "kt-btn kt-btn--outline";
    den.textContent = "💡 BẬT ĐÈN";
    let sang = false;
    den.addEventListener("click", async () => {
      if (!(await apDung(track, [{ torch: !sang }]))) return;
      sang = !sang;
      den.textContent = sang ? "💡 TẮT ĐÈN" : "💡 BẬT ĐÈN";
    });
    hang.appendChild(den);
  }

  let doc;
  if (typeof window.BarcodeDetector === "function") {
    try {
      const det = new window.BarcodeDetector();
      doc = async () => { const ds = await det.detect(video); return ds && ds.length ? ds[0].rawValue : null; };
    } catch (e) { doc = null; }
  }
  if (!doc) {
    bao.textContent = "Đang tải bộ đọc mã…";
    const { taoBoDoc } = await import("/assets/ketoan/ketoan/vendor/zxing1d.js");
    const docAnh = taoBoDoc();
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    doc = async () => {
      const W = video.videoWidth;
      const H = video.videoHeight;
      if (!W) return null;
      // CẮT ĐÚNG Ô NGẮM rồi mới đọc — thu nhỏ cả khung 1080p là ném đi điểm ảnh của mã.
      const { sx, sy, sw, sh } = vungNgam(W, H, video.getBoundingClientRect(), oNgam.getBoundingClientRect());
      const ti = Math.min(1, 720 / Math.max(sw, sh));
      canvas.width = Math.max(1, Math.round(sw * ti));
      canvas.height = Math.max(1, Math.round(sh * ti));
      ctx.drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
      const anh = ctx.getImageData(0, 0, canvas.width, canvas.height);
      return docAnh(anh.data, anh.width, anh.height);
    };
  }
  bao.textContent = "Đưa mã vào giữa khung" + (netDuoc ? " — bấm vào khung để lấy nét." : ".");
  const nhac = setTimeout(() => {
    if (chay && !bao.classList.contains("kt-th-quet-loi")) {
      bao.textContent = "Chưa đọc được? Đưa gần hơn cho mã kín ngang ô ngắm" + (kn.torch ? ", bật đèn" : "") + ', hoặc "Gõ mã bằng tay".';
    }
  }, 7000);
  const vong = async () => {
    if (!chay) return;
    try {
      const ma = await doc();
      if (ma && nhan(ma)) { clearTimeout(nhac); return; }
    } catch (e) { /* khung lỗi -> thử khung sau */ }
    if (!chay) return;
    if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(() => vong());
    else setTimeout(() => requestAnimationFrame(vong), 120);
  };
  if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(() => vong());
  else requestAnimationFrame(vong);
  return () => { chay = false; clearTimeout(nhac); stream.getTracks().forEach((t) => t.stop()); };
}
