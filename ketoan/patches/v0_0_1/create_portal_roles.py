"""Patch: đảm bảo 2 Role tác nghiệp tồn tại (cho site cài app trước khi có after_install,
hoặc nâng cấp). Idempotent — reuse logic ở install.py."""

import frappe


def execute():
    from ketoan.install import create_portal_roles, grant_settings_permissions

    create_portal_roles()
    # Settings có thể chưa tồn tại nếu DocType chưa sync; bọc an toàn.
    try:
        grant_settings_permissions()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ketoan patch: grant settings perms")
