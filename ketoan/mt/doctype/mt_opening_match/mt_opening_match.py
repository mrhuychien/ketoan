"""MT Opening Match — MỘT liên kết giữa một dòng số dư và một chứng từ ERPNext.

Vì sao phải có bảng riêng thay vì một field `sales_invoice` trên dòng:

    Hóa đơn MISA 5449 = 4.893.696đ
      ├─ ERPNext SI  (hàng đi)    +5.893.696
      └─ ERPNext SI  (hàng trả về) −1.000.000   <- siêu thị không nhận vì bẹp méo
                                   ─────────
                                    4.893.696   = đúng số dòng trong file

Một field chỉ giữ được một đầu. Giữ đầu nào cũng mất vế kia, và mất luôn phép
cộng chứng minh con số — phép cộng đó mới là thứ kế toán cần để tin.

Bảng con thuần dữ liệu; mọi luật nằm ở cha (`MT Opening Balance`).
"""

from frappe.model.document import Document

ROLE_SALE = "Hóa đơn gốc"
ROLE_RETURN = "Hóa đơn trả về"
ROLE_OTHER = "Khác"


class MTOpeningMatch(Document):
    pass
