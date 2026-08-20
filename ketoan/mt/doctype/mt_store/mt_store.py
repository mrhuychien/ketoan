"""MT Store — MỘT điểm siêu thị của MỘT chuỗi (master data).

Vì sao cần master riêng thay vì đọc thẳng `store_code` trên dòng bảng kê: mã
điểm trên bảng kê chỉ là một chuỗi ký tự, còn cái mình thật sự cần là "điểm này
thuộc PHÁP NHÂN nào" và "xuất hóa đơn cho điểm này thì lấy địa chỉ/MST ở đâu".
Riêng Saigon Co.op có ~120 siêu thị thành viên, LOTTE 17, Central Retail 59 —
đi đòi nợ và xuất bảng kê chiết khấu đều theo pháp nhân, không theo chuỗi.

DocType này KHÔNG sinh chứng từ kế toán nào. Nó chỉ trả lời hai câu hỏi trên.

KHÓA TỰ NHIÊN `(chain, store_code)`. Không đặt unique index ở DB — dữ liệu seed
lần đầu có thể bẩn và unique index làm hỏng cả mẻ; kiểm trong `validate()` và
tầng seed tra trước khi tạo.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import norm_text


def norm_store_code(s) -> str:
    """Mã điểm -> dạng lưu/so khớp: bỏ \\xa0, trim, KHÔNG ép sang số.

    VÌ SAO không `int()`: LOTTE dùng '01019', Fuji dùng '001'. Ép sang số là mất
    số 0 ở đầu -> '1019' không khớp với bất kỳ dòng bảng kê nào, và điểm đó im
    lặng biến mất khỏi mọi báo cáo công nợ theo siêu thị.
    """
    return norm_text(str(s or "").replace("\xa0", " "))


class MTStore(Document):
    def validate(self):
        self.store_code = norm_store_code(self.store_code)
        self.store_name = norm_text(self.store_name)
        self.vendor_code = norm_text(self.vendor_code)
        self.tax_id = norm_text(self.tax_id).replace(" ", "")

        if not self.store_code:
            frappe.throw(_("Mã điểm không được để trống"))
        if not self.store_name:
            frappe.throw(_("Tên điểm không được để trống"))

        self._check_natural_key()
        self._check_address_customer()

    def _check_natural_key(self):
        """(chuỗi, mã điểm) là DUY NHẤT — chặn nhân bản khi chạy seed lần hai.

        Thiếu chốt này thì bấm 'nạp điểm siêu thị' hai lần là có hai bản ghi cùng
        mã, và mọi phép tra 'điểm này thuộc khách nào' sẽ trả hai đáp án khác
        nhau tùy bản ghi nào được đọc trước.
        """
        dup = frappe.db.get_value(
            "MT Store",
            {"chain": self.chain, "store_code": self.store_code, "name": ("!=", self.name or "")},
            "name")
        if dup:
            frappe.throw(_("Điểm {0} của chuỗi {1} đã có rồi: {2}")
                         .format(self.store_code, self.chain, dup))

    def _check_address_customer(self):
        """Địa chỉ phải thuộc đúng khách của điểm.

        VÌ SAO chặn: `address` là nguồn buyer info khi xuất bảng kê chiết khấu.
        Gắn nhầm địa chỉ của pháp nhân khác nghĩa là in hóa đơn sai MST người
        mua — sai ở đây không chỉ là dữ liệu xấu, là hóa đơn không hợp lệ.

        Chỉ CẢNH BÁO chứ không throw khi địa chỉ không gắn với khách nào: địa chỉ
        dùng chung (kho tổng của chuỗi) là chuyện có thật.
        """
        if not (self.address and self.customer):
            return
        # SQL thô + bóc cột tay thay vì `pluck=True`: một địa chỉ có thể gắn
        # NHIỀU Dynamic Link, và ở chốt chặn hóa đơn thì đừng phụ thuộc vào một
        # tham số tiện lợi có thể đổi hành vi giữa các bản Frappe.
        rows = frappe.db.sql("""
            SELECT dl.link_name
            FROM `tabDynamic Link` dl
            WHERE dl.parenttype = 'Address' AND dl.parent = %(addr)s
              AND dl.link_doctype = 'Customer'
        """, {"addr": self.address})
        owners = [r[0] for r in rows if r and r[0]]
        if not owners:
            frappe.msgprint(_("Địa chỉ {0} không gắn với khách hàng nào — kiểm lại trước khi dùng để xuất hóa đơn.")
                            .format(self.address), indicator="orange", alert=True)
            return
        if self.customer not in owners:
            frappe.throw(_(
                "Địa chỉ {0} thuộc khách {1}, không thuộc {2}. Dùng địa chỉ này để "
                "xuất hóa đơn là ghi sai MST người mua."
            ).format(self.address, ", ".join(owners), self.customer))
