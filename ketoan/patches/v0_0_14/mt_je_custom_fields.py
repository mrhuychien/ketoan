"""Patch: 4 custom field kênh MT trên `Journal Entry`.

    custom_mt_kind         Loại bút toán (Thanh toán / Chiết khấu / Phí)
    custom_mt_source_dt    DocType nguồn
    custom_mt_source_name  Bản ghi nguồn — search_index
    custom_mt_fingerprint  Vân tay chống sinh trùng — search_index

Quy tắc bất di bất dịch của repo: THÊM FIELD MỚI = THÊM PATCH MỚI.
`create_custom_fields` chỉ TẠO field lần đầu; site đã chạy sẽ không có field
nếu không có patch, và khi đó `mt_je.create_journal_entries` mất sạch khả năng
tra ngược lẫn chống trùng — bấm hai lần là hai bộ bút toán y hệt nhau.
"""

import frappe


def execute():
    from ketoan.install import MT_JE_FIELDNAMES, setup_mt_je_fields

    setup_mt_je_fields()
    frappe.clear_cache(doctype="Journal Entry")

    missing = [f for f in MT_JE_FIELDNAMES
               if not frappe.db.has_column("Journal Entry", f)]
    if missing:
        # KHÔNG throw: làm chết `bench migrate` vì mấy field truy vết là đổi một
        # lỗi nhỏ thành site không lên được. Ghi log để quản trị thấy.
        frappe.log_error(
            "Thiếu field trên Journal Entry sau khi chạy patch: %s" % ", ".join(missing),
            "ketoan: mt_je_custom_fields (v0_0_14)")
    else:
        frappe.logger().info("ketoan: đã tạo %d field MT trên Journal Entry (v0_0_14)"
                             % len(MT_JE_FIELDNAMES))

    frappe.db.commit()
