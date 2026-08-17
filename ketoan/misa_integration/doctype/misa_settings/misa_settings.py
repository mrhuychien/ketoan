"""MISA Settings — cấu hình kết nối meInvoice (Single).

Credential nằm ở fieldtype Password (Frappe tự mã hóa trong bảng __Auth).
CẤM đưa username/password/appid vào site_config.json hoặc log ra error_log.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class MISASettings(Document):
    def validate(self):
        for f in ("base_url_official", "base_url_webapp"):
            v = (self.get(f) or "").strip().rstrip("/")
            if v and not v.startswith("https://"):
                frappe.throw(_("{0} phải bắt đầu bằng https://").format(self.meta.get_label(f)))
            self.set(f, v)

        if self.taxcode:
            # MST gõ tay hay dính khoảng trắng / gạch nối lạ.
            self.taxcode = self.taxcode.strip()

        if self.inv_series_list:
            lines = [x.strip().upper() for x in self.inv_series_list.splitlines() if x.strip()]
            # Bỏ trùng, giữ thứ tự nhập.
            seen, out = set(), []
            for x in lines:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
            self.inv_series_list = "\n".join(out)

        if (self.lookback_days or 0) < 1:
            self.lookback_days = 1
        if (self.poll_interval_min or 0) < 5:
            self.poll_interval_min = 5
        if (self.amount_tolerance or 0) < 0:
            self.amount_tolerance = 0

    def series_list(self) -> list:
        """Danh sách ký hiệu hóa đơn đang dùng (đã chuẩn hóa)."""
        return [x.strip().upper() for x in (self.inv_series_list or "").splitlines() if x.strip()]

    def has_appid(self) -> bool:
        """Có AppID = dùng được bộ Open API chính thức."""
        try:
            return bool((self.get_password("appid", raise_exception=False) or "").strip())
        except Exception:
            return False
