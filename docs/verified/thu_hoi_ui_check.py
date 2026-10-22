#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""thu_hoi_ui_check — TAB THU HỒI + MÀN KIỂM HÀNG chạy thật trong Chromium.

`thu_hoi_check` canh phần server (ĐVT, trần trả, trạng thái). Bộ này canh cái người
kiểm hàng CẦM TRÊN TAY: portal thật (shell.js, import map của ketoan.html, shell.css),
chỉ server là giả — trả đúng hình dạng JSON của `ketoan.api.thu_hoi.*`.

════════════════════════════════════════════════════════════════════════════
NHỮNG ĐIỀU MÀN HÌNH HỨA
════════════════════════════════════════════════════════════════════════════

1. **Đếm mù.** Màn kiểm hàng không được hiện số siêu thị khai — kể cả mail siêu thị dán
   nguyên văn (có số lượng) — hiện ra là mời gõ lại số khai.
1b. **Tìm tay gọn**: ô tìm trống KHÔNG hiện khối "Hay trả"; gõ tìm thì mã hay trả nổi lên
   ĐẦU kết quả (có nhãn), kết quả là danh sách dọc đủ tên + mã + ĐVT; thiếu nhóm hàng
   Hàng truyền thống / Hàng Tết trên site thì báo đúng nhóm thiếu.
2. **Bàn số nhiều ĐVT.** "2 thùng + 3 hộp" = 51 hộp hiện ngay trên nút LƯU; client gửi
   CHI TIẾT từng ĐVT (server tự nhân hệ số, không tin tổng client gửi).
3. **Quét lại mã đã có = cộng thêm**, mã vạch thùng mở sẵn tab Thùng; máy không có
   camera vẫn còn đường gõ mã tay.
4. **Toast không nuốt cú chạm.** Toast "Đã lưu…" hiện đúng chỗ nút LƯU của bàn số kế
   tiếp. Trước đây toast bắt chạm, và khi "ẩn" chỉ trượt xuống còn cách đáy ~25px —
   vẫn che nút Chốt phiếu. Người kiểm bấm liên tục nên cú chạm mất là số mất.
5. **Bảng trên máy tính, thẻ trên điện thoại** — không bao giờ hiện cả hai, bảng không
   cuộn ngang ở 1280px.
6. **Luồng tới hóa đơn trả về**: chốt → về lô → chọn hóa đơn gốc → bản nháp + deep link
   Desk + giải thích dòng "không nối dòng gốc"; trang không lỗi JS nào. Danh sách hóa đơn
   gốc = MỌI tờ đã ghi sổ của đúng khách + đúng điểm giao của lô, đủ thông tin (HĐĐT, PO,
   địa chỉ, số tiền, còn nợ); tờ không còn gì để trả vẫn hiện, chỉ khóa nút + nói lý do;
   tìm / "Xem tiếp" / "Xem mọi điểm của khách" đều hỏi lại server.
7. **Hồ sơ lô theo đúng lô mới**: đơn vị thu hồi · mã vận đơn · ngày thu (không còn xe /
   lái xe), mail dán giữ nguyên tab, file Excel TẢI VỀ còn PDF mở tab; lô mới không có cột
   "Siêu thị khai", lô cũ còn bảng hàng khai thì vẫn so khai / kiểm như trước.
8. **Lô bên vận chuyển đã HỦY**: không tính vào "Đang mở", có pill "Đã hủy" riêng, thẻ ghi
   lý do; màn lô có khung "đã HỦY" + lý do, không có nút "Bắt đầu kiểm hàng".
9. **Lô HỦY TẠI CHỖ** (siêu thị hủy, không thu): nằm ở "Đã kiểm hàng" + nhãn, thanh 7 nấc vẽ
   3 nấc giữa là bỏ qua; màn lô có nút "Nhập hàng theo phiếu hủy" → màn nhập THẤY mail dán
   + biên bản để chép (lô thường vẫn đếm mù), nút "Chốt theo phiếu".
10. **Ghi số lên phiếu trả về, chụp, ngồi máy nhập sau**: điện thoại mở CAMERA (capture), ảnh
   được NÉN thành JPEG cạnh dài ≤ 2400px trước khi gửi, xóa được ảnh chụp nhầm; danh sách có
   pill + nhãn "📷 Chờ nhập số". Máy tính: ảnh LỚN bên trái, ô nhập bên phải; xoay / phóng to
   giữ nguyên khi lưu số; gõ phím thật — Enter ở ô tìm chọn mã đầu, số + ←/→ đổi Thùng/Hộp +
   Enter là LƯU, lưu xong con trỏ về ô tìm.
11. **Hóa đơn trả về không cần chọn hóa đơn gốc**: nút chính "Lập hóa đơn trả về" gửi KHÔNG kèm
   hóa đơn gốc, tờ hiện "không theo hóa đơn gốc" (không nhãn "không nối dòng gốc"), kèm lời
   nhắc soát giá; "theo hóa đơn gốc" còn đó làm tùy chọn.

Thử phá (đã làm khi viết): bỏ `pointer-events: none` của `.kt-toast` → bước sửa dòng
kẹt vì toast chặn nút LƯU; trả `.kt-th-cards { display: flex }` ra ngoài media query →
"desktop: bảng hiện, thẻ ẩn" đỏ. Danh sách hóa đơn gốc: tờ khóa vẫn bấm được, "Xem tiếp"
thay vì nối, tìm không gửi server, kết quả tìm cũ về muộn đè kết quả mới, mất con trỏ ô
tìm, điện thoại hiện bảng (tràn mép), bỏ chữ trắng nút <a> — mỗi lần đỏ ĐÚNG mục.
Ảnh phiếu + hóa đơn không theo hóa đơn gốc (15 lần phá): không nén / nén 1200px, bỏ `capture`,
máy tính không chia cột / còn ảnh nhỏ, lưu số vẽ lại ảnh, Enter lan sang bàn số, không trả con
trỏ về ô tìm, bàn số không nghe phím / mũi tên không đổi tab, nút lập vẫn gửi hóa đơn gốc, tờ tự
do mang nhãn "không nối", mất pill "Chờ nhập số", màn lô không mời nhập theo ảnh, xoay bằng CSS.

Chạy KHÔNG cần bench (cần `pip install playwright`; Chromium có sẵn ở /opt/pw-browsers):
    python3 docs/verified/thu_hoi_ui_check.py [--shots THƯ_MỤC]
Không có trình duyệt thì BỎ QUA (thoát 0) như `table_width_check`.
"""

import base64
import glob
import json
import os
import re
import struct
import sys
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PUB = os.path.join(REPO, "ketoan", "public", "ketoan")
PAGE_SRC = os.path.join(REPO, "ketoan", "www", "ketoan.html")
BASE = "/assets/ketoan/ketoan"


def chromium_path():
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                "/opt/pw-browsers/chromium/chrome-linux/chrome"):
        hit = sorted(glob.glob(pat))
        if hit:
            return hit[-1]
    return None


def _bo_qua(msg):
    print("=" * 82)
    print("THU HỒI — MÀN HÌNH THẬT TRONG CHROMIUM")
    print("=" * 82)
    print(f"  ⚠ BỎ QUA — {msg}")
    print("    Cài: pip install playwright  (Chromium đã có sẵn ở /opt/pw-browsers)")
    print("=" * 82)
    print("KẾT QUẢ: BỎ QUA — không có trình duyệt, KHÔNG kết luận gì")
    return 0


def build_page():
    """Trang giống `ketoan.html` sau khi Jinja chạy: CÙNG import map, cùng shell.js."""
    src = open(PAGE_SRC, encoding="utf-8").read()
    imap = re.search(r'<script type="importmap">(.*?)</script>', src, re.S).group(1)
    imap = imap.replace("{{ base }}", BASE).replace("{{ v }}", "1")
    ctx = {
        "user": "kt@x", "fullName": "Kế toán MT", "isManager": False,
        "caps": {"mt": True, "salesany": True, "thuhoi": True},
        "workspaces": ["mt", "thuhoi"], "roles": ["Ke Toan MT"], "company": "HGC",
        "csrfToken": "x", "assetVersion": "1", "settings": {},
    }
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">'
        f'<link rel="stylesheet" href="{BASE}/shell.css">'
        f"<script>window.KETOAN_CONTEXT = {json.dumps(ctx, ensure_ascii=False)};</script>"
        f'<script type="importmap">{imap}</script></head><body>'
        f'<div id="kt-root"></div><script type="module" src="{BASE}/shell.js?v=1"></script></body></html>'
    )


# ═══════════════════════════════════════════════════════════════════════════
# Server giả — đúng hình dạng JSON của ketoan.api.thu_hoi
# ═══════════════════════════════════════════════════════════════════════════

CHANG = ["Tạo yêu cầu", "Đã lấy hàng", "Đã nhận hàng", "Đang kiểm", "Đã kiểm hàng",
         "Đã nhập chứng từ", "Xong"]
LO = {
    "name": "TH-2026-0007", "trang_thai": "Đã nhận hàng", "ngay_yeu_cau": "2026-10-05",
    "so_phieu_sieu_thi": "XT-889", "ly_do": "Hàng date / cận date",
    "customer": "COOP", "customer_name": "Saigon Co.op", "shipping_address_name": "ADDR-HD",
    "ten_diem": "Co.opMart Hà Đông", "ma_diem": "HD01", "dia_chi": "1 Quang Trung, Hà Đông",
    "don_vi_thu_hoi": "Viettel Post", "ma_van_don": "VTP123", "ngay_hen_lay": "2026-10-16",
    "lay_luc": "2026-10-16 08:10:00", "lay_boi": "Điều hành",
    "nhan_luc": "2026-10-16 15:00:00", "nhan_boi": "Kho", "so_kien_du_kien": 3, "so_kien_nhan": 3,
    "so_dinh_kem": 2,
}
# Mail siêu thị dán nguyên văn bên vanchuyen — cột cách nhau bằng tab, có SỐ KHAI (48).
CHI_TIET = "\tMã hàng\tTên hàng\tSL\nBDX-170\tBánh đậu xanh 170g\t48"
LO["chi_tiet_hang"] = CHI_TIET
UOMS = [{"uom": "Thùng", "he_so": 24}, {"uom": "Hộp", "he_so": 1}]
TEN = "Bánh đậu xanh 170g"
KHAI = 48  # siêu thị khai 2 thùng = 48 hộp — con số màn kiểm hàng KHÔNG được để lộ
S = {"phieu": None, "hd": [], "log": []}


def png(w, h, rgb=(200, 40, 40)):
    """PNG một màu w×h — ảnh thật để trình duyệt vẽ / nén / xoay."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def jpeg_wh(b):
    """(rộng, cao) đọc từ khung SOF của JPEG; không phải JPEG thì None."""
    if b[:3] != b"\xff\xd8\xff":
        return None
    i = 2
    while i < len(b) - 9:
        if b[i] != 0xFF:
            i += 1
            continue
        if b[i + 1] in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    return None


ANH_IMG = png(600, 300)  # ảnh phiếu proxy trả về (nằm ngang: xoay 90° thì 300×600)
LO_ANH = dict(LO, name="TH-2026-0010", ten_diem="Co.opMart Rạch Miễu", so_phieu_sieu_thi="XT-901", chi_tiet_hang=None)
A = {"phieu": {"name": "TH-2026-0010", "da_chot": 0, "items": [], "ghi_chu": ""}, "anh": [], "hd": [], "gui": [], "seq": 0}


def tong_a():
    return sum(r["qty"] for r in A["phieu"]["items"])


def lo_anh():
    """Lô người kiểm ghi số lên phiếu trả về rồi chụp — kế toán ngồi máy nhập theo ảnh."""
    ph = A["phieu"]
    kiem = tong_a()
    lap = sum(i["stock_qty"] for h in A["hd"] for i in h["items"])
    chot = bool(ph["da_chot"])
    chang_a = "Đang kiểm" if not chot else ("Đã kiểm hàng" if not A["hd"] else "Đã nhập chứng từ")
    return {"lo": LO_ANH, "khai": [], "co_khai": False, "tong_khai": 0, "files": [],
            "phieu": dict(ph, tong_sl=kiem, so_ma=len(ph["items"])), "anh_phieu": A["anh"], "hoa_don": A["hd"],
            "so_sanh": [{"item_code": "BDX", "item_name": TEN, "stock_uom": "Hộp", "khai": 0, "kiem": kiem, "da_lap": lap}]
            if ph["items"] else [],
            "chang": chang_a, "chang_list": CHANG, "lech": {}, "con_can": {"BDX": kiem - lap} if kiem - lap > 0 else {},
            "flags": {"bat_dau": False, "sua": not chot, "chot": not chot and bool(ph["items"]), "mo_lai": chot and not A["hd"],
                      "lap_hd": chot and kiem - lap > 0, "cap_nhat": False, "xoa": not chot and not A["hd"],
                      "ket_luan": False, "cho_nhap": not chot and bool(A["anh"])},
            "is_chief": False}


def them_anh(a):
    data = base64.b64decode(a["content"])
    A["gui"].append({"sig": data[:3], "wh": jpeg_wh(data), "n": len(data), "filename": a.get("filename")})
    A["seq"] += 1
    n = "FA%d" % A["seq"]
    A["anh"].append({"name": n, "file_name": "anh-phieu-TH-2026-0010-%d.jpg" % A["seq"], "ext": "jpg", "is_image": True,
                     "creation": "2026-10-22 09:0%d:00" % A["seq"], "boi": "Kế toán MT",
                     "url": "/api/method/ketoan.api.thu_hoi.xem_dinh_kem?file=" + n})
    return {"anh_phieu": A["anh"]}


def xoa_anh(a):
    A["anh"] = [x for x in A["anh"] if x["name"] != a["file"]]
    return {"anh_phieu": A["anh"]}


def tong():
    return sum(r["qty"] for r in S["phieu"]["items"]) if S["phieu"] else 0


def da_lap():
    return sum(i["stock_qty"] for h in S["hd"] for i in h["items"])


def phieu_dict():
    p = S["phieu"]
    return p and dict(p, tong_sl=tong(), so_ma=len(p["items"]))


def chang():
    p = S["phieu"]
    if not p:
        return LO["trang_thai"]
    if not p["da_chot"]:
        return "Đang kiểm"
    if not S["hd"] or abs(da_lap() - tong()) > 1e-6:
        return "Đã kiểm hàng"
    return "Xong" if all(h["docstatus"] == 1 for h in S["hd"]) else "Đã nhập chứng từ"


def lo_cu():
    """Lô CŨ (trước khi bỏ bảng hàng khai bên vanchuyen), đã chốt: còn số khai có cấu trúc."""
    lo = dict(LO, name="TH-2026-0005", chi_tiet_hang=None)
    return {
        "lo": lo, "khai": [{"item_code": "BDX", "item_name": TEN, "qty": 2, "uom": "Thùng", "stock_qty": KHAI,
                            "stock_uom": "Hộp"}],
        "co_khai": True, "tong_khai": KHAI, "files": [],
        "phieu": {"name": "TH-2026-0005", "da_chot": 1, "chot_luc": "2026-10-10 10:00:00", "chot_boi": "KT",
                  "items": [{"name": "r1", "item_code": "BDX", "item_name": TEN, "qty": 50, "stock_uom": "Hộp"}],
                  "tong_sl": 50, "so_ma": 1, "ghi_chu": ""},
        "hoa_don": [], "chang": "Đã kiểm hàng", "chang_list": CHANG, "lech": {}, "con_can": {"BDX": 50},
        "so_sanh": [{"item_code": "BDX", "item_name": TEN, "stock_uom": "Hộp", "khai": KHAI, "kiem": 50, "da_lap": 0}],
        "flags": {"lap_hd": True, "mo_lai": True}, "is_chief": False,
    }


HUY = dict(trang_thai="Đã hủy", ly_do_huy="Siêu thị rút yêu cầu trả hàng", huy_boi="Điều hành",
           huy_luc="2026-10-15 09:00:00", huy_tu="Đã lấy hàng")


LO_HTC = dict(LO, name="TH-2026-0008", trang_thai="Hủy tại chỗ", ten_diem="Co.opMart Cống Quỳnh",
              chi_tiet_hang="Biên bản hủy 18/10: BDX-170 hết date 3 hộp", huy_tai_cho_luc="2026-10-18 09:00:00",
              huy_tai_cho_boi="Điều hành", lay_luc=None, nhan_luc=None)
FILE_HTC = {"name": "F9", "file_name": "bien-ban-huy.pdf", "ext": "pdf", "is_image": False,
            "url": "/api/method/ketoan.api.thu_hoi.xem_dinh_kem?file=F9"}


def lo_htc():
    """Lô siêu thị HỦY TẠI CHỖ: chưa / đang chép theo phiếu (S["htc"])."""
    ph = S.get("htc")
    return {"lo": LO_HTC, "khai": [], "co_khai": False, "tong_khai": 0, "files": [FILE_HTC],
            "phieu": ph and dict(ph, tong_sl=0, so_ma=0), "hoa_don": [], "so_sanh": [], "chang": "Đã kiểm hàng",
            "chang_list": CHANG, "lech": {}, "con_can": {},
            "flags": {"bat_dau": not ph, "sua": bool(ph), "chot": False, "mo_lai": False, "lap_hd": False,
                      "cap_nhat": False, "xoa": bool(ph), "ket_luan": False}, "is_chief": False}


def lo_huy():
    """Lô bên vận chuyển đã HỦY yêu cầu: chỉ xem, không có phiếu kiểm."""
    lo = dict(LO, name="TH-2026-0004", ten_diem="Co.opMart Thắng Lợi", chi_tiet_hang=None, **HUY)
    return {"lo": lo, "khai": [], "co_khai": False, "tong_khai": 0, "files": [], "phieu": None, "hoa_don": [],
            "so_sanh": [], "chang": "Đã hủy", "chang_list": CHANG, "lech": {}, "con_can": {},
            "flags": {k: False for k in ("bat_dau", "sua", "chot", "mo_lai", "lap_hd", "cap_nhat", "xoa", "ket_luan")},
            "is_chief": False}


def get_th(a=None):
    if (a or {}).get("name") == "TH-2026-0005":
        return lo_cu()
    if (a or {}).get("name") == "TH-2026-0004":
        return lo_huy()
    if (a or {}).get("name") == "TH-2026-0008":
        return lo_htc()
    if (a or {}).get("name") == "TH-2026-0010":
        return lo_anh()
    p = S["phieu"]
    kiem, lap = tong(), da_lap()
    chot = bool(p and p["da_chot"])
    return {
        "lo": LO,
        # Lô mới: bên vận chuyển không gõ mã hàng — mail dán nguyên văn nằm ở lo.chi_tiet_hang.
        "khai": [], "co_khai": False, "tong_khai": 0,
        "files": [{"name": "F1", "file_name": "phieu-xuat-tra.pdf", "ext": "pdf", "is_image": False,
                   "url": "/api/method/ketoan.api.thu_hoi.xem_dinh_kem?file=F1"},
                  {"name": "F2", "file_name": "ds-hang.xlsx", "ext": "xlsx", "is_image": False,
                   "url": "/api/method/ketoan.api.thu_hoi.xem_dinh_kem?file=F2"}],
        "phieu": phieu_dict(), "hoa_don": S["hd"], "chang": chang(), "chang_list": CHANG, "lech": {},
        "con_can": {"BDX": kiem - lap} if kiem - lap > 0 else {},
        "so_sanh": [{"item_code": "BDX", "item_name": TEN, "stock_uom": "Hộp", "khai": 0,
                     "kiem": kiem, "da_lap": lap}] if p else [],
        "flags": {"bat_dau": not p, "sua": bool(p and not chot),
                  "chot": bool(p and not chot and p["items"]),
                  "mo_lai": chot and not any(h["docstatus"] == 1 for h in S["hd"]),
                  "lap_hd": chot and kiem - lap > 0, "cap_nhat": False,
                  "xoa": bool(p and not chot and not S["hd"]), "ket_luan": False},
        "is_chief": False,
    }


def _quy(a):
    ct = json.loads(a["chi_tiet"]) if a.get("chi_tiet") else []
    if not ct:
        return float(a.get("qty") or 0), ct
    he = {u["uom"]: u["he_so"] for u in UOMS}
    return sum(c["sl"] * he.get(c["uom"], 1) for c in ct), ct


def list_thu_hoi(a):
    rows = [dict(LO, chang=chang(), tuoi=12, kiem_sl=tong(),
                 kiem_so_ma=len(S["phieu"]["items"]) if S["phieu"] else 0,
                 so_hd=len(S["hd"]), so_hd_ghi_so=0, tien_hd=0),
            dict(LO, name="TH-2026-0003", trang_thai="Tạo yêu cầu", chang="Tạo yêu cầu",
                 ten_diem="GO! Thăng Long", customer_name="Central Retail", tuoi=3, so_hd=0),
            dict(LO, name="TH-2026-0004", chang="Đã hủy", ten_diem="Co.opMart Thắng Lợi", tuoi=None, so_hd=0, **HUY),
            dict(LO_HTC, chang="Đã kiểm hàng", tuoi=0, so_hd=0),
            dict(LO_ANH, chang=lo_anh()["chang"], tuoi=2, so_hd=len(A["hd"]), so_anh=len(A["anh"]),
                 cho_nhap=not A["phieu"]["da_chot"] and bool(A["anh"]))]
    f = [r for r in rows if a.get("chang") == "tat_ca"
         or (r.get("cho_nhap") if a.get("chang") == "cho_nhap" else
             r["chang"] not in ("Xong", "Đã hủy") if a.get("chang") == "dang_mo" else r["chang"] == a.get("chang"))]
    counts = {}
    for r in rows:
        counts[r["chang"]] = counts.get(r["chang"], 0) + 1
    return {"rows": f, "total": len(f), "counts": counts, "cho_nhap": sum(1 for r in rows if r.get("cho_nhap")),
            "chang_list": CHANG, "vanchuyen": True, "has_more": False}


def bat_dau_kiem(a):
    if (a or {}).get("name") == "TH-2026-0008":
        S["htc"] = S.get("htc") or {"name": "TH-2026-0008", "da_chot": 0, "items": [], "ghi_chu": "", "theo_phieu": 1}
        return lo_htc()
    S["phieu"] = S["phieu"] or {"name": LO["name"], "da_chot": 0, "items": [], "ghi_chu": ""}
    return get_th()


def boot_kiem(a):
    if (a or {}).get("name") == "TH-2026-0010":  # lô ảnh phiếu: ngồi máy nhập theo ảnh
        return {"lo": LO_ANH, "phieu": lo_anh()["phieu"], "anh_phieu": A["anh"],
                "danh_muc": [{"item": "BDX-300", "ten": "Bánh đậu xanh 300g", "dvt": "Hộp", "uoms": [{"uom": "Hộp", "he_so": 1}]},
                             {"item": "BDX", "ten": TEN, "dvt": "Hộp", "uoms": UOMS}],
                "ma_quet": {}, "goi_y": ["BDX"], "files": [], "nhom_kiem": ["Hàng Tết", "Hàng truyền thống"],
                "thieu_nhom": [], "hom_nay": "2026-10-22"}
    if (a or {}).get("name") == "TH-2026-0008":  # phiếu THEO PHIẾU: server gửi mail + biên bản để chép
        return {"lo": LO_HTC, "phieu": dict(S["htc"], tong_sl=0, so_ma=0),
                "danh_muc": [{"item": "BDX", "ten": TEN, "dvt": "Hộp", "uoms": UOMS}], "ma_quet": {}, "goi_y": [],
                "files": [FILE_HTC], "nhom_kiem": ["Hàng Tết", "Hàng truyền thống"], "thieu_nhom": [],
                "hom_nay": "2026-10-18"}
    # Server thật bỏ mail dán (chi_tiet_hang, có số khai 48) khỏi lô ở đây — thu_hoi_check
    # canh. Bản giả CỐ Ý để lại: có số trong tay thì màn kiểm hàng cũng không được vẽ ra.
    return {
        "lo": LO, "phieu": phieu_dict(),
        # BDX-300 đứng TRƯỚC trong danh mục; BDX là mã hay trả -> khi tìm phải nổi lên đầu.
        "danh_muc": [{"item": "BDX-300", "ten": "Bánh đậu xanh 300g", "dvt": "Hộp", "uoms": [{"uom": "Hộp", "he_so": 1}]},
                     {"item": "BDX", "ten": TEN, "dvt": "Hộp", "uoms": UOMS}],
        "ma_quet": {"8936000000017": {"item": "BDX", "uom": "Thùng"},
                    "8936000000024": {"item": "BDX", "uom": None}, "BDX": {"item": "BDX", "uom": None}},
        "goi_y": ["BDX"], "hom_nay": "2026-10-17",
        "nhom_kiem": ["Hàng truyền thống"] if S.get("thieu") else ["Hàng Tết", "Hàng truyền thống"],
        "thieu_nhom": ["Hàng Tết"] if S.get("thieu") else [],
    }


def them_dong(a):
    q, ct = _quy(a)
    if a.get("name") == "TH-2026-0010":
        A["phieu"]["items"].append({"name": "a%d" % (len(A["phieu"]["items"]) + 1), "item_code": a["item_code"],
                                    "item_name": TEN, "qty": q, "stock_uom": "Hộp", "chi_tiet": ct, "mo_ta_dvt": "",
                                    "nguoi_ghi": "Kế toán MT"})
        return lo_anh()["phieu"]
    r = next((x for x in S["phieu"]["items"] if x["item_code"] == a["item_code"]), None)
    if r:
        r["qty"] += q
        r["mo_ta_dvt"] = "gộp"
    else:
        S["phieu"]["items"].append({"name": "row%d" % (len(S["phieu"]["items"]) + 1), "item_code": a["item_code"],
                                    "item_name": TEN, "qty": q, "stock_uom": "Hộp", "chi_tiet": ct,
                                    "mo_ta_dvt": "", "nguoi_ghi": "Kế toán MT"})
    return phieu_dict()


def sua_dong(a):
    r = next(x for x in S["phieu"]["items"] if x["name"] == a["row"])
    r["qty"], r["chi_tiet"] = _quy(a)
    return phieu_dict()


def xoa_dong(a):
    S["phieu"]["items"] = [x for x in S["phieu"]["items"] if x["name"] != a["row"]]
    return phieu_dict()


def chot(a):
    if (a or {}).get("name") == "TH-2026-0010":
        A["phieu"].update(da_chot=1, chot_luc="2026-10-22 10:00:00", chot_boi="Kế toán MT")
        return lo_anh()
    S["phieu"].update(da_chot=1, chot_luc="2026-10-17 10:00:00", chot_boi="Kế toán MT")
    return get_th()


def _uv_rows(t):
    """Mọi hóa đơn đã ghi sổ của khách COOP: 3 tờ giao đúng điểm của lô, 1 tờ giao điểm khác."""
    base = {"customer": LO["customer"], "customer_name": LO["customer_name"]}
    tai = {"shipping_address_name": LO["shipping_address_name"], "ten_diem": LO["ten_diem"],
           "address_title": "Co.opMart HĐ", "address_line1": "1 Quang Trung", "city": "Hà Nội", "cung_diem": 1}
    mo = {"lap_duoc": True, "nhan": {"BDX": t}, "phu": t, "uoc_tien": t * 10000, "dong_khong_noi": 1,
          "ly_do_khoa": None}
    khoa = {"lap_duoc": False, "nhan": {}, "phu": 0, "uoc_tien": 0, "dong_khong_noi": 0}
    # Mới nhất trước (như ORDER BY posting_date DESC của server).
    return [
        dict(base, **mo, name="HD-0950", posting_date="2026-09-10", grand_total=3600000,
             outstanding_amount=0, po="PO-K", so_hddt="0001300", da_tra=0, cung_diem=0,
             shipping_address_name="ADDR-TX", ten_diem="Co.opMart Thanh Xuân", address_title="Co.opMart TX",
             address_line1="9 Nguyễn Trãi", city="Hà Nội"),
        dict(base, **tai, **mo, name="HD-0900", posting_date="2026-09-01", grand_total=4800000,
             outstanding_amount=1200000, po="PO-1", so_hddt="0001234", da_tra=0),
        dict(base, **tai, **khoa, name="HD-0850", posting_date="2026-08-20", grand_total=2400000,
             outstanding_amount=0, po="PO-0", so_hddt="0001100", da_tra=2400000,
             ly_do_khoa="Các mã cần trả trên tờ này đã trả hết"),
        dict(base, **tai, **khoa, name="HD-0801", posting_date="2026-08-02", grand_total=990000,
             outstanding_amount=0, po=None, so_hddt=None, da_tra=0,
             ly_do_khoa="Tờ này không có mã nào đang cần trả"),
    ]


UV_TRANG = 2  # server thật 50 tờ một trang; bản giả 2 tờ để thử "Xem tiếp"


def ung_vien(a):
    """Như server: đúng khách; đúng điểm giao trừ khi moi_diem; tìm theo số HĐ / PO / HĐĐT; phân trang."""
    if (a.get("tim") or "") == "08":
        time.sleep(1.2)  # lượt tìm "08" về MUỘN hơn lượt gõ sau nó
    t = tong()
    moi = bool(int(a.get("moi_diem") or 0))
    q = (a.get("tim") or "").strip().lower()
    page = max(1, int(a.get("page") or 1))
    ds = [r for r in _uv_rows(t) if moi or r["cung_diem"]]
    if q:
        ds = [r for r in ds if any(q in (r[k] or "").lower() for k in ("name", "po", "so_hddt"))]
    rows = ds[(page - 1) * UV_TRANG:page * UV_TRANG]
    return {"con_can": {"BDX": t}, "rows": rows, "total": len(ds), "page": page,
            "has_more": (page - 1) * UV_TRANG + len(rows) < len(ds), "moi_diem": moi,
            "khach": {"customer": LO["customer"], "customer_name": LO["customer_name"]},
            "diem": {"name": LO["shipping_address_name"], "ten": LO["ten_diem"]}}


def tao_hoa_don_tra(a):
    if not a.get("sales_invoice"):  # KHÔNG theo hóa đơn gốc: một tờ, mỗi mã một dòng ĐVT kho
        t = tong_a()
        A["hd"].append({"name": "RET-0002", "docstatus": 0, "posting_date": "2026-10-22", "return_against": None,
                        "tu_do": True, "tien": t * 10000, "misa_no": "", "route": "/desk/sales-invoice/RET-0002",
                        "items": [{"item_code": "BDX", "item_name": TEN, "qty": t, "uom": "Hộp", "stock_qty": t,
                                   "noi": False}]})
        return {"name": "RET-0002", "route": "/desk/sales-invoice/RET-0002", "so_dong": 1, "tu_do": True,
                "gia_ban_gan_nhat": 1, "thieu_gia": [], "tk_5213": "5213 - HGC", "thu_hoi": lo_anh()}
    t = tong()
    S["hd"].append({
        "name": "RET-0001", "docstatus": 0, "posting_date": "2026-10-17", "return_against": a["sales_invoice"],
        "tien": t * 10000, "misa_no": "", "route": "/desk/sales-invoice/RET-0001",
        "items": [{"item_code": "BDX", "item_name": TEN, "qty": 2, "uom": "Thùng", "stock_qty": 48, "noi": True},
                  {"item_code": "BDX", "item_name": TEN, "qty": t - 48, "uom": "Hộp", "stock_qty": t - 48, "noi": False}]})
    return {"name": "RET-0001", "route": "/desk/sales-invoice/RET-0001", "so_dong": 2, "dong_khong_noi": 1,
            "tk_5213": "5213 - HGC", "thu_hoi": get_th()}


MOCK = {
    "ketoan.api.thu_hoi.list_thu_hoi": list_thu_hoi,
    "ketoan.api.thu_hoi.get_thu_hoi": get_th,
    "ketoan.api.thu_hoi.bat_dau_kiem": bat_dau_kiem,
    "ketoan.api.thu_hoi.boot_kiem": boot_kiem,
    "ketoan.api.thu_hoi.them_dong": them_dong,
    "ketoan.api.thu_hoi.sua_dong": sua_dong,
    "ketoan.api.thu_hoi.xoa_dong": xoa_dong,
    "ketoan.api.thu_hoi.chot": chot,
    "ketoan.api.thu_hoi.ung_vien_hoa_don": ung_vien,
    "ketoan.api.thu_hoi.tao_hoa_don_tra": tao_hoa_don_tra,
    "ketoan.api.thu_hoi.luu_ghi_chu": lambda _a: phieu_dict(),
    "ketoan.api.thu_hoi.them_anh_phieu": them_anh,
    "ketoan.api.thu_hoi.xoa_anh_phieu": xoa_anh,
}
CTYPE = {".js": "text/javascript", ".css": "text/css"}


def make_handler(page):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def _send(self, code, body, ctype):
            b = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            self._route()

        def do_POST(self):
            self._route()

        def _route(self):
            url = self.path.split("?")[0]
            if url == "/":
                return self._send(200, page, "text/html; charset=utf-8")
            if url == "/api/method/ketoan.api.thu_hoi.xem_dinh_kem":
                return self._send(200, ANH_IMG, "image/png")
            if url.startswith("/api/method/"):
                n = int(self.headers.get("content-length") or 0)
                try:
                    args = json.loads(self.rfile.read(n) or b"{}") if n else {}
                except ValueError:
                    args = {}
                m = url[len("/api/method/"):]
                S["log"].append((m, args))
                h = MOCK.get(m)
                if not h:
                    return self._send(404, json.dumps({"exception": "no mock " + m}), "application/json")
                try:
                    return self._send(200, json.dumps({"message": h(args)}, ensure_ascii=False), "application/json")
                except Exception as e:  # noqa: BLE001 — lỗi mock thành lỗi API, để màn hình hiện ra
                    return self._send(417, json.dumps({"exception": "x: %s" % e}), "application/json")
            if url.startswith(BASE + "/"):
                f = os.path.normpath(os.path.join(PUB, url[len(BASE) + 1:]))
                if not f.startswith(PUB + os.sep) or not os.path.isfile(f):
                    return self._send(404, "404", "text/plain")
                with open(f, "rb") as fh:
                    return self._send(200, fh.read(), CTYPE.get(os.path.splitext(f)[1], "text/plain"))
            return self._send(404, "404", "text/plain")

    return Handler


# ═══════════════════════════════════════════════════════════════════════════
# Kịch bản — người kiểm hàng cầm điện thoại, rồi kế toán ngồi máy tính
# ═══════════════════════════════════════════════════════════════════════════

# Phần tử hiện nào của khung ứng viên thò ra quá mép phải của thẻ chứa nó (px; ≤ 0 là gọn).
# Phần tử nằm trong khung cuộn (.kt-table-wrap) thì đo chính khung cuộn, không đo bảng bên trong.
TRAN_JS = """(() => { const b = document.querySelector('#th-uv'), r = b.closest('.kt-card').getBoundingClientRect();
  let x = 0; b.querySelectorAll('*').forEach((e) => {
    if (e.offsetParent === null || e.parentElement.closest('.kt-table-wrap')) return;
    x = Math.max(x, e.getBoundingClientRect().right - r.right); });
  return x; })()"""


def run(pw, exe, root, ok, bad, shots=None):
    """Ghi THẲNG vào `ok` / `bad` của người gọi: dừng giữa chừng thì mục đã đỏ vẫn còn."""
    errs = []

    def expect(label, cond, detail=""):
        (ok if cond else bad).append(label + (f"  ({detail})" if detail else ""))

    def calls(m):
        return [a for (x, a) in S["log"] if x == m]

    def watch(pg):
        def on_console(msg):
            src = (msg.location or {}).get("url", "")
            if msg.type == "error" and not src.endswith("/favicon.ico"):
                errs.append(f"console: {msg.text} @ {src}")

        def on_response(r):
            if r.status >= 400 and not r.url.endswith("/favicon.ico"):
                errs.append(f"HTTP {r.status} {r.url}")

        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", on_console)
        pg.on("response", on_response)
        pg.on("dialog", lambda d: d.accept())
        pg.set_default_timeout(5000)  # thiếu phần tử thì đỏ sau 5 giây, không treo 30 giây

    browser = pw.chromium.launch(executable_path=exe)
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    p = ctx.new_page()
    watch(p)
    p.goto(root + "/#/thu-hoi")
    p.wait_for_timeout(800)

    # 1. Danh sách
    expect("nav có tab Thu hồi", "Thu hồi" in p.text_content(".kt-nav"))
    expect("list: pill Đang mở + 7 chặng + Đã hủy + Tất cả (chưa lô nào chờ nhập số -> không pill đó)",
           len(p.query_selector_all(".kt-th-pill")) == 10 and p.query_selector('.kt-th-pill[data-f="cho_nhap"]') is None)
    pills = p.text_content("#th-pills")
    expect("list: 'Đang mở' KHÔNG đếm lô hủy; 'Đã hủy' 1; 'Tất cả' đếm đủ",
           "Đang mở 4" in pills and "Đã hủy 1" in pills and "Tất cả 5" in pills, pills)
    htc = p.query_selector('.kt-th-card[href="#/thu-hoi/TH-2026-0008"]')
    expect("list: lô HỦY TẠI CHỖ nằm 'Đã kiểm hàng' + nhãn 'Hủy tại chỗ' + 3 nấc giữa vẽ BỎ QUA",
           htc is not None and "Đã kiểm hàng" in htc.text_content() and "Hủy tại chỗ" in htc.text_content()
           and len(htc.query_selector_all(".kt-th-step.is-skip")) == 3)
    expect("list 'Đang mở' không hiện lô hủy", "TH-2026-0004" not in p.text_content(".kt-th-cards"))
    p.click('.kt-th-pill[data-f="Đã hủy"]')
    p.wait_for_timeout(300)
    the = p.text_content(".kt-th-cards")
    expect("pill 'Đã hủy': thẻ lô ghi 🚫 + lý do + huy hiệu đỏ",
           "Siêu thị rút yêu cầu trả hàng" in the and p.query_selector(".kt-th-card .kt-badge--red") is not None, the[:120])
    p.click(".kt-th-card")
    p.wait_for_timeout(600)
    m = p.text_content("main")
    expect("lô hủy: khung 'đã HỦY' + ai + lý do, không nút 'Bắt đầu kiểm hàng'",
           "Bên vận chuyển đã HỦY yêu cầu này" in m and "Điều hành" in m and "Siêu thị rút yêu cầu trả hàng" in m
           and p.query_selector("#th-batdau") is None and "không kiểm hàng" in m)
    if shots:
        p.screenshot(path=os.path.join(shots, "kt_lo_huy.png"), full_page=True)
    p.evaluate("location.hash = '#/thu-hoi'")
    p.wait_for_timeout(600)
    expect("list mobile: hiện thẻ, ẩn bảng", p.is_visible(".kt-th-cards") and not p.is_visible(".kt-th-desk"))
    expect("list mobile: thẻ lô ghi đơn vị thu hồi + mã vận đơn",
           "🚚 Viettel Post · VĐ VTP123" in p.text_content(".kt-th-cards"))
    p.click('.kt-th-pill[data-f="Đã nhận hàng"]')
    p.wait_for_timeout(300)
    expect("list: lọc 'Đã nhận hàng' còn 1 thẻ", len(p.query_selector_all(".kt-th-card")) == 1)
    p.click(".kt-th-card")
    p.wait_for_timeout(600)

    # 2. Lô → bắt đầu kiểm
    expect("lô: file đính kèm mở qua proxy có guard của ketoan",
           len(p.query_selector_all('.kt-th-file[href*="ketoan.api.thu_hoi.xem_dinh_kem"]')) == 2)
    pdf = p.query_selector('.kt-th-file[href*="file=F1"]')
    xl = p.query_selector('.kt-th-file[href*="file=F2"]')
    expect("lô: PDF mở tab mới; Excel TẢI VỀ + biểu tượng Excel",
           pdf is not None and pdf.get_attribute("target") == "_blank"
           and xl is not None and xl.get_attribute("download") == "ds-hang.xlsx"
           and xl.query_selector(".fa-file-excel") is not None)
    ho_so = p.text_content(".kt-th-kv")
    expect("lô: hồ sơ ghi đơn vị thu hồi · vận đơn · ngày thu, không còn 'Xe'",
           "Viettel Post · VĐ VTP123 · thu 16/10/2026" in ho_so and "chưa giao" not in ho_so, ho_so[:160])
    if shots:
        p.screenshot(path=os.path.join(shots, "kt_lo_mobile.png"), full_page=True)
    mail = p.query_selector("#th-mail")  # tra trước: text_content() trên phần tử thiếu là đứng chờ rồi nổ
    expect("lô: mail siêu thị dán NGUYÊN VĂN (giữ tab)", mail is not None and mail.text_content() == CHI_TIET,
           repr(mail.text_content() if mail else None))
    expect("lô: có nút Bắt đầu kiểm hàng", p.query_selector("#th-batdau") is not None)
    p.click("#th-batdau")
    p.wait_for_timeout(900)
    expect("bắt đầu kiểm -> sang #/kiem-hang", p.evaluate("location.hash").startswith("#/kiem-hang/TH-2026-0007"))

    # 3. Kiểm hàng: gợi ý -> bàn số tab Thùng/Hộp -> lưu
    expect("kiểm hàng: không hiện số siêu thị khai (đếm mù)", str(KHAI) not in p.text_content("main"))
    expect("ô tìm trống: KHÔNG còn khối 'Hay trả' (không chip nào)",
           not p.query_selector_all(".kt-th-kh-chip") and "hay trả" not in p.text_content("main").lower())
    p.fill("#kh-tim", "dau xanh")
    p.wait_for_timeout(200)
    chips = [(c.get_attribute("data-item"), c.text_content()) for c in p.query_selector_all(".kt-th-kh-chip")]
    expect("gõ tìm: mã HAY TRẢ nổi lên ĐẦU kết quả (có nhãn), mã thường theo sau, không nhãn",
           [c[0] for c in chips] == ["BDX", "BDX-300"] and "hay trả" in chips[0][1] and "hay trả" not in chips[1][1],
           str(chips))
    expect("kết quả: dòng có đủ mã + ĐVT (tên giống nhau vẫn phân biệt được)", "BDX · Hộp" in chips[0][1], chips[0][1])
    rong = p.evaluate("""(() => { const w = document.querySelector('#kh-chon').getBoundingClientRect().width;
      return [...document.querySelectorAll('.kt-th-kh-chip')].every((c) => Math.abs(c.getBoundingClientRect().width - w) < 2); })()""")
    expect("kết quả là danh sách DỌC — mỗi mã một dòng hết bề ngang", rong)
    if shots:
        p.screenshot(path=os.path.join(shots, "kt_kiem_tim.png"), full_page=True)
    p2 = ctx.new_page()
    watch(p2)
    S["thieu"] = True
    p2.goto(root + "/#/kiem-hang/TH-2026-0007")
    p2.wait_for_timeout(700)
    canh = p2.text_content("main")
    expect("thiếu nhóm 'Hàng Tết' trên site: báo ĐÚNG nhóm thiếu + danh sách đang có gì",
           "“Hàng Tết”" in canh and "danh sách tìm chỉ có Hàng truyền thống" in canh)
    S["thieu"] = False
    p2.close()
    p.click('.kt-th-kh-chip[data-item="BDX"]')
    p.wait_for_timeout(200)
    expect("bàn số: có tab Thùng / Hộp", len(p.query_selector_all(".kt-th-np-tab")) == 2)
    p.click('.kt-th-np-tab[data-tab="0"]')
    p.click('.kt-th-np-key:text-is("2")')
    p.click('.kt-th-np-tab[data-tab="1"]')
    p.click('.kt-th-np-key:text-is("3")')
    ok_txt = p.text_content('[data-ok="chinh"]')
    expect("bàn số: 2 thùng + 3 hộp = 51 HỘP hiện trên nút", "51" in ok_txt, ok_txt)
    p.click('[data-ok="chinh"]')
    p.wait_for_timeout(500)
    th = calls("ketoan.api.thu_hoi.them_dong")
    ct = json.loads((th[0] if th else {}).get("chi_tiet") or "[]")
    expect("lưu: them_dong gửi chi tiết từng ĐVT (server tự nhân hệ số)", len(th) == 1 and len(ct) == 2,
           json.dumps(th[0] if th else {}, ensure_ascii=False))
    expect("dòng mới hiện 51", "51" in p.text_content("#kh-dong"))

    # 4. Quét (headless không có camera) -> gõ mã tay -> mã THÙNG mở tab Thùng -> +1 thùng
    p.click("#kh-quet")
    p.wait_for_timeout(400)
    expect("quét: máy không camera vẫn còn đường gõ mã tay", "Gõ mã bằng tay" in p.text_content(".kt-th-sheet"))
    p.click(".kt-th-quet-tay")
    p.fill(".kt-th-quet-input", "8936000000017")
    p.press(".kt-th-quet-input", "Enter")
    p.wait_for_timeout(300)
    tab_on = p.text_content(".kt-th-np-tab.is-on")
    expect("mã vạch THÙNG -> bàn số mở sẵn tab Thùng", tab_on.startswith("Thùng"), tab_on)
    expect("mã đã có dòng -> nhãn 'Cộng thêm'", "Cộng thêm" in p.text_content(".kt-th-sheet-kicker"))
    p.click('.kt-th-np-key:text-is("1")')
    p.click('[data-ok="chinh"]')
    p.wait_for_timeout(500)
    expect("cộng thêm 1 thùng -> 75", "75" in p.text_content("#kh-dong"))
    toast_txt = p.text_content(".kt-toast")
    expect("toast nói đúng cách đếm + ĐVT kho: '+1 Thùng = 24 Hộp'", "+1 Thùng = 24 Hộp" in toast_txt, toast_txt)
    pe = p.evaluate("getComputedStyle(document.querySelector('.kt-toast')).pointerEvents")
    expect("toast đang hiện không bắt chạm (pointer-events: none)", pe == "none", pe)

    # 5. Sửa tổng -> 50 hộp, NGAY khi toast còn hiện trên nút LƯU
    p.click("[data-sua]")
    p.wait_for_timeout(200)
    p.click('.kt-th-np-tab[data-tab="0"]')
    p.click('.kt-th-np-key:text-is("C")')
    p.click('.kt-th-np-tab[data-tab="1"]')
    p.click('.kt-th-np-key:text-is("5")')
    p.click('.kt-th-np-key:text-is("0")')
    p.click('[data-ok="chinh"]', timeout=5000)
    p.wait_for_timeout(400)
    expect("sửa tổng về 50 hộp", "50" in p.text_content("#kh-dong") and len(calls("ketoan.api.thu_hoi.sua_dong")) == 1)

    # 6. Chốt -> về lô -> lập hóa đơn trả về
    p.click("#kh-chot")
    p.wait_for_timeout(900)
    expect("chốt -> về màn lô", p.evaluate("location.hash").startswith("#/thu-hoi/TH-2026-0007"))
    sau_chot = p.text_content("main")
    expect("sau chốt: lô mới (không bảng khai) -> bảng 'Đã kiểm · đã lập hóa đơn', không cột 'Siêu thị khai'",
           "Đã kiểm · đã lập hóa đơn" in sau_chot and "Siêu thị khai" not in sau_chot)
    mau = p.evaluate("getComputedStyle(document.querySelector('a.kt-btn--primary[href^=\"#/kiem-hang/\"]')).color")
    expect("nút 'Xem phiếu kiểm' (thẻ <a>) giữ chữ trắng trên nền gradient", mau == "rgb(255, 255, 255)", mau)
    p.click("#th-ungvien")
    p.wait_for_timeout(500)
    uv_head = p.text_content(".kt-th-uv-head")
    expect("ứng viên: tiêu đề nói đúng khách + điểm giao của lô + tổng số hóa đơn",
           "Saigon Co.op" in uv_head and "Co.opMart Hà Đông" in uv_head and "3 hóa đơn" in uv_head, uv_head)
    a0 = calls("ketoan.api.thu_hoi.ung_vien_hoa_don")[-1]
    expect("ứng viên: mặc định CHỈ điểm giao của lô (moi_diem = 0, trang 1)",
           int(a0.get("moi_diem", -1)) == 0 and a0.get("page") == 1, str(a0))
    expect("điện thoại: hóa đơn gốc hiện dạng THẺ, bảng ẩn",
           p.is_visible("#th-uv .kt-th-card") and not p.is_visible("#th-uv table"))
    tran = p.evaluate(TRAN_JS)
    expect("điện thoại: khung hóa đơn gốc nằm gọn trong thẻ (không tràn mép phải)", tran <= 0.5, "%.1fpx" % tran)
    d900 = p.query_selector('#th-uv .kt-th-mob .kt-th-card:has([data-tao="HD-0900"])')
    t900 = d900.text_content() if d900 else ""
    expect("ứng viên: dòng đủ thông tin — HĐĐT, PO, khách, điểm, địa chỉ, số tiền, còn nợ",
           all(x in t900 for x in ("HĐĐT 0001234", "PO PO-1", "Saigon Co.op", "Co.opMart Hà Đông",
                                   "1 Quang Trung, Hà Nội", "4.800.000 ₫", "còn nợ 1.200.000 ₫")), t900)
    k850 = p.query_selector('#th-uv .kt-th-mob [data-tao="HD-0850"]')
    d850 = p.query_selector('#th-uv .kt-th-mob .kt-th-card:has([data-tao="HD-0850"])')
    expect("ứng viên: tờ đã trả hết vẫn LIỆT KÊ — nút khóa + lý do + số đã trả về",
           k850 is not None and k850.is_disabled() and "đã trả hết" in d850.text_content()
           and "đã trả về 2.400.000 ₫" in d850.text_content())
    expect("ứng viên: trang 1 có nút Xem tiếp (2/3)", "2/3" in (p.text_content("#uv-tiep") or ""))
    p.click("#uv-tiep")
    p.wait_for_timeout(500)
    a1 = calls("ketoan.api.thu_hoi.ung_vien_hoa_don")[-1]
    expect("Xem tiếp: gọi trang 2 rồi NỐI thêm (3 dòng, hết nút)",
           a1.get("page") == 2 and len(p.query_selector_all("#th-uv .kt-th-mob [data-tao]")) == 3
           and p.query_selector("#uv-tiep") is None, str(a1))
    p.click("#uv-diem")
    p.wait_for_timeout(500)
    a2 = calls("ketoan.api.thu_hoi.ung_vien_hoa_don")[-1]
    tuv = p.text_content("#th-uv")
    expect("'Xem mọi điểm của khách': gửi moi_diem = 1, hiện cả điểm khác + nhãn 'điểm của lô'",
           int(a2.get("moi_diem", 0)) == 1 and a2.get("page") == 1 and "mọi điểm giao" in tuv
           and "Co.opMart Thanh Xuân" in tuv and "điểm của lô" in tuv, str(a2))
    p.click("#uv-diem")
    p.wait_for_timeout(500)
    p.fill("#uv-tim", "08")
    p.wait_for_timeout(450)  # lượt "08" đã gửi, đang chờ server (chậm)
    p.fill("#uv-tim", "0900")
    p.wait_for_timeout(1600)  # lượt "0900" về trước, lượt "08" về sau
    expect("gõ tìm nhanh: kết quả cũ ('08') về muộn KHÔNG đè kết quả mới ('0900')",
           p.query_selector('#th-uv .kt-th-mob [data-tao="HD-0850"]') is None
           and p.query_selector('#th-uv .kt-th-mob [data-tao="HD-0900"]') is not None)
    a3 = calls("ketoan.api.thu_hoi.ung_vien_hoa_don")[-1]
    expect("tìm: gửi `tim` lên server (không lọc trong 1 trang đã tải), còn 1 dòng",
           a3.get("tim") == "0900" and int(a3.get("moi_diem", -1)) == 0
           and len(p.query_selector_all("#th-uv .kt-th-mob [data-tao]")) == 1, str(a3))
    expect("tìm: vẽ lại xong ô tìm vẫn giữ con trỏ (gõ tiếp được)",
           p.evaluate("document.activeElement && document.activeElement.id") == "uv-tim")
    if shots:
        p.screenshot(path=os.path.join(shots, "kt_ung_vien.png"), full_page=True)
    p.click('#th-uv .kt-th-mob [data-tao="HD-0900"]')
    p.wait_for_timeout(700)
    expect("lập HĐ trả về gọi tao_hoa_don_tra với đúng hóa đơn gốc",
           any(a.get("sales_invoice") == "HD-0900" for a in calls("ketoan.api.thu_hoi.tao_hoa_don_tra")))
    txt = p.text_content("main")
    expect("hiện RET-0001 nháp + deep link Desk",
           "RET-0001" in txt and p.query_selector('a[href="/desk/sales-invoice/RET-0001"]') is not None)
    expect("chặng sang 'Đã nhập chứng từ'", "Đã nhập chứng từ" in txt)
    expect("giải thích dòng không nối dòng gốc", "không nối dòng gốc" in txt)

    # 6b. Lô CŨ còn bảng hàng khai: vẫn so khai / kiểm như trước
    p.evaluate("location.hash = '#/thu-hoi/TH-2026-0005'")
    p.wait_for_timeout(600)
    cu = p.text_content("main")
    nhat = p.query_selector(".kt-th-sum-so--nhat")
    expect("lô cũ có bảng khai: vẫn hiện cột 'Siêu thị khai' + tổng khai 48 + lệch +2",
           "Siêu thị khai" in cu and nhat is not None and nhat.text_content() == "48" and "+2" in cu)

    # 6c. Lô HỦY TẠI CHỖ: không đếm — chép theo phiếu siêu thị rồi lập hóa đơn
    p3 = ctx.new_page()
    watch(p3)
    p3.goto(root + "/#/thu-hoi/TH-2026-0008")
    p3.wait_for_timeout(700)
    m3 = p3.text_content("main")
    nut = p3.query_selector("#th-batdau")
    expect("lô hủy tại chỗ: nói rõ không thu về, nhận đủ theo phiếu + nút 'Nhập hàng theo phiếu hủy'",
           "không thu về" in m3 and "Nhận đủ theo phiếu" in m3 and nut is not None
           and "Nhập hàng theo phiếu hủy" in nut.text_content()
           and len(p3.query_selector_all(".kt-view-head .kt-th-step.is-skip")) == 3)
    p3.click("#th-batdau")
    p3.wait_for_timeout(900)
    bd = [x for x in calls("ketoan.api.thu_hoi.bat_dau_kiem") if x.get("name") == "TH-2026-0008"]
    k3 = p3.text_content("main")
    expect("bấm nhập theo phiếu: mở phiếu + sang màn nhập (kicker 'Nhập theo phiếu hủy')",
           bool(bd) and p3.evaluate("location.hash").startswith("#/kiem-hang/TH-2026-0008")
           and "Nhập theo phiếu hủy" in p3.text_content(".kt-th-kh-kicker"))
    expect("màn nhập theo phiếu THẤY mail dán + biên bản đính kèm để chép (không đếm mù)",
           "Biên bản hủy 18/10: BDX-170 hết date 3 hộp" in k3
           and p3.query_selector('a[href*="file=F9"][target="_blank"]') is not None)
    expect("nút chốt ghi 'Chốt theo phiếu', danh sách ghi 'Đã chép theo phiếu'",
           "Chốt theo phiếu" in (p3.text_content("#kh-chot") or "") and "Đã chép theo phiếu" in k3)
    if shots:
        p3.screenshot(path=os.path.join(shots, "kt_htc_nhap.png"), full_page=True)
    p3.close()

    # 6d. Lô có phiếu trả về: ghi số lên phiếu, CHỤP lại trên điện thoại — ngồi máy nhập sau
    p4 = ctx.new_page()
    watch(p4)
    p4.goto(root + "/#/kiem-hang/TH-2026-0010")
    p4.wait_for_timeout(700)
    the4 = p4.text_content(".kt-th-kh-anhcard") if p4.query_selector(".kt-th-kh-anhcard") else ""
    inp = p4.query_selector("#kh-anh-input")
    expect("kiểm hàng: thẻ 'Ảnh phiếu trả về' mời ghi số lên phiếu rồi chụp; nút mở CAMERA sau (capture)",
           "Ghi số đếm thẳng lên phiếu rồi chụp lại" in the4 and inp is not None
           and inp.get_attribute("capture") == "environment" and (inp.get_attribute("accept") or "").startswith("image/"),
           the4[:120])
    p4.set_input_files("#kh-anh-input", files=[{"name": "IMG_0042.png", "mimeType": "image/png",
                                                 "buffer": png(3000, 1500, (30, 120, 200))}])
    p4.wait_for_selector(".kt-th-kh-thumb img", timeout=10000)
    g = A["gui"][-1] if A["gui"] else {}
    expect("ảnh được NÉN trước khi gửi: PNG 3000×1500 thành JPEG, cạnh dài 2400px (chữ viết tay vẫn đọc được)",
           g.get("sig") == b"\xff\xd8\xff" and g.get("wh") == (2400, 1200),
           str({k: v for k, v in g.items() if k != "sig"}))
    expect("chụp xong: 1 ảnh nhỏ + nút thành 'Chụp thêm' + nhắc ngồi máy nhập",
           len(p4.query_selector_all(".kt-th-kh-thumb img")) == 1 and "Chụp thêm" in p4.text_content("#kh-chup")
           and "ngồi máy nhập số theo ảnh" in p4.text_content(".kt-th-kh-anhcard"))
    expect("điện thoại: KHÔNG chia hai cột / không khung ảnh lớn (chỉ máy tính)", not p4.is_visible("#kh-anh-xem"))
    p4.click("[data-xoaanh]")
    p4.wait_for_timeout(600)
    expect("xóa ảnh chụp nhầm: gọi xoa_anh_phieu đúng file, hết ảnh",
           any(x.get("file") == "FA1" and x.get("name") == "TH-2026-0010" for x in calls("ketoan.api.thu_hoi.xoa_anh_phieu"))
           and not p4.query_selector_all(".kt-th-kh-thumb"))
    p4.set_input_files("#kh-anh-input", files=[{"name": "IMG_0043.png", "mimeType": "image/png", "buffer": png(900, 1200)}])
    p4.wait_for_selector(".kt-th-kh-thumb img", timeout=10000)
    if shots:
        p4.screenshot(path=os.path.join(shots, "kt_anh_mobile.png"), full_page=True)
    p4.evaluate("location.hash = '#/thu-hoi'")
    p4.wait_for_timeout(700)
    pills4 = p4.text_content("#th-pills")
    the_a = p4.query_selector('.kt-th-card[href="#/thu-hoi/TH-2026-0010"]')
    expect("danh sách: pill '📷 Chờ nhập số 1' + nhãn trên thẻ lô đã chụp phiếu",
           "Chờ nhập số 1" in pills4 and the_a is not None and "Chờ nhập số" in the_a.text_content(), pills4)
    p4.click('.kt-th-pill[data-f="cho_nhap"]')
    p4.wait_for_timeout(400)
    expect("bấm pill 'Chờ nhập số': gửi chang=cho_nhap, chỉ còn lô đang chờ nhập",
           len(p4.query_selector_all(".kt-th-card")) == 1
           and calls("ketoan.api.thu_hoi.list_thu_hoi")[-1].get("chang") == "cho_nhap")
    p4.close()

    # Toast hết giờ phải ẩn THẬT (trước đây trượt xuống vẫn nằm cách đáy ~25px)
    p.wait_for_timeout(4000)
    vis = p.evaluate("getComputedStyle(document.querySelector('.kt-toast')).visibility")
    expect("toast hết giờ thì ẩn thật (visibility: hidden)", vis == "hidden", vis)

    # 7. Máy tính
    d = browser.new_page(viewport={"width": 1280, "height": 900})
    watch(d)
    d.goto(root + "/#/thu-hoi")
    d.wait_for_timeout(800)
    expect("desktop: bảng hiện, thẻ ẩn", d.is_visible(".kt-th-desk") and not d.is_visible(".kt-th-cards"))
    dong = d.text_content(".kt-th-desk tbody tr")
    expect("desktop: cột Vận chuyển ghi đơn vị thu hồi + mã vận đơn", "Viettel Post" in dong and "VĐ VTP123" in dong)
    sw = d.evaluate("(() => { const w = document.querySelector('.kt-th-desk'); return [w.scrollWidth, w.clientWidth]; })()")
    expect("desktop 1280: bảng không cuộn ngang", sw[0] <= sw[1], str(sw))
    if shots:
        d.screenshot(path=os.path.join(shots, "kt_list_desk.png"))
        d.evaluate("location.hash = '#/thu-hoi/TH-2026-0007'")
        d.wait_for_timeout(700)
        d.screenshot(path=os.path.join(shots, "kt_lo_desk.png"), full_page=True)
    # Ứng viên trên máy tính: bảng đủ cột, không cuộn ngang (lô cũ còn cần lập hóa đơn)
    d.evaluate("location.hash = '#/thu-hoi/TH-2026-0005'")
    d.wait_for_timeout(700)
    d.click("#th-ungvien")
    d.wait_for_timeout(500)
    expect("desktop: hóa đơn gốc hiện dạng BẢNG, thẻ ẩn",
           d.is_visible("#th-uv table") and not d.is_visible("#th-uv .kt-th-card"))
    r900 = d.text_content('#th-uv .kt-th-desk tr:has([data-tao="HD-0900"])') or ""
    expect("desktop: dòng bảng đủ HĐĐT · PO · khách · điểm · địa chỉ · số tiền · còn nợ",
           all(x in r900 for x in ("HĐĐT 0001234", "PO PO-1", "Saigon Co.op", "Co.opMart Hà Đông",
                                   "1 Quang Trung, Hà Nội", "4.800.000 ₫", "còn nợ 1.200.000 ₫")), r900)
    nk = d.query_selector('#th-uv .kt-th-desk [data-tao="HD-0850"]')
    expect("desktop: tờ đã trả hết — nút khóa", nk is not None and nk.is_disabled())
    uw = d.evaluate("(() => { const w = document.querySelector('#th-uv .kt-th-desk'); return [w.scrollWidth, w.clientWidth]; })()")
    expect("desktop 1280: bảng hóa đơn gốc không cuộn ngang", uw[0] <= uw[1], str(uw))
    if shots:
        d.screenshot(path=os.path.join(shots, "kt_ung_vien_desk.png"), full_page=True)
    tb = browser.new_page(viewport={"width": 720, "height": 900})
    watch(tb)
    tb.goto(root + "/#/thu-hoi/TH-2026-0005")
    tb.wait_for_timeout(800)
    tb.click("#th-ungvien")
    tb.wait_for_timeout(500)
    tran_tb = tb.evaluate(TRAN_JS)
    expect("máy tính bảng 720px: bảng hóa đơn gốc nằm gọn trong thẻ (cuộn trong khung nếu chật)",
           tb.is_visible("#th-uv table") and tran_tb <= 0.5, "%.1fpx" % tran_tb)
    if shots:
        tb.screenshot(path=os.path.join(shots, "kt_ung_vien_720.png"), full_page=True)

    # 7b. Ngồi MÁY TÍNH nhập theo ảnh: lô → màn nhập hai cột → xoay / phóng → gõ phím → chốt
    #     → hóa đơn trả về KHÔNG cần chọn hóa đơn gốc
    k = browser.new_page(viewport={"width": 1280, "height": 900})
    watch(k)
    k.goto(root + "/#/thu-hoi/TH-2026-0010")
    k.wait_for_timeout(800)
    mk = k.text_content("main")
    nut = k.query_selector('a.kt-btn--primary[href="#/kiem-hang/TH-2026-0010"]')
    expect("màn lô: '1 ảnh phiếu trả về — 📷 Chờ nhập số' + ảnh nhỏ + nút 'Nhập số theo ảnh phiếu'",
           "1 ảnh phiếu trả về" in mk and "Chờ nhập số" in mk and k.query_selector(".kt-th-anh-lo img") is not None
           and nut is not None and "Nhập số theo ảnh phiếu" in nut.text_content())
    if shots:
        k.screenshot(path=os.path.join(shots, "kt_anh_lo_desk.png"), full_page=True)
    nut.click()
    k.wait_for_timeout(900)
    box = k.evaluate("""(() => { const a = document.querySelector('#kh-anh-xem').getBoundingClientRect(),
      c = document.querySelector('#kh-cot').getBoundingClientRect(); return [a.left, a.right, a.width, c.left, c.width]; })()""")
    expect("máy tính: ảnh LỚN bên trái, ô nhập bên phải (hai cột); ảnh nhỏ trong cột nhập ẩn",
           k.is_visible("#kh-anh-xem img") and box[1] <= box[3] and box[2] > 500 and not k.is_visible(".kt-th-kh-thumbs"),
           str(box))
    kich = "(() => { const i = document.querySelector('#kh-anh-xem img'); return [i.naturalWidth, i.naturalHeight]; })()"
    wh0 = k.evaluate(kich)
    k.click("[data-xoay]")
    k.wait_for_timeout(400)
    wh1 = k.evaluate(kich)
    expect("Xoay 90°: ảnh 600×300 thành 300×600 (khung co theo chiều mới)", wh0 == [600, 300] and wh1 == [300, 600],
           f"{wh0} -> {wh1}")
    k.click("[data-phong]")
    k.wait_for_timeout(200)
    to = k.evaluate("""(() => { const f = document.querySelector('.kt-th-kh-anh-fig');
      return [f.classList.contains('is-to'), f.querySelector('img').getBoundingClientRect().width,
              f.querySelector('.kt-th-kh-anh-khung').clientWidth]; })()""")
    expect("Phóng: ảnh to hơn khung, cuộn trong khung", to[0] and to[1] > to[2] * 1.5, str(to))
    k.click("#kh-tim")
    k.keyboard.type("dau xanh")
    k.keyboard.press("Enter")
    k.wait_for_timeout(300)
    sheet = k.query_selector(".kt-th-sheet")
    expect("Enter ở ô tìm: mở bàn số cho mã ĐẦU kết quả (mã hay trả)",
           sheet is not None and TEN in (k.text_content(".kt-th-sheet-title") or ""))
    expect("Enter mở bàn số KHÔNG lan sang bàn số (không 'LƯU' số 0, không báo lỗi)",
           not (k.text_content(".kt-th-np-loi") or "").strip()
           and not [x for x in calls("ketoan.api.thu_hoi.them_dong") if x.get("name") == "TH-2026-0010"])
    k.keyboard.type("2")
    k.keyboard.press("ArrowRight")
    k.keyboard.type("3")
    ok_txt = k.text_content('[data-ok="chinh"]')
    expect("bàn phím: số + → đổi tab Thùng → Hộp: 2 thùng + 3 hộp = 51 HỘP trên nút", "51" in ok_txt, ok_txt)
    k.keyboard.press("Enter")
    k.wait_for_timeout(600)
    ta = [x for x in calls("ketoan.api.thu_hoi.them_dong") if x.get("name") == "TH-2026-0010"]
    ct = json.loads((ta[-1] if ta else {}).get("chi_tiet") or "[]")
    expect("Enter = LƯU: them_dong gửi chi tiết 2 Thùng + 3 Hộp",
           len(ta) == 1 and {(c["uom"], c["sl"]) for c in ct} == {("Thùng", 2), ("Hộp", 3)}, str(ta))
    expect("lưu xong: con trỏ VỀ ô tìm (gõ mã kế tiếp ngay), ô tìm trống",
           k.evaluate("document.activeElement && document.activeElement.id") == "kh-tim" and k.input_value("#kh-tim") == "")
    expect("lưu số KHÔNG vẽ lại ảnh: vẫn đang xoay, vẫn phóng to",
           k.evaluate(kich) == [300, 600] and k.evaluate("document.querySelector('.kt-th-kh-anh-fig').classList.contains('is-to')"))
    if shots:
        k.screenshot(path=os.path.join(shots, "kt_anh_nhap_desk.png"))
    k.click("#kh-chot")
    k.wait_for_timeout(900)
    expect("chốt -> về màn lô", k.evaluate("location.hash").startswith("#/thu-hoi/TH-2026-0010"))
    lap = k.query_selector("#th-lap")
    can_txt = k.text_content(".kt-th-can") if k.query_selector(".kt-th-can") else ""
    expect("hóa đơn trả về: nút CHÍNH 'Lập hóa đơn trả về' — không cần chọn hóa đơn gốc; theo hóa đơn gốc là tùy chọn",
           lap is not None and "Lập hóa đơn trả về" in lap.text_content() and "Không cần chọn hóa đơn gốc" in can_txt
           and "Hoặc trả theo hóa đơn gốc" in (k.text_content("#th-ungvien") or ""), can_txt[:160])
    lap.click()
    k.wait_for_timeout(700)
    tt = [x for x in calls("ketoan.api.thu_hoi.tao_hoa_don_tra") if x.get("name") == "TH-2026-0010"]
    t2 = k.text_content("main")
    expect("bấm: gọi tao_hoa_don_tra KHÔNG kèm hóa đơn gốc", len(tt) == 1 and "sales_invoice" not in tt[0], str(tt))
    expect("tờ mới: 'không theo hóa đơn gốc', KHÔNG nhãn 'không nối dòng gốc', nhắc soát giá; chặng 'Đã nhập chứng từ'",
           "RET-0002" in t2 and "không theo hóa đơn gốc" in t2 and "không nối dòng gốc" not in t2
           and "lần bán gần nhất" in t2 and "Đã nhập chứng từ" in t2
           and k.query_selector('a[href="/desk/sales-invoice/RET-0002"]') is not None)
    if shots:
        k.screenshot(path=os.path.join(shots, "kt_hd_tu_do.png"), full_page=True)
    k.close()

    expect("không lỗi trang / console / HTTP", not errs, " | ".join(errs))
    browser.close()


def main():
    shots = None
    if "--shots" in sys.argv:
        shots = sys.argv[sys.argv.index("--shots") + 1]
        os.makedirs(shots, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _bo_qua("chưa cài `playwright`")
    exe = chromium_path()
    if not exe:
        return _bo_qua("không tìm thấy Chromium ở /opt/pw-browsers")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(build_page()))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    root = "http://127.0.0.1:%d" % srv.server_address[1]
    ok, bad = [], []
    try:
        with sync_playwright() as pw:
            try:
                run(pw, exe, root, ok, bad, shots)
            except Exception as e:  # noqa: BLE001 — kẹt bước nào thì nói bước đó, không traceback trần
                bad.append(f"kịch bản dừng giữa chừng: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.shutdown()

    print("=" * 82)
    print("THU HỒI — MÀN HÌNH THẬT TRONG CHROMIUM (portal thật, server giả)")
    print("=" * 82)
    for x in ok:
        print("  ✅ " + x)
    for x in bad:
        print("  ❌ " + x)
    print("=" * 82)
    if bad:
        print(f"KẾT QUẢ: ĐỎ — {len(bad)} mục")
        return 1
    print(f"KẾT QUẢ: ĐẠT {len(ok)}/{len(ok)} — đếm mù, bàn số nhiều ĐVT, quét cộng thêm, "
          "toast không nuốt chạm, bảng/thẻ đúng cỡ màn, luồng tới hóa đơn trả về")
    return 0


if __name__ == "__main__":
    sys.exit(main())
