"""Guard + capability theo hệ phân quyền vai trò kế toán.

5 vai trò (1 user chọn nhiều): Kế toán bán hàng / mua hàng / tiền lương / hạch toán
/ trưởng. Mỗi domain có guard riêng; Kế toán trưởng (+ Accounts Manager/System
Manager) đi qua mọi guard. Mọi whitelisted method gọi guard ở DÒNG ĐẦU.
"""

import frappe
from frappe import _

# Bán hàng chia theo KÊNH (nhận diện qua Customer Group):
ROLE_NPP = "Ke Toan NPP"             # Kênh nhà phân phối
ROLE_MT = "Ke Toan MT"               # Kênh MT (siêu thị/hiện đại)
ROLE_TRAVEL = "Ke Toan Du Lich"      # Kênh Du lịch + Khác
ROLE_PURCHASE = "Ke Toan Mua Hang"   # Kế toán mua hàng (công nợ phải trả)
ROLE_PAYROLL = "Ke Toan Tien Luong"  # Kế toán tiền lương
ROLE_GL = "Ke Toan Hach Toan"        # Kế toán hạch toán (quỹ/ngân hàng/bút toán)
ROLE_CHIEF = "Ke Toan Truong"        # Kế toán trưởng (xem tất cả)

PORTAL_ROLES = (ROLE_NPP, ROLE_MT, ROLE_TRAVEL, ROLE_PURCHASE, ROLE_PAYROLL, ROLE_GL, ROLE_CHIEF)

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
    caps = {
        "npp": has_role(ROLE_NPP),
        "mt": has_role(ROLE_MT),
        "travel": has_role(ROLE_TRAVEL),
        "purchase": has_role(ROLE_PURCHASE),
        "payroll": has_role(ROLE_PAYROLL),
        "gl": has_role(ROLE_GL),
        "chief": is_chief(),
    }
    # Có ít nhất 1 kênh bán hàng → dùng chung 360° khách / tiện ích tìm khách.
    caps["salesany"] = caps["npp"] or caps["mt"] or caps["travel"] or caps["chief"]
    return caps


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


def guard_npp() -> None:
    _guard_role(ROLE_NPP, "Chỉ Kế toán NPP/trưởng mới được xem")


def guard_mt() -> None:
    _guard_role(ROLE_MT, "Chỉ Kế toán MT/trưởng mới được xem")


def guard_travel() -> None:
    _guard_role(ROLE_TRAVEL, "Chỉ Kế toán Du lịch-Khác/trưởng mới được xem")


def guard_sales_any() -> None:
    """Bất kỳ kế toán kênh bán hàng nào (NPP/MT/Du lịch) hoặc trưởng."""
    _throw_login()
    if not (has_role(ROLE_NPP) or has_role(ROLE_MT) or has_role(ROLE_TRAVEL)):
        frappe.throw(_("Chỉ kế toán bán hàng các kênh/trưởng mới được xem"), frappe.PermissionError)


# Kênh → guard + mệnh đề lọc Customer Group.
CHANNELS = ("npp", "mt", "khac", "tat-ca")


def guard_channel(channel: str) -> None:
    """Guard theo kênh: npp / mt / khac; 'tat-ca' chỉ dành cho trưởng."""
    if channel == "npp":
        guard_npp()
    elif channel == "mt":
        guard_mt()
    elif channel == "khac":
        guard_travel()
    else:
        guard_manager()


def channel_group_clause(channel: str, params: dict, alias: str = "c") -> str:
    """Mệnh đề SQL lọc Customer Group theo kênh (đọc group từ Settings).

    npp → group NPP; mt → group MT; khac → ngoài 2 nhóm trên; tat-ca → không lọc.
    """
    s = get_settings()
    npp_group = s.npp_customer_group or "NPP"
    mt_group = s.get("mt_customer_group") or "MT"
    if channel == "npp":
        params["ch_npp"] = npp_group
        return f"{alias}.customer_group = %(ch_npp)s"
    if channel == "mt":
        params["ch_mt"] = mt_group
        return f"{alias}.customer_group = %(ch_mt)s"
    if channel == "khac":
        params["ch_npp"] = npp_group
        params["ch_mt"] = mt_group
        return f"COALESCE({alias}.customer_group,'') NOT IN (%(ch_npp)s, %(ch_mt)s)"
    return "1=1"


def allowed_channels() -> set:
    """Các kênh user được xem (chief = tất cả)."""
    if is_chief():
        return {"npp", "mt", "khac"}
    out = set()
    if has_role(ROLE_NPP):
        out.add("npp")
    if has_role(ROLE_MT):
        out.add("mt")
    if has_role(ROLE_TRAVEL):
        out.add("khac")
    return out


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
