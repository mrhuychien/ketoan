"""Kiem Hang Thu Hoi — phiếu KIỂM HÀNG VỀ của một lô thu hồi bên `vanchuyen`.

════════════════════════════════════════════════════════════════════════════
TÊN PHIẾU = TÊN LÔ
════════════════════════════════════════════════════════════════════════════

`autoname: field:lo_thu_hoi`. Một lô chỉ có một phiếu kiểm, và hai người cùng bấm
"Bắt đầu kiểm" thì KHÓA CHÍNH chặn người thứ hai — `MT Hang Hoan` phải tự viết chốt
trùng trong `validate` vì chỗ đó cũng từng có hai người cùng bấm; ở đây cơ sở dữ
liệu làm hộ, kể cả khi hai yêu cầu đến cùng một phần nghìn giây.

`lo_thu_hoi` là Data, không Link: ketoan phải cài được trên site chưa có vanchuyen.

════════════════════════════════════════════════════════════════════════════
TRẠNG THÁI LÀ MÁY SUY
════════════════════════════════════════════════════════════════════════════

    chưa chốt                                        -> Đang kiểm
    chốt, phiếu trả chưa phủ ĐÚNG số đã kiểm          -> Đã kiểm hàng
    phủ đúng từng mã, còn phiếu trả nháp              -> Đã nhập chứng từ
    phủ đúng, mọi phiếu trả đã ghi sổ                  -> Xong
    KTT kết luận "không lập hóa đơn trả về"           -> Xong

Hàm suy ở `ketoan.api.thu_hoi_phan_bo.suy_trang_thai` (thuần, kiểm được không cần
bench). Phiếu trả gắn phiếu kiểm qua `Sales Invoice.custom_kiem_hang_thu_hoi`; kế
toán ghi sổ / hủy / xóa phiếu trả thẳng trên Desk thì hook `thu_hoi.dong_bo_trang_thai`
suy lại — không thì phiếu đứng mãi ở "Đã nhập chứng từ" trong khi việc đã xong.

════════════════════════════════════════════════════════════════════════════
ĐÃ CHỐT THÌ KHÓA DÒNG
════════════════════════════════════════════════════════════════════════════

Phiếu trả dựng trên số đã chốt. Sửa số sau lưng nó là phiếu trả nói một đằng, phiếu
kiểm nói một nẻo — chặn ở đây (cả Desk lẫn portal), muốn sửa thì "Mở lại", và mở lại
bị chặn khi đã có phiếu trả GHI SỔ.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, now_datetime

from ketoan.api.thu_hoi_phan_bo import DA_HUY, EPS, XONG, suy_trang_thai

SI_FIELD = "custom_kiem_hang_thu_hoi"


def hoa_don_tra(name, exclude=None):
    """Phiếu trả (docstatus < 2) gắn phiếu kiểm này, theo thứ tự lập.

    [{"name", "docstatus", "items": {item_code: SL ĐVT kho, dương}}]. Site chưa có cột
    (chưa migrate) → []: chưa có sợi dây thì chưa có phiếu trả nào được tính.

    SQL thô: gộp dòng theo phiếu + mã trong một lượt; đi ORM là một lần get_doc cho
    mỗi phiếu trả, mà hàm này chạy trong hook của MỌI lần lưu Sales Invoice có gắn.
    """
    if not name or not frappe.db.has_column("Sales Invoice", SI_FIELD):
        return []
    p = {"k": name}
    ex = ""
    if exclude:
        ex = "AND r.name != %(ex)s"
        p["ex"] = exclude
    rows = frappe.db.sql(
        f"""SELECT r.name, r.docstatus, r.creation, it.item_code, SUM(ABS(it.stock_qty)) AS sl
        FROM `tabSales Invoice` r
        LEFT JOIN `tabSales Invoice Item` it ON it.parent = r.name AND it.parenttype = 'Sales Invoice'
        WHERE r.`{SI_FIELD}` = %(k)s AND r.is_return = 1 AND r.docstatus < 2 {ex}
        GROUP BY r.name, r.docstatus, r.creation, it.item_code
        ORDER BY r.creation, r.name""",
        p,
        as_dict=True,
    )
    out = {}
    for r in rows:
        h = out.setdefault(r.name, {"name": r.name, "docstatus": cint(r.docstatus), "items": {}})
        if r.item_code:
            h["items"][r.item_code] = h["items"].get(r.item_code, 0.0) + flt(r.sl)
    return list(out.values())


def so_can(doc):
    """{item_code: SL đã kiểm, ĐVT kho}."""
    can = {}
    for r in doc.items or []:
        if r.item_code:
            can[r.item_code] = can.get(r.item_code, 0.0) + flt(r.qty)
    return can


def tinh_trang_thai(doc, exclude_si=None):
    """(trạng thái, lệch) suy từ phiếu kiểm + phiếu trả đang gắn."""
    return suy_trang_thai(cint(doc.da_chot), cint(doc.khong_lap_hd), so_can(doc),
                          hoa_don_tra(doc.name, exclude_si))


class KiemHangThuHoi(Document):
    def before_insert(self):
        # Lô bên vận chuyển đã HỦY yêu cầu thì không mở phiếu kiểm — kể cả tạo tay trên Desk
        # (cửa portal `bat_dau_kiem` chặn trước, và đọc lô bằng khóa). Đọc MỀM: site chưa có
        # vanchuyen thì thôi. SQL thô: bảng của app khác, không có meta khi app đó vắng mặt.
        if not self.lo_thu_hoi or not frappe.db.table_exists("Lo Thu Hoi"):
            return
        tt = frappe.db.sql("SELECT trang_thai FROM `tabLo Thu Hoi` WHERE name = %(n)s", {"n": self.lo_thu_hoi})
        if tt and tt[0][0] == DA_HUY:
            frappe.throw(_("Lô {0} đã bị bên vận chuyển HỦY yêu cầu — không mở phiếu kiểm. Hủy nhầm thì "
                           "nhờ điều phối bấm 'Khôi phục' bên app vận chuyển.").format(self.lo_thu_hoi))

    def validate(self):
        self._chuan_hoa_dong()
        self._khoa_khi_da_chot()
        self.tong_sl = sum(flt(r.qty) for r in self.items or [])
        self.so_ma = len(self.items or [])
        if cint(self.da_chot) and not self.items and not cint(self.khong_lap_hd):
            frappe.throw(_("Phiếu chưa có dòng nào — không chốt được. Hàng không về gì thì nhờ KTT "
                           "kết luận 'Không lập hóa đơn trả về'."))
        self.trang_thai = tinh_trang_thai(self)[0]
        if self.trang_thai == XONG and not self.xong_luc:
            self.xong_luc = now_datetime()
        elif self.trang_thai != XONG:
            self.xong_luc = None

    def on_trash(self):
        hd = hoa_don_tra(self.name)
        if hd:
            frappe.throw(_(
                "Phiếu kiểm {0} đang gắn hóa đơn trả về {1}. Xóa phiếu kiểm là hóa đơn trả về mất gốc — "
                "xóa hóa đơn nháp / hủy hóa đơn đã ghi sổ trước."
            ).format(self.name, ", ".join(h["name"] for h in hd)))

    def _chuan_hoa_dong(self):
        thay = {}
        for r in self.items or []:
            if not r.item_code:
                frappe.throw(_("Dòng {0}: chưa có mã hàng.").format(r.idx))
            if flt(r.qty) <= EPS:
                frappe.throw(_("Dòng {0} ({1}): số lượng phải > 0 — muốn bỏ thì xóa dòng.").format(
                    r.idx, r.item_code))
            # MỘT mã MỘT dòng: quét thêm cùng mã là CỘNG vào dòng đó (portal làm). Hai dòng
            # cùng mã thì phép so khai/kiểm và phép chia vào hóa đơn gốc phải tự cộng lại.
            if r.item_code in thay:
                frappe.throw(_("Mã {0} có ở dòng {1} và {2} — gộp vào một dòng.").format(
                    r.item_code, thay[r.item_code], r.idx))
            thay[r.item_code] = r.idx
            it = frappe.db.get_value("Item", r.item_code, ["item_name", "stock_uom"], as_dict=True)
            if not it:
                frappe.throw(_("Dòng {0}: không có mã hàng {1}.").format(r.idx, r.item_code))
            r.item_name = it.item_name
            r.stock_uom = it.stock_uom

    def _khoa_khi_da_chot(self):
        before = self.get_doc_before_save()
        if not before:
            return
        # Khách / điểm / công ty chép từ lô lúc mở và KHÔNG BAO GIỜ đổi: phiếu trả dựng
        # trên đúng khách đó, và bên vận chuyển đã khóa phía bên kia.
        for f in ("lo_thu_hoi", "company", "customer", "shipping_address_name"):
            if cstr(before.get(f)) != cstr(self.get(f)):
                frappe.throw(_("Không đổi {0} của phiếu kiểm sau khi đã mở.").format(
                    self.meta.get_label(f)))
        if not (cint(before.da_chot) and cint(self.da_chot)):
            return

        def sig(d):
            return sorted((r.item_code, round(flt(r.qty), 6)) for r in d.items or [])

        if sig(before) != sig(self):
            frappe.throw(_("Phiếu {0} đã chốt — bấm 'Mở lại' trước khi sửa số đã kiểm.").format(self.name))
