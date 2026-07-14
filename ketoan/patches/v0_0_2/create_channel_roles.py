"""Patch: tạo các role kênh mới (NPP/MT/Du lịch...) — patch v0_0_1 đã chạy trước
khi bộ role đổi nên migrate không tạo lại. Idempotent, reuse install."""

import frappe


def execute():
    from ketoan.install import create_portal_roles, grant_settings_permissions

    create_portal_roles()
    try:
        grant_settings_permissions()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ketoan patch v0_0_2: grant settings perms")
