"""Quy tắc map nội dung sao kê → tài khoản đối ứng (gợi ý khi nhập sổ quỹ)."""

import frappe
from frappe.model.document import Document


class KetoanBankMapRule(Document):
    def validate(self):
        if self.keyword:
            self.keyword = self.keyword.strip()
        if self.party and not self.party_type:
            frappe.throw("Đã chọn đối tượng thì phải chọn loại đối tượng.")
