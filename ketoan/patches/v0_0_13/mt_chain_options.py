"""Patch: nới options `Customer.custom_mt_chain` — thêm AEON, Fuji, Mega Market.

VÌ SAO PHẢI CÓ PATCH RIÊNG dù chỉ đổi danh sách options: `create_custom_fields`
chỉ TẠO field lần đầu, nó KHÔNG cập nhật `options` của field đã tồn tại. Site đã
chạy v0_0_12 sẽ giữ nguyên 5 chuỗi cũ, và khi kế toán chọn 'AEON' cho một khách
thì Frappe từ chối ở tầng validate với thông báo khó hiểu. Quy ước của dự án:
THÊM/ĐỔI FIELD = THÊM PATCH MỚI. Không có ngoại lệ.

Patch KHÔNG đụng vào giá trị đã gán của khách nào — chỉ mở rộng danh sách chọn.

`MT Payment Advice.chain` không cần patch: nó là field CHUẨN trong DocType JSON,
`bench migrate` tự đồng bộ options khi nạp lại JSON.
"""

import frappe


def execute():
    from ketoan.install import MT_CHAIN_OPTIONS, check_chain_options, setup_mt_fields

    # Tạo field nếu site chưa có (cài mới), rồi mới nói chuyện cập nhật options.
    setup_mt_fields()

    name = frappe.db.get_value("Custom Field",
                               {"dt": "Customer", "fieldname": "custom_mt_chain"}, "name")
    if name:
        current = frappe.db.get_value("Custom Field", name, "options")
        if current != MT_CHAIN_OPTIONS:
            frappe.db.set_value("Custom Field", name, "options", MT_CHAIN_OPTIONS,
                                update_modified=False)
            frappe.logger().info(
                "ketoan: nới options custom_mt_chain %r -> %r (v0_0_13)"
                % (current, MT_CHAIN_OPTIONS))

    frappe.clear_cache(doctype="Customer")
    frappe.clear_cache(doctype="MT Payment Advice")

    # Ba nơi khai danh sách chuỗi phải khớp. Lệch thì GHI LOG chứ không throw:
    # làm chết `bench migrate` vì một danh sách Select là đổi một lỗi nhỏ thành
    # site không lên được. Bộ hồi quy docs/mt/verified/regression_check.py mới là
    # chỗ chặn cứng, và nó chạy trước khi commit.
    for problem in check_chain_options() or []:
        frappe.log_error(problem, "ketoan: danh sách chuỗi MT lệch (v0_0_13)")

    frappe.db.commit()
