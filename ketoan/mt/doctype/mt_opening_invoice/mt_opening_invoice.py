"""MT Opening Invoice — một dòng CÒN NỢ trong bản số dư đầu kỳ.

Bảng con thuần dữ liệu. Mọi luật nằm ở cha (`MT Opening Balance`): dòng nhóm
`co_hoa_don` phải nối được hóa đơn hoặc được người đánh dấu bỏ qua thì cha mới
chốt được.
"""

from frappe.model.document import Document


class MTOpeningInvoice(Document):
    pass
