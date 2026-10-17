"""Patch: ô `custom_kiem_hang_thu_hoi` trên Sales Invoice cho module Thu hồi hàng.

Chạy ở [post_model_sync]: ô là Link tới `Kiem Hang Thu Hoi`, DocType đó phải được đồng
bộ xong trước. Site cài mới đi đường `after_install` → `setup_thu_hoi_fields`; patch
này cho site đã có app. Idempotent.
"""

import frappe


def execute():
    from ketoan.install import setup_thu_hoi_fields

    setup_thu_hoi_fields()
    frappe.clear_cache(doctype="Sales Invoice")
