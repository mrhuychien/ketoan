"""Patch: field `custom_misa_no_locked` trên Sales Invoice.

VÌ SAO CẦN — cái bẫy đã đo được trước khi viết dòng code nào:

`poll_pending` có HAI vòng quét. Vòng 2 lấy mọi hóa đơn ĐÃ có số mà chưa ở
trạng thái cuối, hỏi MISA theo `custom_misa_ref_id`, rồi ghi thẳng `InvNo` trả
về vào `custom_misa_inv_no`.

Khi kế toán gán SỐ HÓA ĐƠN THAY THẾ lên một chứng từ đã ghi sổ (`misa_replace`)
mà không biết RefID của bản thay thế, ref_id trên chứng từ vẫn là ref_id của
hóa đơn ĐÃ CHẾT. Vòng 2 hỏi ref_id đó, MISA trả đúng số cũ, và số vừa gán bị
ghi đè ngược — không báo lỗi, không ai thấy, và lặp lại mỗi lần đồng bộ.

Cờ này để vòng 2 bỏ qua chứng từ đó. Nó KHÔNG bật cho hóa đơn thường: khi
`misa_replace` tìm được bản thay thế trong bảng kê MISA thì nó chuyển luôn
ref_id sang bản mới, đồng bộ tiếp tục chạy đúng và cờ để 0.

Quy tắc: THÊM FIELD MỚI = THÊM PATCH MỚI. Không có ngoại lệ.

Patch KHÔNG bật cờ cho bất kỳ hóa đơn nào. Không có hóa đơn nào đang ở tình
huống đó tại thời điểm cài (tính năng gán số thay thế ra đời cùng patch này),
và đoán hộ ở đây là tự tay tắt đồng bộ của chứng từ người ta.
"""

import frappe


def execute():
    from ketoan.install import setup_misa_integration

    setup_misa_integration()
    frappe.clear_cache(doctype="Sales Invoice")

    if not frappe.db.has_column("Sales Invoice", "custom_misa_no_locked"):
        frappe.logger().info(
            "ketoan: chưa tạo được custom_misa_no_locked — chạy lại migrate (v0_0_17)")
        return

    # Cột Check mới trên bảng có sẵn dữ liệu: MariaDB điền NULL, không phải 0.
    # `poll_pending` lọc bằng `custom_misa_no_locked = 0`, mà NULL không bằng 0
    # — để nguyên là MỌI hóa đơn cũ rơi khỏi vòng quét 2, tức tắt luôn việc phát
    # hiện hóa đơn bị hủy/bị thay thế trên toàn hệ. Đúng cái ngược lại ý đồ.
    frappe.db.sql("""
        UPDATE `tabSales Invoice`
        SET custom_misa_no_locked = 0
        WHERE custom_misa_no_locked IS NULL
    """)
    frappe.db.commit()
