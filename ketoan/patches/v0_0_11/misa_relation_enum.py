"""Patch: cập nhật options `custom_misa_relation` theo bảng enum đã xác minh.

v0_0_10 tạo field khi còn chưa tách được "thay thế" với "điều chỉnh" nên gộp
làm một mục. Nay đã xác minh trên hóa đơn thật (§R.7): `EInvoiceStatus` chính
là trục quan hệ — 1 mới, 3 thay thế, 4 điều chỉnh, 7 bị thay thế, 8 bị điều
chỉnh. Tách hai loại ra là bắt buộc về thuế.

Dữ liệu cũ mang giá trị gộp được đưa về "Chưa xác định" để lần `poll_pending`
tới chấm lại từ enum thật, thay vì giữ một nhãn không còn nằm trong options.
"""

import frappe

OLD_TO_NEW = {
    "Hóa đơn thay thế/điều chỉnh": "Chưa xác định",
    "Bị thay thế/điều chỉnh": "Chưa xác định",
}


def execute():
    from ketoan.install import setup_misa_integration

    setup_misa_integration()
    frappe.clear_cache(doctype="Sales Invoice")

    if not frappe.db.has_column("Sales Invoice", "custom_misa_relation"):
        return

    n = 0
    for old, new in OLD_TO_NEW.items():
        rows = frappe.get_all("Sales Invoice", filters={"custom_misa_relation": old},
                              pluck="name")
        for name in rows:
            frappe.db.set_value("Sales Invoice", name, "custom_misa_relation", new,
                                update_modified=False)
            n += 1

    frappe.db.commit()
    frappe.logger().info(f"ketoan: chuẩn hóa {n} nhãn quan hệ MISA (v0_0_11)")
