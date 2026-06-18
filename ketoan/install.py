"""Install hooks for the Ketoan portal app.

Tạo 2 Role tác nghiệp và cấp quyền cho Single `Ketoan Portal Settings`.
Mọi thao tác idempotent + bọc try/except + log_error: lỗi seed KHÔNG được làm
chết `bench install-app`.
"""

import frappe

# Role app + role chuẩn ERPNext mà nó kế thừa quyền đọc Accounts.
PORTAL_ROLES = ("Ke Toan Cong No", "Ke Toan Truong")


def after_install():
    create_portal_roles()
    grant_settings_permissions()


def create_portal_roles():
    """Tạo Role `Ke Toan Cong No` và `Ke Toan Truong` (desk access)."""
    for role_name in PORTAL_ROLES:
        try:
            if not frappe.db.exists("Role", role_name):
                frappe.get_doc(
                    {
                        "doctype": "Role",
                        "role_name": role_name,
                        "desk_access": 1,
                    }
                ).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"ketoan: create role {role_name}")


def grant_settings_permissions():
    """Cấp quyền cho `Ketoan Portal Settings`:
    - Ke Toan Cong No: chỉ đọc.
    - Ke Toan Truong / Accounts Manager: đọc + ghi.
    Dùng add_permission thay vì ship Custom DocPerm qua fixtures.
    """
    from frappe.permissions import add_permission, update_permission_property

    dt = "Ketoan Portal Settings"
    try:
        # Read cho kế toán công nợ
        add_permission(dt, "Ke Toan Cong No", 0)

        # Read + Write cho kế toán trưởng & Accounts Manager
        for role in ("Ke Toan Truong", "Accounts Manager"):
            add_permission(dt, role, 0)
            update_permission_property(dt, role, 0, "write", 1)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ketoan: grant settings permissions")
