"""Whitelisted methods — Phân quyền vai trò kế toán cho user (chỉ Kế toán trưởng).

Chỉ thao tác trên các PORTAL_ROLES của app; KHÔNG đụng role hệ thống khác.
Ghi Has Role bằng ignore_permissions SAU KHI đã guard_manager (pattern guard-then-ignore).
"""

import json

import frappe
from frappe import _

from ketoan.api._guard import guard_manager
from ketoan.install import PORTAL_ROLES

# Nhãn hiển thị cho từng role.
ROLE_LABELS = {
    "Ke Toan NPP": "Kế toán NPP",
    "Ke Toan MT": "Kế toán MT",
    "Ke Toan Du Lich": "Kế toán Du lịch, Khác",
    "Ke Toan Mua Hang": "Kế toán mua hàng",
    "Ke Toan Tien Luong": "Kế toán tiền lương",
    "Ke Toan Hach Toan": "Kế toán hạch toán",
    "Ke Toan Truong": "Kế toán trưởng",
}


def _assert_editable(user: str) -> None:
    if user == "Administrator":
        frappe.throw(_("Không thể sửa quyền Administrator"))
    if user == "Guest":
        frappe.throw(_("User không hợp lệ"))
    # Không cho kế toán trưởng (không phải System Manager) sửa tài khoản quản trị.
    target_roles = set(frappe.get_roles(user))
    if "System Manager" in target_roles and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Chỉ System Manager mới sửa được tài khoản quản trị hệ thống"))


@frappe.whitelist()
def get_users() -> dict:
    """Danh sách System User đang bật + vai trò kế toán từng người."""
    guard_manager()

    users = frappe.get_all(
        "User",
        filters={"enabled": 1, "user_type": "System User", "name": ["not in", ["Administrator", "Guest"]]},
        fields=["name", "full_name"],
        order_by="full_name asc",
        limit=500,
    )
    # Map user -> set portal roles (1 query Has Role).
    has = frappe.get_all(
        "Has Role",
        filters={"parenttype": "User", "role": ["in", list(PORTAL_ROLES)]},
        fields=["parent", "role"],
        limit=5000,
    )
    role_map = {}
    for h in has:
        role_map.setdefault(h.parent, []).append(h.role)

    for u in users:
        u["roles"] = sorted(role_map.get(u.name, []))

    return {
        "roles": [{"role": r, "label": ROLE_LABELS.get(r, r)} for r in PORTAL_ROLES],
        "users": users,
    }


@frappe.whitelist()
def set_roles(user: str, roles) -> dict:
    """Đặt vai trò kế toán cho 1 user (thay thế trọn bộ trong phạm vi PORTAL_ROLES).

    roles: JSON list — chỉ chấp nhận role nằm trong PORTAL_ROLES.
    """
    guard_manager()
    if not user or not frappe.db.exists("User", user):
        frappe.throw(_("User không tồn tại"))
    _assert_editable(user)

    if isinstance(roles, str):
        roles = json.loads(roles)
    want = {r for r in (roles or []) if r in PORTAL_ROLES}

    doc = frappe.get_doc("User", user)
    current = {d.role for d in doc.roles if d.role in PORTAL_ROLES}

    to_add = want - current
    to_remove = current - want

    # Guard đã kiểm quyền nghiệp vụ → ghi hộ bằng ignore_permissions.
    for r in to_remove:
        doc.roles = [d for d in doc.roles if d.role != r]
    for r in to_add:
        doc.append("roles", {"role": r})
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)

    return {
        "user": user,
        "roles": sorted(want),
        "added": sorted(to_add),
        "removed": sorted(to_remove),
    }
