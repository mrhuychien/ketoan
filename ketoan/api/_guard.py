"""Guard + capability theo hệ phân quyền vai trò kế toán.

5 vai trò (1 user chọn nhiều): Kế toán bán hàng / mua hàng / tiền lương / hạch toán
/ trưởng. Mỗi domain có guard riêng; Kế toán trưởng (+ Accounts Manager/System
Manager) đi qua mọi guard. Mọi whitelisted method gọi guard ở DÒNG ĐẦU.
"""

import frappe
from frappe import _

ROLE_SALES = "Ke Toan Ban Hang"      # Kế toán bán hàng (công nợ phải thu)
ROLE_PURCHASE = "Ke Toan Mua Hang"   # Kế toán mua hàng (công nợ phải trả)
ROLE_PAYROLL = "Ke Toan Tien Luong"  # Kế toán tiền lương
ROLE_GL = "Ke Toan Hach Toan"        # Kế toán hạch toán (quỹ/ngân hàng/bút toán)
ROLE_CHIEF = "Ke Toan Truong"        # Kế toán trưởng (xem tất cả)

PORTAL_ROLES = (ROLE_SALES, ROLE_PURCHASE, ROLE_PAYROLL, ROLE_GL, ROLE_CHIEF)

# Vai trò "toàn quyền xem" — đi qua mọi guard.
CHIEF_ROLES = {ROLE_CHIEF, "Accounts Manager", "System Manager"}

# Mọi vai trò được vào portal (bất kỳ kế toán nào).
VIEW_ROLES = set(PORTAL_ROLES) | {"Accounts User", "Accounts Manager", "System Manager"}


def _roles() -> set:
    return set(frappe.get_roles())


def is_chief() -> bool:
    return bool(CHIEF_ROLES & _roles())


def has_role(role: str) -> bool:
    """User có vai trò này (hoặc là kế toán trưởng)."""
    return role in _roles() or is_chief()


def capabilities() -> dict:
    """Cờ workspace user được thấy (chief thấy tất cả)."""
    return {
        "sales": has_role(ROLE_SALES),
        "purchase": has_role(ROLE_PURCHASE),
        "payroll": has_role(ROLE_PAYROLL),
        "gl": has_role(ROLE_GL),
        "chief": is_chief(),
    }


def _throw_login():
    if frappe.session.user == "Guest":
        frappe.throw(_("Vui lòng đăng nhập"), frappe.PermissionError)


def guard_view() -> None:
    """Bất kỳ kế toán nào (đã đăng nhập, có 1 trong các vai trò)."""
    _throw_login()
    if not (VIEW_ROLES & _roles()):
        frappe.throw(_("Bạn không có quyền truy cập portal kế toán"), frappe.PermissionError)


def _guard_role(role: str, msg: str) -> None:
    _throw_login()
    if not has_role(role):
        frappe.throw(_(msg), frappe.PermissionError)


def guard_sales() -> None:
    _guard_role(ROLE_SALES, "Chỉ Kế toán bán hàng/trưởng mới được xem")


def guard_purchase() -> None:
    _guard_role(ROLE_PURCHASE, "Chỉ Kế toán mua hàng/trưởng mới được xem")


def guard_payroll() -> None:
    _guard_role(ROLE_PAYROLL, "Chỉ Kế toán tiền lương/trưởng mới được xem")


def guard_gl() -> None:
    """Nghiệp vụ quỹ / ngân hàng / bút toán → Kế toán hạch toán."""
    _guard_role(ROLE_GL, "Chỉ Kế toán hạch toán/trưởng mới được xem nghiệp vụ quỹ/ngân hàng")


# Alias tương thích ngược (cash trước đây).
def guard_cash() -> None:
    guard_gl()


def guard_manager() -> None:
    _throw_login()
    if not is_chief():
        frappe.throw(_("Chỉ Kế toán trưởng/quản lý mới được thao tác này"), frappe.PermissionError)


def can_view_cash() -> bool:
    """Được xem nghiệp vụ quỹ/tiền (Kế toán hạch toán hoặc trưởng)."""
    return has_role(ROLE_GL)


def is_manager() -> bool:
    return is_chief()


def get_settings():
    return frappe.get_cached_doc("Ketoan Portal Settings")


def resolve_company(company: str | None = None) -> str:
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
    flt = get_settings().cash_bank_account_filter or "Cash and Bank"
    if flt == "Cash":
        return ("Cash",)
    if flt == "Bank":
        return ("Bank",)
    return ("Cash", "Bank")
