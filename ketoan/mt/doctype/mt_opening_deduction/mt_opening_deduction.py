"""MT Opening Deduction — một sheet ghi giảm của file công nợ.

Sheet ghi giảm theo dõi hóa đơn mình xuất TRẢ và hóa đơn dịch vụ siêu thị xuất
cho mình. Phần `remaining` (chưa cấn trừ) mới là phần TRỪ vào nợ đầu kỳ — phần
đã cấn trừ thì bảng chính đã trừ rồi. Bỏ qua các sheet này là báo nợ cao hơn
thực tế 183.968.726đ trên bộ file mẫu.
"""

from frappe.model.document import Document


class MTOpeningDeduction(Document):
    pass
