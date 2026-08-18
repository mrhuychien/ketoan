"""MT Payment Advice — bảng kê thanh toán của MỘT chuỗi siêu thị cho MỘT kỳ.

Phạm vi cố ý HẸP: chỉ GHI NHẬN dòng đọc từ file + đánh dấu kết quả đối soát.
DocType này TUYỆT ĐỐI không tạo/sửa/hủy Payment Entry, Journal Entry hay bất kỳ
chứng từ kế toán nào — con người quyết định hạch toán sau khi xem bảng kê.

MỘT FILE ≠ MỘT BẢN GHI: một file có thể chứa nhiều kỳ thanh toán (LOTTE có 2
Payment Date trong cùng file; Co.op có 8 sheet = 8 lần thanh toán riêng). Mỗi kỳ
phải là MỘT MT Payment Advice riêng, nếu không thì gộp nhầm tiền của hai kỳ.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ketoan.misa_integration.doctype.misa_invoice_snapshot.misa_invoice_snapshot import norm_text

# Ánh xạ loại dòng -> trường tổng. Dòng "Khác" gộp chung với "Ghi giảm" ở
# total_other: cả hai đều là khoản chưa phân loại chắc chắn, để kế toán soi tay.
_KIND_TO_TOTAL = {
    "Thanh toán": "total_payment",
    "Chiết khấu": "total_discount",
    "Phí": "total_fee",
    "Ghi giảm": "total_other",
    "Khác": "total_other",
}

_TOTAL_FIELDS = ("total_payment", "total_discount", "total_fee", "total_other")


class MTPaymentAdvice(Document):
    def validate(self):
        self.advice_no = norm_text(self.advice_no)
        self.file_name = norm_text(self.file_name)
        if not self.status:
            self.status = "Nháp"

        self._validate_lines()
        self._compute_totals()
        self._warn_declared_mismatch()
        self._validate_status()

    def _validate_lines(self):
        """Frappe KHÔNG tự chạy validate() của child doctype — phải gọi tay.

        Nếu không gọi, inv_no_norm rỗng và mọi phép khớp hóa đơn sẽ trượt trong im
        lặng (khớp hụt = báo "chưa thanh toán" cho hóa đơn đã được trả).
        """
        for row in self.lines or []:
            row.validate()

    def _compute_totals(self):
        """Cộng tổng theo LOẠI DÒNG, giữ nguyên dấu mà tầng đọc file đã ghi.

        KHÔNG dùng abs() và KHÔNG đảo dấu ở đây: mỗi chuỗi một quy ước dấu
        (Central Retail/Emart để hàng hóa ÂM, LOTTE để hàng hóa DƯƠNG). Dấu là
        chốt để đối chiếu với dòng tổng do chính chuỗi in trong file — đổi dấu ở
        tầng này là mất chốt đối chiếu.
        """
        totals = {f: 0.0 for f in _TOTAL_FIELDS}
        for row in self.lines or []:
            field = _KIND_TO_TOTAL.get(row.row_kind)
            if not field:
                # row_kind là trường bắt buộc; tới đây mà rỗng nghĩa là dữ liệu
                # nhập sai -> báo lỗi chứ không âm thầm bỏ tiền ra khỏi tổng.
                frappe.throw(_("Dòng {0}: chưa chọn Loại dòng.").format(row.idx))
            totals[field] += flt(row.total_amount)

        for field, value in totals.items():
            setattr(self, field, value)

    def _warn_declared_mismatch(self):
        """So tổng đọc được với SỐ KIỂM TRA do chính chuỗi in trong file.

        CẢNH BÁO chứ không chặn: Co.op làm tròn chiết khấu ở cấp dòng và tiền
        thanh toán ở cấp nhóm độc lập nhau nên lệch ±1..3 đồng là BÌNH THƯỜNG và
        đã được xác minh trên file thật. Chặn cứng ở đây sẽ khóa nghiệp vụ đúng;
        ngược lại lệch lớn thì kế toán phải thấy ngay. Con người quyết định.
        """
        checks = (
            (self.declared_total_payment, self.total_payment, _("Tổng thanh toán")),
            (self.declared_total_discount, self.total_discount, _("Tổng chiết khấu")),
        )
        for declared, computed, label in checks:
            if not declared:
                continue  # không có số kiểm tra trong file -> không có gì để so
            diff = flt(declared) - flt(computed)
            if diff:
                frappe.msgprint(
                    _("{0}: file ghi {1}, cộng từ các dòng ra {2} — lệch {3}. Kiểm tra trước khi đánh dấu đã đối chiếu.").format(
                        label, flt(declared), flt(computed), diff
                    ),
                    title=_("Lệch số kiểm tra"),
                    indicator="orange",
                )

    def _validate_status(self):
        """'Đã ghi nhận' là trạng thái con người đã chốt — bắt buộc đã đối chiếu.

        Không tự tick 'reconciled' hộ kế toán ở bất kỳ nhánh nào.
        """
        if self.status == "Đã ghi nhận" and not self.reconciled:
            frappe.throw(_("Chưa tick 'Đã đối chiếu khớp' thì không được chuyển trạng thái 'Đã ghi nhận'."))
