"""Guard + context dùng chung cho mọi whitelisted method của portal.

Nguyên tắc: mọi method gọi `guard_view()` (hoặc `guard_manager()`) ở DÒNG ĐẦU.
Quyền hiển thị ở SPA chỉ là tiện dụng — quyền thật kiểm ở đây.
"""

import frappe
from frappe import _

# Role được xem dữ liệu kế toán tác nghiệp.
VIEW_ROLES = {
    "Ke Toan Cong No",
    "Ke Toan Truong",
    "Accounts User",
    "Accounts Manager",
    "System Manager",
}

# Role quản lý (thấy field nhạy cảm, cấu hình, được submit nếu bật).
MANAGER_ROLES = {
    "Ke Toan Truong",
    "Accounts Manager",
    "System Manager",
}


def _roles() -> set:
    return set(frappe.get_roles())


def is_manager() -> bool:
    return bool(MANAGER_ROLES & _roles())


def guard_view() -> None:
    """Chặn Guest + người không có role xem kế toán."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Vui lòng đăng nhập"), frappe.PermissionError)
    if not (VIEW_ROLES & _roles()):
        frappe.throw(_("Bạn không có quyền xem dữ liệu kế toán tác nghiệp"), frappe.PermissionError)


def guard_manager() -> None:
    guard_view()
    if not is_manager():
        frappe.throw(_("Chỉ kế toán trưởng/quản lý mới được thao tác này"), frappe.PermissionError)


def get_settings():
    """Single Ketoan Portal Settings (cached)."""
    return frappe.get_cached_doc("Ketoan Portal Settings")


def resolve_company(company: str | None = None) -> str:
    """Trả về company hợp lệ: tham số → Settings → mặc định của user/hệ thống."""
    if company:
        return company
    settings = get_settings()
    if settings.default_company:
        return settings.default_company
    return (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )


def cash_account_types() -> tuple:
    """Tuple account_type để lọc TK tiền theo cấu hình (cho mệnh đề IN %s)."""
    flt = get_settings().cash_bank_account_filter or "Cash and Bank"
    if flt == "Cash":
        return ("Cash",)
    if flt == "Bank":
        return ("Bank",)
    return ("Cash", "Bank")
