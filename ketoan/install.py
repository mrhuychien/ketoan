"""Install hooks — tạo hệ vai trò kế toán + cấp quyền cho Single Settings.

5 vai trò: Kế toán bán hàng / mua hàng / tiền lương / hạch toán / trưởng.
Idempotent + bọc try/except + log_error: lỗi seed KHÔNG được làm chết install.
"""

import frappe

PORTAL_ROLES = (
    "Ke Toan NPP",
    "Ke Toan MT",
    "Ke Toan Du Lich",
    "Ke Toan Mua Hang",
    "Ke Toan Tien Luong",
    "Ke Toan Hach Toan",
    "Ke Toan Truong",
)

# Role cũ đã bỏ (map người dùng sang role mới trước khi xóa nếu cần).
LEGACY_ROLES = ("Ke Toan Cong No", "Ke Toan Ban Hang")


# ═══════════════════════════════════════════════════════════════════════════
# Ma trận quyền nghiệp vụ: Role → DocType → các quyền được cấp.
# Cấp bằng add_permission/update_permission_property (KHÔNG ship DocPerm fixtures).
# ═══════════════════════════════════════════════════════════════════════════

FULL_DOC = ("read", "write", "create", "submit", "cancel", "amend", "print", "email", "report")
DRAFT_DOC = ("read", "write", "create", "print", "report")  # nháp — không submit/cancel
READ_DOC = ("read", "report", "print")

# Quyền chung cho 1 kế toán kênh bán hàng (NPP/MT/Du lịch):
# SI đầy đủ (xem/sửa/ghi sổ/hủy) · JE nháp · thu tiền · xem sổ cái/khách/địa chỉ.
_SALES_CHANNEL_PERMS = {
    "Sales Invoice": FULL_DOC,
    "Journal Entry": DRAFT_DOC,
    "Payment Entry": ("read", "write", "create", "submit", "print", "report"),
    "Customer": ("read", "write", "report", "print"),
    "Address": ("read", "write", "create"),
    "Contact": ("read", "write", "create"),
    "GL Entry": ("read", "report"),
    "Account": ("read",),
    "Payment Ledger Entry": ("read", "report"),
    "Sales Order": READ_DOC,
    "Delivery Note": ("read", "report"),
    "Customer Group": ("read",),
    "Item": ("read",),
}

BUSINESS_PERMS = {
    "Ke Toan NPP": _SALES_CHANNEL_PERMS,
    "Ke Toan MT": _SALES_CHANNEL_PERMS,
    "Ke Toan Du Lich": _SALES_CHANNEL_PERMS,
    "Ke Toan Mua Hang": {
        "Purchase Invoice": FULL_DOC,
        "Journal Entry": DRAFT_DOC,
        "Payment Entry": ("read", "write", "create", "submit", "print", "report"),
        "Supplier": ("read", "write", "report", "print"),
        "Address": ("read", "write", "create"),
        "Contact": ("read", "write", "create"),
        "GL Entry": ("read", "report"),
        "Account": ("read",),
        "Payment Ledger Entry": ("read", "report"),
        "Purchase Order": READ_DOC,
        "Purchase Receipt": ("read", "report"),
        "Supplier Group": ("read",),
        "Item": ("read",),
    },
    "Ke Toan Tien Luong": {
        # DocType lương custom — bọc exists khi cấp.
        "SalaryDay": FULL_DOC,
        "SalaryProduct": FULL_DOC,
        "Employee": ("read", "report", "print"),
        "Journal Entry": DRAFT_DOC,
        # Module lương chuẩn (nếu dùng HRMS) — chỉ xem.
        "Payroll Entry": ("read", "report"),
        "Salary Slip": ("read", "report", "print"),
        "Salary Structure": ("read",),
        "Attendance": ("read", "report"),
        "GL Entry": ("read", "report"),
        "Account": ("read",),
    },
    "Ke Toan Hach Toan": {
        "Journal Entry": FULL_DOC,
        "Payment Entry": FULL_DOC,
        "GL Entry": ("read", "report"),
        "Account": ("read", "report", "print"),
        "Bank Account": ("read", "write", "create"),
        "Bank Transaction": ("read", "write", "create", "report"),
        "Mode of Payment": ("read",),
        "Cost Center": ("read", "report"),
        "Fiscal Year": ("read",),
        "Currency Exchange": ("read",),
        "Period Closing Voucher": ("read", "report"),
        "Address": ("read",),
        "Contact": ("read",),
        "Customer": ("read", "report"),
        "Supplier": ("read", "report"),
        "Payment Ledger Entry": ("read", "report"),
        "Sales Invoice": ("read", "report", "print"),
        "Purchase Invoice": ("read", "report", "print"),
    },
}
# Kế toán trưởng = hợp nhất mọi quyền trên + quyền khóa kỳ.
_chief: dict = {}
for _perms in BUSINESS_PERMS.values():
    for _dt, _rights in _perms.items():
        _chief[_dt] = tuple(sorted(set(_chief.get(_dt, ())) | set(_rights)))
_chief["Period Closing Voucher"] = FULL_DOC
BUSINESS_PERMS["Ke Toan Truong"] = _chief

# Quyền NỀN Desk — cấp cho MỌI vai trò kế toán: không có thì Desk chặn ngay khi
# mở trang ("không có quyền truy cập doctype ... tài liệu Trang/Page").
BASELINE_DESK_PERMS = {
    "Page": ("read",),            # mở các trang Desk
    "Report": ("read",),          # mở màn báo cáo
    "Company": ("read",),         # filter công ty
    "Currency": ("read",),
    "Fiscal Year": ("read",),
    "Print Format": ("read",),    # in chứng từ
    "Letter Head": ("read",),
    "Terms and Conditions": ("read",),
    "File": ("read", "write", "create"),  # đính kèm chứng từ
    "UOM": ("read",),
    "Territory": ("read",),
    "Warehouse": ("read",),
}

# Báo cáo chuẩn ERPNext cần thêm role vào Report.roles mới mở được.
REPORT_ROLES = {
    "General Ledger": ["Ke Toan NPP", "Ke Toan MT", "Ke Toan Du Lich", "Ke Toan Mua Hang", "Ke Toan Hach Toan", "Ke Toan Truong"],
    "Accounts Receivable": ["Ke Toan NPP", "Ke Toan MT", "Ke Toan Du Lich", "Ke Toan Truong"],
    "Accounts Receivable Summary": ["Ke Toan NPP", "Ke Toan MT", "Ke Toan Du Lich", "Ke Toan Truong"],
    "Sales Register": ["Ke Toan NPP", "Ke Toan MT", "Ke Toan Du Lich", "Ke Toan Truong"],
    "Accounts Payable": ["Ke Toan Mua Hang", "Ke Toan Truong"],
    "Purchase Register": ["Ke Toan Mua Hang", "Ke Toan Truong"],
    "Trial Balance": ["Ke Toan Hach Toan", "Ke Toan Truong"],
    "Cash Flow": ["Ke Toan Hach Toan", "Ke Toan Truong"],
    "Balance Sheet": ["Ke Toan Truong"],
    "Profit and Loss Statement": ["Ke Toan Truong"],
    "Gross Profit": ["Ke Toan Truong"],
}


def after_install():
    create_portal_roles()
    grant_settings_permissions()
    grant_business_permissions()


def create_portal_roles():
    """Tạo 5 Role tác nghiệp (desk access)."""
    for role_name in PORTAL_ROLES:
        try:
            if not frappe.db.exists("Role", role_name):
                frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": 1}).insert(
                    ignore_permissions=True
                )
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"ketoan: create role {role_name}")


def grant_settings_permissions():
    """Read cho mọi vai trò; Write cho Kế toán trưởng + Accounts Manager."""
    from frappe.permissions import add_permission, update_permission_property

    dt = "Ketoan Portal Settings"
    try:
        for role in PORTAL_ROLES:
            add_permission(dt, role, 0)
        for role in ("Ke Toan Truong", "Accounts Manager"):
            update_permission_property(dt, role, 0, "write", 1)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ketoan: grant settings permissions")


def grant_business_permissions():
    """Cấp quyền DocType nghiệp vụ theo BUSINESS_PERMS + mở Report chuẩn.

    Idempotent: add_permission bỏ qua nếu đã có; update_permission_property chỉ set 1.
    Mỗi DocType bọc try/except (DocType lương custom có thể chưa cài).
    """
    from frappe.permissions import add_permission, update_permission_property

    def grant(role, doctype, rights):
        try:
            if not frappe.db.exists("DocType", doctype):
                return
            add_permission(doctype, role, 0)
            for right in rights:
                if right == "read":
                    continue  # add_permission đã set read
                update_permission_property(doctype, role, 0, right, 1)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"ketoan perms: {role} @ {doctype}")

    for role, doc_perms in BUSINESS_PERMS.items():
        for doctype, rights in doc_perms.items():
            grant(role, doctype, rights)

    # Quyền nền Desk cho mọi vai trò.
    for role in PORTAL_ROLES:
        for doctype, rights in BASELINE_DESK_PERMS.items():
            grant(role, doctype, rights)

    _grant_report_roles()


def _grant_report_roles():
    """Thêm role vào Report.roles để mở được báo cáo chuẩn (GL, AR, ...). Idempotent."""
    for report, roles in REPORT_ROLES.items():
        try:
            if not frappe.db.exists("Report", report):
                continue
            doc = frappe.get_doc("Report", report)
            have = {r.role for r in (doc.roles or [])}
            changed = False
            for role in roles:
                if role not in have and frappe.db.exists("Role", role):
                    doc.append("roles", {"role": role})
                    changed = True
            if changed:
                doc.flags.ignore_permissions = True
                doc.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"ketoan report roles: {report}")
