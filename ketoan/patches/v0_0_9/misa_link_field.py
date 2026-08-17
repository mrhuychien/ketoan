"""Patch: tạo `custom_misa_link` và mọi custom field MISA còn thiếu.

Bẫy đã sập: patch v0_0_6 tạo bộ custom field MISA, nhưng Frappe chỉ chạy mỗi
patch ĐÚNG MỘT LẦN. Thêm field mới vào MISA_CUSTOM_FIELDS ở lần sửa sau thì
site đã migrate KHÔNG bao giờ nhận được — truy vấn field đó gãy với
"Unknown column ... in 'SELECT'".

Quy tắc từ nay: THÊM FIELD MỚI = THÊM PATCH MỚI. Không có ngoại lệ.
"""

import frappe


def execute():
    from ketoan.install import setup_misa_integration

    setup_misa_integration()
    frappe.logger().info("ketoan: đồng bộ custom field MISA (v0_0_9)")
