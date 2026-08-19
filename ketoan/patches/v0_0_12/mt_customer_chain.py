"""Patch: field `custom_mt_chain` trên Customer — gán chuỗi siêu thị cho khách.

Trước đó ánh xạ khách -> chuỗi chỉ suy được từ bảng kê đã nạp, mà đó là vòng
luẩn quẩn: khách chưa có bảng kê nào thì không gán được chuỗi.

Patch còn ĐIỀN SẴN từ dữ liệu đã có: khách nào đã xuất hiện trên bảng kê với
đúng MỘT chuỗi thì gán luôn chuỗi đó. Khách bị gán nhiều chuỗi thì để trống —
máy không chọn hộ, kế toán tự quyết.

Quy tắc: THÊM FIELD MỚI = THÊM PATCH MỚI. Không có ngoại lệ.
"""

import frappe


def execute():
    from ketoan.install import setup_mt_fields

    setup_mt_fields()
    frappe.clear_cache(doctype="Customer")

    if not frappe.db.has_column("Customer", "custom_mt_chain"):
        return
    if not frappe.db.table_exists("MT Payment Advice"):
        return

    rows = frappe.db.sql("""
        SELECT customer, chain, COUNT(*) AS n
        FROM `tabMT Payment Advice`
        WHERE IFNULL(customer, '') != '' AND IFNULL(chain, '') != ''
        GROUP BY customer, chain
    """, as_dict=True)

    by_cus = {}
    for r in rows:
        by_cus.setdefault(r.customer, set()).add(r.chain)

    n = 0
    for cus, chains in by_cus.items():
        if len(chains) != 1:
            continue   # nhiều chuỗi -> để trống, người quyết
        if frappe.db.get_value("Customer", cus, "custom_mt_chain"):
            continue   # đã có giá trị -> không đè
        frappe.db.set_value("Customer", cus, "custom_mt_chain",
                            next(iter(chains)), update_modified=False)
        n += 1

    frappe.db.commit()
    frappe.logger().info(f"ketoan: gán chuỗi MT cho {n} khách hàng (v0_0_12)")
