"""thu_hoi — THEO DÕI THU HỒI · KIỂM HÀNG VỀ · HÓA ĐƠN TRẢ VỀ (portal /ketoan#/thu-hoi).

════════════════════════════════════════════════════════════════════════════
MỘT LÔ, BẢY CHẶNG, HAI CHỦ
════════════════════════════════════════════════════════════════════════════

    vanchuyen  `Lo Thu Hoi`         Tạo yêu cầu → Đã lấy hàng → Đã nhận hàng
    ketoan     `Kiem Hang Thu Hoi`  Đang kiểm → Đã kiểm hàng → Đã nhập chứng từ → Xong

Chặng TỔNG = `COALESCE(phiếu kiểm, lô)`. Module này ĐỌC SỐNG + MỀM bảng của vanchuyen
(`table_exists` trước khi đọc) và KHÔNG BAO GIỜ ghi vào đó — cùng luật `mt_hoan` với
`Su Co Van Chuyen`. Ghi chéo bằng `db.set_value` là bỏ qua controller bên kia, mà
controller bên kia chính là chỗ khóa khách / điểm khi kế toán đã mở phiếu kiểm.

Kế toán chỉ tiếp nối khi lô đã "Đã nhận hàng": đếm hàng chưa về kho là đếm trên giấy.
Lô bên vận chuyển HỦY yêu cầu ("Đã hủy", kèm lý do) thì chỉ xem — không mở phiếu kiểm;
`bat_dau_kiem` đọc lô bằng KHÓA để không chạy đua với nút "Hủy yêu cầu" bên kia.
Lô HỦY TẠI CHỖ (siêu thị hủy, không thu) đi tắt tới "Đã kiểm hàng" (nhận đủ theo phiếu):
phiếu kiểm của nó là phiếu `theo_phieu` — kế toán CHÉP mã + số theo phiếu siêu thị (không
đếm, nên màn nhập được thấy mail / biên bản), chốt rồi lập hóa đơn trả về như lô thường.

════════════════════════════════════════════════════════════════════════════
KIỂM HÀNG — dựng theo màn Ghi hộp của app sx
════════════════════════════════════════════════════════════════════════════

Quét / tìm mã → bàn số (tab Thùng / Hộp) → lưu NGAY từng lần. MỘT mã MỘT dòng: quét
lại mã đã có là CỘNG thêm vào dòng đó. Số lưu theo ĐVT kho; hệ số quy đổi SERVER tra
lại trên Item, không tin hệ số client gửi. Mọi lần ghi khóa hàng phiếu (`for_update`):
hai điện thoại cùng cộng vào một mã thì lượt sau đọc được lượt trước, không đè nhau.

Lô có PHIẾU TRẢ VỀ đi kèm hàng: người kiểm ghi số đếm thẳng lên phiếu rồi CHỤP lại
(`them_anh_phieu`) — kế toán ngồi máy nhập số sau, ảnh hiện ngay cạnh ô nhập. Ảnh gắn vào
PHIẾU KIỂM (bảng của ketoan, private, xem qua proxy có guard), chỉ nhận ảnh thật (soát chữ
ký đầu file). Phiếu chưa chốt mà đã có ảnh = "Chờ nhập số" — hàng việc của kế toán, không
phải một chặng.

════════════════════════════════════════════════════════════════════════════
HÓA ĐƠN TRẢ VỀ — NHÁP, đúng ERPNext v16
════════════════════════════════════════════════════════════════════════════

MẶC ĐỊNH — KHÔNG theo hóa đơn gốc (`tao_hoa_don_tra` không truyền hóa đơn gốc): MỘT tờ
cho mọi số đã kiểm mà chưa có phiếu trả, mỗi mã một dòng theo ĐVT KHO, không
`return_against`. Đơn giá = lần bán GẦN NHẤT (đã ghi sổ) cho đúng khách, ưu tiên đúng điểm
giao (`_gia_ban_gan_nhat`) — ghi giảm theo giá siêu thị đã trả, sát hơn bảng giá chung; mã
chưa từng bán cho khách thì ERPNext lấy theo bảng giá. Thuế theo mẫu của hóa đơn vừa lấy
giá, không có thì mẫu mặc định của công ty. Cái giá phải trả: `mt._returns_join` và sổ Hàng
hoàn chỉ nhận phiếu trả CÓ nối hóa đơn gốc — tờ đứng rời ghi giảm công nợ khách (131) mà
không trừ vào hóa đơn nào; muốn trừ đúng tờ thì đối trừ trên ERPNext, hoặc lập theo hóa đơn gốc.

TÙY CHỌN — theo hóa đơn gốc: `make_return_doc` của hóa đơn gốc, rồi THAY bảng hàng bằng kế
hoạch của `thu_hoi_phan_bo.phan_bo` (đọc docstring ở đó: vì sao dòng trả phải giữ ĐVT của
dòng gốc khi `update_stock = 0`). Hàng về từ nhiều hóa đơn gốc → nhiều phiếu trả, mỗi tờ một
`return_against`: kế toán chọn trong danh sách ứng viên (`ung_vien_hoa_don`).

Cả hai đường:
  · `update_stock = 0` — quy ước Client Script; hàng vào kho bằng phiếu kho riêng;
  · TK doanh thu dòng trả → TK 5213 của công ty nếu có (Client Script cũng đặt vậy);
  · `update_outstanding_for_self` giữ MẶC ĐỊNH của ERPNext như `doitru.create_return`;
  · `doc.insert()` KHÔNG ignore_permissions — tôn trọng quyền tạo Sales Invoice của
    người bấm. Ghi sổ thì mở Desk (deep link): con người soát rồi ấn nút.

Quyền: mọi method `guard_sales_any()` ở dòng đầu (kế toán NPP / MT / Du lịch + KTT);
kết luận "không lập hóa đơn trả về" chỉ `guard_manager()`.
"""

import base64
import binascii
import json
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, date_diff, flt, now_datetime, nowdate

from ketoan.api._guard import guard_manager, guard_sales_any, is_chief
from ketoan.api.mt import SI_NO_FIELD, _company, po_column
from ketoan.api.thu_hoi_phan_bo import (
    CHANG_KE_TOAN,
    DA_HUY,
    DA_KIEM,
    HUY_TAI_CHO,
    DANG_KIEM,
    EPS,
    XONG,
    con_can,
    gop_chi_tiet,
    mo_ta_chi_tiet,
    phan_bo,
    tong_theo_ma,
)
from ketoan.ketoan.doctype.kiem_hang_thu_hoi.kiem_hang_thu_hoi import (
    SI_FIELD,
    hoa_don_tra,
    so_can,
    tinh_trang_thai,
)

DT = "Kiem Hang Thu Hoi"
LO = "Lo Thu Hoi"            # bảng của vanchuyen — CHỈ ĐỌC, đọc MỀM
LO_HANG = "Lo Thu Hoi Hang"
DA_NHAN = "Đã nhận hàng"
CHANG_VC = ("Tạo yêu cầu", "Đã lấy hàng", DA_NHAN)
CHANG = CHANG_VC + CHANG_KE_TOAN
# Lô bị bên vận chuyển hủy yêu cầu (DA_HUY) không phải một nấc của 7 chặng: không tính vào
# "đang mở", xếp CUỐI danh sách (FIELD() trả 0 cho giá trị lạ = lên ĐẦU).
_THU_TU = CHANG + (DA_HUY,)

# Cột lô đọc sang. Tách hằng để danh sách và chi tiết không lệch nhau. Hàng do đơn vị
# vận chuyển ngoài lấy (Viettel Post / Nhất Tín): đơn vị + mã vận đơn + ngày thu
# (`ngay_hen_lay`), không còn lái xe / xe. `chi_tiet_hang` = mail siêu thị dán nguyên văn.
_LO_COLS = (
    "trang_thai", "ngay_yeu_cau", "so_phieu_sieu_thi", "ly_do", "customer", "customer_name",
    "shipping_address_name", "ten_diem", "ma_diem", "dia_chi", "sdt_diem", "nguoi_lien_he",
    "sdt_lien_he", "ghi_chu", "don_vi_thu_hoi", "ma_van_don", "ngay_hen_lay", "lay_luc", "lay_boi",
    "nhan_luc", "nhan_boi", "so_kien_du_kien", "so_kien_nhan", "gia_tri_khai", "so_dinh_kem",
    "ly_do_huy", "huy_boi", "huy_luc", "huy_tu", "chi_tiet_hang",
)
# Danh sách 30 lô một trang không kéo theo 30 bản mail dán (Long Text) — chỉ màn lô cần.
_LO_COLS_DS = tuple(c for c in _LO_COLS if c != "chi_tiet_hang")
# Ảnh / PDF mở trong tab; loại khác (Excel, Word, mail…) TẢI VỀ — cùng luật proxy bên vanchuyen.
DUOI_XEM_TRONG_TAB = frozenset(("jpg", "jpeg", "png", "webp", "gif", "pdf"))
_DATE_COLS = ("ngay_yeu_cau", "ngay_hen_lay", "lay_luc", "nhan_luc", "huy_luc", "chot_luc", "xong_luc",
              "posting_date")
UNG_VIEN_TRANG = 50  # một trang ứng viên hóa đơn gốc; "Xem tiếp" lấy trang sau
# Ảnh phiếu trả về chụp lúc kiểm hàng: màn hình nén còn ~0,5 MB một ảnh; trần để chặn gửi bừa.
ANH_TOI_DA = 8 * 1024 * 1024
ANH_TOI_DA_SO = 30


# ═══════════════════════════════════════════════════════════════════════════
# ĐỌC LÔ BÊN `vanchuyen` — CHỈ ĐỌC, ĐỌC MỀM
# ═══════════════════════════════════════════════════════════════════════════

def _co_lo():
    return bool(frappe.db.table_exists(LO))


def _require_lo():
    if not _co_lo():
        frappe.throw(_(
            "Site này chưa có app `vanchuyen` (thiếu bảng {0}) — chưa có lô thu hồi nào để theo dõi. "
            "Quản trị cài vanchuyen rồi chạy: bench --site TÊN_SITE migrate"
        ).format(LO))


def _lo_col(field, alias="l"):
    """`l.<field>` nếu bảng lô có cột đó, không thì NULL — bản vanchuyen cũ hơn không nổ."""
    return f"{alias}.`{field}`" if frappe.db.has_column(LO, field) else "NULL"


def _str_dates(d):
    for f in _DATE_COLS:
        if d.get(f):
            d[f] = str(d[f])
    return d


def _lo(name, khoa=False):
    """Bản ghi SỐNG của lô bên vanchuyen. Không có → throw.

    `khoa=True`: đọc KHÓA (`FOR UPDATE`) — thấy bản mới nhất đã commit và giữ khóa hàng lô
    tới hết giao dịch. Vẫn là ĐỌC (không ghi bảng của vanchuyen); `huy_lo` bên kia khóa
    cùng hàng, nên "Bắt đầu kiểm" và "Hủy yêu cầu" bấm cùng lúc thì một bên chờ bên kia.
    """
    _require_lo()
    cols = ", ".join(f"{_lo_col(c)} AS `{c}`" for c in _LO_COLS)
    rows = frappe.db.sql(
        f"SELECT l.name, {cols} FROM `tab{LO}` l WHERE l.name = %(n)s" + (" FOR UPDATE" if khoa else ""),
        {"n": name}, as_dict=True)
    if not rows:
        frappe.throw(_("Không tìm thấy lô thu hồi {0} bên vận chuyển.").format(name))
    return _str_dates(rows[0])


def _hang_khai(name):
    if not frappe.db.table_exists(LO_HANG):
        return []
    return frappe.db.sql(
        f"""SELECT item_code, item_name, qty, uom, stock_qty, stock_uom
        FROM `tab{LO_HANG}` WHERE parent = %(p)s AND parenttype = %(t)s ORDER BY idx""",
        {"p": name, "t": LO}, as_dict=True)


def _files(name, dt=LO):
    """File đính kèm của LÔ bên vanchuyen — hoặc của PHIẾU KIỂM (`dt=DT`: ảnh phiếu trả về chụp
    lúc kiểm). Cả hai xem qua proxy `xem_dinh_kem` có guard."""
    rows = frappe.get_all(
        "File", filters={"attached_to_doctype": dt, "attached_to_name": name},
        fields=["name", "file_name", "creation", "owner"], order_by="creation asc", limit_page_length=0)
    for f in rows:
        f["url"] = "/api/method/ketoan.api.thu_hoi.xem_dinh_kem?file=" + quote(f.name)
        f["ext"] = _duoi(f.file_name)
        f["is_image"] = f["ext"] in ("jpg", "jpeg", "png", "webp", "gif")
        f["creation"] = str(f.creation)
        f["boi"] = (frappe.utils.get_fullname(f.owner) or f.owner) if f.owner else ""
    return rows


def _dem_anh(names):
    """{phiếu kiểm: số ảnh phiếu} cho cả trang danh sách — một truy vấn (tên phiếu = tên lô)."""
    if not names:
        return {}
    return {r.n: cint(r.c) for r in frappe.db.sql(
        """SELECT attached_to_name AS n, COUNT(*) AS c FROM `tabFile`
        WHERE attached_to_doctype = %(dt)s AND attached_to_name IN %(names)s
        GROUP BY attached_to_name""", {"dt": DT, "names": tuple(names)}, as_dict=True)}


def _duoi(ten):
    """Phần mở rộng, chữ thường, không dấu chấm: "DS.XLSX" → "xlsx"."""
    t = cstr(ten)
    return t.rsplit(".", 1)[-1].lower() if "." in t else ""


def _expr():
    """Biểu thức CHẶNG TỔNG — một chỗ, cho WHERE / GROUP BY / ORDER BY. Lô hủy tại chỗ chưa có
    phiếu đứng ở "Đã kiểm hàng" (nhận đủ theo phiếu) — cùng luật `lo_thu_hoi.chang_tong`."""
    return ("(CASE WHEN k.name IS NULL THEN "
            "(CASE WHEN l.trang_thai = %(htc)s THEN %(da_kiem)s ELSE l.trang_thai END) "
            "WHEN IFNULL(k.trang_thai, '') = '' THEN %(dang_kiem)s ELSE k.trang_thai END)")


def _chang_lo(lo, tt=None):
    """Chặng tổng của MỘT lô (màn chi tiết) — cùng luật `_expr()`."""
    if tt:
        return tt
    return DA_KIEM if lo.get("trang_thai") == HUY_TAI_CHO else lo.get("trang_thai")


# ═══════════════════════════════════════════════════════════════════════════
# THEO DÕI THU HỒI — danh sách mọi lô
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def list_thu_hoi(chang=None, tim=None, tu_ngay=None, den_ngay=None, page=1, page_size=30):
    """MỌI lô tạo bên vanchuyen + chặng tổng; pill đếm đủ 7 chặng (+ "Đã hủy") trên cùng bộ tìm.

    `chang` = một trong 7 chặng · "Đã hủy" · "dang_mo" (mặc định: chưa Xong, chưa hủy) · "tat_ca"
    · "cho_nhap" (phiếu kiểm CHƯA chốt đã có ảnh phiếu — người kiểm ghi số lên phiếu trả về
    rồi chụp, còn việc ngồi máy nhập; không phải một chặng, đếm riêng ở `cho_nhap`).

    Lọc + đếm ở SERVER. Xếp chặng sớm trước, lô cũ trước: việc treo lâu nhất nổi lên đầu.
    SQL thô: JOIN mềm sang bảng app khác, biểu thức chặng dùng chung ba mệnh đề.
    """
    guard_sales_any()
    if not _co_lo():
        return {"rows": [], "total": 0, "counts": {}, "chang_list": list(CHANG), "vanchuyen": False,
                "note": _("Site chưa cài app vận chuyển — chưa có lô thu hồi nào.")}
    page = max(1, cint(page))
    page_size = min(cint(page_size) or 30, 100)
    expr = _expr()
    p = {"dang_kiem": DANG_KIEM, "xong": XONG, "huy": DA_HUY, "htc": HUY_TAI_CHO, "da_kiem": DA_KIEM}
    conds = ["1 = 1"]
    if cstr(tim).strip():
        p["q"] = "%" + cstr(tim).strip() + "%"
        conds.append(f"(l.name LIKE %(q)s OR l.customer_name LIKE %(q)s OR {_lo_col('ten_diem')} LIKE %(q)s "
                     f"OR {_lo_col('ma_diem')} LIKE %(q)s OR {_lo_col('so_phieu_sieu_thi')} LIKE %(q)s "
                     f"OR {_lo_col('ma_van_don')} LIKE %(q)s)")
    if tu_ngay:
        p["tu"] = tu_ngay
        conds.append("l.ngay_yeu_cau >= %(tu)s")
    if den_ngay:
        p["den"] = den_ngay
        conds.append("l.ngay_yeu_cau <= %(den)s")
    base = " AND ".join(conds)
    join = f"LEFT JOIN `tab{DT}` k ON k.lo_thu_hoi = l.name"

    counts = {cstr(r.chang): cint(r.n) for r in frappe.db.sql(
        f"SELECT {expr} AS chang, COUNT(*) AS n FROM `tab{LO}` l {join} WHERE {base} GROUP BY chang",
        p, as_dict=True)}
    p["dt"] = DT
    cho_nhap = ("(k.name IS NOT NULL AND IFNULL(k.da_chot, 0) = 0 AND EXISTS (SELECT 1 FROM `tabFile` f "
                "WHERE f.attached_to_doctype = %(dt)s AND f.attached_to_name = k.name))")
    n_cho = cint(frappe.db.sql(f"SELECT COUNT(*) FROM `tab{LO}` l {join} WHERE {base} AND {cho_nhap}", p)[0][0])

    where = base
    chang = cstr(chang).strip() or "dang_mo"
    if chang == "cho_nhap":
        where += f" AND {cho_nhap}"
    elif chang == "dang_mo":
        where += f" AND {expr} NOT IN (%(xong)s, %(huy)s)"
    elif chang in _THU_TU:
        p["chang"] = chang
        where += f" AND {expr} = %(chang)s"
    total = cint(frappe.db.sql(f"SELECT COUNT(*) FROM `tab{LO}` l {join} WHERE {where}", p)[0][0])

    p.update({"c%d" % i: c for i, c in enumerate(_THU_TU)})
    p["lim"], p["off"] = page_size, (page - 1) * page_size
    order = ", ".join("%(c{0})s".format(i) for i in range(len(_THU_TU)))
    cols = ", ".join(f"{_lo_col(c)} AS `{c}`" for c in _LO_COLS_DS)
    rows = frappe.db.sql(
        f"""SELECT l.name, {cols}, {expr} AS chang,
               k.name AS phieu, k.tong_sl AS kiem_sl, k.so_ma AS kiem_so_ma, k.da_chot
        FROM `tab{LO}` l {join}
        WHERE {where}
        ORDER BY FIELD({expr}, {order}), l.ngay_yeu_cau ASC, l.name ASC
        LIMIT %(lim)s OFFSET %(off)s""",
        p, as_dict=True)

    hd = _tom_tat_hoa_don([r.name for r in rows])
    anh = _dem_anh([r.phieu for r in rows if r.phieu])
    today = nowdate()
    for r in rows:
        _str_dates(r)
        r["tuoi"] = date_diff(today, r.ngay_yeu_cau) if r.ngay_yeu_cau and r.chang not in (XONG, DA_HUY) else None
        r.update(hd.get(r.name) or {"so_hd": 0, "so_hd_ghi_so": 0, "tien_hd": 0.0})
        r["so_anh"] = anh.get(r.phieu, 0) if r.phieu else 0
        r["cho_nhap"] = bool(r.phieu) and not cint(r.da_chot) and r["so_anh"] > 0
    return {
        "rows": rows, "total": total, "page": page, "page_size": page_size,
        "has_more": (page - 1) * page_size + len(rows) < total,
        "counts": counts, "cho_nhap": n_cho, "chang_list": list(CHANG), "vanchuyen": True,
    }


def _tom_tat_hoa_don(names):
    """{phiếu kiểm: số phiếu trả, số đã ghi sổ, tổng tiền} — một truy vấn cho cả trang."""
    if not names or not frappe.db.has_column("Sales Invoice", SI_FIELD):
        return {}
    rows = frappe.db.sql(
        f"""SELECT r.`{SI_FIELD}` AS k, COUNT(*) AS n, SUM(r.docstatus = 1) AS n1,
               SUM(ABS(r.grand_total)) AS tien
        FROM `tabSales Invoice` r
        WHERE r.`{SI_FIELD}` IN %(n)s AND r.is_return = 1 AND r.docstatus < 2
        GROUP BY r.`{SI_FIELD}`""",
        {"n": tuple(names)}, as_dict=True)
    return {r.k: {"so_hd": cint(r.n), "so_hd_ghi_so": cint(r.n1), "tien_hd": flt(r.tien)} for r in rows}


# ═══════════════════════════════════════════════════════════════════════════
# CHI TIẾT MỘT LÔ
# ═══════════════════════════════════════════════════════════════════════════

def _phieu_dict(doc):
    if not doc:
        return None
    d = {f: doc.get(f) for f in ("name", "lo_thu_hoi", "trang_thai", "company", "customer",
                                  "customer_name", "shipping_address_name", "ten_diem", "tong_sl",
                                  "so_ma", "da_chot", "chot_luc", "chot_boi", "xong_luc", "ghi_chu",
                                  "khong_lap_hd", "ly_do_khong_lap", "ket_luan_boi", "theo_phieu")}
    d["da_chot"] = cint(d["da_chot"])
    d["khong_lap_hd"] = cint(d["khong_lap_hd"])
    d["items"] = []
    for r in doc.items or []:
        try:
            ct = json.loads(r.chi_tiet) if r.chi_tiet else []
        except ValueError:
            ct = []
        d["items"].append({"name": r.name, "item_code": r.item_code, "item_name": r.item_name,
                           "qty": flt(r.qty), "stock_uom": r.stock_uom, "mo_ta_dvt": r.mo_ta_dvt,
                           "chi_tiet": ct, "ma_quet": r.ma_quet, "nguoi_ghi": r.nguoi_ghi,
                           "ghi_chu": r.ghi_chu})
    d["modified"] = str(doc.modified)
    return _str_dates(d)


def _hoa_don_chi_tiet(name):
    """Phiếu trả gắn phiếu kiểm: tiêu đề + dòng, cho màn chi tiết."""
    if not frappe.db.has_column("Sales Invoice", SI_FIELD):
        return []
    misa = f"r.`{SI_NO_FIELD}`" if frappe.db.has_column("Sales Invoice", SI_NO_FIELD) else "NULL"
    heads = frappe.db.sql(
        f"""SELECT r.name, r.docstatus, r.posting_date, r.return_against, ABS(r.grand_total) AS tien,
               {misa} AS misa_no
        FROM `tabSales Invoice` r
        WHERE r.`{SI_FIELD}` = %(k)s AND r.is_return = 1 AND r.docstatus < 2
        ORDER BY r.creation, r.name""", {"k": name}, as_dict=True)
    if not heads:
        return []
    lines = frappe.db.sql(
        """SELECT parent, item_code, item_name, qty, uom, stock_qty, rate, sales_invoice_item
        FROM `tabSales Invoice Item` WHERE parent IN %(p)s AND parenttype = 'Sales Invoice'
        ORDER BY parent, idx""", {"p": tuple(h.name for h in heads)}, as_dict=True)
    by = {}
    for ln in lines:
        by.setdefault(ln.parent, []).append({
            "item_code": ln.item_code, "item_name": ln.item_name, "qty": abs(flt(ln.qty)),
            "uom": ln.uom, "stock_qty": abs(flt(ln.stock_qty)), "rate": flt(ln.rate),
            "noi": bool(ln.sales_invoice_item)})
    out = []
    for h in heads:
        d = _str_dates(dict(h))
        d["tien"] = flt(h.tien)
        d["misa_no"] = cstr(h.misa_no or "")
        d["items"] = by.get(h.name, [])
        d["tu_do"] = not h.return_against  # không theo hóa đơn gốc: dòng nào cũng "không nối", là đúng
        d["route"] = f"/desk/sales-invoice/{quote(h.name)}"
        out.append(d)
    return out


@frappe.whitelist()
def get_thu_hoi(name):
    """Một lô: hồ sơ bên vận chuyển (đơn vị thu hồi, mail dán, đính kèm) + phiếu kiểm (kèm ảnh
    phiếu trả về chụp lúc kiểm) + phiếu trả + so sánh. Cột "khai" chỉ có với lô CŨ còn bảng
    hàng khai bên vanchuyen."""
    guard_sales_any()
    lo = _lo(name)
    doc = frappe.get_doc(DT, name) if frappe.db.exists(DT, name) else None
    anh = _files(name, DT) if doc else []
    khai = _hang_khai(name)
    hd = _hoa_don_chi_tiet(name) if doc else []
    tt, lech = tinh_trang_thai(doc) if doc else (None, {})
    can = so_can(doc) if doc else {}
    da_lap = tong_theo_ma([{"items": {i["item_code"]: i["stock_qty"] for i in h["items"]}} for h in hd])

    # So KHAI — KIỂM — ĐÃ LẬP theo từng mã. Lệch khai/kiểm là thứ đáng tiền nhất:
    # siêu thị trừ tiền theo số họ khai, mình chỉ trả về theo số mình nhận.
    so = {}
    for r in khai:
        s = so.setdefault(r.item_code, {"item_code": r.item_code, "item_name": r.item_name,
                                        "stock_uom": r.stock_uom, "khai": 0.0, "kiem": 0.0, "da_lap": 0.0})
        s["khai"] += flt(r.stock_qty)
    for r in (doc.items if doc else []):
        s = so.setdefault(r.item_code, {"item_code": r.item_code, "item_name": r.item_name,
                                        "stock_uom": r.stock_uom, "khai": 0.0, "kiem": 0.0, "da_lap": 0.0})
        s["kiem"] += flt(r.qty)
    for it, q in da_lap.items():
        s = so.setdefault(it, {"item_code": it, "item_name": it, "stock_uom": "", "khai": 0.0,
                               "kiem": 0.0, "da_lap": 0.0})
        s["da_lap"] += q

    chot = bool(doc and cint(doc.da_chot))
    co_ghi_so = any(h["docstatus"] == 1 for h in hd)
    co_nhap = any(h["docstatus"] == 0 for h in hd)
    con = con_can(can, [{"items": {i["item_code"]: i["stock_qty"] for i in h["items"]}} for h in hd])
    return {
        "lo": lo,
        "khai": [dict(r, qty=flt(r.qty), stock_qty=flt(r.stock_qty)) for r in khai],
        "co_khai": bool(khai),
        "tong_khai": sum(flt(r.stock_qty) for r in khai),
        "files": _files(name),
        "phieu": _phieu_dict(doc),
        "anh_phieu": anh,
        "hoa_don": hd,
        "so_sanh": sorted(so.values(), key=lambda x: cstr(x["item_name"])),
        "chang": _chang_lo(lo, tt),
        "chang_list": list(CHANG),
        "lech": lech,
        "con_can": con,
        "flags": {
            "bat_dau": not doc and lo["trang_thai"] in (DA_NHAN, HUY_TAI_CHO),
            "sua": bool(doc) and not chot,
            "chot": bool(doc) and not chot and bool(doc.items),
            "mo_lai": chot and not co_ghi_so and (is_chief() or not cint(doc.khong_lap_hd)),
            "lap_hd": chot and not cint(doc.khong_lap_hd) and bool(con),
            "cap_nhat": chot and co_nhap and bool(lech),
            "xoa": bool(doc) and not chot and not hd,
            "ket_luan": is_chief() and bool(doc) and not hd and not cint(doc.khong_lap_hd),
            "cho_nhap": bool(doc) and not chot and bool(anh),
        },
        "is_chief": is_chief(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# KIỂM HÀNG
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def bat_dau_kiem(name):
    """Mở phiếu kiểm cho một lô ĐÃ NHẬN HÀNG — hoặc lô HỦY TẠI CHỖ (phiếu `theo_phieu`: chép số
    theo phiếu siêu thị, không đếm). Gọi lại khi đã có phiếu → trả phiếu cũ.

    Đọc lô bằng KHÓA (`_lo(khoa=True)`): bên vận chuyển bấm "Hủy yêu cầu" cùng lúc thì hai
    bên lần lượt, bên sau thấy kết quả bên trước — không có lô vừa hủy vừa đang kiểm.
    """
    guard_sales_any()
    lo = _lo(name, khoa=True)
    if not frappe.db.exists(DT, name):
        if lo["trang_thai"] == DA_HUY:
            frappe.throw(_(
                "Lô {0} đã bị bên vận chuyển HỦY yêu cầu ({1}) — không kiểm hàng. Hủy nhầm thì nhờ "
                "điều phối bấm 'Khôi phục' bên app vận chuyển."
            ).format(name, lo.get("ly_do_huy") or _("không ghi lý do")))
        if lo["trang_thai"] not in (DA_NHAN, HUY_TAI_CHO):
            frappe.throw(_(
                "Lô {0} đang ở '{1}' bên vận chuyển. Kiểm hàng khi hàng đã về kho — nhờ điều phối "
                "bấm 'Đã nhận hàng' trước."
            ).format(name, lo["trang_thai"]))
        doc = frappe.new_doc(DT)
        doc.lo_thu_hoi = name
        doc.company = _company()
        doc.customer = lo["customer"]
        doc.customer_name = lo["customer_name"]
        doc.shipping_address_name = lo["shipping_address_name"]
        doc.ten_diem = lo["ten_diem"]
        doc.theo_phieu = 1 if lo["trang_thai"] == HUY_TAI_CHO else 0
        try:
            doc.insert()  # tôn trọng DocPerm của phiếu kiểm (vai trò kế toán kênh bán hàng)
        except frappe.DuplicateEntryError:
            # Người khác vừa mở cùng lúc — khóa chính chặn bản thứ hai; dùng bản của họ.
            frappe.db.rollback()
    return get_thu_hoi(name)


# Danh mục màn kiểm hàng: CHỈ hai nhóm hàng này, kể cả mọi nhóm con trong cây Item Group —
# hàng siêu thị trả về là hàng truyền thống / hàng Tết; tìm trong cả trăm mã hàng bán là
# chậm tay và dễ chọn nhầm. Tên khớp Item Group trên site (MariaDB so không phân biệt hoa
# thường). Không thấy nhóm nào thì màn kiểm vẫn dùng được: tìm trong mọi mã hàng bán + báo.
NHOM_KIEM = ("Hàng truyền thống", "Hàng Tết")


def _nhom_kiem():
    """(mọi Item Group thuộc NHOM_KIEM kể cả nhánh con, các nhóm gốc tìm thấy trên site).

    Nhánh con lấy theo cây nested set (lft/rgt); cây hỏng (rgt <= lft) thì chỉ lấy đúng
    nhóm gốc, không bung bừa ra cả cây. SQL thô: bung mọi nhóm gốc trong một truy vấn.
    """
    rows = frappe.db.sql(
        """SELECT g.name AS goc, c.name
        FROM `tabItem Group` g
        INNER JOIN `tabItem Group` c
            ON c.name = g.name OR (g.rgt > g.lft AND c.lft > g.lft AND c.rgt < g.rgt)
        WHERE g.name IN %(g)s""", {"g": NHOM_KIEM}, as_dict=True)
    return sorted({r.name for r in rows}), sorted({r.goc for r in rows})


def _danh_muc(codes=None, nhom=None):
    """Mã hàng bán được + mọi ĐVT đã khai quy đổi: [{item, ten, dvt, uoms:[{uom, he_so}]}].

    `codes`: đúng các mã này (bất kể nhóm). `nhom`: chỉ Item thuộc các Item Group này.
    """
    filters = {"disabled": 0, "is_sales_item": 1, "has_variants": 0}
    if codes is not None:
        if not codes:
            return []
        filters = {"name": ["in", list(codes)]}
    elif nhom:
        filters["item_group"] = ["in", list(nhom)]
    items = frappe.get_all("Item", filters=filters, fields=["name", "item_name", "stock_uom"],
                           order_by="item_name asc", limit_page_length=5000)
    uoms = {}
    if items:
        for r in frappe.get_all(
            "UOM Conversion Detail",
            filters={"parent": ["in", [i.name for i in items]], "parenttype": "Item"},
            fields=["parent", "uom", "conversion_factor"], limit_page_length=0,
        ):
            if flt(r.conversion_factor) > 0:
                uoms.setdefault(r.parent, {})[r.uom] = flt(r.conversion_factor)
    out = []
    for i in items:
        u = uoms.get(i.name) or {}
        u.setdefault(i.stock_uom, 1.0)
        out.append({"item": i.name, "ten": i.item_name or i.name, "dvt": i.stock_uom,
                    "uoms": sorted(({"uom": k, "he_so": v} for k, v in u.items()), key=lambda x: -x["he_so"])})
    return out


# Màn kiểm hàng đếm MÙ: không nhận gì có số siêu thị khai — giá trị phiếu, và cả bản mail
# dán nguyên văn (`chi_tiet_hang` chính là danh sách hàng + số lượng siêu thị khai).
_SO_KHAI = ("gia_tri_khai", "chi_tiet_hang")


@frappe.whitelist()
def boot_kiem(name):
    """Mọi thứ màn kiểm hàng cần, MỘT lượt: danh mục + bảng tra mã quét + gợi ý + phiếu + ảnh
    phiếu trả về đã chụp (ảnh do chính người kiểm chụp — ngồi máy nhập theo ảnh).

    Danh mục = mã thuộc NHOM_KIEM (+ mã đã kiểm trên phiếu mà ngoài nhóm — vẫn sửa / cộng
    thêm được). Tra mã quét ở MÁY (như sx `_ma_quet`): quét phải phản hồi tức thì, đợi mạng
    trong kho là mất cái lợi của việc quét. Mã thùng (ITF-14) khai trên `Item Barcode.uom`
    thì bàn số mở đúng tab Thùng. Gợi ý (`goi_y`) là mã HAY TRẢ — màn hình đưa lên đầu khi tìm.
    """
    guard_sales_any()
    doc = frappe.get_doc(DT, name)
    # Đếm MÙ tới tận payload: màn này không nhận số siêu thị khai, cả tổng lẫn từng mã.
    # Gợi ý chỉ mang MÃ, không mang số; so khai/kiểm là việc của màn lô sau khi chốt.
    # NGOẠI LỆ: phiếu theo phiếu (lô hủy tại chỗ) — không đếm, mà CHÉP từ phiếu siêu thị, nên
    # phải thấy mail dán + biên bản / phiếu đính kèm.
    theo_phieu = bool(cint(doc.get("theo_phieu")))
    lo = {k: v for k, v in _lo(name).items() if theo_phieu or k not in _SO_KHAI}
    nhom, goc = _nhom_kiem()
    danh_muc = _danh_muc(nhom=nhom) if nhom else _danh_muc()
    co = {d["item"] for d in danh_muc}
    ngoai = list(dict.fromkeys(r.item_code for r in doc.items or [] if r.item_code and r.item_code not in co))
    if ngoai:
        danh_muc += _danh_muc(ngoai)
        co = {d["item"] for d in danh_muc}
    ma_quet = {}
    for b in frappe.get_all("Item Barcode", fields=["barcode", "parent", "uom"], limit_page_length=0):
        if b.barcode and b.parent in co:
            ma_quet[cstr(b.barcode).strip()] = {"item": b.parent, "uom": b.uom or None}
    for c in co:
        ma_quet.setdefault(c, {"item": c, "uom": None})
    # Gợi ý: mã siêu thị khai, rồi mã khách này mua trong 6 tháng — hàng trả về gần như
    # luôn nằm trong hai nhóm đó.
    goi_y = [r.item_code for r in _hang_khai(name)]
    for r in frappe.db.sql(
        """SELECT it.item_code, MAX(si.posting_date) AS d
        FROM `tabSales Invoice Item` it
        INNER JOIN `tabSales Invoice` si ON si.name = it.parent
        WHERE si.customer = %(c)s AND si.docstatus = 1 AND si.is_return = 0
          AND si.posting_date >= %(tu)s
        GROUP BY it.item_code ORDER BY d DESC LIMIT 40""",
        {"c": doc.customer, "tu": add_days(nowdate(), -180)}, as_dict=True,
    ):
        if r.item_code not in goi_y:
            goi_y.append(r.item_code)
    return {
        "lo": lo,
        "phieu": _phieu_dict(doc),
        "danh_muc": danh_muc,
        "ma_quet": ma_quet,
        "goi_y": [g for g in goi_y if g in co][:40],
        "files": _files(name) if theo_phieu else [],
        "anh_phieu": _files(name, DT),
        "nhom_kiem": goc,
        "thieu_nhom": [g for g in NHOM_KIEM if g.lower() not in {x.lower() for x in goc}],
        "hom_nay": nowdate(),
    }


def _kieu_anh(data):
    """Đuôi theo CHỮ KÝ đầu file — "jpg" / "png" / "webp"; không phải ảnh thì None. Không tin đuôi
    tên client gửi: proxy mở inline theo đuôi, một file .html đổi tên .jpg là script trên tên miền site."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


@frappe.whitelist()
def them_anh_phieu(name, content, filename=None):
    """Đính kèm MỘT ảnh phiếu trả về (base64) vào phiếu kiểm. Lô có phiếu trả về đi kèm hàng thì
    người kiểm ghi số đếm thẳng lên phiếu rồi chụp lại — kế toán ngồi máy nhập số sau. Chỉ khi
    phiếu CHƯA chốt (chốt rồi là số đã khóa; cần thêm ảnh thì "Mở lại").

    File PRIVATE gắn vào PHIẾU KIỂM (bảng của ketoan — không gắn vào lô bên vanchuyen). Tên file
    do server đặt, đuôi theo chữ ký đầu file; `filename` của máy chỉ để báo lỗi cho dễ hiểu.
    """
    guard_sales_any()
    doc = _khoa(name)
    try:
        data = base64.b64decode(cstr(content).split(",")[-1], validate=True)
    except (binascii.Error, ValueError):
        frappe.throw(_("Ảnh {0} gửi lên bị hỏng — chụp lại.").format(cstr(filename)))
    duoi = _kieu_anh(data)
    if not duoi:
        frappe.throw(_("{0} không phải ảnh chụp — chỉ nhận JPG / PNG / WEBP.").format(cstr(filename) or _("File")))
    if len(data) > ANH_TOI_DA:
        frappe.throw(_("Ảnh quá lớn ({0} MB) — tối đa {1} MB.").format(
            round(len(data) / 1048576.0, 1), ANH_TOI_DA // 1048576))
    co = frappe.db.count("File", {"attached_to_doctype": DT, "attached_to_name": doc.name})
    if co >= ANH_TOI_DA_SO:
        frappe.throw(_("Phiếu {0} đã có {1} ảnh — xóa bớt ảnh chụp nhầm rồi chụp tiếp.").format(doc.name, co))
    f = frappe.get_doc({
        "doctype": "File",
        "file_name": f"anh-phieu-{doc.name}-{frappe.generate_hash(length=6)}.{duoi}",
        "attached_to_doctype": DT,
        "attached_to_name": doc.name,
        "is_private": 1,
        "content": data,
    })
    # Sau guard + đúng phiếu, chưa chốt (khóa hàng ở `_khoa`): quyền DocType File không thêm gì.
    f.save(ignore_permissions=True)
    return {"anh_phieu": _files(doc.name, DT)}


@frappe.whitelist()
def xoa_anh_phieu(name, file):
    """Xóa một ảnh phiếu chụp nhầm — chỉ khi phiếu CHƯA chốt, chỉ file gắn đúng phiếu này."""
    guard_sales_any()
    doc = _khoa(name)
    f = frappe.db.get_value("File", file, ["attached_to_doctype", "attached_to_name"], as_dict=True)
    if not f or f.attached_to_doctype != DT or f.attached_to_name != doc.name:
        frappe.throw(_("Ảnh không thuộc phiếu kiểm {0}.").format(doc.name))
    # Ảnh có thể do người khác chụp (vai trò kế toán kênh không xóa được File của người khác):
    # guard + hai chốt trên thay cho quyền đó, như `xoa_phieu`.
    frappe.delete_doc("File", file, ignore_permissions=True)
    return {"anh_phieu": _files(doc.name, DT)}


def _khoa(name):
    """Phiếu kiểm để GHI: khóa hàng (for_update) + chặn khi đã chốt."""
    doc = frappe.get_doc(DT, name, for_update=True)
    if cint(doc.da_chot):
        frappe.throw(_("Phiếu {0} đã chốt — bấm 'Mở lại' để sửa.").format(name))
    return doc


def _quy_doi(item_code, qty, chi_tiet):
    """(tổng ĐVT kho, chi tiết sạch). Có chi tiết thì TỔNG TÍNH LẠI từ hệ số trên Item."""
    if isinstance(chi_tiet, str):
        chi_tiet = json.loads(chi_tiet or "[]")
    if not chi_tiet:
        return flt(qty), []
    he_so = {u["uom"]: u["he_so"] for d in _danh_muc([item_code]) for u in d["uoms"]}
    sach, tong = [], 0.0
    for c in chi_tiet:
        u = cstr(c.get("uom"))
        sl = flt(c.get("sl"))
        if sl <= 0:
            continue
        if u not in he_so:
            frappe.throw(_("Mã {0} chưa khai quy đổi đơn vị {1}.").format(item_code, u))
        sach.append({"uom": u, "sl": sl, "he_so": he_so[u]})
        tong += sl * he_so[u]
    return tong, sach


@frappe.whitelist()
def them_dong(name, item_code, qty=0, chi_tiet=None, ma_quet=None):
    """Ghi một lần đếm. Mã đã có dòng thì CỘNG vào dòng đó (một mã một dòng)."""
    guard_sales_any()
    doc = _khoa(name)
    item_code = cstr(item_code).strip()
    if not frappe.db.exists("Item", item_code):
        frappe.throw(_("Không có mã hàng {0}.").format(item_code))
    them, ct = _quy_doi(item_code, qty, chi_tiet)
    if them <= EPS:
        frappe.throw(_("Số lượng phải > 0."))
    ai = frappe.utils.get_fullname(frappe.session.user) or frappe.session.user
    row = next((r for r in doc.items if r.item_code == item_code), None)
    if row:
        try:
            cu = json.loads(row.chi_tiet) if row.chi_tiet else []
        except ValueError:
            cu = []
        row.qty = flt(row.qty) + them
        gop = gop_chi_tiet(cu, ct) if (cu or ct) else []
        row.chi_tiet = json.dumps(gop, ensure_ascii=False) if gop else None
        row.mo_ta_dvt = mo_ta_chi_tiet(gop) or None
        row.ma_quet = cstr(ma_quet).strip() or row.ma_quet
        row.nguoi_ghi = ai
    else:
        doc.append("items", {
            "item_code": item_code, "qty": them,
            "chi_tiet": json.dumps(ct, ensure_ascii=False) if ct else None,
            "mo_ta_dvt": mo_ta_chi_tiet(ct) or None,
            "ma_quet": cstr(ma_quet).strip() or None, "nguoi_ghi": ai,
        })
    doc.save()
    return _phieu_dict(doc)


@frappe.whitelist()
def sua_dong(name, row, qty=0, chi_tiet=None, ghi_chu=None):
    """Sửa TỔNG của một dòng (bấm vào số). Về 0 thì phải bấm ✕ — xóa là một ý định riêng."""
    guard_sales_any()
    doc = _khoa(name)
    r = next((x for x in doc.items if x.name == row), None)
    if not r:
        frappe.throw(_("Dòng không còn trên phiếu — có người vừa xóa. Tải lại."))
    tong, ct = _quy_doi(r.item_code, qty, chi_tiet)
    if tong <= EPS:
        frappe.throw(_("Số lượng phải > 0. Muốn bỏ mã này thì bấm ✕."))
    r.qty = tong
    r.chi_tiet = json.dumps(ct, ensure_ascii=False) if ct else None
    r.mo_ta_dvt = mo_ta_chi_tiet(ct) or None
    if ghi_chu is not None:
        r.ghi_chu = cstr(ghi_chu).strip() or None
    r.nguoi_ghi = frappe.utils.get_fullname(frappe.session.user) or frappe.session.user
    doc.save()
    return _phieu_dict(doc)


@frappe.whitelist()
def xoa_dong(name, row):
    """Xóa một dòng đếm."""
    guard_sales_any()
    doc = _khoa(name)
    giu = [x for x in doc.items if x.name != row]
    if len(giu) == len(doc.items):
        frappe.throw(_("Dòng không còn trên phiếu — tải lại."))
    doc.set("items", giu)
    doc.save()
    return _phieu_dict(doc)


@frappe.whitelist()
def luu_ghi_chu(name, ghi_chu=None):
    """Ghi chú chung của phiếu kiểm — sửa được cả khi đã chốt (không đụng số)."""
    guard_sales_any()
    doc = frappe.get_doc(DT, name, for_update=True)
    doc.ghi_chu = cstr(ghi_chu).strip() or None
    doc.save()
    return _phieu_dict(doc)


@frappe.whitelist()
def chot(name):
    """Chốt phiếu: khóa số đã kiểm, mở đường lập hóa đơn trả về."""
    guard_sales_any()
    doc = _khoa(name)
    if not doc.items:
        frappe.throw(_("Phiếu chưa có dòng nào — quét / chọn mã rồi nhập số trước khi chốt."))
    doc.da_chot = 1
    doc.chot_luc = now_datetime()
    doc.chot_boi = frappe.utils.get_fullname(frappe.session.user) or frappe.session.user
    doc.save()
    return get_thu_hoi(name)


@frappe.whitelist()
def mo_lai(name):
    """Mở lại phiếu đã chốt để sửa. Chặn khi đã có phiếu trả GHI SỔ.

    Phiếu trả NHÁP thì vẫn mở được: sửa xong chốt lại rồi bấm "Cập nhật hóa đơn trả về"
    — máy chia lại các bản nháp theo số mới. Bản đã ghi sổ thì không chia lại được nữa.
    """
    guard_sales_any()
    doc = frappe.get_doc(DT, name, for_update=True)
    if not cint(doc.da_chot):
        return get_thu_hoi(name)
    ghi_so = [h["name"] for h in hoa_don_tra(name) if h["docstatus"] == 1]
    if ghi_so:
        frappe.throw(_(
            "Hóa đơn trả về {0} đã ghi sổ trên số này. Hủy nó trên Desk trước rồi mới mở lại phiếu kiểm."
        ).format(", ".join(ghi_so)))
    if cint(doc.khong_lap_hd) and not is_chief():
        frappe.throw(_("Phiếu này đã được KTT kết luận 'không lập hóa đơn trả về' — chỉ KTT mở lại."))
    doc.da_chot = 0
    doc.chot_luc = doc.chot_boi = None
    doc.khong_lap_hd = 0
    doc.ly_do_khong_lap = doc.ket_luan_boi = None
    doc.save()
    return get_thu_hoi(name)


@frappe.whitelist()
def ket_luan_khong_lap(name, ly_do):
    """KTT kết luận lô này KHÔNG lập hóa đơn trả về (đổi hàng ngang giá, hàng không về…).

    Không phải cờ "bỏ qua": có lý do bắt buộc + ai kết luận, như "Không cần chứng từ" của
    sổ hàng hoàn — người soát sau sẽ hỏi đúng câu "vì sao lô này không ghi giảm công nợ".
    """
    guard_manager()
    if len(cstr(ly_do).strip()) < 5:
        frappe.throw(_("Ghi rõ lý do không lập hóa đơn trả về."))
    doc = frappe.get_doc(DT, name, for_update=True)
    hd = hoa_don_tra(name)
    if hd:
        frappe.throw(_("Lô đã có hóa đơn trả về {0} — xóa / hủy trước khi kết luận không lập.").format(
            ", ".join(h["name"] for h in hd)))
    ai = frappe.utils.get_fullname(frappe.session.user) or frappe.session.user
    if not cint(doc.da_chot):
        doc.da_chot = 1
        doc.chot_luc = now_datetime()
        doc.chot_boi = ai
    doc.khong_lap_hd = 1
    doc.ly_do_khong_lap = cstr(ly_do).strip()
    doc.ket_luan_boi = ai
    doc.save()
    return get_thu_hoi(name)


@frappe.whitelist()
def xoa_phieu(name):
    """Xóa phiếu kiểm mở nhầm — chỉ khi CHƯA chốt và chưa gắn hóa đơn trả về nào."""
    guard_sales_any()
    doc = frappe.get_doc(DT, name)
    if cint(doc.da_chot):
        frappe.throw(_("Phiếu đã chốt — mở lại trước nếu thật sự muốn xóa."))
    # on_trash chặn tiếp khi còn hóa đơn trả về. Vai trò kế toán kênh không có quyền
    # xóa DocType này: guard + hai chốt trên đã thay cho quyền đó.
    frappe.delete_doc(DT, name, ignore_permissions=True)
    return {"deleted": name}


# ═══════════════════════════════════════════════════════════════════════════
# HÓA ĐƠN TRẢ VỀ
# ═══════════════════════════════════════════════════════════════════════════

def _ke_hoach_nhieu(invoices, can, bo_qua=None):
    """{hóa đơn gốc: (kế hoạch, còn thiếu, dòng gốc)} cho nhiều hóa đơn, BA truy vấn tổng.

    `bo_qua` = phiếu trả không tính vào "đã trả" (bản nháp đang được chia lại).
    """
    invoices = [i for i in invoices if i]
    if not invoices or not can:
        return {}
    dong = frappe.db.sql(
        """SELECT parent, name, item_code, qty, conversion_factor, uom, rate, idx
        FROM `tabSales Invoice Item`
        WHERE parent IN %(inv)s AND parenttype = 'Sales Invoice' AND item_code IN %(items)s
        ORDER BY parent, idx""",
        {"inv": tuple(invoices), "items": tuple(can)}, as_dict=True)
    p = {"inv": tuple(invoices), "bq": cstr(bo_qua)}
    # Trần đếm MỌI phiếu trả chưa hủy, kể cả nháp — xem docstring `thu_hoi_phan_bo`.
    tra = frappe.db.sql(
        """SELECT r.return_against AS goc, it.sales_invoice_item, it.item_code,
               ABS(it.qty) AS qty, ABS(it.stock_qty) AS stock_qty
        FROM `tabSales Invoice` r
        INNER JOIN `tabSales Invoice Item` it ON it.parent = r.name AND it.parenttype = 'Sales Invoice'
        WHERE r.return_against IN %(inv)s AND r.is_return = 1 AND r.docstatus < 2
          AND r.name != %(bq)s""", p, as_dict=True)
    uoms = {r.uom for r in dong if r.uom}
    nguyen = set(frappe.get_all("UOM", filters={"name": ["in", list(uoms)], "must_be_whole_number": 1},
                                pluck="name")) if uoms else set()
    precision = cint(frappe.get_precision("Sales Invoice Item", "qty")) or 3
    out = {}
    for inv in invoices:
        rows = [dict(r) for r in dong if r.parent == inv]
        da_dong, da_ma = {}, {}
        for t in tra:
            if t.goc != inv:
                continue
            if t.sales_invoice_item:
                da_dong[t.sales_invoice_item] = da_dong.get(t.sales_invoice_item, 0.0) + flt(t.qty)
            da_ma[t.item_code] = da_ma.get(t.item_code, 0.0) + flt(t.stock_qty)
        plan, thieu = phan_bo(can, rows, da_dong, da_ma, precision, nguyen)
        out[inv] = (plan, thieu, rows)
    return out


@frappe.whitelist()
def ung_vien_hoa_don(name, tim=None, moi_diem=0, page=1):
    """MỌI hóa đơn bán đã ghi sổ của ĐÚNG khách + ĐÚNG điểm giao của lô — để chọn hóa đơn gốc.

    Liệt kê HẾT (50 tờ một trang, mới nhất trước), KHÔNG lọc theo mã đã kiểm: kế toán nhìn
    số tiền / số HĐĐT / PO / ngày mà chọn. Mỗi dòng kèm "nhận được bao nhiêu" trong số đang
    cần trả; tờ không nhận được gì VẪN hiện (biết là có tờ đó) — chỉ khóa nút lập, kèm lý do.
    `moi_diem=1`: mở ra mọi điểm của khách, khi hàng giao điểm khác rồi siêu thị gom về đây trả.
    `tim`: số hóa đơn / PO / số HĐĐT.

    SQL thô: lọc + đếm + phân trang một lượt, kèm số đã trả về của từng tờ (GROUP BY).
    """
    guard_sales_any()
    doc = frappe.get_doc(DT, name)
    can = con_can(so_can(doc), hoa_don_tra(name))
    page = max(1, cint(page))
    p = {"c": doc.company, "cu": doc.customer, "addr": cstr(doc.shipping_address_name),
         "lim": UNG_VIEN_TRANG, "off": (page - 1) * UNG_VIEN_TRANG}
    conds = ["si.docstatus = 1", "si.is_return = 0", "si.company = %(c)s", "si.customer = %(cu)s"]
    if not cint(moi_diem):
        conds.append("si.shipping_address_name = %(addr)s")
    so_hddt = f"si.`{SI_NO_FIELD}`" if frappe.db.has_column("Sales Invoice", SI_NO_FIELD) else "NULL"
    q = cstr(tim).strip()
    if q:
        p["q"] = f"%{q}%"
        conds.append(f"(si.name LIKE %(q)s OR {po_column()} LIKE %(q)s OR {so_hddt} LIKE %(q)s)")
    where = " AND ".join(conds)
    total = cint(frappe.db.sql(f"SELECT COUNT(*) FROM `tabSales Invoice` si WHERE {where}", p)[0][0])
    ten_mt = ("(SELECT ms.store_name FROM `tabMT Store` ms WHERE ms.address = si.shipping_address_name "
              "AND ms.customer = si.customer LIMIT 1)") if frappe.db.table_exists("MT Store") else "NULL"
    rows = frappe.db.sql(
        f"""SELECT si.name, si.posting_date, si.customer, si.customer_name, si.shipping_address_name,
               {ten_mt} AS ten_diem, a.address_title, a.address_line1, a.city,
               si.grand_total, si.outstanding_amount, {po_column()} AS po, {so_hddt} AS so_hddt,
               (IFNULL(si.shipping_address_name, '') = %(addr)s) AS cung_diem
        FROM `tabSales Invoice` si
        LEFT JOIN `tabAddress` a ON a.name = si.shipping_address_name
        WHERE {where}
        ORDER BY si.posting_date DESC, si.name DESC
        LIMIT %(lim)s OFFSET %(off)s""", p, as_dict=True)
    names = [r.name for r in rows]
    da_tra = {}
    if names:
        da_tra = {r.goc: flt(r.tien) for r in frappe.db.sql(
            """SELECT return_against AS goc, SUM(ABS(grand_total)) AS tien FROM `tabSales Invoice`
            WHERE is_return = 1 AND docstatus = 1 AND return_against IN %(inv)s
            GROUP BY return_against""", {"inv": tuple(names)}, as_dict=True)}
    kh = _ke_hoach_nhieu(names, can) if can else {}
    for r in rows:
        plan, _thieu, dong = kh.get(r.name, ([], {}, []))
        nhan = {}
        for x in plan:
            nhan[x["item_code"]] = nhan.get(x["item_code"], 0.0) + flt(x["stock_qty"])
        gia = {d["name"]: flt(d["rate"]) / (flt(d["conversion_factor"]) or 1.0) for d in dong}
        _str_dates(r)
        r["cung_diem"] = cint(r.cung_diem)
        r["da_tra"] = da_tra.get(r.name, 0.0)
        r["nhan"] = nhan
        r["phu"] = sum(nhan.values())
        r["uoc_tien"] = sum(flt(x["stock_qty"]) * gia.get(x["src"], 0.0) for x in plan)
        r["dong_khong_noi"] = sum(1 for x in plan if not x["noi"])
        r["lap_duoc"] = bool(nhan)
        r["ly_do_khoa"] = "" if nhan else (
            _("Không còn mã nào cần trả") if not can else
            _("Tờ này không có mã nào đang cần trả") if not dong else
            _("Các mã cần trả trên tờ này đã trả hết"))
    return {
        "con_can": can, "rows": rows, "total": total, "page": page,
        "has_more": (page - 1) * UNG_VIEN_TRANG + len(rows) < total,
        "moi_diem": bool(cint(moi_diem)),
        "khach": {"customer": doc.customer, "customer_name": doc.customer_name},
        "diem": {"name": doc.shipping_address_name, "ten": doc.ten_diem},
    }


def _tk_5213(company):
    """TK 5213 "Hàng bán bị trả lại" của công ty — theo SỐ tài khoản, không theo tên gõ."""
    return frappe.db.get_value("Account", {"company": company, "account_number": "5213", "is_group": 0},
                               "name") or frappe.db.get_value(
        "Account", {"company": company, "name": ["like", "5213 %"], "is_group": 0}, "name")


_BO_QUA = {"name", "idx", "parent", "parentfield", "parenttype", "doctype", "creation", "modified",
           "owner", "modified_by", "docstatus"}


def _dong_tra(mapped, plan, tk):
    """Dòng phiếu trả từ dòng `make_return_doc` đã map + kế hoạch phân bổ."""
    out = []
    for x in plan:
        base = mapped.get(x["src"])
        if not base:
            frappe.throw(_("Dòng gốc {0} không còn trên hóa đơn — tải lại danh sách ứng viên.").format(x["src"]))
        d = {k: v for k, v in base.as_dict().items() if k not in _BO_QUA and not k.startswith("__")}
        cf = flt(d.get("conversion_factor")) or 1.0
        if x["noi"]:
            d["qty"] = -flt(x["qty"])
            d["stock_qty"] = -flt(x["qty"]) * cf
        else:
            # Dòng KHÔNG NỐI, ĐVT kho: đơn giá = đơn giá dòng gốc ÷ hệ số. Bỏ mọi tham chiếu
            # dòng gốc / phiếu giao / đơn bán — dòng này không trừ vào dòng nào của ERPNext.
            d.update({"uom": d.get("stock_uom"), "conversion_factor": 1.0,
                      "qty": -flt(x["stock_qty"]), "stock_qty": -flt(x["stock_qty"]),
                      "sales_invoice_item": None, "dn_detail": None, "so_detail": None,
                      "delivery_note": None, "sales_order": None})
            for f in ("price_list_rate", "base_price_list_rate", "rate", "base_rate", "net_rate",
                      "base_net_rate", "rate_with_margin", "base_rate_with_margin", "discount_amount"):
                if d.get(f):
                    d[f] = flt(d[f]) / cf
            if d.get("margin_type") == "Amount" and d.get("margin_rate_or_amount"):
                d["margin_rate_or_amount"] = flt(d["margin_rate_or_amount"]) / cf
        # Phiếu trả `update_stock = 0` không đụng kho: tham chiếu lô / serial chép từ dòng gốc
        # không mang nghĩa gì, chỉ mời kiểm tra lô chạy trên một chứng từ không có hàng đi.
        d.update({"batch_no": None, "serial_no": None, "use_serial_batch_fields": 0,
                  "serial_and_batch_bundle": None})
        if tk:
            d["income_account"] = tk
        out.append(d)
    return out


def _gia_ban_gan_nhat(company, customer, addr, items):
    """{mã: {"rate" theo ĐVT KHO, "si", "posting_date", "taxes_and_charges"}} — dòng bán GẦN NHẤT
    (đã ghi sổ, không phải phiếu trả, không phải hàng tặng) cho ĐÚNG khách, ưu tiên ĐÚNG điểm
    giao của lô. Mã chưa từng bán cho khách thì không có mặt.

    Hóa đơn trả về không theo hóa đơn gốc vẫn phải ghi giảm theo giá siêu thị đã trả: giá bán
    gần nhất cho chính khách đó (chiết khấu chuỗi nằm sẵn trên dòng) sát hơn bảng giá chung.
    Đơn giá theo ĐVT KHO = đơn giá dòng ÷ hệ số, như dòng "không nối" của đường hóa đơn gốc.

    SQL thô: ROW_NUMBER() lấy một dòng mới nhất cho MỖI mã trong một lượt.
    """
    items = [i for i in items or [] if i]
    if not items:
        return {}
    rows = frappe.db.sql(
        """SELECT x.item_code, x.rate, x.conversion_factor, x.si, x.posting_date, x.taxes_and_charges
        FROM (
            SELECT it.item_code, it.rate, it.conversion_factor, si.name AS si, si.posting_date,
                   si.taxes_and_charges,
                   ROW_NUMBER() OVER (PARTITION BY it.item_code
                       ORDER BY (IFNULL(si.shipping_address_name, '') = %(addr)s) DESC,
                                si.posting_date DESC, si.creation DESC, it.idx ASC) AS rn
            FROM `tabSales Invoice Item` it
            INNER JOIN `tabSales Invoice` si ON si.name = it.parent
            WHERE it.parenttype = 'Sales Invoice' AND it.item_code IN %(items)s
              AND IFNULL(it.is_free_item, 0) = 0 AND it.qty > 0
              AND si.docstatus = 1 AND si.is_return = 0
              AND si.company = %(c)s AND si.customer = %(cu)s
        ) x
        WHERE x.rn = 1""",
        {"items": tuple(items), "addr": cstr(addr), "c": company, "cu": customer}, as_dict=True)
    return {r.item_code: {"rate": flt(r.rate) / (flt(r.conversion_factor) or 1.0), "si": r.si,
                          "posting_date": cstr(r.posting_date), "taxes_and_charges": r.taxes_and_charges}
            for r in rows}


def _mau_thue(company, gia):
    """Mẫu thuế của hóa đơn trả về không theo hóa đơn gốc: mẫu của hóa đơn bán MỚI NHẤT vừa cho
    giá (cùng khách → cùng cách tính thuế), không có thì mẫu mặc định của công ty."""
    co = [g for g in (gia or {}).values() if g.get("taxes_and_charges")]
    if co:
        return max(co, key=lambda g: cstr(g.get("posting_date")))["taxes_and_charges"]
    return frappe.db.get_value("Sales Taxes and Charges Template",
                               {"company": company, "is_default": 1, "disabled": 0}, "name")


def _dong_tra_tu_do(can, dvt, gia, tk, giu=None):
    """Dòng hóa đơn trả về KHÔNG theo hóa đơn gốc: mỗi mã một dòng theo ĐVT KHO — đúng số đã kiểm,
    không quy ra thùng (không có dòng gốc nào phải giữ ĐVT). Đơn giá theo ĐVT kho, lấy lần lượt:

      `giu`  đơn giá đang có trên bản nháp (người soát sửa trên Desk rồi thì GIỮ khi cập nhật);
      `gia`  lần bán gần nhất cho khách (`_gia_ban_gan_nhat`);
      không có cả hai thì để trống — ERPNext lấy theo bảng giá của khách lúc dựng.
    """
    giu = giu or {}
    out = []
    for it, sl in (can or {}).items():
        d = {"item_code": it, "qty": -flt(sl), "stock_qty": -flt(sl), "conversion_factor": 1.0}
        if dvt.get(it):
            d["uom"] = d["stock_uom"] = dvt[it]
        if it in giu:
            d["rate"] = d["price_list_rate"] = flt(giu[it])
        elif (gia.get(it) or {}).get("rate"):
            d["rate"] = d["price_list_rate"] = flt(gia[it]["rate"])
        if tk:
            d["income_account"] = tk
        out.append(d)
    return out


def _dung_tra_tu_do(doc, can, posting_date=None):
    """(Sales Invoice trả về KHÔNG theo hóa đơn gốc — chưa insert, bảng giá đã dùng, TK 5213)."""
    gia = _gia_ban_gan_nhat(doc.company, doc.customer, doc.shipping_address_name, list(can))
    tk = _tk_5213(doc.company)
    si = frappe.new_doc("Sales Invoice")
    si.company = doc.company
    si.customer = doc.customer
    si.is_return = 1
    si.is_debit_note = 0
    si.ignore_pricing_rule = 1  # như make_return_doc: đơn giá đặt sẵn, quy tắc giá không được đè
    si.update_stock = 0  # quy ước Client Script: hàng vào kho bằng phiếu kho riêng
    si.set_posting_time = 1
    si.posting_date = posting_date or nowdate()
    if doc.shipping_address_name:
        si.shipping_address_name = doc.shipping_address_name
    si.taxes_and_charges = _mau_thue(doc.company, gia)
    if frappe.db.exists("Print Heading", "Credit Note"):
        si.select_print_heading = "Credit Note"
    si.set(SI_FIELD, doc.name)
    si.remarks = _("Trả hàng — thu hồi {0} (không theo hóa đơn gốc)").format(doc.name)
    for d in _dong_tra_tu_do(can, {r.item_code: r.stock_uom for r in doc.items or []}, gia, tk):
        si.append("items", d)
    # Khách (địa chỉ, TK công nợ), dòng (tên, TK, thuế từng mặt hàng, giá bảng cho mã chưa có giá)
    # và dòng THUẾ chép từ mẫu: chỉ bản `for_validate=False` chép dòng thuế, insert() chạy bản kia.
    si.set_missing_values()
    return si, gia, tk


@frappe.whitelist()
def tao_hoa_don_tra(name, sales_invoice=None, posting_date=None):
    """Lập hóa đơn trả về NHÁP cho phần đã kiểm mà chưa có phiếu trả.

    Không truyền `sales_invoice` (mặc định): một tờ KHÔNG theo hóa đơn gốc cho TOÀN BỘ phần đó —
    xem docstring đầu file. Có `sales_invoice`: trả theo đúng hóa đơn gốc đó, phần tờ đó nhận được.
    """
    guard_sales_any()
    doc = frappe.get_doc(DT, name)
    if not cint(doc.da_chot):
        frappe.throw(_("Chốt phiếu kiểm trước — hóa đơn trả về dựng trên số đã chốt."))
    if cint(doc.khong_lap_hd):
        frappe.throw(_("KTT đã kết luận lô này không lập hóa đơn trả về."))
    if not frappe.get_meta("Sales Invoice").has_field(SI_FIELD):
        frappe.throw(_("Site chưa có ô {0} trên Sales Invoice — quản trị chạy bench migrate.").format(SI_FIELD))
    can = con_can(so_can(doc), hoa_don_tra(name))
    if not can:
        frappe.throw(_("Số đã kiểm đã có đủ hóa đơn trả về."))
    if not sales_invoice:
        si, gia, tk = _dung_tra_tu_do(doc, can, posting_date)
        si.insert()  # KHÔNG ignore_permissions: quyền tạo Sales Invoice của chính người bấm
        return {
            "name": si.name, "route": f"/desk/sales-invoice/{quote(si.name)}", "so_dong": len(si.items),
            "tu_do": True, "gia_ban_gan_nhat": sum(1 for it in can if it in gia),
            "thieu_gia": [d.item_code for d in si.items if not flt(d.rate)],
            "tk_5213": tk or "", "thu_hoi": get_thu_hoi(name),
        }
    goc = frappe.db.get_value("Sales Invoice", sales_invoice,
                              ["docstatus", "is_return", "customer", "company"], as_dict=True)
    if not goc or cint(goc.docstatus) != 1 or cint(goc.is_return):
        frappe.throw(_("{0} không phải hóa đơn bán đã ghi sổ.").format(sales_invoice))
    if goc.customer != doc.customer or goc.company != doc.company:
        frappe.throw(_("Hóa đơn {0} không cùng khách / công ty với lô {1}.").format(sales_invoice, name))
    plan, _thieu, _rows = _ke_hoach_nhieu([sales_invoice], can).get(sales_invoice, ([], {}, []))
    if not plan:
        frappe.throw(_("Hóa đơn {0} không còn mặt hàng nào trả được cho lô này (đã trả hết, hoặc không "
                       "có mã cần trả). Chọn hóa đơn khác.").format(sales_invoice))

    from erpnext.controllers.sales_and_purchase_return import make_return_doc

    si = make_return_doc("Sales Invoice", sales_invoice)
    mapped = {r.sales_invoice_item: r for r in si.items}
    tk = _tk_5213(doc.company)
    si.set("items", [])
    for d in _dong_tra(mapped, plan, tk):
        si.append("items", d)
    si.set(SI_FIELD, doc.name)
    si.set_posting_time = 1
    si.posting_date = posting_date or nowdate()
    # Quy ước Client Script: phiếu trả không trừ/nhập kho; hàng vào kho bằng phiếu kho riêng.
    si.update_stock = 0
    si.remarks = _("Trả hàng — thu hồi {0}").format(doc.name)
    si.insert()  # KHÔNG ignore_permissions: quyền tạo Sales Invoice của chính người bấm
    return {
        "name": si.name, "route": f"/desk/sales-invoice/{quote(si.name)}",
        "so_dong": len(si.items), "dong_khong_noi": sum(1 for x in plan if not x["noi"]),
        "tk_5213": tk or "", "thu_hoi": get_thu_hoi(name),
    }


def _hoa_don_nhap_cua(name, sales_invoice):
    si = frappe.get_doc("Sales Invoice", sales_invoice)
    if cstr(si.get(SI_FIELD)) != name or not cint(si.is_return):
        frappe.throw(_("{0} không phải hóa đơn trả về của lô {1}.").format(sales_invoice, name))
    if cint(si.docstatus) != 0:
        frappe.throw(_("{0} đã ghi sổ — hủy trên Desk, app không đụng chứng từ đã ghi sổ.").format(sales_invoice))
    if not frappe.has_permission("Sales Invoice", "write", si):
        frappe.throw(_("Bạn không có quyền sửa hóa đơn {0}.").format(sales_invoice), frappe.PermissionError)
    return si


@frappe.whitelist()
def cap_nhat_hoa_don(name):
    """Chia LẠI các hóa đơn trả về NHÁP theo số đã kiểm hiện tại (sau khi mở lại + sửa).

    Bản đã ghi sổ giữ nguyên và được trừ trước. Rồi tới bản nháp NỐI hóa đơn gốc (theo thứ tự
    lập — bị trần từng dòng gốc chặn), cuối cùng bản nháp KHÔNG theo hóa đơn gốc nhận hết phần
    còn lại, GIỮ đơn giá người soát đã sửa trên Desk. Làm ngược thì bản tự do nuốt hết, bản nối
    bị xóa oan. Bản nháp không còn gì để trả thì XÓA — bản app dựng, chưa có số, chưa vào sổ.
    """
    guard_sales_any()
    doc = frappe.get_doc(DT, name)
    if not cint(doc.da_chot):
        frappe.throw(_("Chốt phiếu kiểm trước khi cập nhật hóa đơn trả về."))
    hd = hoa_don_tra(name)
    nhap = [h for h in hd if h["docstatus"] == 0]
    if not nhap:
        frappe.throw(_("Không có hóa đơn trả về nháp nào để cập nhật."))
    can = con_can(so_can(doc), [h for h in hd if h["docstatus"] == 1])
    tk = _tk_5213(doc.company)
    ket_qua = []
    from erpnext.controllers.sales_and_purchase_return import make_return_doc

    ds = [_hoa_don_nhap_cua(name, h["name"]) for h in nhap]
    ds.sort(key=lambda x: 0 if x.return_against else 1)  # sort ổn định: giữ thứ tự lập trong nhóm
    dvt = {r.item_code: r.stock_uom for r in doc.items or []}
    for si in ds:
        if not si.return_against:
            if not can:
                frappe.delete_doc("Sales Invoice", si.name, ignore_permissions=True)
                ket_qua.append({"name": si.name, "xoa": True})
                continue
            giu = {r.item_code: flt(r.rate) / (flt(r.conversion_factor) or 1.0) for r in si.items if r.item_code}
            ma_moi = [it for it in can if it not in giu]
            gia = _gia_ban_gan_nhat(doc.company, doc.customer, doc.shipping_address_name, ma_moi) if ma_moi else {}
            si.set("items", [])
            for d in _dong_tra_tu_do(can, dvt, gia, tk, giu):
                si.append("items", d)
            si.set_missing_values()  # mã mới thêm: tên, TK, thuế từng mặt hàng, giá bảng
            si.save()
            ket_qua.append({"name": si.name, "so_dong": len(si.items), "tu_do": True})
            can = {}
            continue
        plan = []
        if can:
            plan, _t, _r = _ke_hoach_nhieu([si.return_against], can, bo_qua=si.name).get(
                si.return_against, ([], {}, []))
        if not plan:
            frappe.delete_doc("Sales Invoice", si.name, ignore_permissions=True)
            ket_qua.append({"name": si.name, "xoa": True})
            continue
        moi = make_return_doc("Sales Invoice", si.return_against)
        mapped = {r.sales_invoice_item: r for r in moi.items}
        si.set("items", [])
        for d in _dong_tra(mapped, plan, tk):
            si.append("items", d)
        si.save()
        for x in plan:
            can[x["item_code"]] = flt(can.get(x["item_code"])) - flt(x["stock_qty"])
        can = {k: v for k, v in can.items() if v > EPS}
        ket_qua.append({"name": si.name, "so_dong": len(si.items)})
    return {"ket_qua": ket_qua, "thu_hoi": get_thu_hoi(name)}


@frappe.whitelist()
def xoa_hoa_don_nhap(name, sales_invoice):
    """Xóa một hóa đơn trả về NHÁP của lô (chọn nhầm hóa đơn gốc chẳng hạn)."""
    guard_sales_any()
    si = _hoa_don_nhap_cua(name, sales_invoice)
    # Vai trò kế toán kênh không có quyền xóa Sales Invoice; chỉ xóa bản NHÁP do chính luồng
    # này dựng, đã kiểm đúng lô + quyền ghi ở `_hoa_don_nhap_cua`.
    frappe.delete_doc("Sales Invoice", si.name, ignore_permissions=True)
    return get_thu_hoi(name)


# ═══════════════════════════════════════════════════════════════════════════
# FILE ĐÍNH KÈM CỦA LÔ — proxy có guard
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist(methods=["GET"])
def xem_dinh_kem(file):
    """Nội dung file đính kèm của một lô thu hồi — của LÔ, hoặc ảnh phiếu của PHIẾU KIỂM.

    File lô lưu PRIVATE bên vanchuyen, và kế toán không có quyền DocType `Lo Thu Hoi` nên
    không mở thẳng được — guard kế toán ở đây thay cho DocPerm. Chỉ file gắn vào lô hoặc
    phiếu kiểm; file gắn chứng từ khác thì không (proxy này không phải cửa sau vào /private).
    """
    guard_sales_any()
    f = frappe.db.get_value("File", file, ["attached_to_doctype", "file_name"], as_dict=True)
    if not f or f.attached_to_doctype not in (LO, DT):
        frappe.throw(_("Không tìm thấy file."), frappe.DoesNotExistError)
    frappe.local.response.filename = f.file_name or "dinh-kem"
    frappe.local.response.filecontent = frappe.get_doc("File", file).get_content()
    frappe.local.response.type = "download"
    # Chỉ ảnh / PDF inline. File .html / .svg gắn vào lô mà mở inline trên tên miền site là
    # script chạy bằng phiên của kế toán (Frappe tự ép tải về các loại này ở /private/files).
    frappe.local.response.display_content_as = (
        "inline" if _duoi(f.file_name) in DUOI_XEM_TRONG_TAB else "attachment"
    )


# ═══════════════════════════════════════════════════════════════════════════
# HOOK Sales Invoice — giữ trạng thái phiếu kiểm khi phiếu trả đổi thẳng trên Desk
# ═══════════════════════════════════════════════════════════════════════════

def dong_bo_trang_thai(doc, method=None):
    """after_insert / on_update / on_submit / on_cancel / on_trash của Sales Invoice.

    Bọc try/except TOÀN BỘ: hỏng ở đây KHÔNG được chặn kế toán ghi sổ hóa đơn. Ghi bằng
    `db.set_value` chứ không `save()` — save() chạy lại validate của phiếu kiểm vào giữa
    giao dịch của hóa đơn, và một lỗi ở đó ném ngược vào chính lần ghi sổ đang chạy.
    `on_trash` loại chính bản đang xóa khỏi phép đếm.
    """
    try:
        name = cstr(doc.get(SI_FIELD))
        if not name or not cint(doc.get("is_return")) or not frappe.db.exists(DT, name):
            return
        k = frappe.get_doc(DT, name)
        tt = tinh_trang_thai(k, exclude_si=doc.name if method == "on_trash" else None)[0]
        vals = {"trang_thai": tt}
        if tt == XONG and not k.xong_luc:
            vals["xong_luc"] = now_datetime()
        elif tt != XONG and k.xong_luc:
            vals["xong_luc"] = None
        frappe.db.set_value(DT, name, vals, update_modified=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ketoan thu_hoi: dong_bo_trang_thai")
