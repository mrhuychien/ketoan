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
# SI đầy đủ (xem/sửa/ghi sổ/hủy — TOÀN BỘ hóa đơn, if_owner=0) · JE nháp ·
# thu tiền · xem sổ cái/khách/địa chỉ · chọn BẢNG GIÁ + THUẾ trên hóa đơn
# và hàng trả về (Price List/Item Price/mẫu thuế/thuế mặt hàng/Pricing Rule).
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
    # Bảng giá & thuế cho hóa đơn bán / hàng trả về:
    "Price List": ("read",),
    "Item Price": ("read", "report"),
    "Sales Taxes and Charges Template": ("read",),
    "Item Tax Template": ("read",),
    "Tax Category": ("read",),
    "Pricing Rule": ("read",),
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


# ═══════════════════════════════════════════════════════════════════════════
# MISA meInvoice — role + custom field trên Sales Invoice + quyền 3 DocType.
#
# Ship bằng add_permission/create_custom_fields chứ KHÔNG bằng fixtures: đúng
# quy ước sẵn có của app (DocPerm hash name) và không cần bench export-fixtures.
# Fieldname ASCII, label tiếng Việt. Field ghi sau khi submit → allow_on_submit=1,
# thiếu là chết ngay lần poll đầu ("Not allowed to change ... after submission").
# ═══════════════════════════════════════════════════════════════════════════

MISA_ROLE = "MISA Reconciler"

MISA_STATUS_OPTIONS = "\n".join(
    ("", "Chưa đẩy", "Đã đẩy (nháp)", "Đã phát hành", "Phát hành lỗi", "Lệch tiền", "Đã hủy", "Đã thay thế")
)

MISA_CUSTOM_FIELDS = {
    "Sales Invoice": [
        {
            # TAB Break, KHÔNG phải Section Break.
            #
            # Section Break thu gọn đặt nhầm chỗ sẽ NUỐT mọi field đứng sau vào
            # phần gấp lại — người dùng thấy như mất hẳn nhóm field (đã xảy ra
            # thật với nhóm "KẾ TOÁN" của Sales Invoice). Tab Break tách hẳn
            # sang tab riêng: đặt sai thì cùng lắm là nằm nhầm tab, vẫn NHÌN
            # THẤY được, không bao giờ biến mất.
            "fieldname": "custom_misa_section",
            "label": "MISA",
            "fieldtype": "Tab Break",
        },
        {
            "fieldname": "custom_misa_status",
            "label": "Trạng thái MISA",
            "fieldtype": "Select",
            "options": MISA_STATUS_OPTIONS,
            "allow_on_submit": 1,
            "read_only": 1,
            "in_standard_filter": 1,
            "insert_after": "custom_misa_section",
        },
        {
            "fieldname": "custom_misa_inv_series",
            "label": "Ký hiệu hóa đơn",
            "fieldtype": "Data",
            "allow_on_submit": 1,
            "read_only": 1,
            "insert_after": "custom_misa_status",
        },
        {
            "fieldname": "custom_misa_inv_no",
            "label": "Số hóa đơn MISA",
            "fieldtype": "Data",
            "allow_on_submit": 1,
            "read_only": 1,
            "search_index": 1,
            "insert_after": "custom_misa_inv_series",
        },
        {
            "fieldname": "custom_misa_inv_date",
            "label": "Ngày phát hành MISA",
            "fieldtype": "Date",
            "allow_on_submit": 1,
            "read_only": 1,
            "insert_after": "custom_misa_inv_no",
        },
        {
            "fieldname": "custom_misa_column_break",
            "fieldtype": "Column Break",
            "insert_after": "custom_misa_inv_date",
        },
        {
            "fieldname": "custom_misa_transaction_id",
            "label": "Mã tra cứu MISA",
            "fieldtype": "Data",
            "allow_on_submit": 1,
            "read_only": 1,
            "search_index": 1,
            "insert_after": "custom_misa_column_break",
        },
        {
            "fieldname": "custom_misa_invoice_code",
            "label": "Mã CQT",
            "fieldtype": "Data",
            "allow_on_submit": 1,
            "read_only": 1,
            "insert_after": "custom_misa_transaction_id",
        },
        {
            "fieldname": "custom_misa_ref_id",
            "label": "RefID (khóa nối MISA)",
            "fieldtype": "Data",
            "read_only": 1,
            "search_index": 1,
            "description": "Sinh trước khi ghi sổ, gửi kèm khi đẩy sang MISA. Không sửa tay.",
            "insert_after": "custom_misa_invoice_code",
        },
        {
            "fieldname": "custom_misa_pushed_at",
            "label": "Đẩy sang MISA lúc",
            "fieldtype": "Datetime",
            "allow_on_submit": 1,
            "read_only": 1,
            "insert_after": "custom_misa_ref_id",
        },
        {
            "fieldname": "custom_misa_last_checked",
            "label": "Kiểm tra lần cuối",
            "fieldtype": "Datetime",
            "allow_on_submit": 1,
            "read_only": 1,
            "insert_after": "custom_misa_pushed_at",
        },
        {
            "fieldname": "custom_misa_note",
            "label": "Ghi chú xử lý MISA",
            "fieldtype": "Small Text",
            "allow_on_submit": 1,
            "insert_after": "custom_misa_last_checked",
        },
    ]
}

# Role → DocType → quyền, cho 3 DocType của module MISA Integration.
# (System Manager / Accounts Manager / Accounts User đã nằm sẵn trong DocType JSON.)
MISA_DOC_PERMS = {
    "Ke Toan Truong": {
        "MISA Settings": ("read", "write"),
        "MISA Invoice Snapshot": ("read", "write", "create", "delete", "report", "print", "export"),
        "MISA Sync Run": ("read", "delete", "report"),
    },
    MISA_ROLE: {
        "MISA Invoice Snapshot": ("read", "write", "report", "print"),
        "MISA Sync Run": ("read", "report"),
    },
}


def _last_field_before_misa(doctype="Sales Invoice"):
    """Fieldname CUỐI CÙNG của form, bỏ qua nhóm custom_misa_*.

    Section Break KHÔNG khai insert_after sẽ bị Frappe đặt vào giữa form, và vì
    nó thu gọn được nên MỌI field đứng sau bị nuốt vào trong — nhìn như mất field.
    Neo tường minh vào cuối form là cách duy nhất chắc chắn không nuốt của ai.
    """
    try:
        names = [
            (df.fieldname or "")
            for df in frappe.get_meta(doctype).fields
            if not (df.fieldname or "").startswith("custom_misa")
        ]
        return names[-1] if names else None
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ketoan: _last_field_before_misa")
        return None


def repair_misa_field_order():
    """Trả nhóm field MISA về đúng chỗ: Tab Break riêng, neo vào cuối form.

    Sửa được site đã cài bản hỏng (Section Break thu gọn nuốt mất nhóm KẾ TOÁN).
    Chạy được nhiều lần. Trả về dict để soi khi chạy tay bằng bench execute.
    """
    name = "Sales Invoice-custom_misa_section"
    if not frappe.db.exists("Custom Field", name):
        return {"ok": False, "reason": "chưa có custom_misa_section"}

    before = frappe.db.get_value(
        "Custom Field", name, ["insert_after", "fieldtype", "collapsible"], as_dict=True
    )
    anchor = _last_field_before_misa()
    if not anchor:
        return {"ok": False, "reason": "không xác định được field cuối form"}

    frappe.db.set_value(
        "Custom Field", name,
        {"insert_after": anchor, "fieldtype": "Tab Break", "label": "MISA", "collapsible": 0},
        update_modified=False,
    )
    frappe.clear_cache(doctype="Sales Invoice")
    return {
        "ok": True,
        "truoc": dict(before or {}),
        "sau": {"insert_after": anchor, "fieldtype": "Tab Break", "collapsible": 0},
    }


def remove_misa_custom_fields():
    """VAN AN TOÀN — gỡ toàn bộ custom field custom_misa_* khỏi form Sales Invoice.

    Dùng khi nhóm field MISA làm hỏng bố cục form và cần trả giao diện về ngay.

    KHÔNG mất dữ liệu nghiệp vụ: xóa Custom Field chỉ gỡ field khỏi form, cột dữ
    liệu trong bảng `tabSales Invoice` vẫn còn nguyên. Chạy lại
    `setup_misa_integration()` là dựng lại được đúng như cũ.

        bench --site <site> execute ketoan.install.remove_misa_custom_fields
    """
    removed = []
    for row in frappe.get_all(
        "Custom Field",
        filters={"dt": "Sales Invoice", "fieldname": ("like", "custom_misa%")},
        pluck="name",
    ):
        try:
            frappe.delete_doc("Custom Field", row, ignore_permissions=True, force=True)
            removed.append(row)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"ketoan: remove {row}")
    frappe.db.commit()
    frappe.clear_cache(doctype="Sales Invoice")
    return {"removed": removed, "note": "Cột dữ liệu vẫn còn. Chạy setup_misa_integration() để dựng lại."}


def setup_misa_integration():
    """Tạo role MISA Reconciler + custom field custom_misa_* + quyền 3 DocType. Idempotent."""
    import copy

    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    from frappe.permissions import add_permission, update_permission_property

    try:
        if not frappe.db.exists("Role", MISA_ROLE):
            frappe.get_doc({"doctype": "Role", "role_name": MISA_ROLE, "desk_access": 1}).insert(
                ignore_permissions=True
            )
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"ketoan: create role {MISA_ROLE}")

    try:
        # Neo section vào CUỐI form. Thiếu bước này, Frappe đặt Section Break vào
        # giữa form và nó nuốt trọn các field đứng sau vào phần thu gọn.
        fields = copy.deepcopy(MISA_CUSTOM_FIELDS)
        anchor = _last_field_before_misa()
        if anchor:
            fields["Sales Invoice"][0]["insert_after"] = anchor
        create_custom_fields(fields, ignore_validate=True)
        repair_misa_field_order()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ketoan: misa custom fields")

    for role, doc_perms in MISA_DOC_PERMS.items():
        for doctype, rights in doc_perms.items():
            try:
                if not (frappe.db.exists("DocType", doctype) and frappe.db.exists("Role", role)):
                    continue
                add_permission(doctype, role, 0)
                for right in rights:
                    if right == "read":
                        continue  # add_permission đã set read
                    update_permission_property(doctype, role, 0, right, 1)
                update_permission_property(doctype, role, 0, "if_owner", 0)
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"ketoan misa perms: {role} @ {doctype}")


def after_install():
    create_portal_roles()
    grant_settings_permissions()
    grant_business_permissions()
    setup_misa_integration()


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
            # Xem TOÀN BỘ chứng từ của doctype (không giới hạn "chỉ của tôi").
            update_permission_property(doctype, role, 0, "if_owner", 0)
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
