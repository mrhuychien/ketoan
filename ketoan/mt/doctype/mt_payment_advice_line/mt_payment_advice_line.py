"""MT Payment Advice Line — một dòng của bảng kê thanh toán chuỗi siêu thị.

Đây là bản GHI NHẬN dòng đọc từ file của chuỗi (WinCommerce / Central Retail /
LOTTE / Emart / Saigon Co.op), KHÔNG phải chứng từ kế toán. Việc hạch toán
(Payment Entry / Journal Entry) do con người quyết định.

Chuẩn hóa ký hiệu + số hóa đơn dùng ĐÚNG hàm của MISA Invoice Snapshot để hai
tầng đối soát không lệch nhau. Lệch chuẩn hóa = khớp hụt hóa đơn.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document

from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import (
    norm_inv_no,
    norm_series,
    norm_text,
)

# Chỉ dòng thanh toán hàng hóa mới được nối sang Sales Invoice.
ROW_KIND_PAYMENT = "Thanh toán"


def norm_series_mt(s) -> str:
    """Ký hiệu để SO KHỚP: chuẩn hóa như MISA rồi BỎ CHỮ SỐ DẠNG HÓA ĐƠN Ở ĐẦU.

    VÌ SAO: §E của hợp đồng — ngay trong MỘT file của chuỗi đã có cả 'C26THG' và
    '1C26THG' cho CÙNG một dải hóa đơn (đã gặp thật ở Central Retail, LOTTE,
    Co.op). Không bỏ chữ số đầu thì coi là hai ký hiệu khác nhau và hóa đơn
    không tìm được Sales Invoice.

    Chỉ dùng ở TẦNG KHỚP. Trường inv_series vẫn lưu NGUYÊN VĂN của file để còn
    đối soát ngược với bản in của chuỗi.
    """
    v = norm_series(s)
    if not v:
        return ""
    stripped = re.sub(r"^\d+", "", v)
    # Ký hiệu toàn chữ số là bất thường -> trả nguyên bản, không nuốt mất dữ liệu.
    return stripped or v


class MTPaymentAdviceLine(Document):
    def validate(self):
        """Chuẩn hóa + chặn nối nhầm hóa đơn.

        LƯU Ý: Frappe KHÔNG tự gọi validate() của child doctype khi lưu cha —
        MT Payment Advice.validate() phải gọi tay cho từng dòng.
        """
        self.inv_series = norm_series(self.inv_series)
        self.inv_no = norm_text(self.inv_no)
        self.inv_no_norm = norm_inv_no(self.inv_no)
        self.store_code = norm_text(self.store_code)
        self.store_name = norm_text(self.store_name)
        self.doc_no = norm_text(self.doc_no)
        self.match_method = norm_text(self.match_method)

        if self.sales_invoice and self.row_kind != ROW_KIND_PAYMENT:
            # BẪY TIỀN THẬT: dòng chiết khấu của Central Retail (Doc.Type=KS) mang
            # ký hiệu hóa đơn bán ra của chính mình ('1C26THG|5656') nhưng KHÔNG
            # phải thanh toán hóa đơn đó. Nối sang Sales Invoice là đánh dấu hóa
            # đơn "đã thanh toán" trong khi thực tế chưa.
            frappe.throw(
                _("Dòng {0}: loại dòng '{1}' KHÔNG được nối Hóa đơn ERPNext. Chỉ dòng '{2}' mới được khớp.").format(
                    self.idx, self.row_kind or "", ROW_KIND_PAYMENT
                )
            )

        if not self.sales_invoice:
            # Không còn nối SI thì "cách khớp" cũ vô nghĩa. Giữ nguyên độ tin cậy
            # vì "Không khớp" là kết luận hợp lệ cho dòng chưa có hóa đơn.
            self.match_method = None
