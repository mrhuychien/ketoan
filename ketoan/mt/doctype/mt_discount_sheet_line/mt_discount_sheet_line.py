"""MT Discount Sheet Line — MỘT hóa đơn trên bảng kê chiết khấu."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_inv_no,
    norm_series,
    norm_text,
)


class MTDiscountSheetLine(Document):
    def validate(self):
        self.inv_series = norm_series(self.inv_series)
        self.inv_no = norm_text(self.inv_no)
        self.inv_no_norm = norm_inv_no(self.inv_no)
        if not self.inv_no:
            frappe.throw(_("Dòng {0}: thiếu số hóa đơn").format(self.idx))

        # GIỮ NGUYÊN DẤU: dòng hàng trả là số âm và phải trừ vào tổng. Mẫu BKCK
        # thật của LOTTE (kỳ 3.2026) có hai dòng âm — abs() ở đây là cộng thêm
        # thay vì trừ đi, sai đúng hai lần số đó.
        self.total_amount = flt(self.amount_before_vat) + flt(self.vat_amount)
