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

════════════════════════════════════════════════════════════════════════════
KIỂM HÀNG — dựng theo màn Ghi hộp của app sx
════════════════════════════════════════════════════════════════════════════

Quét / tìm mã → bàn số (tab Thùng / Hộp) → lưu NGAY từng lần. MỘT mã MỘT dòng: quét
lại mã đã có là CỘNG thêm vào dòng đó. Số lưu theo ĐVT kho; hệ số quy đổi SERVER tra
lại trên Item, không tin hệ số client gửi. Mọi lần ghi khóa hàng phiếu (`for_update`):
hai điện thoại cùng cộng vào một mã thì lượt sau đọc được lượt trước, không đè nhau.

════════════════════════════════════════════════════════════════════════════
HÓA ĐƠN TRẢ VỀ — NHÁP, đúng ERPNext v16
════════════════════════════════════════════════════════════════════════════

`make_return_doc` của hóa đơn gốc, rồi THAY bảng hàng bằng kế hoạch của
`thu_hoi_phan_bo.phan_bo` (đọc docstring ở đó: vì sao dòng trả phải giữ ĐVT của dòng
gốc khi `update_stock = 0`). Chốt thêm:

  · `return_against` BẮT BUỘC — `mt._returns_join` chỉ trừ phiếu trả có nối hóa đơn gốc;
  · `update_stock = 0` — quy ước Client Script; hàng vào kho bằng phiếu kho riêng;
  · TK doanh thu dòng trả → TK 5213 của công ty nếu có (Client Script cũng đặt vậy);
  · `update_outstanding_for_self` giữ MẶC ĐỊNH của ERPNext như `doitru.create_return`;
  · `doc.insert()` KHÔNG ignore_permissions — tôn trọng quyền tạo Sales Invoice của
    người bấm. Ghi sổ thì mở Desk (deep link): con người soát rồi ấn nút.

Hàng về từ nhiều hóa đơn gốc → nhiều phiếu trả, mỗi tờ một `return_against`: kế toán
chọn trong danh sách ứng viên (`ung_vien_hoa_don`), làm lại tới khi phủ đủ.

Quyền: mọi method `guard_sales_any()` ở dòng đầu (kế toán NPP / MT / Du lịch + KTT);
kết luận "không lập hóa đơn trả về" chỉ `guard_manager()`.
"""

import json
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, date_diff, flt, now_datetime, nowdate

from ketoan.api._guard import guard_manager, guard_sales_any, is_chief
from ketoan.api.mt import SI_NO_FIELD, _company, po_column
from ketoan.api.thu_hoi_phan_bo import (
    CHANG_KE_TOAN,
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

# Cột lô đọc sang. Tách hằng để danh sách và chi tiết không lệch nhau. Hàng do đơn vị
# vận chuyển ngoài lấy (Viettel Post / Nhất Tín): đơn vị + mã vận đơn + ngày thu
# (`ngay_hen_lay`), không còn lái xe / xe. `chi_tiet_hang` = mail siêu thị dán nguyên văn.
_LO_COLS = (
    "trang_thai", "ngay_yeu_cau", "so_phieu_sieu_thi", "ly_do", "customer", "customer_name",
    "shipping_address_name", "ten_diem", "ma_diem", "dia_chi", "sdt_diem", "nguoi_lien_he",
    "sdt_lien_he", "ghi_chu", "don_vi_thu_hoi", "ma_van_don", "ngay_hen_lay", "lay_luc", "lay_boi",
    "nhan_luc", "nhan_boi", "so_kien_du_kien", "so_kien_nhan", "gia_tri_khai", "so_dinh_kem",
    "chi_tiet_hang",
)
# Danh sách 30 lô một trang không kéo theo 30 bản mail dán (Long Text) — chỉ màn lô cần.
_LO_COLS_DS = tuple(c for c in _LO_COLS if c != "chi_tiet_hang")
# Ảnh / PDF mở trong tab; loại khác (Excel, Word, mail…) TẢI VỀ — cùng luật proxy bên vanchuyen.
DUOI_XEM_TRONG_TAB = frozenset(("jpg", "jpeg", "png", "webp", "gif", "pdf"))
_DATE_COLS = ("ngay_yeu_cau", "ngay_hen_lay", "lay_luc", "nhan_luc", "chot_luc", "xong_luc",
              "posting_date")
MAX_UNG_VIEN = 40


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


def _lo(name):
    """Bản ghi SỐNG của lô bên vanchuyen. Không có → throw."""
    _require_lo()
    cols = ", ".join(f"{_lo_col(c)} AS `{c}`" for c in _LO_COLS)
    rows = frappe.db.sql(
        f"SELECT l.name, {cols} FROM `tab{LO}` l WHERE l.name = %(n)s", {"n": name}, as_dict=True)
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


def _files(name):
    rows = frappe.get_all(
        "File", filters={"attached_to_doctype": LO, "attached_to_name": name},
        fields=["name", "file_name", "creation"], order_by="creation asc", limit_page_length=0)
    for f in rows:
        f["url"] = "/api/method/ketoan.api.thu_hoi.xem_dinh_kem?file=" + quote(f.name)
        f["ext"] = _duoi(f.file_name)
        f["is_image"] = f["ext"] in ("jpg", "jpeg", "png", "webp", "gif")
        f["creation"] = str(f.creation)
    return rows


def _duoi(ten):
    """Phần mở rộng, chữ thường, không dấu chấm: "DS.XLSX" → "xlsx"."""
    t = cstr(ten)
    return t.rsplit(".", 1)[-1].lower() if "." in t else ""


def _expr():
    """Biểu thức CHẶNG TỔNG — một chỗ, cho WHERE / GROUP BY / ORDER BY."""
    return ("(CASE WHEN k.name IS NULL THEN l.trang_thai "
            "WHEN IFNULL(k.trang_thai, '') = '' THEN %(dang_kiem)s ELSE k.trang_thai END)")


# ═══════════════════════════════════════════════════════════════════════════
# THEO DÕI THU HỒI — danh sách mọi lô
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def list_thu_hoi(chang=None, tim=None, tu_ngay=None, den_ngay=None, page=1, page_size=30):
    """MỌI lô tạo bên vanchuyen + chặng tổng; pill đếm đủ 7 chặng trên cùng bộ tìm.

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
    p = {"dang_kiem": DANG_KIEM, "xong": XONG}
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

    where = base
    chang = cstr(chang).strip() or "dang_mo"
    if chang == "dang_mo":
        where += f" AND {expr} != %(xong)s"
    elif chang in CHANG:
        p["chang"] = chang
        where += f" AND {expr} = %(chang)s"
    total = cint(frappe.db.sql(f"SELECT COUNT(*) FROM `tab{LO}` l {join} WHERE {where}", p)[0][0])

    p.update({"c%d" % i: c for i, c in enumerate(CHANG)})
    p["lim"], p["off"] = page_size, (page - 1) * page_size
    order = ", ".join("%(c{0})s".format(i) for i in range(len(CHANG)))
    cols = ", ".join(f"{_lo_col(c)} AS `{c}`" for c in _LO_COLS_DS)
    rows = frappe.db.sql(
        f"""SELECT l.name, {cols}, {expr} AS chang,
               k.tong_sl AS kiem_sl, k.so_ma AS kiem_so_ma, k.da_chot
        FROM `tab{LO}` l {join}
        WHERE {where}
        ORDER BY FIELD({expr}, {order}), l.ngay_yeu_cau ASC, l.name ASC
        LIMIT %(lim)s OFFSET %(off)s""",
        p, as_dict=True)

    hd = _tom_tat_hoa_don([r.name for r in rows])
    today = nowdate()
    for r in rows:
        _str_dates(r)
        r["tuoi"] = date_diff(today, r.ngay_yeu_cau) if r.ngay_yeu_cau and r.chang != XONG else None
        r.update(hd.get(r.name) or {"so_hd": 0, "so_hd_ghi_so": 0, "tien_hd": 0.0})
    return {
        "rows": rows, "total": total, "page": page, "page_size": page_size,
        "has_more": (page - 1) * page_size + len(rows) < total,
        "counts": counts, "chang_list": list(CHANG), "vanchuyen": True,
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
                                  "khong_lap_hd", "ly_do_khong_lap", "ket_luan_boi")}
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
        d["route"] = f"/desk/sales-invoice/{quote(h.name)}"
        out.append(d)
    return out


@frappe.whitelist()
def get_thu_hoi(name):
    """Một lô: hồ sơ bên vận chuyển (đơn vị thu hồi, mail dán, đính kèm) + phiếu kiểm + phiếu
    trả + so sánh. Cột "khai" chỉ có với lô CŨ còn bảng hàng khai bên vanchuyen."""
    guard_sales_any()
    lo = _lo(name)
    doc = frappe.get_doc(DT, name) if frappe.db.exists(DT, name) else None
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
        "hoa_don": hd,
        "so_sanh": sorted(so.values(), key=lambda x: cstr(x["item_name"])),
        "chang": tt or lo["trang_thai"],
        "chang_list": list(CHANG),
        "lech": lech,
        "con_can": con,
        "flags": {
            "bat_dau": not doc and lo["trang_thai"] == DA_NHAN,
            "sua": bool(doc) and not chot,
            "chot": bool(doc) and not chot and bool(doc.items),
            "mo_lai": chot and not co_ghi_so and (is_chief() or not cint(doc.khong_lap_hd)),
            "lap_hd": chot and not cint(doc.khong_lap_hd) and bool(con),
            "cap_nhat": chot and co_nhap and bool(lech),
            "xoa": bool(doc) and not chot and not hd,
            "ket_luan": is_chief() and bool(doc) and not hd and not cint(doc.khong_lap_hd),
        },
        "is_chief": is_chief(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# KIỂM HÀNG
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def bat_dau_kiem(name):
    """Mở phiếu kiểm cho một lô ĐÃ NHẬN HÀNG. Gọi lại khi đã có phiếu → trả phiếu cũ."""
    guard_sales_any()
    lo = _lo(name)
    if not frappe.db.exists(DT, name):
        if lo["trang_thai"] != DA_NHAN:
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
        try:
            doc.insert()  # tôn trọng DocPerm của phiếu kiểm (vai trò kế toán kênh bán hàng)
        except frappe.DuplicateEntryError:
            # Người khác vừa mở cùng lúc — khóa chính chặn bản thứ hai; dùng bản của họ.
            frappe.db.rollback()
    return get_thu_hoi(name)


def _danh_muc(codes=None):
    """Mã hàng bán được + mọi ĐVT đã khai quy đổi: [{item, ten, dvt, uoms:[{uom, he_so}]}]."""
    filters = {"disabled": 0, "is_sales_item": 1, "has_variants": 0}
    if codes is not None:
        if not codes:
            return []
        filters = {"name": ["in", list(codes)]}
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
    """Mọi thứ màn kiểm hàng cần, MỘT lượt: danh mục + bảng tra mã quét + gợi ý + phiếu.

    Tra mã quét ở MÁY (như sx `_ma_quet`): quét phải phản hồi tức thì, đợi mạng trong
    kho là mất cái lợi của việc quét. Mã thùng (ITF-14) khai trên `Item Barcode.uom`
    thì bàn số mở đúng tab Thùng.
    """
    guard_sales_any()
    doc = frappe.get_doc(DT, name)
    # Đếm MÙ tới tận payload: màn này không nhận số siêu thị khai, cả tổng lẫn từng mã.
    # Gợi ý chỉ mang MÃ, không mang số; so khai/kiểm là việc của màn lô sau khi chốt.
    lo = {k: v for k, v in _lo(name).items() if k not in _SO_KHAI}
    danh_muc = _danh_muc()
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
        "hom_nay": nowdate(),
    }


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
def ung_vien_hoa_don(name):
    """Hóa đơn gốc có thể nhận phần ĐÃ KIỂM mà chưa có phiếu trả.

    Cùng khách, cùng công ty, đã ghi sổ, có ít nhất một mã cần trả. Cùng ĐIỂM lấy hàng
    lên trước (siêu thị trả hàng ở điểm nào thì gần như luôn là hàng đã giao điểm đó),
    rồi mới tới hóa đơn gần nhất. Mỗi dòng kèm "nhận được bao nhiêu" — chọn tờ phủ nhiều
    nhất trước là ít phiếu trả nhất.
    """
    guard_sales_any()
    doc = frappe.get_doc(DT, name)
    can = con_can(so_can(doc), hoa_don_tra(name))
    if not can:
        return {"con_can": {}, "rows": []}
    p = {"c": doc.company, "cu": doc.customer, "items": tuple(can),
         "addr": cstr(doc.shipping_address_name), "lim": MAX_UNG_VIEN}
    rows = frappe.db.sql(
        f"""SELECT si.name, si.posting_date, ABS(si.grand_total) AS grand_total, si.outstanding_amount,
               si.shipping_address_name, {po_column()} AS po,
               (IFNULL(si.shipping_address_name, '') = %(addr)s) AS cung_diem
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND si.is_return = 0 AND si.company = %(c)s AND si.customer = %(cu)s
          AND EXISTS (SELECT 1 FROM `tabSales Invoice Item` it
                      WHERE it.parent = si.name AND it.parenttype = 'Sales Invoice'
                        AND it.item_code IN %(items)s)
        ORDER BY cung_diem DESC, si.posting_date DESC, si.name DESC
        LIMIT %(lim)s""", p, as_dict=True)
    kh = _ke_hoach_nhieu([r.name for r in rows], can)
    out = []
    for r in rows:
        plan, _thieu, dong = kh.get(r.name, ([], {}, []))
        nhan = {}
        for x in plan:
            nhan[x["item_code"]] = nhan.get(x["item_code"], 0.0) + flt(x["stock_qty"])
        if not nhan:
            continue
        gia = {d["name"]: flt(d["rate"]) / (flt(d["conversion_factor"]) or 1.0) for d in dong}
        _str_dates(r)
        r["cung_diem"] = cint(r.cung_diem)
        r["nhan"] = nhan
        r["phu"] = sum(nhan.values())
        r["uoc_tien"] = sum(flt(x["stock_qty"]) * gia.get(x["src"], 0.0) for x in plan)
        r["dong_khong_noi"] = sum(1 for x in plan if not x["noi"])
        out.append(r)
    return {"con_can": can, "rows": out}


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


@frappe.whitelist()
def tao_hoa_don_tra(name, sales_invoice, posting_date=None):
    """Lập hóa đơn trả về NHÁP trả cho `sales_invoice`, phần đã kiểm mà chưa có phiếu trả."""
    guard_sales_any()
    doc = frappe.get_doc(DT, name)
    if not cint(doc.da_chot):
        frappe.throw(_("Chốt phiếu kiểm trước — hóa đơn trả về dựng trên số đã chốt."))
    if cint(doc.khong_lap_hd):
        frappe.throw(_("KTT đã kết luận lô này không lập hóa đơn trả về."))
    if not frappe.get_meta("Sales Invoice").has_field(SI_FIELD):
        frappe.throw(_("Site chưa có ô {0} trên Sales Invoice — quản trị chạy bench migrate.").format(SI_FIELD))
    goc = frappe.db.get_value("Sales Invoice", sales_invoice,
                              ["docstatus", "is_return", "customer", "company"], as_dict=True)
    if not goc or cint(goc.docstatus) != 1 or cint(goc.is_return):
        frappe.throw(_("{0} không phải hóa đơn bán đã ghi sổ.").format(sales_invoice))
    if goc.customer != doc.customer or goc.company != doc.company:
        frappe.throw(_("Hóa đơn {0} không cùng khách / công ty với lô {1}.").format(sales_invoice, name))
    can = con_can(so_can(doc), hoa_don_tra(name))
    if not can:
        frappe.throw(_("Số đã kiểm đã có đủ hóa đơn trả về."))
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

    Bản đã ghi sổ giữ nguyên và được trừ trước; các bản nháp chia phần còn lại theo thứ tự
    lập. Bản nháp không còn gì để trả thì XÓA — nó là bản app dựng, chưa có số, chưa vào sổ.
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

    for h in nhap:
        si = _hoa_don_nhap_cua(name, h["name"])
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
    """Nội dung file đính kèm của một lô thu hồi.

    File lưu PRIVATE bên vanchuyen, và kế toán không có quyền DocType `Lo Thu Hoi` nên
    không mở thẳng được — guard kế toán ở đây thay cho DocPerm. Chỉ file gắn vào lô.
    """
    guard_sales_any()
    f = frappe.db.get_value("File", file, ["attached_to_doctype", "file_name"], as_dict=True)
    if not f or f.attached_to_doctype != LO:
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
