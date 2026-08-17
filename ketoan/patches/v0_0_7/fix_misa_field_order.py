"""Patch: neo section "Hóa đơn điện tử MISA" vào CUỐI form Sales Invoice.

Bản v0_0_6 tạo section này mà không khai `insert_after`. Frappe đặt Section
Break vào giữa form, và vì nó thu gọn được nên mọi field đứng sau — gồm cả
nhóm thông tin xuất hóa đơn của kế toán — bị nuốt vào trong, nhìn như mất field.

Không mất dữ liệu: chỉ là thứ tự hiển thị. Patch này trả lại đúng chỗ.
"""

import frappe


def execute():
    from ketoan.install import repair_misa_field_order

    result = repair_misa_field_order()
    frappe.logger().info(f"ketoan: repair_misa_field_order → {result}")
