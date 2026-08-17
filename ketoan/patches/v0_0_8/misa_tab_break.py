"""Patch: đổi nhóm field MISA từ Section Break sang Tab Break riêng.

v0_0_6 tạo `custom_misa_section` là Section Break THU GỌN và không khai
`insert_after`. Frappe xếp nó vào giữa form Sales Invoice, làm nhóm "KẾ TOÁN"
(tên đơn vị, địa chỉ, MST, ngày/số hóa đơn, hình thức thanh toán, email nhận
hóa đơn) bị hút sang section `custom_logistic`.

v0_0_7 neo lại vị trí nhưng vẫn giữ Section Break — đặt sai lần nữa là lại
xáo trộn. Patch này đổi hẳn sang Tab Break: nhóm MISA sang tab riêng, đặt sai
thì cùng lắm nằm nhầm tab chứ không kéo theo field của ai.

Gọi thẳng setup_misa_integration() thay vì chỉ repair, để tự dựng lại
custom_misa_section nếu người dùng đã xóa tay nó đi lúc chữa cháy.

Không mất dữ liệu — chỉ đổi cách hiển thị.
"""

import frappe


def execute():
    from ketoan.install import repair_misa_field_order, setup_misa_integration

    setup_misa_integration()          # dựng lại field còn thiếu (idempotent)
    result = repair_misa_field_order()  # neo vào cuối form + ép Tab Break
    frappe.logger().info(f"ketoan: misa_tab_break → {result}")
