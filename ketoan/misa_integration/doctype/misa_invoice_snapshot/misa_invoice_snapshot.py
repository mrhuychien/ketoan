"""MISA Invoice Snapshot — ảnh chụp 1 hóa đơn bên MISA để đối soát với Sales Invoice.

Khóa tự nhiên: (inv_series, inv_no_norm). Không đặt unique index ở DB (dữ liệu cũ
kéo về có thể bẩn, unique index làm hỏng cả mẻ import) — kiểm trong controller và
để job upsert tra trước khi tạo.
"""

import unicodedata

import frappe
from frappe import _
from frappe.model.document import Document


def norm_text(s) -> str:
    """Chuẩn hóa chuỗi trước khi so khớp: NFC + strip. Hai vế phải cùng đi qua hàm này."""
    return unicodedata.normalize("NFC", str(s or "")).strip()


def norm_series(s) -> str:
    """Ký hiệu hóa đơn: NFC + strip + upper."""
    return norm_text(s).upper()


def norm_inv_no(s) -> str:
    """Số hóa đơn: bỏ khoảng trắng và số 0 ở đầu ('00000123' → '123').

    Giữ nguyên chuỗi gốc nếu toàn số 0 hoặc không phải số (không nuốt mất dữ liệu).
    """
    v = norm_text(s).replace(" ", "")
    if not v:
        return ""
    stripped = v.lstrip("0")
    return stripped or v


class MISAInvoiceSnapshot(Document):
    def validate(self):
        self.inv_series = norm_series(self.inv_series)
        self.inv_no = norm_text(self.inv_no)
        self.inv_no_norm = norm_inv_no(self.inv_no)
        self.buyer_tax_code = norm_text(self.buyer_tax_code).replace(" ", "")
        self.transaction_id = norm_text(self.transaction_id)
        self.ref_id = norm_text(self.ref_id)

        if not self.origin:
            self.origin = "Chưa xác định"
        if not self.match_status:
            self.match_status = "Chưa xác định"
        if not self.sales_invoice:
            # Không còn nối với SI thì cách khớp/độ tin cậy cũ không còn nghĩa.
            self.match_method = None
            self.match_confidence = None

        self._check_natural_key()

    def _check_natural_key(self):
        """(ký hiệu, số hóa đơn chuẩn hóa) là duy nhất — chặn nhân bản khi job chạy lại."""
        if not (self.inv_series and self.inv_no_norm):
            return
        dup = frappe.db.get_value(
            "MISA Invoice Snapshot",
            {"inv_series": self.inv_series, "inv_no_norm": self.inv_no_norm, "name": ("!=", self.name)},
            "name",
        )
        if dup:
            frappe.throw(_("Đã có bản ghi cho hóa đơn {0} số {1}: {2}").format(self.inv_series, self.inv_no, dup))
