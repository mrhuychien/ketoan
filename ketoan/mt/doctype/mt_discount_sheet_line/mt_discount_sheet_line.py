"""MT Discount Sheet Line — MỘT hóa đơn trên bảng kê chiết khấu."""

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

        # KHÔNG chặn `inv_no` rỗng Ở ĐÂY. Dòng chỉ nhìn thấy chính nó, mà quy tắc
        # đúng lại là quy tắc về CẢ BẢNG KÊ: hoặc mọi dòng có số hóa đơn (chuỗi
        # chốt theo hóa đơn), hoặc không dòng nào có (Emart chốt gộp cả kỳ trên
        # `All-Store Thiso Retail`). Chặn ở cấp dòng thì bảng kê Emart — hình
        # dạng thật của chứng từ — không bao giờ ghi được, mà mọi phép kiểm
        # ngoại tuyến vẫn xanh vì chúng dựng kế hoạch chứ không ghi.
        #
        # Quy tắc đồng nhất nằm ở `MTDiscountSheet._check_invoice_numbers`.

        # GIỮ NGUYÊN DẤU: dòng hàng trả là số âm và phải trừ vào tổng. Mẫu BKCK
        # thật của LOTTE (kỳ 3.2026) có hai dòng âm — abs() ở đây là cộng thêm
        # thay vì trừ đi, sai đúng hai lần số đó.
        self.total_amount = flt(self.amount_before_vat) + flt(self.vat_amount)
