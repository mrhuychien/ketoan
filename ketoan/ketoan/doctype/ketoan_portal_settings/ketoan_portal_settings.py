"""Single DocType: cấu hình ngưỡng cho portal kế toán tác nghiệp."""

import frappe
from frappe.model.document import Document
from frappe.utils import cint


class KetoanPortalSettings(Document):
    def validate(self):
        # Rổ tuổi nợ phải tăng dần để aging hợp lệ.
        b1, b2, b3 = cint(self.aging_bucket_1), cint(self.aging_bucket_2), cint(self.aging_bucket_3)
        if not (0 < b1 < b2 < b3):
            frappe.throw("Rổ tuổi nợ phải tăng dần: 0 < rổ 1 < rổ 2 < rổ 3.")
        if cint(self.dso_window_days) <= 0:
            frappe.throw("Cửa sổ tính DSO phải lớn hơn 0.")
